#!/usr/bin/env python3
"""Codex Stop hook quality reporter for UI and literary work.

This hook is advisory-only. It must not block Stop; normal workflow hooks should
surface missing verification without trapping the agent or skipping auto-commit.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
from pathlib import Path


_REPO_LIB = Path(__file__).resolve().parents[2] / "lib"
if str(_REPO_LIB) not in sys.path:
    sys.path.insert(0, str(_REPO_LIB))
import touch_ledger  # type: ignore  # noqa: E402  (repo lib, resolved relative to this file)

# The runtime whose registration decides whether the touch ledger is
# authoritative. This file lives under hooks/codex/; a wrapper may override.
RUNTIME = os.environ.get("AGENT_DO_HOOK_RUNTIME", "codex")

UI_EXTENSIONS = {".tsx", ".jsx", ".html", ".htm", ".vue", ".svelte", ".astro", ".css", ".scss", ".less"}

# Design-system filename hints for files that DON'T have a UI extension (e.g.
# theme.ts, tokens.ts, styles.ts in a styled-components or vanilla-extract
# codebase). Hints must be specific to design files; generic words ("global",
# "config") cause false positives on test files, build scripts, etc.
#
# Match shape: the file's basename must equal one of these (with any extension)
# OR start with one followed by "." or "-". Substring match was too permissive
# (test_global_hooks.py matched on "global" — wrong category entirely).
UI_NAME_HINT_BASENAMES = {"theme", "tokens", "design-tokens", "design-system"}

# Skip patterns that look design-adjacent but aren't:
# - JS/TS test conventions (foo.test.tsx, foo.spec.js)
# - Python test conventions (test_foo.py, foo_test.py)  ← added; was missing
# - Build/tooling configs (tailwind.config.ts, vite.config.ts, postcss.config.js)
# - TypeScript declaration files (foo.d.ts)
UI_SKIP_RE = re.compile(
    r"(\.test\.|\.spec\.|^test_|_test\.py$|\.config\.|tailwind\.|postcss\.|vite\.|\.d\.ts$)",
    re.I,
)

# HTML files that are PLUMBING, not user-visible UI. Browser extensions have a
# pile of host pages (chrome.offscreen, service-worker hosts, message-relay
# iframes) that satisfy the .html extension but contain no visual surface to
# evaluate. Same for popup/sidepanel host shells that exist purely so the
# extension API has a frame to attach to.
NON_UI_HTML_BASENAMES = {
    "offscreen.html",       # chrome.offscreen.createDocument host
    "background.html",      # MV2 background page
    "service-worker.html",  # MV3 SW host
    "sw.html",
    "worker.html",
    "iframe.html",          # message-relay iframes
    "inject.html",          # content-script bootstrap
    "sandbox.html",         # extension sandbox frame
    "capture.html",         # tabCapture/displayMedia capture host (common name)
    "relay.html",
}

# Whole-directory exclusions: paths inside browser extensions or other
# non-visual artefact trees. We're not running design checks on
# `*-extension/`, `chrome-extension/`, `firefox-extension/`, etc.
NON_UI_DIR_RE = re.compile(
    r"(?:^|/)(?:[a-z0-9_-]+-extension|chrome-extension|firefox-extension|"
    r"webextension|web-ext|browser-extension|extension)/",
    re.I,
)

# Document/source/data trees: an .html file here is an archived source text,
# a work-order attachment, a generated deliverable, or test data — not an app
# surface anyone can `browse open`. These are this workspace's own conventions
# (.handoff/ = the single work-order root, .dev/ = generated deliverables) plus
# the universal docs/ and fixtures/ roots. Advisory advice ("open the app")
# is unfollowable for these files, which is the tell that they never belonged
# in the UI category.
NON_UI_DOC_DIR_RE = re.compile(
    r"(?:^|/)(?:\.handoff|\.dev|docs|fixtures)/",
    re.I,
)

WRITING_DIR_HINTS = ("/the_book/", "/novel/", "/manuscript/", "/chapters/", "/writing/")
WRITING_EXTENSIONS = {".md", ".markdown", ".txt"}
WRITING_SKIP_RE = re.compile(r"(BRIEF|REPORT|README|OUTLINE)", re.I)


def load_payload() -> dict:
    try:
        return json.load(sys.stdin)
    except Exception:
        return {}


def run(cmd: list[str], cwd: str | None = None, timeout: int = 5) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=cwd,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )


def git_root(cwd: str) -> str | None:
    proc = run(["git", "-C", cwd, "rev-parse", "--show-toplevel"], cwd=cwd)
    if proc.returncode != 0:
        return None
    return proc.stdout.strip() or None


def git_changed_files(repo: str) -> list[str]:
    files: set[str] = set()
    commands = [
        ["git", "-C", repo, "diff", "--name-only"],
        ["git", "-C", repo, "diff", "--cached", "--name-only"],
        ["git", "-C", repo, "ls-files", "--others", "--exclude-standard"],
    ]
    for cmd in commands:
        proc = run(cmd, cwd=repo)
        if proc.returncode != 0:
            continue
        for line in proc.stdout.splitlines():
            line = line.strip()
            if line:
                files.add(line)
    return sorted(files)


def ledger_registered() -> bool:
    return touch_ledger.hook_registered(RUNTIME)


def changed_files_for_gate(repo: str, payload: dict) -> tuple[list[str], str]:
    """The files this gate may attribute to the agent, and the evidence kind.

    'ledger'   — the touch-ledger hook is registered, so the agent's own edit
                 tools wrote every entry; the ledger is consumed here so the
                 next Stop only sees what was touched after this one. An empty
                 result means: this agent edited nothing this turn.
    'worktree' — no ledger hook is registered; git drift is the only evidence
                 left, and it cannot tell this agent's edits from another
                 lane's, a dropped-in document, or pre-existing untracked files.
                 The advisory says so.
    """
    if ledger_registered():
        key, _ = touch_ledger.session_key(payload)
        repo_root = Path(repo).resolve()
        rels: set[str] = set()
        for entry in touch_ledger.read_and_consume(key):
            raw = entry.get("path")
            if not raw:
                continue
            try:
                rels.add(str(Path(raw).resolve().relative_to(repo_root)))
            except ValueError:
                continue
        return sorted(rels), "ledger"
    return git_changed_files(repo), "worktree"


def ui_files(files: list[str]) -> list[str]:
    matches = []
    for rel in files:
        path = rel.lower()
        name = Path(path).name
        ext = Path(path).suffix.lower()
        stem = Path(path).stem  # name without extension
        if UI_SKIP_RE.search(name):
            continue
        # Skip browser-extension trees outright — no visual surface to evaluate.
        if NON_UI_DIR_RE.search(path):
            continue
        # Skip document/source/data trees — archived texts and fixtures, not UI.
        if NON_UI_DOC_DIR_RE.search(path):
            continue
        # Skip known plumbing HTML basenames (offscreen.html, background.html,
        # etc.) even when they live outside an extension directory.
        if ext in {".html", ".htm"} and name in NON_UI_HTML_BASENAMES:
            continue
        # Direct UI extension is a positive match.
        if ext in UI_EXTENSIONS:
            matches.append(rel)
            continue
        # Otherwise the file's STEM (or its first dotted/dashed segment) must
        # exactly match a design-system filename hint. Substring matching was
        # too permissive (caught test_global_*, global_config.py, etc.).
        stem_head = re.split(r"[.\-]", stem, maxsplit=1)[0]
        if stem in UI_NAME_HINT_BASENAMES or stem_head in UI_NAME_HINT_BASENAMES:
            matches.append(rel)
    return matches


def writing_files(files: list[str]) -> list[str]:
    matches = []
    for rel in files:
        lowered = rel.lower()
        name = Path(rel).name
        ext = Path(rel).suffix.lower()
        if not any(hint in lowered for hint in WRITING_DIR_HINTS):
            continue
        if ext not in WRITING_EXTENSIONS:
            continue
        if WRITING_SKIP_RE.search(name) or name.endswith((".py", ".json")):
            continue
        matches.append(rel)
    return matches


def resolve_agent_do() -> str | None:
    direct = shutil.which("agent-do")
    if direct:
        return direct
    local = Path.home() / ".local" / "bin" / "agent-do"
    if local.exists():
        return str(local)
    breadcrumb = Path.home() / ".agent-do" / "install-path"
    if breadcrumb.exists():
        candidate = Path(breadcrumb.read_text().strip()) / "agent-do"
        if candidate.exists():
            return str(candidate)
    return None


def derive_browse_session() -> str:
    explicit = os.environ.get("AGENT_BROWSER_SESSION")
    if explicit:
        return explicit

    def compact(value: str) -> str:
        return re.sub(r"[^a-zA-Z0-9]+", "", value).lower()[:16]

    def sanitize(value: str) -> str:
        return re.sub(r"[^a-zA-Z0-9._-]+", "-", value).strip("-_.").lower()[:24]

    for prefix, env_name in (
        ("codex", "CODEX_THREAD_ID"),
        ("claude", "CLAUDE_THREAD_ID"),
        ("claude", "CLAUDE_SESSION_ID"),
        ("claude", "CLAUDE_AGENT_ID"),
    ):
        value = os.environ.get(env_name)
        if value:
            short = compact(value)
            if short:
                return f"{prefix}-{short}"

    tmux_pane = os.environ.get("TMUX_PANE")
    if tmux_pane:
        short = sanitize(tmux_pane).lstrip("%")
        if short:
            return f"tmux-{short}"
    return "default"


def current_browse_socket() -> Path | None:
    session = derive_browse_session()
    tempdir = Path(tempfile.gettempdir())
    candidate = tempdir / f"agent-browser-{session}.sock"
    if candidate.exists():
        return candidate
    return None


def resolve_dpt_engine(agent_do: str | None) -> Path | None:
    candidates: list[Path] = []
    if agent_do:
        root = Path(agent_do).resolve().parent
        candidates.append(root / "tools" / "agent-dpt" / "dist" / "dpt-engine.js")
    candidates.append(Path.home() / "Documents" / "AI" / "Custom_Coding" / "agent-do" / "tools" / "agent-dpt" / "dist" / "dpt-engine.js")
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def dpt_score_for_current_session(agent_do: str | None) -> dict | None:
    sock_path = current_browse_socket()
    if not sock_path or not sock_path.exists():
        return None
    engine = resolve_dpt_engine(agent_do)
    if not engine:
        return {"error": "engine_missing"}

    try:
        script = engine.read_text()
        message = json.dumps({"id": "codex-stop-gate", "action": "evaluate", "script": script}).encode("utf-8") + b"\n"
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(45)
        sock.connect(str(sock_path))
        sock.sendall(message)
        chunks: list[bytes] = []
        while True:
            try:
                chunk = sock.recv(131072)
                if not chunk:
                    break
                chunks.append(chunk)
                try:
                    json.loads(b"".join(chunks))
                    break
                except json.JSONDecodeError:
                    continue
            except socket.timeout:
                break
        sock.close()
        payload = json.loads(b"".join(chunks).decode("utf-8", errors="replace"))
        if not payload.get("success"):
            return {"error": "dpt_failed"}
        result = payload.get("data", {}).get("result", {})
        if isinstance(result, str):
            result = json.loads(result)
        syn = result.get("synthesis", {})
        dims = syn.get("dimensions", {})
        return {
            "score": syn.get("overall_score"),
            "grade": syn.get("overall_grade"),
            "critical": syn.get("critical_failures") or [],
            "url": result.get("meta", {}).get("url"),
            "dims": {
                "chromatic": dims.get("chromatic", {}).get("score"),
                "typography": dims.get("typography", {}).get("score"),
                "spatial": dims.get("spatial", {}).get("score"),
                "attention": dims.get("attention", {}).get("score"),
                "coherence": dims.get("coherence", {}).get("score"),
            },
        }
    except Exception:
        return {"error": "dpt_failed"}


def summarize_paths(paths: list[str], limit: int = 4) -> str:
    if not paths:
        return ""
    sample = paths[:limit]
    summary = ", ".join(sample)
    if len(paths) > limit:
        summary += ", ..."
    return summary


def build_response(payload: dict) -> dict:
    cwd = payload.get("cwd") or os.getcwd()
    repo = git_root(cwd)
    if not repo:
        return {"continue": True}

    files, evidence = changed_files_for_gate(repo, payload)
    ui = ui_files(files)
    writing = writing_files(files)
    stop_hook_active = bool(payload.get("stop_hook_active"))
    agent_do = resolve_agent_do()

    advisory_reasons: list[str] = []
    system_messages: list[str] = []

    # Worktree drift is weak evidence and the advisory must say so — it is the
    # reading a gate falls back to only when nobody is writing ledgers.
    drift_note = (
        " (Evidence: worktree drift, because the agent-do touch-ledger hook is not registered for this runtime — "
        "these files may not be this agent's edits; `install.sh --register-hooks` makes attribution exact.)"
        if evidence == "worktree" else ""
    )

    if ui:
        dpt = dpt_score_for_current_session(agent_do)
        if not stop_hook_active:
            if dpt is None:
                advisory_reasons.append(
                    "This agent edited UI files this turn (`%s`) without an active browser session. "
                    "Needed next if this was UI work: open the app with `agent-do browse open <dev-url>`, visually verify the page, and run `agent-do dpt score`.%s"
                    % (summarize_paths(ui), drift_note)
                )
            elif dpt.get("error") == "engine_missing":
                advisory_reasons.append(
                    "UI files changed (`%s`) but the DPT engine is unavailable. Needed next if this was UI work: run `agent-do dpt build` once, then verify the page."
                    % summarize_paths(ui)
                )
            elif dpt.get("error") == "dpt_failed":
                advisory_reasons.append(
                    "UI files changed (`%s`) and the DPT scan failed for the current browser session. Needed next if this was UI work: run `agent-do dpt score` manually and make one more pass."
                    % summarize_paths(ui)
                )
            else:
                score = dpt.get("score")
                grade = dpt.get("grade")
                critical = dpt.get("critical") or []
                dims = dpt.get("dims") or {}
                dim_bits = " ".join(
                    f"{name[:3]}{value}"
                    for name, value in dims.items()
                    if value is not None
                )
                score_line = f"DPT {score} {grade}" if score is not None else "DPT completed"
                if dim_bits:
                    score_line += f" ({dim_bits})"
                system_messages.append(
                    f"UI files changed: {summarize_paths(ui)}. {score_line}."
                )
                if critical or (isinstance(score, int) and score < 80):
                    critical_text = f" Critical failures: {'; '.join(critical)}." if critical else ""
                    advisory_reasons.append(
                        f"UI files changed (`{summarize_paths(ui)}`). {score_line}.{critical_text} "
                        "Recommended next if this was UI work: do one more visual polish/verification pass."
                    )

    if writing and not stop_hook_active:
        advisory_reasons.append(
            "Literary prose files changed (`%s`). Recommended next if this was prose work: do one final pass for register, rhythm, filter words, echoes, and pacing."
            % summarize_paths(writing)
        )

    response: dict[str, object] = {"continue": True}
    if advisory_reasons:
        system_messages.append("Quality advisory: " + " ".join(advisory_reasons))
    if system_messages:
        response["systemMessage"] = " ".join(system_messages)
    return response


def main() -> None:
    payload = load_payload()
    json.dump(build_response(payload), sys.stdout)


if __name__ == "__main__":
    main()
