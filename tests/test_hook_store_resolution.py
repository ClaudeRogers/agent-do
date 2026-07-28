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


def _extract_bash_func(name: str) -> str:
    source = CLAUDE_HOOK.read_text(encoding="utf-8")
    match = re.search(rf"^{name}\(\) \{{\n.*?^\}}", source, re.S | re.M)
    if not match:
        raise AssertionError(f"{name} not found in claude hook")
    return match.group(0)


def bash_store_root(
    cwd: str,
    toplevel: str = "",
    home: str | None = None,
    fake_uid: str | None = None,
) -> str:
    """Run the claude hook's own zpc_store_root, extracted by name.

    A rename breaks this test rather than silently skipping it, which is the
    intent: the function is the contract.
    """
    body = _extract_bash_func("zpc_store_root")
    uid_fn = _extract_bash_func("_path_uid")
    # Overriding `id` exercises the ownership branch without needing a file
    # owned by another user, which an unprivileged test cannot create.
    spoof = f"id() {{ echo {fake_uid}; }}\n" if fake_uid else ""
    script = f'{uid_fn}\n{body}\n{spoof}CWD_TOPLEVEL="$2"\nzpc_store_root "$1"'
    env = {"PATH": "/usr/bin:/bin:/usr/sbin:/sbin"}
    if home is not None:
        env["HOME"] = home
    proc = subprocess.run(
        ["bash", "-c", script, "_", cwd, toplevel],
        capture_output=True,
        text=True,
        check=False,
        env=env,
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
        subprocess.run(["git", "init", "-q", str(root)], check=False)

        # Inside the boundary the hooks must match zpc exactly. Outside it they
        # are deliberately stricter, which the boundary cases below cover.
        print("store at project root, session opened four levels down:")

        truth = zpc_reported_project(str(deep))
        check(
            "zpc status --json resolves the walked-up root",
            truth == str(root),
            f"got {truth!r}, want {str(root)!r}",
        )

        codex_answer = codex.zpc_store_root(str(deep), root)
        check(
            "codex hook agrees with zpc",
            codex_answer is not None and str(codex_answer) == truth,
            f"hook {str(codex_answer)!r} vs zpc {truth!r}",
        )

        bash_answer = bash_store_root(str(deep), str(root))
        check(
            "claude hook agrees with zpc",
            bash_answer == truth,
            f"hook {bash_answer!r} vs zpc {truth!r}",
        )

        print("session opened at the store root:")
        at_root_codex = codex.zpc_store_root(str(root), root)
        check(
            "codex hook resolves to itself",
            at_root_codex is not None and str(at_root_codex) == str(root),
            f"got {str(at_root_codex)!r}",
        )
        check(
            "claude hook resolves to itself",
            bash_store_root(str(root), str(root)) == str(root),
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

    # --- boundary: an unattended walk must not read a store it did not come for
    with tempfile.TemporaryDirectory() as tmp:
        planted = Path(tmp).resolve()
        (planted / ".zpc" / "memory").mkdir(parents=True)
        deep = planted / "scratch" / "work"
        deep.mkdir(parents=True)
        fake_home = planted / "elsewhere"
        fake_home.mkdir()

        print("planted store above a non-git dir outside $HOME:")
        check(
            "codex hook does not discover it",
            codex.zpc_store_root(str(deep), None) is None,
        )
        check(
            "claude hook does not discover it",
            bash_store_root(str(deep), "", home=str(fake_home)) == "",
        )

        print("same planted store, but cwd is a git worktree rooted below it:")
        worktree = planted / "scratch"
        check(
            "codex hook stops at the toplevel",
            codex.zpc_store_root(str(deep), worktree) is None,
        )
        check(
            "claude hook stops at the toplevel",
            bash_store_root(str(deep), str(worktree), home=str(fake_home)) == "",
        )

        print("$HOME ceiling: store above $HOME is out of reach:")
        home_dir = planted / "home"
        (home_dir / "projects" / "thing").mkdir(parents=True)
        check(
            "codex hook stops at $HOME",
            codex.zpc_store_root(str(home_dir / "projects" / "thing"), None) is None,
        )
        check(
            "claude hook stops at $HOME",
            bash_store_root(
                str(home_dir / "projects" / "thing"), "", home=str(home_dir)
            )
            == "",
        )

    # --- ownership: a store the current uid does not own is never trusted
    with tempfile.TemporaryDirectory() as tmp:
        owned = Path(tmp).resolve() / "project"
        (owned / ".zpc" / "memory").mkdir(parents=True)
        sub = owned / "src"
        sub.mkdir()

        print("store owned by another uid:")
        real_getuid = codex.os.getuid
        try:
            codex.os.getuid = lambda: real_getuid() + 12345
            check(
                "codex hook refuses it",
                codex.zpc_store_root(str(sub), owned) is None,
            )
        finally:
            codex.os.getuid = real_getuid
        check(
            "claude hook refuses it",
            bash_store_root(str(sub), str(owned), fake_uid="999999") == "",
        )
        check(
            "codex hook still accepts a store it does own",
            str(codex.zpc_store_root(str(sub), owned)) == str(owned),
        )
        check(
            "claude hook still accepts a store it does own",
            bash_store_root(str(sub), str(owned)) == str(owned),
        )

    if FAILURES:
        print(f"\nhook store resolution tests FAILED ({len(FAILURES)})")
        return 1
    print("\nhook store resolution tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
