#!/usr/bin/env python3
"""The session-start hooks resolve a zpc store the same way zpc does.

Both hooks answer "where is this project's store" locally, with an upward walk,
rather than paying a dispatcher startup per session to ask. That is only safe
while the two walks agree, so this pins the equivalence: hook resolution is
compared against `zpc status --json`, whose `project` field is the tool's own
answer (ensure_zpc -> init_zpc_dirs -> resolve_zpc_dir).

If zpc ever changes how it resolves a store, this fails loudly instead of the
hooks silently reading the wrong memory in subdirectory sessions.
"""

from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CLAUDE_HOOK = REPO / "hooks" / "claude" / "agent-do-session-start.sh"
CODEX_HOOK = REPO / "hooks" / "codex" / "agent-do-session-start.py"
AGENT_DO = REPO / "agent-do"

FAILURES: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"  ok: {label}")
    else:
        FAILURES.append(f"{label}{f' — {detail}' if detail else ''}")
        print(f"  FAIL: {label}{f' — {detail}' if detail else ''}")


def load_codex_module():
    spec = importlib.util.spec_from_file_location("codex_session_start", CODEX_HOOK)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def bash_store_root(cwd: str) -> str:
    """Run the claude hook's own zpc_store_root, extracted by name.

    A rename breaks this test rather than silently skipping it, which is the
    intent: the function is the contract.
    """
    source = CLAUDE_HOOK.read_text(encoding="utf-8")
    match = re.search(r"^zpc_store_root\(\) \{\n(.*?)^\}", source, re.S | re.M)
    if not match:
        return "<zpc_store_root not found in claude hook>"
    body = match.group(0)
    proc = subprocess.run(
        ["bash", "-c", f'{body}\nzpc_store_root "$1"', "_", cwd],
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.stdout.strip()


def zpc_reported_project(cwd: str) -> str:
    proc = subprocess.run(
        [str(AGENT_DO), "zpc", "status", "--json"],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    if proc.returncode != 0:
        return ""
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return ""
    if isinstance(data.get("result"), dict) and "project" in data["result"]:
        return data["result"]["project"]
    return data.get("project", "")


def main() -> int:
    codex = load_codex_module()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp).resolve() / "project"
        deep = root / "packages" / "api" / "src"
        deep.mkdir(parents=True)
        (root / ".zpc" / "memory").mkdir(parents=True)
        (root / ".zpc" / "memory" / "lessons.jsonl").write_text("", encoding="utf-8")

        print("store at project root, session opened four levels down:")

        truth = zpc_reported_project(str(deep))
        check(
            "zpc status --json resolves the walked-up root",
            truth == str(root),
            f"got {truth!r}, want {str(root)!r}",
        )

        codex_answer = codex.zpc_store_root(str(deep))
        check(
            "codex hook agrees with zpc",
            codex_answer is not None and str(codex_answer) == truth,
            f"hook {str(codex_answer)!r} vs zpc {truth!r}",
        )

        bash_answer = bash_store_root(str(deep))
        check(
            "claude hook agrees with zpc",
            bash_answer == truth,
            f"hook {bash_answer!r} vs zpc {truth!r}",
        )

        print("session opened at the store root:")
        at_root_codex = codex.zpc_store_root(str(root))
        check(
            "codex hook resolves to itself",
            at_root_codex is not None and str(at_root_codex) == str(root),
            f"got {str(at_root_codex)!r}",
        )
        check(
            "claude hook resolves to itself",
            bash_store_root(str(root)) == str(root),
        )

    with tempfile.TemporaryDirectory() as tmp:
        storeless = Path(tmp).resolve() / "nothing" / "here"
        storeless.mkdir(parents=True)
        print("no store anywhere up the tree:")
        check(
            "codex hook reports no store",
            codex.zpc_store_root(str(storeless)) is None,
        )
        check(
            "claude hook reports no store",
            bash_store_root(str(storeless)) == "",
        )

    if FAILURES:
        print(f"\nhook store resolution tests FAILED ({len(FAILURES)})")
        return 1
    print("\nhook store resolution tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
