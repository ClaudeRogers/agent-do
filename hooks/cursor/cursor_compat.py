#!/usr/bin/env python3
"""Translate between Cursor hook payloads and agent-do's Claude hook format."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


def resolve_repo() -> Path | None:
    env_root = os.environ.get("AGENT_DO_REPO")
    if env_root:
        candidate = Path(env_root).expanduser()
        if candidate.is_dir():
            return candidate

    breadcrumb = Path.home() / ".agent-do" / "install-path"
    if breadcrumb.is_file():
        try:
            candidate = Path(breadcrumb.read_text().strip()).expanduser()
            if candidate.is_dir():
                return candidate
        except OSError:
            pass

    return None


def workspace_root(raw: dict[str, Any]) -> str | None:
    roots = raw.get("workspace_roots")
    if isinstance(roots, list) and roots:
        first = roots[0]
        if isinstance(first, str) and first:
            return first
    return None


def normalize_cwd(raw: dict[str, Any]) -> str:
    cwd = raw.get("cwd")
    if isinstance(cwd, str) and cwd:
        return cwd
    root = workspace_root(raw)
    if root:
        return root
    return os.getcwd()


def claude_to_cursor_output(payload: dict[str, Any], *, continue_prompt: bool = False) -> dict[str, Any]:
    hook_specific = payload.get("hookSpecificOutput")
    if not isinstance(hook_specific, dict):
        return {"continue": True} if continue_prompt else {}

    output: dict[str, Any] = {}
    additional = hook_specific.get("additionalContext")
    if isinstance(additional, str) and additional.strip():
        output["additional_context"] = additional

    permission = hook_specific.get("permissionDecision")
    if permission in {"allow", "deny", "ask"}:
        output["permission"] = permission

    reason = hook_specific.get("reason")
    if isinstance(reason, str) and reason.strip():
        output["agent_message"] = reason

    if continue_prompt:
        output["continue"] = permission != "deny"

    return output


def run_canonical_hook(repo: Path, hook_rel: str, stdin_payload: dict[str, Any]) -> dict[str, Any]:
    hook = repo / hook_rel
    if not hook.is_file():
        return {}

    env = os.environ.copy()
    env["AGENT_DO_HOOK_RUNTIME"] = "cursor"
    lib_dir = str(repo / "lib")
    if lib_dir not in sys.path:
        sys.path.insert(0, lib_dir)

    cmd = [sys.executable, str(hook)] if hook.suffix == ".py" else [str(hook)]
    try:
        proc = subprocess.run(
            cmd,
            input=json.dumps(stdin_payload),
            text=True,
            capture_output=True,
            check=False,
            env=env,
            timeout=8,
        )
    except subprocess.TimeoutExpired:
        return {}

    if proc.returncode != 0 or not proc.stdout.strip():
        return {}

    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {}


def resolve_agent_do_dir() -> str | None:
    repo = resolve_repo()
    if repo and (repo / "agent-do").is_file():
        return str(repo)

    local = Path.home() / ".local" / "bin" / "agent-do"
    if local.exists():
        return str(local.parent)

    return None
