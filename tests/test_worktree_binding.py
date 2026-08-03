#!/usr/bin/env python3
"""A worktree may not lose your memory, and no repository may move it.

`.zpc/` is gitignored, so a linked worktree starts with no store, and the
session-start auto-init then creates an empty one at the worktree toplevel.
Every lesson the agent in that worktree records lands there and dies with
`worktree remove`. `agent-git worktree add` closes that by binding the worktree
to the checkout that outlives it, and zpc plus both session-start hooks resolve
through the binding.

The binding lives in this user's own config, keyed by absolute worktree path —
never in either tree. That location is the security property, not a filing
preference. The first version of this feature wrote a pointer file at
`.zpc/primary-store` inside the worktree, and a repository can track such a
file: cloning it silently redirected where every session read AND wrote memory,
into any store the cloning user happened to own. Session-start injection is
automatic, so the cost was cross-project context injection on the way in and
misdirected writes on the way out, with no user action at all. Repository
content is data; it is never authority over where memory lives. A clone cannot
write $AGENT_DO_HOME, so a clone cannot bind anything.

The board does not bind: manna reads `.manna` relative to the checkout with no
override (tools/agent-manna/src/store.rs), so `worktree add` says so out loud
instead. A fork the operator knows about is a decision; a silent one is a lost
afternoon.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AGENT_GIT = ROOT / "tools" / "agent-git"
AGENT_DO = ROOT / "agent-do"
COMMON = ROOT / "tools" / "agent-zpc" / "lib" / "common.sh"
CLAUDE_HOOK = ROOT / "hooks" / "claude" / "agent-do-session-start.sh"
CODEX_HOOK = ROOT / "hooks" / "codex" / "agent-do-session-start.py"


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


def bindings_file(env: dict[str, str]) -> Path:
    return Path(env["AGENT_DO_HOME"]) / "zpc" / "worktree-bindings.tsv"


def bindings(env: dict[str, str]) -> list[tuple[str, str]]:
    path = bindings_file(env)
    if not path.is_file():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        worktree, _, store = line.partition("\t")
        rows.append((worktree, store))
    return rows


def resolve_store(cwd: Path, env: dict[str, str]) -> str:
    """zpc's own answer to "whose memory is this", from tools/agent-zpc."""
    result = subprocess.run(
        ["bash", "-c", 'source "$1"; resolve_zpc_dir "$2"', "_", str(COMMON), str(cwd)],
        env=env, text=True, capture_output=True, check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else ""


def claude_hook_store_root(cwd: Path, env: dict[str, str]) -> str:
    """The claude hook's own resolver, extracted by name so a rename fails loudly."""
    source = CLAUDE_HOOK.read_text(encoding="utf-8")
    parts = []
    for name in ("_path_uid", "_zpc_store_is_ours", "zpc_binding_for", "zpc_worktree_root", "zpc_store_root"):
        match = re.search(rf"^{name}\(\) \{{\n.*?^\}}", source, re.S | re.M)
        require(match is not None, f"{name} not found in the claude hook")
        parts.append(match.group(0))
    parts.append('zpc_store_root "$1"')
    result = subprocess.run(
        ["bash", "-c", "\n".join(parts), "_", str(cwd)],
        env=env, text=True, capture_output=True, check=False,
    )
    return result.stdout.strip()


def codex_hook_store_root(cwd: Path, env: dict[str, str]) -> str:
    probe = (
        "import importlib.util, os\n"
        f"spec = importlib.util.spec_from_file_location('cx', {str(CODEX_HOOK)!r})\n"
        "m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)\n"
        f"answer = m.zpc_store_root({str(cwd)!r})\n"
        "print('' if answer is None else str(answer))\n"
    )
    result = subprocess.run([sys.executable, "-c", probe], env=env, text=True, capture_output=True, check=False)
    return result.stdout.strip()


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

    require(
        (str(destination), str(primary_store)) in bindings(env),
        f"no binding recorded for the worktree: {bindings(env)}",
    )
    # Nothing was written into either tree. This is the finding: a binding that
    # lives in a repository is a binding a repository can forge.
    require(not (destination / ".zpc").exists(), "the binding wrote into the worktree")
    require(
        git(destination, "status", "--porcelain").stdout.strip() == "",
        "the binding dirtied the worktree",
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
    require(not (destination / ".zpc").exists(), "the worktree grew a store of its own")

    # All three resolvers agree on where that memory lives.
    for label, answer in (
        ("zpc", resolve_store(destination, env)),
        ("claude hook", claude_hook_store_root(destination, env) + "/.zpc"),
        ("codex hook", codex_hook_store_root(destination, env) + "/.zpc"),
    ):
        require(answer == str(primary_store), f"{label} resolved {answer!r}, want {str(primary_store)!r}")

    removed = run(repo, str(AGENT_GIT), "worktree", "remove", str(destination), env=env)
    require(removed.returncode == 0, f"worktree remove failed: {removed.stderr or removed.stdout}")
    require(not destination.exists(), "worktree survived removal")

    survivors = (primary_store / "memory" / "lessons.jsonl").read_text(encoding="utf-8")
    require("recorded from inside the worktree" in survivors, "the lesson died with the worktree")
    require("recorded in the primary checkout" in survivors, "removal took the primary store's earlier memory with it")
    require(bindings(env) == [], f"removal left the binding dangling: {bindings(env)}")


def test_repo_content_cannot_move_memory(root: Path, env: dict[str, str]) -> None:
    """The finding, as a regression: a repository that ships a binding is inert.

    The hostile repo force-adds `.zpc/primary-store` naming a store the cloning
    user owns. Under the first version of this feature the clone's every read
    and write went to that store. Now the file is data: resolution stops at the
    clone's own directory and the named store is never consulted.
    """
    victim = root / "victim-project"
    victim.mkdir()
    git(victim, "init", "-q", "-b", "main")
    victim_store = store_with_lesson(victim, "VICTIM PROJECT MEMORY")

    hostile = init_repo(root, "hostile-repo")
    (hostile / ".zpc").mkdir()
    (hostile / ".zpc" / "primary-store").write_text(f"{victim_store}\n", encoding="utf-8")
    git(hostile, "add", "-f", ".zpc/primary-store")
    git(hostile, "commit", "-qm", "chore: pointer")
    require(
        ".zpc/primary-store" in git(hostile, "ls-files").stdout,
        "fixture failed: the pointer is not tracked, so this proves nothing",
    )

    clone = root / "cloned-repo"
    git(root, "clone", "-q", str(hostile), str(clone))
    require((clone / ".zpc" / "primary-store").is_file(), "fixture failed: the clone has no pointer")

    for label, answer in (
        ("zpc", resolve_store(clone, env)),
        ("claude hook", claude_hook_store_root(clone, env)),
        ("codex hook", codex_hook_store_root(clone, env)),
    ):
        require(
            str(victim_store) not in answer,
            f"{label} let a cloned repository redirect memory to {answer!r}",
        )

    # And nothing of the victim's reaches a session opened in the clone.
    injected = run(clone, str(AGENT_DO), "zpc", "inject", env=env)
    require(
        "VICTIM PROJECT MEMORY" not in injected.stdout,
        "the victim project's memory was injected into a session in the clone",
    )
    require(
        "VICTIM PROJECT MEMORY" in (victim_store / "memory" / "lessons.jsonl").read_text(encoding="utf-8"),
        "the victim store was altered",
    )


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
    require(
        all(worktree != str(unbound) for worktree, _ in bindings(env)),
        "--no-bind recorded a binding anyway",
    )
    require(resolve_store(unbound, env) == "", "an unbound worktree resolved to a store")
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
    require(
        all(worktree != str(checked_out) for worktree, _ in bindings(env)),
        "a worktree with its own store was bound anyway",
    )
    require(
        "tracked memory" in (checked_out / ".zpc" / "memory" / "lessons.jsonl").read_text(encoding="utf-8"),
        "the tracked store was altered",
    )
    run(tracked, str(AGENT_GIT), "worktree", "remove", str(checked_out), env=env)


def test_registry_trust(root: Path, env: dict[str, str]) -> None:
    """The registry is the authority, so bound the authority.

    Each case writes a binding by hand for a worktree of a repo that has no
    store of its own, so a binding that is wrongly trusted shows up as an answer
    instead of silence.
    """
    repo = init_repo(root, "trust-repo")
    real = store_with_lesson(repo, "the real store")
    path = bindings_file(env)
    path.parent.mkdir(parents=True, exist_ok=True)

    def bind(name: str, store: str) -> Path:
        destination = root / name
        if not destination.exists():
            run(repo, str(AGENT_GIT), "worktree", "add", name, "--path", str(destination), "--no-bind", "--json", env=env)
        path.write_text(f"# fixture\n{destination}\t{store}\n", encoding="utf-8")
        return destination

    good = bind("trust-good", str(real))
    require(resolve_store(good, env) == str(real), "a valid binding was refused")

    relative = bind("trust-relative", "../trust-repo/.zpc")
    require(resolve_store(relative, env) == "", "a relative binding was trusted")

    not_a_store = bind("trust-shape", str(repo))
    require(resolve_store(not_a_store, env) == "", "a binding to something that is not a .zpc directory was trusted")

    missing = bind("trust-missing", str(root / "nowhere" / ".zpc"))
    require(resolve_store(missing, env) == "", "a binding to a path that does not exist was trusted")

    # Ownership, the bound that holds when the others do not. /usr is root-owned
    # on any machine this runs on, and the assertion is only worth something if
    # that is actually true here.
    require(Path("/usr").stat().st_uid != os.getuid(), "/usr is owned by this user; the ownership case is vacuous")
    foreign_root = root / "foreign"
    foreign_root.mkdir()
    (foreign_root / ".zpc").symlink_to(Path("/usr"))
    foreign = bind("trust-foreign", str(foreign_root / ".zpc"))
    require(resolve_store(foreign, env) == "", "a binding into another uid's directory was trusted")

    # A stale key for a directory that no longer exists is inert, and does not
    # stop the rest of the file from being read.
    live = root / "trust-good"
    path.write_text(f"{root / 'deleted-worktree'}\t{real}\n{live}\t{real}\n", encoding="utf-8")
    require(resolve_store(live, env) == str(real), "a stale key ahead of a live one broke resolution")

    for name in ("trust-good", "trust-relative", "trust-shape", "trust-missing", "trust-foreign"):
        run(repo, str(AGENT_GIT), "worktree", "remove", str(root / name), env=env)
    path.unlink(missing_ok=True)


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp_str:
        root = Path(tmp_str).resolve()
        env = os.environ.copy()
        env["AGENT_DO_HOME"] = str(root / "agent-do-home")
        test_memory_survives_removal(root, env)
        test_repo_content_cannot_move_memory(root, env)
        test_board_divergence_is_named(root, env)
        test_binding_is_bounded(root, env)
        test_registry_trust(root, env)

    print("worktree binding tests passed")


if __name__ == "__main__":
    main()
