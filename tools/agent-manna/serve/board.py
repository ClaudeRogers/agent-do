#!/usr/bin/env python3
"""Board derivation for `manna serve`: one board directory in, one JSON view out.

Everything on the human page is derived here from what the board already
stores. Nothing is authored: no lane config, no hand-listed horizon, no
invented states. The inputs are the documented on-disk board (SCHEMA.md),
the repository's git history, and coord's live presence. The output is a
rendering for a human eye; agents keep `manna context|list|show`.

Read-only by construction: this module never writes into a project. It does
not run `manna reconcile` (which writes drift.yaml); it reads the drift file
the last reconcile left behind and reports its age.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

# Title conventions that mean "a human must rule before this moves". Manna has
# no typed decision state yet; the board's own convention is the marker in the
# title. Matched case-insensitively at the start of the title.
DECISION_MARKERS = ("[ERIK]", "[HUMAN]", "[DECISION]")

# Fields that never leave the board directory. claim_token_hash is the digest
# of a private bearer token (SCHEMA.md); legacy_migration is admission
# history a reader has no use for.
PRIVATE_FIELDS = frozenset({"claim_token_hash", "legacy_migration"})

# git log field separators (ASCII unit / record separators, never in a subject).
_FS = "\x1f"
_RS = "\x1e"

COORD_SIGNATURE_FILES = ("agents.json", "sessions.json", "claims.json", "focus.json")

_MN_ID = re.compile(r"\bmn-[0-9a-f]{6,}\b")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime | None) -> str | None:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z") if dt else None


def mtime_iso(path: Path) -> str | None:
    try:
        return iso(datetime.fromtimestamp(path.stat().st_mtime, timezone.utc))
    except FileNotFoundError:
        return None


def find_board_root(start: Path) -> Path | None:
    """Nearest ancestor (inclusive) holding a .manna/ directory."""
    current = start.resolve()
    for candidate in (current, *current.parents):
        if (candidate / ".manna").is_dir():
            return candidate
    return None


def run(cmd: list[str], cwd: Path, timeout: float) -> str:
    try:
        completed = subprocess.run(
            cmd, cwd=str(cwd), capture_output=True, text=True, check=False, timeout=timeout
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return completed.stdout if completed.returncode == 0 else ""


# ---------------------------------------------------------------- raw reads


def read_issues(board_dir: Path) -> list[dict[str, Any]]:
    path = board_dir / "issues.jsonl"
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(row, dict) or not isinstance(row.get("id"), str):
                continue
            rows.append({k: v for k, v in row.items() if k not in PRIVATE_FIELDS})
    return rows


def read_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (yaml.YAMLError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def read_order(board_dir: Path) -> list[str]:
    items = read_yaml(board_dir / "handoff-order.yaml").get("items")
    return [i for i in items if isinstance(i, str)] if isinstance(items, list) else []


def read_drift(board_dir: Path) -> dict[str, Any]:
    path = board_dir / "drift.yaml"
    data = read_yaml(path)
    findings = data.get("findings")
    findings = [f for f in findings if isinstance(f, dict)] if isinstance(findings, list) else []
    kinds: dict[str, int] = {}
    for finding in findings:
        kind = str(finding.get("kind", "unknown"))
        kinds[kind] = kinds.get(kind, 0) + 1
    return {
        "present": path.is_file(),
        "generated_at": data.get("generated_at"),
        "findings": findings,
        "count": len(findings),
        "kinds": kinds,
    }


# ---------------------------------------------------------------- git


def git_dir(root: Path) -> Path | None:
    out = run(["git", "rev-parse", "--git-dir"], root, timeout=5).strip()
    if not out:
        return None
    path = Path(out)
    return (root / path).resolve() if not path.is_absolute() else path


def git_summary(root: Path) -> dict[str, Any]:
    branch = run(["git", "branch", "--show-current"], root, timeout=5).strip()
    head = run(["git", "rev-parse", "--short", "HEAD"], root, timeout=5).strip()
    dirty = run(["git", "status", "--porcelain"], root, timeout=10).splitlines()
    return {
        "branch": branch or None,
        "head": head or None,
        "dirty_paths": len(dirty),
        "is_repo": bool(head),
    }


def git_trailers(root: Path) -> dict[str, list[dict[str, Any]]]:
    """Every commit carrying a `Manna:` trailer, indexed by the ids it names.

    One log call over the whole local history; the trailer is the receipt the
    board doctrine requires on any commit advancing an item, so this is the
    evidence column without a receipt config.
    """
    fmt = f"%h{_FS}%cI{_FS}%s{_FS}%(trailers:key=Manna,valueonly,separator={_RS})"
    out = run(["git", "log", f"--format={fmt}", "--grep=^Manna:", "--extended-regexp"], root, timeout=20)
    index: dict[str, list[dict[str, Any]]] = {}
    for line in out.splitlines():
        parts = line.split(_FS)
        if len(parts) != 4:
            continue
        short, when, subject, trailers = parts
        ids = set()
        for value in trailers.split(_RS):
            ids.update(_MN_ID.findall(value))
        for issue_id in ids:
            index.setdefault(issue_id, []).append({"sha": short, "at": when, "subject": subject})
    return index


# ---------------------------------------------------------------- coord


def coord_peers(root: Path, agent_do: Path | None) -> list[dict[str, Any]]:
    if agent_do is None or not agent_do.is_file():
        return []
    out = run([str(agent_do), "coord", "peers", "--json"], root, timeout=10)
    if not out:
        return []
    try:
        data = json.loads(out)
    except json.JSONDecodeError:
        return []
    peers = data.get("peers") if isinstance(data, dict) else None
    if not isinstance(peers, list):
        return []
    slim = []
    for peer in peers:
        if not isinstance(peer, dict):
            continue
        focus = peer.get("focus") if isinstance(peer.get("focus"), dict) else {}
        slim.append(
            {
                "agent_id": peer.get("agent_id"),
                "alias": peer.get("alias"),
                "status": peer.get("status"),
                "age": peer.get("age"),
                "runtime": peer.get("runtime"),
                "role": peer.get("role"),
                "mode": peer.get("mode"),
                "phase": peer.get("phase"),
                "goal": focus.get("goal"),
                "paths": focus.get("paths") or peer.get("territory") or [],
            }
        )
    return slim


def _identity_hex(value: str | None) -> str:
    """The hex tail shared by manna's claimant label and coord's agent id.

    manna: claude-3c15edbd486045ef / codex-01a02afe94d27b52
    coord: session-3c15edbd4860   / codex-01a02afe94d27b52
    Both derive from the same session id; one is a prefix of the other.
    """
    if not value:
        return ""
    tail = value.rsplit("-", 1)[-1].lower()
    return tail if re.fullmatch(r"[0-9a-f]+", tail) else value.lower()


def match_peer(claimed_by: str | None, peers: list[dict[str, Any]]) -> dict[str, Any] | None:
    want = _identity_hex(claimed_by)
    if not want:
        return None
    for peer in peers:
        have = _identity_hex(peer.get("agent_id"))
        if have and (want.startswith(have) or have.startswith(want)):
            return peer
    return None


# ---------------------------------------------------------------- derivation


_LEADING_TAGS = re.compile(r"^\s*((?:\[[^\]]*\]\s*)+)")


def is_decision(issue: dict[str, Any]) -> bool:
    """A marker counts only when it leads the title; a mention mid-sentence is prose."""
    match = _LEADING_TAGS.match(str(issue.get("title", "")))
    if not match:
        return False
    tags = {tag.upper() for tag in re.findall(r"\[[^\]]*\]", match.group(1))}
    return any(marker in tags for marker in DECISION_MARKERS)


def strip_markers(title: str) -> str:
    return re.sub(r"^(\s*\[[^\]]*\]\s*)+", "", title).strip() or title


def derive(root: Path, agent_do: Path | None = None) -> dict[str, Any]:
    """Build the whole page model for one board root."""
    board_dir = root / ".manna"
    issues = read_issues(board_dir)
    order = read_order(board_dir)
    drift = read_drift(board_dir)
    workflow = read_yaml(board_dir / "workflow.yaml")
    board_meta = read_yaml(board_dir / "board.yaml")
    git = git_summary(root)
    trailers = git_trailers(root) if git["is_repo"] else {}
    peers = coord_peers(root, agent_do) if git["is_repo"] else []

    by_id = {i["id"]: i for i in issues}
    order_index = {issue_id: n for n, issue_id in enumerate(order)}
    tracks = {i["id"]: i for i in issues if i.get("type") == "track"}

    def kind(issue: dict[str, Any]) -> str:
        return issue.get("type") or "item"

    def unresolved(issue: dict[str, Any]) -> list[dict[str, Any]]:
        out = []
        for dep in issue.get("blocked_by") or []:
            target = by_id.get(dep)
            if target is None:
                out.append({"id": dep, "status": "missing", "title": dep})
            elif target.get("status") != "done":
                out.append({"id": dep, "status": target.get("status"), "title": target.get("title", dep)})
        return out

    # Enrich every row once; sections are filters over this list.
    rows: list[dict[str, Any]] = []
    for issue in issues:
        status = issue.get("status", "open")
        blockers = unresolved(issue)
        peer = match_peer(issue.get("claimed_by"), peers)
        track_id = issue.get("track")
        row = {
            **issue,
            "kind": kind(issue),
            "title_plain": strip_markers(str(issue.get("title", ""))),
            "track_title": tracks.get(track_id, {}).get("title") if track_id else None,
            "order": order_index.get(issue["id"]),
            "blockers": blockers,
            "dependents": [],
            "decision": is_decision(issue) and status != "done",
            "claimant": (
                {
                    "label": issue.get("claimed_by"),
                    "liveness": peer.get("status") if peer else "unseen",
                    "age": peer.get("age") if peer else None,
                    "runtime": peer.get("runtime") if peer else None,
                    "goal": peer.get("goal") if peer else None,
                }
                if issue.get("claimed_by")
                else None
            ),
            "commits": trailers.get(issue["id"], []),
        }
        # effective: what the graph says, not only what the status field says
        if kind(issue) == "track":
            row["effective"] = "track"
        elif kind(issue) == "dream":
            row["effective"] = "dream" if status != "done" else "done"
        elif status == "done":
            row["effective"] = "done"
        elif status == "in_progress":
            row["effective"] = "active"
        elif blockers:
            row["effective"] = "waiting"
        elif row["decision"]:
            row["effective"] = "decision"
        else:
            row["effective"] = "ready"
        rows.append(row)

    row_by_id = {r["id"]: r for r in rows}
    for row in rows:
        for dep in row.get("blocked_by") or []:
            if dep in row_by_id:
                row_by_id[dep]["dependents"].append(row["id"])

    def order_key(row: dict[str, Any]) -> tuple:
        pos = row["order"]
        return (pos is None, pos if pos is not None else 0, row.get("updated_at") or "", row["id"])

    now_rows = sorted((r for r in rows if r["effective"] == "active"), key=order_key)
    next_rows = sorted((r for r in rows if r["effective"] == "ready"), key=order_key)
    decision_rows = sorted((r for r in rows if r["decision"] and r["effective"] != "done"), key=order_key)
    waiting_rows = [r for r in rows if r["effective"] == "waiting"]
    dream_rows = sorted((r for r in rows if r["effective"] == "dream"), key=lambda r: r.get("updated_at") or "", reverse=True)

    # Waves: topological layers of the waiting set. Wave 1 waits only on
    # non-waiting work (ready/active/decision); wave n waits on waves < n.
    waves: list[dict[str, Any]] = []
    remaining = {r["id"] for r in waiting_rows}
    placed: set[str] = set()
    while remaining:
        layer = sorted(
            (
                row_by_id[i]
                for i in remaining
                if all(b["id"] not in remaining or b["id"] in placed for b in row_by_id[i]["blockers"])
            ),
            key=order_key,
        )
        if not layer:
            break
        waves.append({"wave": len(waves) + 1, "items": layer})
        for row in layer:
            placed.add(row["id"])
            remaining.discard(row["id"])
    unlayered = sorted((row_by_id[i] for i in remaining), key=order_key)

    counts: dict[str, int] = {}
    for row in rows:
        counts[row["effective"]] = counts.get(row["effective"], 0) + 1
    status_counts: dict[str, int] = {}
    for issue in issues:
        s = issue.get("status", "open")
        status_counts[s] = status_counts.get(s, 0) + 1

    track_groups = []
    for track_id, track in tracks.items():
        members = sorted((r for r in rows if r.get("track") == track_id and r["kind"] != "track"), key=order_key)
        track_groups.append({"id": track_id, "title": track.get("title"), "status": track.get("status"), "items": members})
    orphans = sorted((r for r in rows if r["kind"] != "track" and not r.get("track")), key=order_key)
    if orphans:
        track_groups.append({"id": None, "title": "(no track)", "status": None, "items": orphans})

    handoff_dir = workflow.get("handoff_dir") or ".handoff"
    return {
        "generated_at": iso(utc_now()),
        "root": str(root),
        "name": root.name,
        "board": {
            "path": ".manna/issues.jsonl",
            "workflow": board_meta.get("workflow"),
            "handoff_dir": handoff_dir,
            "issues_modified_at": mtime_iso(board_dir / "issues.jsonl"),
            "order_count": len(order),
        },
        "git": git,
        "peers": peers,
        "counts": counts,
        "status_counts": status_counts,
        "total": len(issues),
        "now": now_rows,
        "next": next_rows,
        "decisions": decision_rows,
        "waves": waves,
        "unlayered": unlayered,
        "dreams": dream_rows,
        "tracks": track_groups,
        "drift": drift,
        "all": sorted(rows, key=order_key),
    }


# ---------------------------------------------------------------- signature


def signature_paths(root: Path, gitdir: Path | None) -> list[Path]:
    board_dir = root / ".manna"
    paths = [
        board_dir / "issues.jsonl",
        board_dir / "handoff-order.yaml",
        board_dir / "drift.yaml",
        board_dir / "board.yaml",
        board_dir / "workflow.yaml",
    ]
    if gitdir:
        paths.extend([gitdir / "HEAD", gitdir / "index", gitdir / "logs" / "HEAD"])
        # Presence, claims, and focus move the page; pulse.json and
        # events.jsonl churn on every tool call and would re-render for nothing.
        coord_root = gitdir / "agent-do" / "coord"
        paths.extend(coord_root / name for name in COORD_SIGNATURE_FILES)
    return paths


def signature(root: Path, gitdir: Path | None) -> str:
    parts = []
    for path in signature_paths(root, gitdir):
        try:
            st = path.stat()
            parts.append(f"{path}:{st.st_mtime_ns}:{st.st_size}")
        except OSError:
            parts.append(f"{path}:missing")
    return "|".join(parts)


def summary(root: Path) -> dict[str, Any]:
    """Cheap index-row view of a board: counts and freshness, no git walk."""
    board_dir = root / ".manna"
    issues = read_issues(board_dir)
    status_counts: dict[str, int] = {}
    dreams = 0
    decisions = 0
    for issue in issues:
        if issue.get("type") == "track":
            continue
        if issue.get("type") == "dream":
            dreams += 1
            continue
        s = issue.get("status", "open")
        status_counts[s] = status_counts.get(s, 0) + 1
        if is_decision(issue) and s != "done":
            decisions += 1
    drift = read_drift(board_dir)
    latest = max((i.get("updated_at") or "" for i in issues), default="") or None
    return {
        "name": root.name,
        "root": str(root),
        "exists": board_dir.is_dir(),
        "total": len(issues),
        "status_counts": status_counts,
        "dreams": dreams,
        "decisions": decisions,
        "drift_count": drift["count"],
        "drift_generated_at": drift["generated_at"],
        "latest_update": latest,
        "issues_modified_at": mtime_iso(board_dir / "issues.jsonl"),
    }
