#!/usr/bin/env python3
"""Regression coverage for `zpc init --store-only`.

Auto-init runs unattended, at session start, in whatever repo the user happened
to open. Plain init writes two files that belong to that repo: a `.gitignore`
block and an agent instruction file (or an import line appended to one that
already exists). A silent hook may not do either. So this mode creates the store
and nothing else, and keeps the one side effect worth keeping by writing the
ignore rule into `.git/info/exclude`, which is machine-local and never tracked.

The `--store-only` token in the help text is load-bearing: the session-start
hooks gate auto-init on finding that literal string, because init's argument
loop swallows flags it does not know and an ungated call to an older zpc would
run the invasive path and report success.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AGENT_DO = ROOT / "agent-do"

GATE_TOKEN = "--store-only"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def run(cwd: Path, env: dict[str, str], *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(AGENT_DO), "zpc", *args],
        cwd=cwd, env=env, text=True, capture_output=True, check=False,
    )


def checked(cwd: Path, env: dict[str, str], *args: str) -> subprocess.CompletedProcess[str]:
    result = run(cwd, env, *args)
    require(result.returncode == 0, f"zpc {' '.join(args)} failed: {result.stderr or result.stdout}")
    return result


def git(cwd: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=cwd, text=True, capture_output=True, check=False,
    )
    require(result.returncode == 0, f"git {' '.join(args)} failed: {result.stderr}")
    return result.stdout


def make_repo(path: Path, gitignore: str = "node_modules/\n") -> Path:
    """A repo shaped like the one the flag exists for: tracked, and not ours."""
    path.mkdir(parents=True)
    git(path, "init", "-q", ".")
    git(path, "config", "user.email", "test@example.com")
    git(path, "config", "user.name", "test")
    (path / "README.md").write_text("# Project\n")
    (path / "AGENTS.md").write_text("# Agent instructions\n\nNothing about memory here.\n")
    (path / ".gitignore").write_text(gitignore)
    git(path, "add", "-A")
    git(path, "commit", "-qm", "baseline")
    return path


def store_files(project: Path) -> list[str]:
    return sorted(p.name for p in (project / ".zpc" / "memory").iterdir())


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp_str:
        tmp = Path(tmp_str)
        env = os.environ.copy()
        env["AGENT_DO_HOME"] = str(tmp / "agent-home")

        # The gate the hooks read. Losing this string silently disables
        # auto-init everywhere, and nothing else would notice.
        help_text = checked(tmp, env, "init", "--help").stdout
        require(GATE_TOKEN in help_text, f"the help text must name the flag:\n{help_text}")

        repo = make_repo(tmp / "repo")
        before = {name: (repo / name).read_text() for name in ("README.md", "AGENTS.md", ".gitignore")}

        checked(repo, env, "init", "--store-only")

        require(
            store_files(repo) == ["decisions.jsonl", "lessons.jsonl", "patterns.md", "profile.md"],
            f"the store is still a store: {store_files(repo)}",
        )
        for sub in (".state", "team"):
            require((repo / ".zpc" / sub).is_dir(), f".zpc/{sub} missing")

        # The whole point: a repo that cannot tell the hook ran.
        status = git(repo, "status", "--porcelain")
        require(status == "", f"a store-only init touched the working tree:\n{status}")
        for name, text in before.items():
            require((repo / name).read_text() == text, f"{name} was modified by a store-only init")

        exclude = (repo / ".git" / "info" / "exclude").read_text()
        require(".zpc/" in exclude, f"the store must be excluded, untracked:\n{exclude}")
        ignored = subprocess.run(
            ["git", "check-ignore", "-q", ".zpc"], cwd=repo, check=False,
        )
        require(ignored.returncode == 0, "git does not consider the store ignored")

        # Twice is once: session start runs on every session.
        checked(repo, env, "init", "--store-only")
        require(
            (repo / ".git" / "info" / "exclude").read_text().count("\n.zpc/\n") == 1,
            "a second store-only init duplicated the exclude block",
        )
        require(git(repo, "status", "--porcelain") == "", "a second store-only init dirtied the tree")

        # A repo that already ignores the store needs no help from us.
        pre = make_repo(tmp / "pre-ignored", gitignore=".zpc/\n")
        checked(pre, env, "init", "--store-only")
        pre_exclude = pre / ".git" / "info" / "exclude"
        require(
            not pre_exclude.exists() or ".zpc/" not in pre_exclude.read_text(),
            "an already-ignored store was excluded again",
        )
        require(git(pre, "status", "--porcelain") == "", "the pre-ignored repo was modified")

        # No git, no exclude, still a store: the flag is about what it does not
        # write, not about requiring a repo.
        bare = tmp / "bare"
        bare.mkdir()
        checked(bare, env, "init", "--store-only")
        require((bare / ".zpc" / "memory" / "lessons.jsonl").exists(), "a non-git store was not created")

        # Plain init keeps writing the files a human asked it to write.
        plain = make_repo(tmp / "plain")
        checked(plain, env, "init")
        require(".zpc/" in (plain / ".gitignore").read_text(), "plain init stopped writing .gitignore")
        require(
            "@.zpc/zpc-brain.md" in (plain / "AGENTS.md").read_text(),
            "plain init stopped importing itself into the instruction file",
        )

        # Both modes report themselves, and --json parses at all: the quoted
        # heredoc used to reach Python with an unexpanded "$platform" in it.
        store_json = json.loads(checked(tmp / "bare", env, "init", "--store-only", "--json").stdout)
        require(store_json["result"]["store_only"] is True, f"store-only must say so: {store_json}")
        require(store_json["result"]["platform"] is None, f"store-only writes no platform: {store_json}")
        plain_json = json.loads(
            checked(plain, env, "init", "--platform", "generic", "--json").stdout
        )
        require(plain_json["result"]["store_only"] is False, f"plain init is not store-only: {plain_json}")
        require(plain_json["result"]["platform"] == "generic", f"plain init names its platform: {plain_json}")

        # Every store lands in the machine-wide index, however it was created.
        index = (Path(env["AGENT_DO_HOME"]) / "zpc" / "project-index.jsonl").read_text()
        projects = {json.loads(line)["project"] for line in index.splitlines() if line.strip()}
        for project in (repo, pre, bare, plain):
            require(
                any(Path(seen).resolve() == project.resolve() for seen in projects),
                f"{project.name} missing from the project index",
            )

    print("zpc init --store-only: a store in the repo, no mark on the repo")


if __name__ == "__main__":
    main()
