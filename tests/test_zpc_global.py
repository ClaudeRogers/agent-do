#!/usr/bin/env python3
"""Isolated regression coverage for ZPC machine-wide lesson reads."""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AGENT_DO = ROOT / "agent-do"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def aged(day: str) -> str:
    """`2026-07-20 (14d ago)` — the fixture's date the way inject renders it.

    Computed rather than pinned: the expected age of a fixed date changes
    every midnight, and an age that is merely present proves nothing.
    """
    when = datetime.strptime(day, "%Y-%m-%d").date()
    days = (datetime.now().date() - when).days
    return f"{day} (today)" if days == 0 else f"{day} ({days}d ago)"


def run(project: Path, env: dict[str, str], *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(AGENT_DO), "zpc", *args],
        cwd=project,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def checked(project: Path, env: dict[str, str], *args: str) -> subprocess.CompletedProcess[str]:
    result = run(project, env, *args)
    require(result.returncode == 0, f"zpc {' '.join(args)} failed: {result.stderr or result.stdout}")
    return result


def json_result(result: subprocess.CompletedProcess[str]) -> dict:
    payload = json.loads(result.stdout)
    return payload.get("result", payload)


def init_project(root: Path, name: str, env: dict[str, str]) -> Path:
    project = root / name
    project.mkdir()
    checked(project, env, "init", "--platform", "generic")
    return project


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp_str:
        tmp = Path(tmp_str)
        home = tmp / "agent-home"
        env = os.environ.copy()
        env["AGENT_DO_HOME"] = str(home)

        source = init_project(tmp, "source", env)
        for problem, solution, takeaway, tags in (
            (
                "ignored env files are absent in a fresh worktree",
                "seed ignored files from the parent checkout",
                "Seed ignored env files from the parent worktree.",
                "harness-seed,git,worktree,env",
            ),
            (
                "the browser daemon wedged",
                "restart only the verified session daemon",
                "A wedged daemon keeps saved browser state on disk.",
                "harness-seed,browse,daemon",
            ),
        ):
            checked(
                source,
                env,
                "learn",
                "harness upgrade",
                problem,
                solution,
                takeaway,
                "--tags",
                tags,
            )

        first = json_result(checked(source, env, "promote", "harness-seed", "--to", "global", "--json"))
        second = json_result(checked(source, env, "promote", "harness-seed", "--to", "global", "--json"))
        require(first["promoted"] == 2, f"expected two promoted lessons: {first}")
        require(second["promoted"] == 0 and second["skipped"] == 2, f"promotion must deduplicate: {second}")

        consumer = init_project(tmp, "consumer", env)
        checked(
            consumer,
            env,
            "learn",
            "consumer project",
            "local issue",
            "local fix",
            "Keep project lessons after global lessons.",
            "--tags",
            "local",
        )

        injected = checked(consumer, env, "inject").stdout
        global_header = "--- Global Lessons (machine-wide) ---"
        recent_header = "--- Recent Lessons (newest last) ---"
        require(global_header in injected, f"global section missing: {injected}")
        require(injected.index(global_header) < injected.index(recent_header), "global lessons must precede project lessons")
        require(injected.count("Seed ignored env files from the parent worktree.") == 1, "worktree seed duplicated")
        require(injected.count("A wedged daemon keeps saved browser state on disk.") == 1, "browse seed duplicated")

        status = json.loads(checked(consumer, env, "status", "--json").stdout)
        require(status["global_lessons"] == 2, f"global count missing from status: {status}")

        query = json_result(checked(consumer, env, "query", "--global", "--tag", "harness-seed", "--json"))
        require(query["count"] == 2, f"global query did not include promoted lessons: {query}")
        require(all(item.get("_scope") == "global" for item in query["results"]), f"global scope tags missing: {query}")
        query_text = checked(consumer, env, "query", "--global", "--tag", "harness-seed").stdout
        require(query_text.count("[global]") == 2, f"text query must label global entries: {query_text}")

        tail_env = env.copy()
        tail_home = tmp / "tail-home"
        tail_env["AGENT_DO_HOME"] = str(tail_home)
        tail = init_project(tmp, "tail", tail_env)
        tail_store = tail_home / "zpc" / "global-lessons.jsonl"
        tail_store.parent.mkdir(parents=True, exist_ok=True)
        tail_store.write_text(
            "".join(
                json.dumps(
                    {
                        "date": f"2026-07-{index:02d}",
                        "context": "tail limit",
                        "problem": f"global problem {index}",
                        "solution": f"global solution {index}",
                        "takeaway": f"global takeaway {index}",
                        "tags": ["tail-limit"],
                    }
                )
                + "\n"
                for index in range(1, 13)
            ),
            encoding="utf-8",
        )
        tail_injected = checked(tail, tail_env, "inject").stdout
        require(
            "global takeaway 1 " not in tail_injected and not tail_injected.endswith("global takeaway 1"),
            "inject included a global lesson older than the newest 10",
        )
        require(
            "global takeaway 2" not in tail_injected,
            "inject included a global lesson older than the newest 10",
        )
        require(tail_injected.count("global takeaway") == 10, "inject must include exactly the newest 10 global lessons")

        # Machine-wide claims render like every other claim: dated, kinded, and
        # carrying the id you would need to retract one.
        require(
            f"[{aged('2026-07-12')}] les-" in tail_injected,
            f"global lessons must render dated, aged, and addressable: {tail_injected}",
        )
        require("[tags: tail-limit]" in tail_injected, "global lessons must render their tags")
        require('"context": "tail limit"' not in tail_injected, "global slice must not dump raw rows")

        # A retracted machine-wide claim stops being delivered, which a raw tail
        # of the file could never honour.
        tail_ids = re.findall(r"\b(les-[0-9a-f]{6})\b", tail_injected)
        require(tail_ids, "no claim ids rendered in the global slice")
        checked(tail, tail_env, "retract", tail_ids[-1], "--evidence", "the newest global lesson is a fixture")
        require(
            "global takeaway 12" not in checked(tail, tail_env, "inject").stdout,
            "a retracted global lesson kept rendering",
        )

        empty_env = env.copy()
        empty_env["AGENT_DO_HOME"] = str(tmp / "empty-home")
        empty = init_project(tmp, "empty", empty_env)
        require(global_header not in checked(empty, empty_env, "inject").stdout, "empty global store emitted a section")

    print("zpc global read-surface tests passed")


if __name__ == "__main__":
    main()
