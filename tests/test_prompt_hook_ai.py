#!/usr/bin/env python3
"""Focused tests for AI-backed UserPromptSubmit routing."""

from __future__ import annotations

import json
import importlib.util
import os
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def run_hook(prompt: str, *, cwd: Path | None = None, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    payload = {"prompt": prompt}
    if cwd is not None:
        payload["cwd"] = str(cwd)
    return subprocess.run(
        ["python3", "hooks/claude/agent-do-prompt-router.py"],
        cwd=ROOT,
        env=env,
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        check=False,
    )


def main() -> int:
    router_path = ROOT / "hooks" / "claude" / "agent-do-prompt-router.py"
    spec = importlib.util.spec_from_file_location("agent_do_prompt_router_test", router_path)
    require(spec is not None and spec.loader is not None, "could not load prompt router for catalog check")
    router = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(router)
    compact_catalog = router.build_ai_catalog(router.load_registry())
    encoded_catalog = json.dumps(compact_catalog, separators=(",", ":")).encode("utf-8")
    require(
        len(compact_catalog) == len(router.load_registry().get("tools", {})),
        f"compact classifier catalog lost tools: {len(compact_catalog)}",
    )
    require(len(encoded_catalog) < 15_000, f"classifier catalog exceeded 15KB latency budget: {len(encoded_catalog)}")
    require(
        all(set(entry) <= {"tool", "description", "entrypoints"} for entry in compact_catalog),
        "classifier catalog included heavyweight registry fields",
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        fake = tmp / "anthropic.py"
        fake.write_text(
            """
import json


class _Chunk:
    def __init__(self, text):
        self.text = text


class _Response:
    def __init__(self, payload):
        self.content = [_Chunk(json.dumps(payload))]


class _Messages:
    def create(self, **kwargs):
        prompt = kwargs["messages"][0]["content"]
        assert kwargs["model"] == "claude-haiku-4-5-20251001"
        assert kwargs["max_tokens"] == 600
        assert "thinking" not in kwargs
        assert "output_config" not in kwargs
        assert '"tool": "vercel"' in prompt
        assert '"tool": "context"' in prompt
        assert '"capabilities"' not in prompt
        assert '"routing_intents"' not in prompt
        assert "Candidate tools" not in prompt

        if "deploy this on vercel and check logs" in prompt:
            return _Response({
                "prompt_kind": "work_starting",
                "starts_work": True,
                "coord": {"block": False, "reason": "", "focus_command": ""},
                "emit_tools": True,
                "tool_suggestions": [{
                    "tool": "vercel",
                    "command": "agent-do vercel deploy <project>",
                    "why": "deployment is the requested first action",
                    "confidence": 0.94
                }]
            })

        if "fix the render config in this repo" in prompt:
            return _Response({
                "prompt_kind": "work_starting",
                "starts_work": True,
                "coord": {
                    "block": True,
                    "reason": "active peer exists and repo work is starting",
                    "focus_command": "agent-do coord focus set \\"fix render config\\" --path render.yaml"
                },
                "emit_tools": False,
                "tool_suggestions": []
            })

        if "wait what was pr 6" in prompt:
            return _Response({
                "prompt_kind": "discussion",
                "starts_work": False,
                "coord": {"block": False, "reason": "", "focus_command": ""},
                "emit_tools": False,
                "tool_suggestions": []
            })

        if "use Opus 4.8 as an in-app API" in prompt:
            return _Response({
                "prompt_kind": "work_starting",
                "starts_work": True,
                "coord": {"block": False, "reason": "", "focus_command": ""},
                "needs_docs_retrieval": True,
                "docs_query": "Anthropic API Opus 4.8 model docs",
                "emit_tools": False,
                "tool_suggestions": []
            })

        return _Response({
            "prompt_kind": "other",
            "starts_work": False,
            "coord": {"block": False, "reason": "", "focus_command": ""},
            "emit_tools": True,
            "tool_suggestions": [{
                "tool": "context",
                "command": "agent-do context search authentication",
                "why": "weak match",
                "confidence": 0.2
            }]
        })


class Anthropic:
    def __init__(self, **kwargs):
        assert kwargs["timeout"] <= 3.0
        assert kwargs["max_retries"] == 0
        self.messages = _Messages()
""",
            encoding="utf-8",
        )

        env = os.environ.copy()
        env["PYTHONPATH"] = f"{tmp}:{env.get('PYTHONPATH', '')}"
        env["ANTHROPIC_API_KEY"] = "test-key"
        env["AGENT_DO_HOOK_AI"] = "1"
        env.pop("AGENT_DO_AI_MODEL", None)
        env.pop("AGENT_DO_AI_MAX_TOKENS", None)
        env.pop("AGENT_DO_AI_EFFORT", None)

        suggest = run_hook("deploy this on vercel and check logs", env=env)
        require(suggest.returncode == 0, f"AI prompt hook failed: {suggest.stderr}\\n{suggest.stdout}")
        suggest_payload = json.loads(suggest.stdout)
        suggest_context = suggest_payload["hookSpecificOutput"]["additionalContext"]
        require("agent-do vercel deploy <project>" in suggest_context, f"expected exact AI suggestion: {suggest_context}")
        require("agent-do context search" not in suggest_context, f"unexpected weak context suggestion: {suggest_context}")

        weak = run_hook("maybe look around", env=env)
        require(weak.returncode == 0, f"weak AI prompt hook failed: {weak.stderr}")
        require(weak.stdout.strip() == "", f"expected low-confidence suggestion suppression, got: {weak.stdout}")

        project = tmp / "project"
        project.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=project, check=True)
        coord_home = tmp / "coord-home"
        peer_env = dict(env)
        peer_env["AGENT_DO_HOME"] = str(coord_home)
        peer_env["CODEX_THREAD_ID"] = "peer-one"
        subprocess.run(
            [str(ROOT / "agent-do"), "coord", "touch", "--json"],
            cwd=project,
            env=peer_env,
            text=True,
            capture_output=True,
            check=True,
        )

        current_env = dict(env)
        current_env["AGENT_DO_HOME"] = str(coord_home)
        current_env["CODEX_THREAD_ID"] = "peer-two"

        focus = run_hook("fix the render config in this repo", cwd=project, env=current_env)
        require(focus.returncode == 0, f"coord AI focus context failed: {focus.stderr}")
        focus_payload = json.loads(focus.stdout)
        focus_context = focus_payload["hookSpecificOutput"]["additionalContext"]
        require(focus_payload.get("decision") != "block", f"did not expect blocking hook output: {focus_payload}")
        require("Coord Focus Required" in focus_context, f"expected coord focus context: {focus_context}")
        require("agent-do coord focus set" in focus_context, f"expected focus command: {focus_context}")
        require("render.yaml" in focus_context, f"expected AI focus path: {focus_context}")

        discussion = run_hook("wait what was pr 6?", cwd=project, env=current_env)
        require(discussion.returncode == 0, f"discussion hook failed: {discussion.stderr}")
        require(discussion.stdout.strip() == "", f"expected discussion prompt to pass silently: {discussion.stdout}")

        docs = run_hook("use Opus 4.8 as an in-app API in this project", cwd=project, env=current_env)
        require(docs.returncode == 0, f"docs hook failed: {docs.stderr}")
        docs_payload = json.loads(docs.stdout)
        docs_context = docs_payload["hookSpecificOutput"]["additionalContext"]
        require("agent-do context retrieve 'Anthropic API Opus 4.8 model docs' --require-fresh --require-official --prefer-latest --max-tokens 8000" in docs_context, f"expected strict context retrieve command: {docs_context}")
        require("agent-do context fetch-llms docs.claude.com --trust official" in docs_context, f"expected Anthropic source fallback: {docs_context}")

    print("prompt hook AI tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
