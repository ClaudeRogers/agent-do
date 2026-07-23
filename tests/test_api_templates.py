#!/usr/bin/env python3
"""Regression tests for agent-do api canonical templates."""

from __future__ import annotations

import json
import os
import py_compile
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

from registry import find_raw_cli_equivalent, load_registry, match_prompt_tools  # noqa: E402


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def run(args: list[str], *, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def run_json(args: list[str], *, env: dict[str, str]) -> dict:
    result = run(args, env=env)
    require(result.returncode == 0, f"command failed: {' '.join(args)}\n{result.stderr}\n{result.stdout}")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise AssertionError(f"expected JSON from {' '.join(args)}, got: {result.stdout}") from exc


def main() -> int:
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        env = os.environ.copy()
        env["AGENT_DO_HOME"] = str(tmp / "agent-home")
        env["AGENT_DO_SUGGEST_AI"] = "0"

        listing = run_json(["./agent-do", "api", "list", "--json"], env=env)
        templates = listing.get("templates") or []
        anthropic = next((item for item in templates if item.get("name") == "anthropic"), None)
        require(anthropic is not None, f"expected seeded anthropic template, got: {listing}")
        require(
            anthropic.get("default_model") == "claude-opus-4-8",
            f"expected Opus 4.8 default, got: {anthropic}",
        )
        require(anthropic.get("revision") == 1, f"expected initial revision 1, got: {anthropic}")

        shown = run_json(["./agent-do", "api", "show", "anthropic", "--json"], env=env)
        manifest = shown.get("manifest") or {}
        template = shown.get("template") or ""
        require(manifest.get("context_source_id") == "docs-claude-com-llms", f"missing context link: {manifest}")
        require("from anthropic import Anthropic" in template, "expected Anthropic SDK import in template")
        require("def chat(" in template, "expected single chat entrypoint in template")
        require("cache_control" in template, "expected prompt caching in template")
        require("ANTHROPIC_API_KEY" in template, "expected fail-loud credential check in template")

        target = tmp / "project" / "llm.py"
        scaffolded = run_json(
            ["./agent-do", "api", "scaffold", "anthropic", "--target", str(target), "--json"],
            env=env,
        )
        require(scaffolded.get("success") is True, f"unexpected scaffold result: {scaffolded}")
        require(target.exists(), f"expected scaffold target to exist: {target}")
        source = target.read_text(encoding="utf-8")
        require("{{PROJECT_NAME}}" not in source, "project placeholder should be substituted")
        require("Canonical Anthropic Messages API client for project" in source, "expected project name substitution")
        require("claude-opus-4-8" in source, "expected current default model in scaffold")
        require("DEFAULT_MAX_TOKENS" in source and "64000" in source, "expected max token default in scaffold")
        py_compile.compile(str(target), doraise=True)

        second_scaffold = run(
            ["./agent-do", "api", "scaffold", "anthropic", "--target", str(target)],
            env=env,
        )
        require(second_scaffold.returncode != 0, "scaffold must not overwrite an existing target")
        require("target already exists" in second_scaffold.stderr, f"unexpected overwrite stderr: {second_scaffold.stderr}")

        target.write_text(source + "\n# saved-marker\n", encoding="utf-8")
        saved = run_json(["./agent-do", "api", "save", "anthropic", "--from", str(target), "--json"], env=env)
        require(saved.get("revision") == 2, f"expected save to increment revision, got: {saved}")
        reshow = run_json(["./agent-do", "api", "show", "anthropic", "--json"], env=env)
        require("# saved-marker" in (reshow.get("template") or ""), "expected saved template marker")

        agent_home = Path(env["AGENT_DO_HOME"])
        (agent_home / "api-envs.json").write_text(json.dumps({"local": "http://127.0.0.1:3000"}), encoding="utf-8")
        (agent_home / "api-history.json").write_text(
            json.dumps([{"method": "GET", "url": "http://127.0.0.1:3000/health", "timestamp": "legacy"}]),
            encoding="utf-8",
        )
        snapshot = run_json(["./agent-do", "api", "snapshot"], env=env)
        require(snapshot.get("environments", {}).get("local") == "http://127.0.0.1:3000", f"expected legacy envs, got: {snapshot}")
        require(snapshot.get("total_requests") == 1, f"expected legacy history compatibility, got: {snapshot}")
        require("recent_requests" in snapshot, f"expected HTTP snapshot compatibility, got: {snapshot}")

        health = run(["./agent-do", "--health", "api"], env=env)
        require(health.returncode == 0, f"api health failed: {health.stderr}\n{health.stdout}")
        require("anthropic template ready" in health.stdout, f"expected api health note, got: {health.stdout}")

        suggest = run_json(["./agent-do", "suggest", "build me a Claude client with the Anthropic SDK", "--json"], env=env)
        first = (suggest.get("results") or [{}])[0]
        require(first.get("tool") == "api", f"expected api suggestion, got: {suggest}")
        require(
            first.get("primary") == "agent-do api scaffold anthropic --target ./lib/llm.py",
            f"expected scaffold as primary suggestion, got: {first}",
        )

    registry = load_registry()
    matches = match_prompt_tools(registry, "build me a Claude client with the Anthropic SDK", limit=3)
    require(matches and matches[0]["tool"] == "api", f"expected api to route Claude client prompt, got: {matches}")
    equivalent = find_raw_cli_equivalent(registry, "from anthropic import Anthropic")
    require(equivalent and equivalent["tool"] == "api", f"expected api raw equivalent, got: {equivalent}")

    print("api template tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
