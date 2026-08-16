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
import os
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


def bash_store_root(cwd: str, home: str | None = None, agent_do_home: str | None = None) -> str:
    """Run the claude hook's own zpc_store_root, extracted by name.

    A rename breaks this test rather than silently skipping it, which is the
    intent: the function is the contract.
    """
    parts = [
        _extract_bash_func("_path_uid"),
        _extract_bash_func("_zpc_store_is_ours"),
        _extract_bash_func("zpc_binding_for"),
        _extract_bash_func("zpc_worktree_root"),
        _extract_bash_func("zpc_store_root"),
    ]
    parts.append('zpc_store_root "$1"')
    env = {"PATH": "/usr/bin:/bin:/usr/sbin:/sbin"}
    if agent_do_home is not None:
        env["AGENT_DO_HOME"] = agent_do_home
    if home is not None:
        env["HOME"] = home
    proc = subprocess.run(
        ["bash", "-c", "\n".join(parts), "_", cwd],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    return proc.stdout.strip()


def with_home(codex, home: str, fn):
    """Run fn with $HOME pointed at a fixture, then put it back."""
    previous = codex.os.environ.get("HOME")
    codex.os.environ["HOME"] = home
    try:
        return fn()
    finally:
        if previous is None:
            codex.os.environ.pop("HOME", None)
        else:
            codex.os.environ["HOME"] = previous


def zpc_reported_project(cwd: str, agent_do_home: str | None = None) -> str:
    env = dict(os.environ)
    if agent_do_home is not None:
        env["AGENT_DO_HOME"] = agent_do_home
    proc = subprocess.run(
        [str(AGENT_DO), "zpc", "status", "--json"],
        cwd=cwd,
        env=env,
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
            codex.zpc_store_root(str(deep)) is None,
        )
        check(
            "claude hook does not discover it",
            bash_store_root(str(deep), home=str(fake_home)) == "",
        )

        print("same planted store, cwd inside a worktree rooted below it:")
        # .git as a FILE, which is what a submodule or linked worktree leaves
        # behind — the toplevel probe tests existence, not directory-ness.
        (planted / "scratch" / ".git").write_text("gitdir: /elsewhere\n", encoding="utf-8")
        check(
            "codex hook stops at the toplevel",
            codex.zpc_store_root(str(deep)) is None,
        )
        check(
            "claude hook stops at the toplevel",
            bash_store_root(str(deep), home=str(fake_home)) == "",
        )

        print("$HOME ceiling: store above $HOME is out of reach:")
        home_dir = planted / "home"
        thing = home_dir / "projects" / "thing"
        thing.mkdir(parents=True)
        check(
            "codex hook stops at $HOME",
            with_home(codex, str(home_dir), lambda: codex.zpc_store_root(str(thing)))
            is None,
        )
        check(
            "claude hook stops at $HOME",
            bash_store_root(str(thing), home=str(home_dir)) == "",
        )

    # --- ownership: a store the current uid does not own is never trusted.
    # The unowned store is a symlink to a root-owned directory, so these run
    # against real uids — an unprivileged test cannot chown, and bash's EUID is
    # readonly, so there is no spoof here to fool itself with.
    with tempfile.TemporaryDirectory() as tmp:
        project = Path(tmp).resolve() / "project"
        project.mkdir(parents=True)
        # The worktree marker is what licenses the walk at all out here: this
        # fixture lives outside $HOME, where a bare directory probes only itself.
        (project / ".git").mkdir()
        sub = project / "src"
        sub.mkdir()
        (project / ".zpc").symlink_to(Path("/usr"))

        print("the only store in reach is owned by another uid:")
        check(
            "the decoy really does resolve to another uid",
            Path("/usr").stat().st_uid != Path(tmp).stat().st_uid,
            "test fixture assumption failed",
        )
        check(
            "codex hook refuses it",
            codex.zpc_store_root(str(sub)) is None,
            f"got {str(codex.zpc_store_root(str(sub)))!r}",
        )
        answer = bash_store_root(str(sub))
        check("claude hook refuses it", answer == "", f"got {answer!r}")

        print("a store we do own, same shape:")
        (project / ".zpc").unlink()
        (project / ".zpc" / "memory").mkdir(parents=True)
        check(
            "codex hook accepts it",
            str(codex.zpc_store_root(str(sub))) == str(project),
        )
        check(
            "claude hook accepts it",
            bash_store_root(str(sub)) == str(project),
        )

    # --- an unowned store is stepped over, not fatal, and a symlinked .zpc is
    # judged by what it resolves to rather than by the link.
    with tempfile.TemporaryDirectory() as tmp:
        owned = Path(tmp).resolve() / "project"
        (owned / ".zpc" / "memory").mkdir(parents=True)
        (owned / ".git").mkdir()
        shadow = owned / "src"
        shadow.mkdir()
        root_owned = Path("/usr")  # exists, is a directory, uid 0, not ours
        (shadow / ".zpc").symlink_to(root_owned)

        print("store below ours, symlinked to a directory owned by root:")
        check(
            "the decoy really does resolve to another uid",
            root_owned.stat().st_uid != Path(tmp).stat().st_uid,
            "test fixture assumption failed",
        )
        check(
            "codex hook steps over it and finds ours above",
            str(codex.zpc_store_root(str(shadow))) == str(owned),
            f"got {str(codex.zpc_store_root(str(shadow)))!r}",
        )
        answer = bash_store_root(str(shadow))
        check(
            "claude hook steps over it and finds ours above",
            answer == str(owned),
            f"got {answer!r}",
        )

    # --- a bound worktree: the binding `agent-git worktree add` records in this
    # user's config, whose whole purpose is that all three resolvers follow it
    # to the checkout that outlives the worktree. If one of them stops at the
    # worktree instead, that session's lessons die with `worktree remove`.
    with tempfile.TemporaryDirectory() as tmp:
        primary = Path(tmp).resolve() / "primary"
        (primary / ".zpc" / "memory").mkdir(parents=True)
        (primary / ".zpc" / "memory" / "lessons.jsonl").write_text("", encoding="utf-8")
        subprocess.run(["git", "init", "-q", str(primary)], check=False)

        worktree = Path(tmp).resolve() / "worktree"
        worktree.mkdir()
        (worktree / ".git").write_text(f"gitdir: {primary}/.git/worktrees/worktree\n", encoding="utf-8")

        agent_do_home = Path(tmp).resolve() / "agent-do-home"
        registry = agent_do_home / "zpc" / "worktree-bindings.tsv"
        registry.parent.mkdir(parents=True)
        registry.write_text(f"# bound by agent-git worktree add\n{worktree}\t{primary}/.zpc\n", encoding="utf-8")

        previous_home = os.environ.get("AGENT_DO_HOME")
        os.environ["AGENT_DO_HOME"] = str(agent_do_home)
        try:
            print("a worktree bound to the primary checkout's store:")
            truth = zpc_reported_project(str(worktree), agent_do_home=str(agent_do_home))
            check(
                "zpc status --json resolves through the binding",
                truth == str(primary),
                f"got {truth!r}, want {str(primary)!r}",
            )
            codex_answer = codex.zpc_store_root(str(worktree))
            check(
                "codex hook agrees with zpc",
                codex_answer is not None and str(codex_answer) == truth,
                f"hook {str(codex_answer)!r} vs zpc {truth!r}",
            )
            bash_answer = bash_store_root(str(worktree), agent_do_home=str(agent_do_home))
            check("claude hook agrees with zpc", bash_answer == truth, f"hook {bash_answer!r} vs zpc {truth!r}")

            print("the same binding, aimed at a directory owned by another uid:")
            registry.write_text(f"{worktree}\t/usr\n", encoding="utf-8")
            check(
                "zpc refuses it",
                zpc_reported_project(str(worktree), agent_do_home=str(agent_do_home)) == "",
            )
            check(
                "codex hook refuses it",
                codex.zpc_store_root(str(worktree)) is None,
                f"got {str(codex.zpc_store_root(str(worktree)))!r}",
            )
            answer = bash_store_root(str(worktree), agent_do_home=str(agent_do_home))
            check("claude hook refuses it", answer == "", f"got {answer!r}")

            print("a pointer file inside the worktree, which no resolver may honor:")
            registry.unlink()
            (worktree / ".zpc").mkdir()
            (worktree / ".zpc" / "primary-store").write_text(f"{primary}/.zpc\n", encoding="utf-8")
            # The worktree's own .zpc is a store at its own path — that much is
            # unchanged — but nothing in it may move memory to another one.
            for label, got in (
                ("zpc", zpc_reported_project(str(worktree), agent_do_home=str(agent_do_home))),
                ("codex hook", str(codex.zpc_store_root(str(worktree)))),
                ("claude hook", bash_store_root(str(worktree), agent_do_home=str(agent_do_home))),
            ):
                check(
                    f"{label} ignores a repo-resident pointer",
                    got != str(primary),
                    f"followed it to {got!r}",
                )
        finally:
            if previous_home is None:
                os.environ.pop("AGENT_DO_HOME", None)
            else:
                os.environ["AGENT_DO_HOME"] = previous_home

    if FAILURES:
        print(f"\nhook store resolution tests FAILED ({len(FAILURES)})")
        return 1
    print("\nhook store resolution tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
