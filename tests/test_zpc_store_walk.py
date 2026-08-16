#!/usr/bin/env python3
"""Regression coverage for the bounds on zpc's store walk.

Resolution answers "whose memory is this?", and unbounded it answered with
whatever it met first on the way to `/`. A cwd in a scratch directory would
adopt a planted `/tmp/.zpc`, or another account's store, and every zpc command
after that reads and writes memory somebody else controls — inject then pastes
it into an agent's context as this project's recorded truth.

Three bounds and an ownership check, exercised here against planted stores:
a git worktree ends at its toplevel, `$HOME` is the floor and the last rung,
and outside `$HOME` with no worktree only cwd is probed. The hooks implement
the identical rule (mn-90eb96), so these cases are also the contract between
the tool's answer and theirs.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
COMMON = ROOT / "tools" / "agent-zpc" / "lib" / "common.sh"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def resolve(cwd: Path, home: Path) -> str | None:
    """Call resolve_zpc_dir with a controlled $HOME. Returns the store or None."""
    result = subprocess.run(
        ["bash", "-c", f'source "$1"; resolve_zpc_dir "$2"', "_", str(COMMON), str(cwd)],
        env={**os.environ, "HOME": str(home)},
        text=True, capture_output=True, check=False,
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def predicate(path: Path, home: Path) -> bool:
    result = subprocess.run(
        ["bash", "-c", f'source "$1"; _zpc_store_is_ours "$2"', "_", str(COMMON), str(path)],
        env={**os.environ, "HOME": str(home)},
        text=True, capture_output=True, check=False,
    )
    return result.returncode == 0


def store(at: Path) -> Path:
    (at / ".zpc" / "memory").mkdir(parents=True, exist_ok=True)
    return at / ".zpc"


def repo(at: Path, as_file: bool = False) -> Path:
    """A worktree marker. Submodules and linked worktrees use a FILE, not a dir."""
    at.mkdir(parents=True, exist_ok=True)
    if as_file:
        (at / ".git").write_text("gitdir: /somewhere/else\n")
    else:
        (at / ".git").mkdir(exist_ok=True)
    return at


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp_str:
        tmp = Path(tmp_str).resolve()

        # A fake HOME, so the floor is a directory this test controls.
        home = tmp / "home"
        home.mkdir()

        # A: the ordinary case. Store at the toplevel, session deep inside it.
        project = repo(home / "work" / "project")
        project_store = store(project)
        deep = project / "src" / "a" / "b"
        deep.mkdir(parents=True)
        require(
            resolve(deep, home) == str(project_store),
            "a session deep in a repo must find that repo's store",
        )
        require(resolve(project, home) == str(project_store), "the toplevel finds its own store")

        # B: the workspace case. A store ABOVE the toplevel is out of reach from
        # inside a repo that has none — the repository's memory is the
        # repository's. This is the 91-repo change under Custom-Coding.
        workspace_store = store(home / "work")
        bare_repo = repo(home / "work" / "storeless")
        inside = bare_repo / "src"
        inside.mkdir(parents=True)
        require(
            resolve(inside, home) is None,
            "a repo with no store must not adopt the workspace store above it",
        )

        # C: ... while the workspace itself still reaches its own store, since
        # the walk is only bounded by a toplevel when there is one.
        loose = home / "work" / "notes"
        loose.mkdir()
        require(
            resolve(loose, home) == str(workspace_store),
            "a non-repo directory still walks up to the workspace store",
        )

        # D: outside $HOME with no worktree, only cwd is probed. This is the
        # planted /tmp/.zpc that started the whole finding.
        outside = tmp / "scratch"
        planted = store(outside)
        below = outside / "work"
        below.mkdir(parents=True)
        require(
            resolve(below, home) is None,
            f"a planted store outside $HOME was adopted from a subdirectory: {planted}",
        )

        # E: ... but a store at cwd is still cwd's store. "cwd only" includes cwd.
        require(resolve(outside, home) == str(planted), "outside $HOME, cwd's own store still resolves")

        # F: a real worktree outside $HOME still walks to its toplevel, which is
        # what makes scratch repos and CI checkouts work at all.
        far = repo(tmp / "elsewhere" / "checkout")
        far_store = store(far)
        far_deep = far / "pkg" / "mod"
        far_deep.mkdir(parents=True)
        require(
            resolve(far_deep, home) == str(far_store),
            "a worktree outside $HOME must still resolve from its subdirectories",
        )

        # G: $HOME is the last rung, not a rung we stop short of.
        home_store = store(home)
        plain = home / "documents" / "notes"
        plain.mkdir(parents=True)
        require(resolve(plain, home) == str(home_store), "$HOME must be probed, not skipped")

        # H: and nothing above it is. A store planted beside $HOME is unreachable
        # from inside it.
        above_store = store(tmp)
        stray = home / "documents"
        require(
            resolve(stray, home) == str(home_store),
            "the walk must stop at $HOME rather than reach the store above it",
        )
        (home / ".zpc").rename(home / ".zpc-parked")
        require(
            resolve(stray, home) is None,
            f"with no store at or below $HOME the walk must find nothing, not {above_store}",
        )
        (home / ".zpc-parked").rename(home / ".zpc")

        # I: a repository that CONTAINS $HOME must not raise the floor. Someone
        # ran git init one directory up; the store beside it stays unreachable.
        repo(tmp)
        (home / ".zpc").rename(home / ".zpc-parked")
        require(
            resolve(stray, home) is None,
            "a repo containing $HOME lifted the floor and reached the store above it",
        )
        (home / ".zpc-parked").rename(home / ".zpc")

        # K: a .git FILE bounds exactly like a .git directory, or submodules and
        # linked worktrees would quietly keep walking.
        sub = repo(home / "work" / "submodule", as_file=True)
        sub_inside = sub / "src"
        sub_inside.mkdir(parents=True)
        require(
            resolve(sub_inside, home) is None,
            "a .git file must bound the walk the way a .git directory does",
        )

        # J: ownership, the bound that holds when the other three do not. /usr is
        # root-owned on any machine this runs on; the assertion is only worth
        # something if that is actually true here.
        usr = Path("/usr")
        require(usr.stat().st_uid != os.getuid(), "/usr is owned by this user; ownership case is vacuous")
        require(not predicate(usr, home), "a store owned by another uid must be rejected")
        require(predicate(home, home), "a store owned by this user must be accepted")

        # And the walk skips a rejected store rather than dying on it: with the
        # predicate forced to refuse, resolution continues and finds nothing
        # rather than returning the store it just refused.
        forced = subprocess.run(
            ["bash", "-c",
             'source "$1"; _zpc_store_is_ours() { return 1; }; resolve_zpc_dir "$2"',
             "_", str(COMMON), str(deep)],
            env={**os.environ, "HOME": str(home)},
            text=True, capture_output=True, check=False,
        )
        require(
            forced.returncode != 0 and forced.stdout.strip() == "",
            f"a store failing the ownership check was still returned: {forced.stdout!r}",
        )

    print("zpc store walk: bounded by toplevel, floored at $HOME, and owned by us")


if __name__ == "__main__":
    main()
