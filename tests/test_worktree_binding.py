#!/usr/bin/env python3
"""A worktree may not lose your memory, and may not fork your board in silence.

`.zpc/` is gitignored, so a linked worktree starts with no store, and the
session-start auto-init then creates an empty one at the worktree toplevel.
Every lesson the agent in that worktree records lands there and dies with
`worktree remove`. `agent-git worktree add` closes that by writing a bound
store — a real `.zpc/` holding one `primary-store` pointer — which zpc and both
session-start hooks resolve through to the checkout that outlives the worktree.

The board does not bind: manna reads `.manna` relative to the checkout with no
override (tools/agent-manna/src/store.rs), so `worktree add` says so out loud
instead. A fork the operator knows about is a decision; a silent one is a lost
afternoon.

The pointer is a trust surface, so it is bounded here too: only from a store
this uid owns, only to an absolute path, only to a `.zpc` directory this uid
owns, and one hop. A pointer that fails any of those is not a store at all —
resolution steps over it rather than handing back an empty stand-in.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AGENT_GIT = ROOT / "tools" / "agent-git"
AGENT_DO = ROOT / "agent-do"
COMMON = ROOT / "tools" / "agent-zpc" / "lib" / "common.sh"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def git(cwd: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(["git", *args], cwd=cwd, text=True, capture_output=True, check=False)
    if check:
        require(result.returncode == 0, f"git {' '.join(args)} failed: {result.stderr or result.stdout}")
    return result


def run(cwd: Path, *args: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(list(args), cwd=cwd, env=env, text=True, capture_output=True, check=False)


def resolve_store(cwd: Path) -> str:
    """zpc's own answer to "whose memory is this", from tools/agent-zpc."""
    result = subprocess.run(
        ["bash", "-c", 'source "$1"; resolve_zpc_dir "$2"', "_", str(COMMON), str(cwd)],
        text=True, capture_output=True, check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else ""


def init_repo(root: Path, name: str) -> Path:
    repo = root / name
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    git(repo, "config", "user.email", "worktree-binding@example.invalid")
    git(repo, "config", "user.name", "Worktree Binding Test")
    (repo / ".gitignore").write_text(".zpc/\n.env*\n", encoding="utf-8")
    (repo / "README.md").write_text("base\n", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "chore: initial")
    return repo


def store_with_lesson(repo: Path, text: str) -> Path:
    memory = repo / ".zpc" / "memory"
    memory.mkdir(parents=True)
    (memory / "lessons.jsonl").write_text(json.dumps({"takeaway": text}) + "\n", encoding="utf-8")
    return repo / ".zpc"


def test_memory_survives_removal(root: Path, env: dict[str, str]) -> None:
    repo = init_repo(root, "memory-repo")
    primary_store = store_with_lesson(repo, "recorded in the primary checkout")
    (repo / ".manna").mkdir()
    (repo / ".manna" / "issues.jsonl").write_text("", encoding="utf-8")
    git(repo, "add", ".manna/issues.jsonl")
    git(repo, "commit", "-qm", "chore: board")

    destination = root / "bound-worktree"
    added = run(repo, str(AGENT_GIT), "worktree", "add", "bind-branch", "--path", str(destination), "--json", env=env)
    require(added.returncode == 0, f"worktree add failed: {added.stderr or added.stdout}")
    payload = json.loads(added.stdout)
    require(payload["zpc_store"] == str(primary_store), f"add did not report the bound store: {payload}")

    pointer = destination / ".zpc" / "primary-store"
    require(pointer.is_file(), "no pointer written into the worktree")
    require(str(primary_store) in pointer.read_text(encoding="utf-8"), "pointer does not name the primary store")

    require(
        resolve_store(destination) == str(primary_store),
        "zpc did not resolve the worktree to the primary store",
    )

    # The whole point: a lesson written from inside the worktree lands in the
    # store that outlives it.
    learn = run(
        destination, str(AGENT_DO), "zpc", "learn",
        "worktree context", "worktree problem", "worktree solution",
        "recorded from inside the worktree", "--tags", "worktree",
        env=env,
    )
    require(learn.returncode == 0, f"zpc learn from the worktree failed: {learn.stderr or learn.stdout}")
    lessons = (primary_store / "memory" / "lessons.jsonl").read_text(encoding="utf-8")
    require("recorded from inside the worktree" in lessons, "the worktree's lesson never reached the primary store")
    require(
        not (destination / ".zpc" / "memory").exists(),
        "the worktree grew a store of its own beside the pointer",
    )

    # A bound worktree stays clean, which is what lets `worktree remove` work
    # without --force: a symlinked .zpc would not match the `.zpc/` ignore rule
    # and would leave the tree untracked-dirty instead.
    status = git(destination, "status", "--porcelain").stdout.strip()
    require(status == "", f"the binding dirtied the worktree: {status!r}")

    removed = run(repo, str(AGENT_GIT), "worktree", "remove", str(destination), env=env)
    require(removed.returncode == 0, f"worktree remove failed: {removed.stderr or removed.stdout}")
    require(not destination.exists(), "worktree survived removal")

    survivors = (primary_store / "memory" / "lessons.jsonl").read_text(encoding="utf-8")
    require("recorded from inside the worktree" in survivors, "the lesson died with the worktree")
    require("recorded in the primary checkout" in survivors, "removal took the primary store's earlier memory with it")


def test_board_divergence_is_named(root: Path, env: dict[str, str]) -> None:
    repo = init_repo(root, "board-repo")
    store_with_lesson(repo, "board fixture")
    (repo / ".manna").mkdir()
    (repo / ".manna" / "issues.jsonl").write_text('{"id":"mn-000001"}\n', encoding="utf-8")
    git(repo, "add", ".manna/issues.jsonl")
    git(repo, "commit", "-qm", "chore: board")

    destination = root / "board-worktree"
    added = run(repo, str(AGENT_GIT), "worktree", "add", "board-branch", "--path", str(destination), "--json", env=env)
    require(added.returncode == 0, f"worktree add failed: {added.stderr or added.stdout}")
    payload = json.loads(added.stdout)
    require(len(payload["warnings"]) == 1, f"the board fork went unnamed: {payload}")
    warning = payload["warnings"][0]
    for fragment in ("manna board does not follow", str(destination / ".manna"), "manna claim"):
        require(fragment in warning, f"warning missed {fragment!r}: {warning!r}")
    require(warning in added.stderr, "the warning never reached a stream a human reads")
    run(repo, str(AGENT_GIT), "worktree", "remove", str(destination), env=env)

    # No board, no warning: the notice is about a real divergence, not a ritual.
    plain = init_repo(root, "boardless-repo")
    store_with_lesson(plain, "boardless fixture")
    other = root / "boardless-worktree"
    added = run(plain, str(AGENT_GIT), "worktree", "add", "quiet-branch", "--path", str(other), "--json", env=env)
    require(json.loads(added.stdout)["warnings"] == [], "warned about a board that does not exist")
    run(plain, str(AGENT_GIT), "worktree", "remove", str(other), env=env)


def test_binding_is_bounded(root: Path, env: dict[str, str]) -> None:
    repo = init_repo(root, "bounds-repo")
    store_with_lesson(repo, "bounds fixture")

    # --no-bind is honored, and an unbound worktree resolves to nothing rather
    # than to the store above it: a repository's memory is the repository's.
    unbound = root / "unbound-worktree"
    added = run(repo, str(AGENT_GIT), "worktree", "add", "unbound-branch", "--path", str(unbound), "--no-bind", "--json", env=env)
    require(added.returncode == 0, f"worktree add --no-bind failed: {added.stderr or added.stdout}")
    require(json.loads(added.stdout)["zpc_store"] is None, "--no-bind still reported a binding")
    require(not (unbound / ".zpc").exists(), "--no-bind wrote a store anyway")
    run(repo, str(AGENT_GIT), "worktree", "remove", str(unbound), env=env)

    # An existing .zpc in the destination is never touched.
    occupied = root / "occupied-worktree"
    occupied.mkdir()
    (occupied / ".zpc" / "memory").mkdir(parents=True)
    (occupied / ".zpc" / "memory" / "lessons.jsonl").write_text('{"takeaway":"pre-existing"}\n', encoding="utf-8")
    added = run(repo, str(AGENT_GIT), "worktree", "add", "occupied-branch", "--path", str(occupied), "--json", env=env)
    require(added.returncode != 0, "worktree add overwrote an existing destination")
    require(
        (occupied / ".zpc" / "memory" / "lessons.jsonl").read_text(encoding="utf-8").strip().endswith('"pre-existing"}'),
        "an existing store was clobbered",
    )

    # A repo that TRACKS its store gets that store checked out into every
    # worktree, and the binding must leave it alone: it is real memory that
    # travels with the branch, not the blank the ignore rule leaves behind.
    tracked = init_repo(root, "tracked-store-repo")
    (tracked / ".gitignore").write_text(".env*\n", encoding="utf-8")
    memory = tracked / ".zpc" / "memory"
    memory.mkdir(parents=True)
    (memory / "lessons.jsonl").write_text('{"takeaway":"tracked memory"}\n', encoding="utf-8")
    git(tracked, "add", "-A")
    git(tracked, "commit", "-qm", "chore: track the store")

    checked_out = root / "tracked-worktree"
    added = run(tracked, str(AGENT_GIT), "worktree", "add", "tracked-branch", "--path", str(checked_out), "--json", env=env)
    require(added.returncode == 0, f"worktree add failed: {added.stderr or added.stdout}")
    require(json.loads(added.stdout)["zpc_store"] is None, "binding overrode a store the worktree already had")
    require(not (checked_out / ".zpc" / "primary-store").exists(), "a pointer was written into a tracked store")
    require(
        "tracked memory" in (checked_out / ".zpc" / "memory" / "lessons.jsonl").read_text(encoding="utf-8"),
        "the tracked store was altered",
    )
    run(tracked, str(AGENT_GIT), "worktree", "remove", str(checked_out), env=env)


def test_pointer_trust(root: Path, env: dict[str, str]) -> None:
    """A pointer is a store's say-so about where memory lives. Bound the say-so.

    Each case plants a pointer in a worktree of a repo that has no store of its
    own, so a pointer that is wrongly trusted shows up as an answer instead of
    silence.
    """
    repo = init_repo(root, "trust-repo")
    real = store_with_lesson(repo, "the real store")

    def bound_worktree(name: str, body: str) -> Path:
        destination = root / name
        run(repo, str(AGENT_GIT), "worktree", "add", name, "--path", str(destination), "--no-bind", "--json", env=env)
        (destination / ".zpc").mkdir()
        (destination / ".zpc" / "primary-store").write_text(body, encoding="utf-8")
        return destination

    good = bound_worktree("trust-good", f"# comment\n\n{real}\n")
    require(resolve_store(good) == str(real), "a valid pointer past comments and blanks was refused")

    relative = bound_worktree("trust-relative", "../trust-repo/.zpc\n")
    require(resolve_store(relative) == "", "a relative pointer was trusted")

    not_a_store = bound_worktree("trust-shape", f"{repo}\n")
    require(resolve_store(not_a_store) == "", "a pointer to something that is not a .zpc directory was trusted")

    missing = bound_worktree("trust-missing", f"{root / 'nowhere' / '.zpc'}\n")
    require(resolve_store(missing) == "", "a pointer to a path that does not exist was trusted")

    # Ownership, the bound that holds when the others do not. /usr is root-owned
    # on any machine this runs on, and the assertion is only worth something if
    # that is actually true here.
    require(Path("/usr").stat().st_uid != os.getuid(), "/usr is owned by this user; the ownership case is vacuous")
    foreign_root = root / "foreign"
    foreign_root.mkdir()
    (foreign_root / ".zpc").symlink_to(Path("/usr"))
    foreign = bound_worktree("trust-foreign", f"{foreign_root / '.zpc'}\n")
    require(resolve_store(foreign) == "", "a pointer into another uid's directory was trusted")

    # One hop: a pointer whose target is itself a bound store resolves to that
    # target and stops, so no pair of stores can send resolution in a circle.
    hop = bound_worktree("trust-hop", f"{real}\n")
    (real / "primary-store").write_text(f"{(root / 'trust-hop' / '.zpc')}\n", encoding="utf-8")
    require(resolve_store(hop) == str(real), "resolution followed a second hop")
    (real / "primary-store").unlink()

    for name in ("trust-good", "trust-relative", "trust-shape", "trust-missing", "trust-foreign", "trust-hop"):
        run(repo, str(AGENT_GIT), "worktree", "remove", str(root / name), env=env)


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp_str:
        root = Path(tmp_str).resolve()
        env = os.environ.copy()
        env["AGENT_DO_HOME"] = str(root / "agent-do-home")
        test_memory_survives_removal(root, env)
        test_board_divergence_is_named(root, env)
        test_binding_is_bounded(root, env)
        test_pointer_trust(root, env)

    print("worktree binding tests passed")


if __name__ == "__main__":
    main()
