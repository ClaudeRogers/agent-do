#!/usr/bin/env python3
"""The memory delivery bound is derived, and a store's claims actually arrive.

This is the regression for mn-84072c. The measured failure it pins: a store of
197 rows delivered ZERO claims into a session, because inject took an invented
top-20 and the session-start hook then cut the result at an invented 6000
characters — a cut that landed inside the protocol header, so what reached the
agent was boilerplate plus the four words `[zpc inject truncated]`.

Four properties, and each one is a way that failure could come back:

  DERIVED     the budget is read from the quantity authority at call time and no
              literal stands in for it anywhere in the delivery path.
  DELIVERED   a store whose claims fit the budget hands over all of them.
  RANKED      when the budget binds, the cut takes the least valuable records —
              oldest claims, not whatever landed past a byte offset — and the
              law that frames them is never what gets trimmed.
  COUNTED     every marker carries both numbers, so a reader can tell how much
              is missing rather than only that something is.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AGENT_DO = ROOT / "agent-do"
ZPC_LIB = ROOT / "tools" / "agent-zpc" / "lib"

# The delivery path: everything between a store on disk and an agent's context.
# A bare bounding literal anywhere in it is the defect, so the whole path is
# swept rather than the one file where it happened to live last time.
DELIVERY_PATH = [
    ROOT / "tools" / "agent-zpc" / "lib" / "integration.sh",
    ROOT / "tools" / "agent-zpc" / "lib" / "delivery.py",
    ROOT / "tools" / "agent-zpc" / "lib" / "counsel.sh",
    ROOT / "hooks" / "claude" / "agent-do-session-start.sh",
    ROOT / "hooks" / "codex" / "agent-do-session-start.py",
]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def run(cwd: Path, env: dict, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [str(AGENT_DO), "zpc", *args],
        cwd=cwd, env=env, text=True, capture_output=True, check=False,
    )


def checked(cwd: Path, env: dict, *args: str) -> str:
    result = run(cwd, env, *args)
    require(result.returncode == 0, f"zpc {' '.join(args)} failed: {result.stderr or result.stdout}")
    return result.stdout


def authority_minimum() -> int:
    """The smallest single delivery the authority publishes, read the same way
    lib/delivery.py reads it — through agent-do's own resolver, never copied."""
    payload = subprocess.run(
        [str(AGENT_DO), "harness", "quantity", "keys", "--json"],
        text=True, capture_output=True, check=True,
    )
    keys = json.loads(payload.stdout)["keys"]
    deliveries = [item["value"] for item in keys if item["key"].endswith(".max_tokens")]
    require(deliveries, "the authority publishes no max_tokens; the bound has nothing to derive from")
    return min(deliveries)


def seed(store: Path, count: int) -> None:
    store.parent.mkdir(parents=True, exist_ok=True)
    with store.open("w") as handle:
        for index in range(count):
            handle.write(json.dumps({
                "date": f"2026-01-{index % 28 + 1:02d}",
                "context": "seeded", "problem": f"p{index}", "solution": f"s{index}",
                "takeaway": f"seeded claim {index}", "tags": ["seed"],
            }) + "\n")


def main() -> None:
    budget = authority_minimum()

    # ── DERIVED: the resolver answers, and answers the same number ──────────
    import sys

    sys.path.insert(0, str(ZPC_LIB))
    import delivery

    resolved = delivery.budget(str(ROOT / "lib"))
    require(resolved is not None, "lib/delivery.py could not reach the quantity authority")
    require(
        resolved["tokens"] == budget,
        f"delivery.py and the authority disagree: {resolved['tokens']} vs {budget}",
    )
    require(
        resolved["key"].endswith(".max_tokens"),
        f"the budget must cite a published delivery ceiling: {resolved['key']}",
    )

    # An unreachable authority yields no ceiling rather than a substitute one.
    # In a fresh interpreter, because a resolver already imported in this one
    # would answer from sys.modules and hide exactly the case being tested.
    unreachable = subprocess.run(
        [
            "python3", "-c",
            "import sys; sys.path.insert(0, sys.argv[1]); import delivery; "
            "print(delivery.budget('/nonexistent/lib'))",
            str(ZPC_LIB),
        ],
        text=True, capture_output=True, check=True,
    )
    require(
        unreachable.stdout.strip() == "None",
        f"an unreachable authority must yield no bound, never a fallback constant: {unreachable.stdout}",
    )
    require(delivery.fit([{"key": "a", "body": "x\ny\nz"}], None)["cut"] is False,
            "with no budget resolved, nothing may be cut")

    # tokens <= bytes is the whole conversion, and it is a proof rather than a
    # constant: every token of a byte-level tokenizer decodes to at least one
    # byte. If this ever stops being how the blob is measured, the bound is
    # being converted by a folk factor again.
    require(delivery.measured("é") == 2, "the budget must be held in bytes, not characters")

    # ── DERIVED: no literal stands in for the budget anywhere on the path ───
    #
    # Checked with lib/bounds.py's own scanner rather than a regex written here.
    # It is the definition the contracts gate enforces repo-wide, it knows a
    # number quoted in a comment from one sitting in a bounding position, and
    # using anything else would let this test and the gate disagree about what a
    # shipped bound is.
    sys.path.insert(0, str(ROOT / "lib"))
    from bounds import scan_text

    for path in DELIVERY_PATH:
        require(path.exists(), f"delivery path file missing: {path}")
        label = str(path.relative_to(ROOT))
        shipped = [
            finding
            for finding in scan_text(label, path.read_text(), require_family=False)
            if finding["site_kind"] == "code"
        ]
        require(
            not shipped,
            f"the delivery path ships a bare bounding literal again: "
            f"{[(f['file'], f['line'], f['parameter'], f['value']) for f in shipped]}",
        )

    with tempfile.TemporaryDirectory() as tmp_str:
        tmp = Path(tmp_str)
        env = os.environ.copy()
        env["AGENT_DO_HOME"] = str(tmp / "home")

        project = tmp / "project"
        project.mkdir()
        checked(project, env, "init", "--platform", "generic")

        # ── DELIVERED: 197 rows, the measured size of the store that failed ──
        rows = 197
        seed(project / ".zpc" / "memory" / "lessons.jsonl", rows)
        checked(project, env, "retract", "--backfill")

        blob = checked(project, env, "inject")
        arrived = len(re.findall(r"^\[2026-", blob, flags=re.M))
        require(
            arrived == rows,
            f"a store of {rows} distinct claims must deliver all of them, not {arrived}:\n{blob[:400]}",
        )
        require(len(blob.encode()) <= budget, f"the derived budget must hold: {len(blob.encode())}")
        require("truncated" not in blob, f"a blob that fits must not claim a cut:\n{blob[-400:]}")

        # ── DELIVERED: identical rows collapse, and say how many collapsed ───
        with (project / ".zpc" / "memory" / "lessons.jsonl").open("a") as handle:
            for index in range(40):
                handle.write(json.dumps({
                    "date": "2026-02-02", "context": "auto", "problem": f"e{index}",
                    "solution": f"f{index}",
                    "takeaway": "Error resolved (review and enrich this auto-lesson)",
                    "tags": ["auto"],
                }) + "\n")
        checked(project, env, "retract", "--backfill")
        collapsed = checked(project, env, "inject")
        require(
            collapsed.count("Error resolved (review and enrich this auto-lesson)") == 1,
            "identical takeaways must collapse to one line",
        )
        require(
            "[x40 identical]" in collapsed,
            f"a collapse is a cut and must carry its magnitude:\n{collapsed[-600:]}",
        )

        # ── RANKED: squeezed, the cut takes the oldest and keeps the law ─────
        squeeze = 2500
        tight = checked(project, env, "inject", "--max-tokens", str(squeeze))
        require(len(tight.encode()) <= squeeze, f"the caller's budget must hold: {len(tight.encode())}")
        require(
            "seeded claim 196" in tight,
            f"the newest claim must survive a cut:\n{tight}",
        )
        require(
            "seeded claim 0 " not in tight and "seeded claim 1 " not in tight,
            f"the oldest claims are what a cut takes:\n{tight}",
        )
        require(
            "Live observation outranks memory" in tight,
            f"the law that frames the claims is never what gets trimmed:\n{tight}",
        )
        require(
            "ZPC Agent Protocol" in tight,
            "the protocol section survives every cut",
        )

        # ── COUNTED: every marker says how much went ─────────────────────────
        markers = [line for line in tight.splitlines() if "truncated" in line]
        require(markers, f"a cut blob must admit the cut:\n{tight}")
        for line in markers:
            found = re.search(r"\b(\d+) of (\d+)\b", line)
            require(found, f"a marker without magnitude is a half-receipt: {line!r}")
            require(
                int(found.group(1)) < int(found.group(2)),
                f"a marker must show fewer kept than total: {line!r}",
            )
        require(
            any(line.startswith("[budget:") for line in tight.splitlines()),
            f"a cut must name the budget that made it:\n{tight}",
        )
        require(
            f"[budget: {squeeze} tokens from --max-tokens" in tight,
            f"the receipt must report the budget actually applied:\n{tight}",
        )

    print(f"zpc memory bounds: budget {budget} tokens, derived; {rows} of {rows} claims delivered")


if __name__ == "__main__":
    main()
