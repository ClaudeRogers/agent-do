#!/usr/bin/env python3
"""Regression tests for authority-aware context retrieval."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "agent-context" / "agent-context"
LIB = ROOT / "tools" / "agent-context" / "lib"


def run(args: list[str], *, env: dict[str, str], input_text: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=ROOT,
        env=env,
        input=input_text,
        text=True,
        capture_output=True,
        check=False,
    )


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def index_package(
    *,
    env: dict[str, str],
    package_id: str,
    name: str,
    package_type: str,
    description: str,
    tags: str,
    trust: str,
    token_count: int,
    cache_path: Path,
    source: str,
) -> None:
    script = """
source "$1"
source "$2"
shift 2
ensure_init
_index_package "$@"
"""
    result = run(
        [
            "bash",
            "-c",
            script,
            "bash",
            str(LIB / "common.sh"),
            str(LIB / "search.sh"),
            package_id,
            name,
            package_type,
            description,
            tags,
            trust,
            str(token_count),
            str(cache_path),
            source,
        ],
        env=env,
    )
    require(result.returncode == 0, f"index package failed: {result.stderr}\n{result.stdout}")


def main() -> int:
    with tempfile.TemporaryDirectory() as tmpdir:
        home = Path(tmpdir) / "agent-home"
        env = os.environ.copy()
        env["AGENT_DO_HOME"] = str(home)

        init = run([str(TOOL), "init"], env=env)
        require(init.returncode == 0, f"context init failed: {init.stderr}")

        cache_root = home / "context" / "cache" / "fetched"
        skill_cache = cache_root / "skill-claude-api"
        official_cache = cache_root / "docs-claude-com-llms"
        skill_cache.mkdir(parents=True)
        official_cache.mkdir(parents=True)

        skill_text = (
            "# Claude API Skill\n\n"
            + ("Anthropic API Opus 4.8 model docs local skill stale memory. " * 80)
        )
        official_text = (
            "# Anthropic Developer Documentation\n\n"
            "Official Messages API docs for claude-opus-4-8 and in-app API usage.\n"
        )
        (skill_cache / "SKILL.md").write_text(skill_text, encoding="utf-8")
        (official_cache / "content.md").write_text(official_text, encoding="utf-8")

        index_package(
            env=env,
            package_id="skill-claude-api",
            name="claude-api",
            package_type="skill",
            description="Local Claude API skill",
            tags="ai,llm,claude",
            trust="local",
            token_count=1200,
            cache_path=skill_cache,
            source=str(Path(tmpdir) / "skills"),
        )
        index_package(
            env=env,
            package_id="docs-claude-com-llms",
            name="docs.claude.com-llms",
            package_type="reference",
            description="Official Claude API documentation",
            tags="ai,llm,claude",
            trust="official",
            token_count=100,
            cache_path=official_cache,
            source="https://docs.claude.com/llms-full.txt",
        )

        query = "Anthropic API Opus 4.8 model docs"
        retrieve = run(
            [
                str(TOOL),
                "retrieve",
                query,
                "--fresh",
                "--prefer-latest",
                "--max-tokens",
                "5000",
                "--json",
            ],
            env=env,
        )
        require(retrieve.returncode == 0, f"retrieve failed: {retrieve.stderr}\n{retrieve.stdout}")
        payload = json.loads(retrieve.stdout)
        packages = payload.get("packages") or []
        require(packages, f"expected packages, got: {payload}")
        require(
            packages[0]["id"] == "docs-claude-com-llms",
            f"expected official Claude docs first, got: {packages}",
        )

        official = run(
            [
                str(TOOL),
                "retrieve",
                query,
                "--require-official",
                "--max-tokens",
                "5000",
                "--json",
            ],
            env=env,
        )
        require(official.returncode == 0, f"require-official retrieve failed: {official.stderr}\n{official.stdout}")
        official_payload = json.loads(official.stdout)
        official_packages = official_payload.get("packages") or []
        require(official_packages, f"expected official packages, got: {official_payload}")
        require(
            all(item["trust"] == "official" for item in official_packages),
            f"local packages must not satisfy --require-official: {official_packages}",
        )
        require(
            "skill-claude-api" not in {item["id"] for item in official_packages},
            f"local skill leaked into --require-official results: {official_packages}",
        )

    print("context retrieve authority tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
