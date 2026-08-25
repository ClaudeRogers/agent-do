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
# no typed decision state yet; the board's own convention is a leading marker
# in the title, matched case-insensitively. A machine adds its own names
# (`manna serve --decision-marker "[NAME]"`); the shipped defaults name a role.
DECISION_MARKERS = ("[DECISION]", "[HUMAN]", "[OWNER]")

# Fields that never leave the board directory. claim_token_hash is the digest
# of a private bearer token (SCHEMA.md); legacy_migration is admission
# history a reader has no use for.
PRIVATE_FIELDS = frozenset({"claim_token_hash", "legacy_migration"})

# git log field separators (ASCII unit / record separators, never in a subject).
_FS = "\x1f"
_RS = "\x1e"

COORD_SIGNATURE_FILES = ("agents.json", "sessions.json", "claims.json", "focus.json")

_MN_ID = re.compile(r"\bmn-[0-9a-f]{6,}\b")
_BOARD_ID = re.compile(r"^mb-[0-9a-f]{32}$")
_MANNA_URI = re.compile(r"^manna://mb-[0-9a-f]{32}/mn-[0-9a-f]{6,}$")
RELATION_KINDS = frozenset({"counterpart", "informed_by", "depends_on", "supersedes"})


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


def run(cmd: list[str], cwd: Path, timeout: float, any_exit: bool = False) -> str:
    """stdout of a command, or "" when it failed. `any_exit` keeps stdout on a
    nonzero exit, for verbs like reconcile that exit 1 *because* they found
    something and still print the structured answer."""
    try:
        completed = subprocess.run(
            cmd, cwd=str(cwd), capture_output=True, text=True, check=False, timeout=timeout
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    if completed.returncode == 0 or any_exit:
        return completed.stdout
    return ""


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


def read_federation(board_dir: Path) -> dict[str, Any]:
    """Read the portable declaration only. Resolution remains a separate,
    derived operation through the machine-local registry."""
    path = board_dir / "federation.yaml"
    if path.is_symlink():
        return {"enabled": True, "board_id": None, "relations": [], "error": "symlinked federation manifest refused"}
    if not path.is_file():
        return {"enabled": False, "board_id": None, "relations": []}
    data = read_yaml(path)
    board_id = data.get("board_id")
    rows = data.get("relations")
    if data.get("version") != 1 or not isinstance(board_id, str) or not _BOARD_ID.fullmatch(board_id):
        return {"enabled": True, "board_id": None, "relations": [], "error": "invalid federation manifest"}
    relations = []
    if not isinstance(rows, list):
        return {"enabled": True, "board_id": board_id, "relations": [], "error": "invalid federation relations"}
    for row in rows:
        if not isinstance(row, dict):
            return {"enabled": True, "board_id": board_id, "relations": [], "error": "invalid federation relation"}
        source, kind, target = row.get("from"), row.get("kind"), row.get("to")
        if (
            not isinstance(source, str)
            or not _MN_ID.fullmatch(source)
            or kind not in RELATION_KINDS
            or not isinstance(target, str)
            or not _MANNA_URI.fullmatch(target)
        ):
            return {"enabled": True, "board_id": board_id, "relations": [], "error": "invalid federation relation"}
        relation = {"from": source, "kind": kind, "to": target}
        if isinstance(row.get("hint"), str) and row["hint"].strip():
            relation["hint"] = row["hint"]
        relations.append(relation)
    return {"enabled": True, "board_id": board_id, "relations": relations}


def live_drift(root: Path, agent_do: Path | None) -> dict[str, Any] | None:
    """Findings as of now. `manna reconcile --json` reads the board and git
    without writing; the file it would write needs --write-drift, which the
    page never passes. None when the CLI is unavailable or fails."""
    if agent_do is None or not agent_do.is_file():
        return None
    out = run([str(agent_do), "manna", "reconcile", "--json"], root, timeout=60, any_exit=True)
    if not out:
        return None
    try:
        data = json.loads(out)
    except json.JSONDecodeError:
        return None
    findings = data.get("findings") if isinstance(data, dict) else None
    if not isinstance(findings, list):
        return None
    findings = [f for f in findings if isinstance(f, dict)]
    kinds: dict[str, int] = {}
    for finding in findings:
        kind = str(finding.get("kind", "unknown"))
        kinds[kind] = kinds.get(kind, 0) + 1
    return {"findings": findings, "count": len(findings), "kinds": kinds, "generated_at": iso(utc_now())}


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
                "age_seconds": peer.get("age_seconds"),
                "runtime": peer.get("runtime"),
                "role": peer.get("role"),
                "mode": peer.get("mode"),
                "phase": peer.get("phase"),
                "goal": focus.get("goal"),
                "paths": focus.get("paths") or peer.get("territory") or [],
                "pulse": slim_pulse(peer.get("pulse")),
            }
        )
    for peer in slim:
        peer["attention"] = attention_rank(peer)
    return slim


# Attention-first, the order coord peers itself uses: whoever waits on a
# human outranks whoever failed, outranks whoever is working, outranks the
# merely present; the finished and the gone sink.
ATTENTION_ORDER = ("needs-user", "failed", "working", "present", "idle", "finished", "ended", "gone")


def slim_pulse(pulse: Any) -> dict[str, Any] | None:
    """The telemetry fields the page shows. Pulse is a hint about what a
    session is doing now, never evidence of what the board records."""
    if not isinstance(pulse, dict):
        return None
    out = {
        "status": pulse.get("status"),
        "activity": pulse.get("activity"),
        "latest_prompt": pulse.get("latest_prompt"),
        "updated_at": pulse.get("updated_at"),
        "turns": pulse.get("turns"),
    }
    todo = pulse.get("todo")
    if isinstance(todo, dict):
        out["todo"] = {"done": todo.get("done"), "total": todo.get("total"), "current": todo.get("current")}
    return out


def attention_rank(peer: dict[str, Any]) -> str:
    liveness = peer.get("status")
    pulse = peer.get("pulse") or {}
    pstatus = pulse.get("status")
    if liveness in ("dead", "stopped", "stale"):
        return "gone"
    if pstatus in ("needs-user", "failed", "working", "finished", "ended"):
        return pstatus
    if liveness == "active":
        return "present"
    if liveness == "idle":
        return "idle"
    return "present"


def attention_key(peer: dict[str, Any]) -> tuple:
    rank = peer.get("attention") or attention_rank(peer)
    pos = ATTENTION_ORDER.index(rank) if rank in ATTENTION_ORDER else len(ATTENTION_ORDER)
    return (pos, peer.get("age_seconds") if isinstance(peer.get("age_seconds"), (int, float)) else 10**9)


def coord_json(root: Path, agent_do: Path | None, *verb: str, key: str) -> list[dict[str, Any]]:
    if agent_do is None or not agent_do.is_file():
        return []
    out = run([str(agent_do), "coord", *verb, "--json"], root, timeout=10)
    if not out:
        return []
    try:
        data = json.loads(out)
    except json.JSONDecodeError:
        return []
    rows = data.get(key) if isinstance(data, dict) else None
    return [r for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []


LIVE_OWNER = frozenset({"active", "idle"})
EMPTY_COORD: dict[str, Any] = {"claims": [], "contention": [], "drops": [], "needs": []}


def _overlaps(a: str, b: str) -> bool:
    a, b = a.rstrip("/"), b.rstrip("/")
    return a == b or a.startswith(b + "/") or b.startswith(a + "/") or a == "." or b == "."


def coord_snapshot(root: Path, agent_do: Path | None, peers: list[dict[str, Any]]) -> dict[str, Any]:
    """Claims, drops, needs, and the contention the page can see for itself:
    two live owners whose claimed paths overlap. coord's own interrupts are
    per-session; the daemon has no session, so it derives the shared view."""
    claims = []
    for c in coord_json(root, agent_do, "claims", key="claims"):
        claims.append(
            {
                "path": c.get("path"),
                "owner": c.get("owner"),
                "owner_alias": c.get("owner_alias"),
                "owner_status": c.get("owner_status"),
                "reason": c.get("reason"),
                "strength": c.get("strength"),
                "updated_at": c.get("updated_at") or c.get("created_at"),
                "stale": c.get("owner_status") not in LIVE_OWNER,
            }
        )
    live = [c for c in claims if not c["stale"] and c.get("path")]
    contention: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for i, a in enumerate(live):
        for b in live[i + 1 :]:
            if a["owner"] == b["owner"] or not _overlaps(str(a["path"]), str(b["path"])):
                continue
            key = tuple(sorted((f"{a['owner']}:{a['path']}", f"{b['owner']}:{b['path']}")))
            if key in seen:
                continue
            seen.add(key)
            contention.append({"paths": sorted({str(a["path"]), str(b["path"])}), "owners": sorted({str(a["owner"]), str(b["owner"])})})
    for c in claims:
        c["contended"] = any(c["owner"] in x["owners"] and c["path"] in x["paths"] for x in contention)
    claims.sort(key=lambda c: (c["stale"], not c["contended"], str(c["path"])))

    drops = []
    for d in coord_json(root, agent_do, "drops", key="drops"):
        drops.append(
            {
                "for": d.get("for"),
                "path": d.get("path") or d.get("paths"),
                "note": d.get("note"),
                "owner": d.get("owner_label") or d.get("owner"),
                "key": d.get("key"),
                "created_at": d.get("created_at"),
            }
        )
    drops.sort(key=lambda d: d.get("created_at") or "", reverse=True)
    needs = [{"key": n.get("key"), "why": n.get("why"), "owner": n.get("owner") or n.get("owner_label")} for n in coord_json(root, agent_do, "need", "list", "--all", key="needs")]
    return {"claims": claims, "contention": contention, "drops": drops, "needs": needs}


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


def is_decision(issue: dict[str, Any], markers: tuple[str, ...] = DECISION_MARKERS) -> bool:
    """A marker counts only when it leads the title; a mention mid-sentence is prose."""
    match = _LEADING_TAGS.match(str(issue.get("title", "")))
    if not match:
        return False
    tags = {tag.upper() for tag in re.findall(r"\[[^\]]*\]", match.group(1))}
    return any(marker.upper() in tags for marker in markers)


def strip_markers(title: str) -> str:
    return re.sub(r"^(\s*\[[^\]]*\]\s*)+", "", title).strip() or title


def derive(
    root: Path,
    agent_do: Path | None = None,
    markers: tuple[str, ...] = DECISION_MARKERS,
    live: bool = False,
    *,
    peers: list[dict[str, Any]] | None = None,
    coord: dict[str, Any] | None = None,
    drift_live: dict[str, Any] | None = None,
    trailers: dict[str, list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    """Build the whole page model for one board root.

    `live` runs reconcile for current drift (the daemon does; tests and quick
    summaries do not). Either way the file's findings and age are reported,
    so the page can say how stale the last written reconcile is. The daemon
    passes precomputed pieces so the expensive ones (reconcile, git log,
    coord) are cached on their own clocks."""
    board_dir = root / ".manna"
    issues = read_issues(board_dir)
    order = read_order(board_dir)
    drift_file = read_drift(board_dir)
    if drift_live is None and live:
        drift_live = live_drift(root, agent_do)
    if drift_live:
        drift = {**drift_live, "source": "reconcile", "present": True, "file": {"present": drift_file["present"], "generated_at": drift_file["generated_at"], "count": drift_file["count"]}}
    else:
        drift = {**drift_file, "source": "file", "file": {"present": drift_file["present"], "generated_at": drift_file["generated_at"], "count": drift_file["count"]}}
    workflow = read_yaml(board_dir / "workflow.yaml")
    board_meta = read_yaml(board_dir / "board.yaml")
    federation = read_federation(board_dir)
    git = git_summary(root)
    if trailers is None:
        trailers = git_trailers(root) if git["is_repo"] else {}
    if peers is None:
        peers = coord_peers(root, agent_do) if git["is_repo"] else []
    if coord is None:
        coord = coord_snapshot(root, agent_do, peers) if peers else EMPTY_COORD

    by_id = {i["id"]: i for i in issues}
    order_index = {issue_id: n for n, issue_id in enumerate(order)}
    tracks = {i["id"]: i for i in issues if i.get("type") == "track"}
    relations_by_source: dict[str, list[dict[str, Any]]] = {}
    for relation in federation.get("relations") or []:
        relations_by_source.setdefault(relation["from"], []).append(relation)

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
            "handoff_exists": (root / str(issue["prompt"])).is_file() if issue.get("prompt") else None,
            "blockers": blockers,
            "dependents": [],
            "decision": is_decision(issue, markers) and status != "done",
            "claimant": (
                {
                    "label": issue.get("claimed_by"),
                    "liveness": peer.get("status") if peer else "unseen",
                    "age": peer.get("age") if peer else None,
                    "runtime": peer.get("runtime") if peer else None,
                    "goal": peer.get("goal") if peer else None,
                    "pulse": peer.get("pulse") if peer else None,
                    "attention": peer.get("attention") if peer else "unseen",
                }
                if issue.get("claimed_by")
                else None
            ),
            "commits": trailers.get(issue["id"], []),
            "relations": [dict(relation) for relation in relations_by_source.get(issue["id"], [])],
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
    for peer in peers:
        peer["holding"] = [
            {"id": r["id"], "title": r["title"]}
            for r in rows
            if r.get("claimed_by") and r.get("status") == "in_progress" and match_peer(r["claimed_by"], [peer]) is peer
        ]

    def order_key(row: dict[str, Any]) -> tuple:
        pos = row["order"]
        return (pos is None, pos if pos is not None else 0, row.get("updated_at") or "", row["id"])

    def now_key(row: dict[str, Any]) -> tuple:
        claimant = row.get("claimant") or {}
        rank = claimant.get("attention") or "unseen"
        pos = ATTENTION_ORDER.index(rank) if rank in ATTENTION_ORDER else len(ATTENTION_ORDER)
        return (pos, *order_key(row))

    now_rows = sorted((r for r in rows if r["effective"] == "active"), key=now_key)
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
            "board_id": federation.get("board_id"),
            "decision_markers": list(markers),
        "handoff_dir": handoff_dir,
            "issues_modified_at": mtime_iso(board_dir / "issues.jsonl"),
            "order_count": len(order),
        },
        "git": git,
        "peers": sorted(peers, key=attention_key),
        "attention": {rank: sum(1 for p in peers if p.get("attention") == rank) for rank in ATTENTION_ORDER},
        "coord": coord,
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
        "federation": federation,
        "all": sorted(rows, key=order_key),
    }


# ---------------------------------------------------------------- signature


def signature_paths(root: Path, gitdir: Path | None, include_coord: bool = True) -> list[Path]:
    board_dir = root / ".manna"
    paths = [
        board_dir / "issues.jsonl",
        board_dir / "handoff-order.yaml",
        board_dir / "drift.yaml",
        board_dir / "board.yaml",
        board_dir / "workflow.yaml",
        board_dir / "federation.yaml",
    ]
    if gitdir:
        paths.extend([gitdir / "HEAD", gitdir / "index", gitdir / "logs" / "HEAD"])
        if include_coord:
            coord_root = gitdir / "agent-do" / "coord"
            paths.extend(coord_root / name for name in COORD_SIGNATURE_FILES)
    return paths


def base_signature(root: Path, gitdir: Path | None) -> str:
    """Board + git only. Presence files are excluded on purpose: every tool
    call by any agent in the repo touches them, so a signature that included
    them would never settle. Presence is read on its own cadence."""
    return signature(root, gitdir, include_coord=False)


def coord_signature(root: Path, gitdir: Path | None) -> str:
    """Only the coord presence files: what the estate glance depends on."""
    if not gitdir:
        return "no-git"
    parts = []
    for name in COORD_SIGNATURE_FILES:
        path = gitdir / "agent-do" / "coord" / name
        try:
            st = path.stat()
            parts.append(f"{name}:{st.st_mtime_ns}:{st.st_size}")
        except OSError:
            parts.append(f"{name}:missing")
    return "|".join(parts)


def glance(root: Path, agent_do: Path | None) -> dict[str, Any]:
    """Attention counts for one board's coord presence: the index-row view."""
    return glance_from_peers(coord_peers(root, agent_do))


def glance_from_peers(peers: list[dict[str, Any]]) -> dict[str, Any]:
    counts = {rank: sum(1 for p in peers if p.get("attention") == rank) for rank in ATTENTION_ORDER}
    return {
        "attention": counts,
        "needs_you": counts["needs-user"] + counts["failed"],
        "working": counts["working"],
        "here": sum(v for k, v in counts.items() if k != "gone"),
        "gone": counts["gone"],
    }


def signature(root: Path, gitdir: Path | None, include_coord: bool = True) -> str:
    parts = []
    for path in signature_paths(root, gitdir, include_coord):
        try:
            st = path.stat()
            parts.append(f"{path}:{st.st_mtime_ns}:{st.st_size}")
        except OSError:
            parts.append(f"{path}:missing")
    return "|".join(parts)


def summary(root: Path, markers: tuple[str, ...] = DECISION_MARKERS) -> dict[str, Any]:
    """Cheap index-row view of a board: counts and freshness, no git walk."""
    board_dir = root / ".manna"
    issues = read_issues(board_dir)
    # Effective rules, the same ones the board page renders with (the blocker
    # graph outranks the status field), so an estate number always matches
    # the section a click on it opens.
    by_id = {i["id"]: i for i in issues}
    status_counts: dict[str, int] = {}
    dreams = 0
    decisions = 0
    for issue in issues:
        if issue.get("type") == "track":
            continue
        if issue.get("type") == "dream":
            if issue.get("status") != "done":
                dreams += 1
            continue
        s = issue.get("status", "open")
        blocked = any((by_id.get(dep) or {}).get("status") != "done" for dep in issue.get("blocked_by") or [])
        decision = is_decision(issue, markers) and s != "done"
        if s == "done":
            key = "done"
        elif s == "in_progress":
            key = "active"
        elif blocked:
            key = "blocked"
        elif decision:
            key = "decision"
        else:
            key = "ready"
        status_counts[key] = status_counts.get(key, 0) + 1
        if decision:
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
