#!/usr/bin/env python3
"""Codex SessionStart hook: inject compact agent-do project context."""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
from pathlib import Path

ZPC_INJECT_TIMEOUT = 3
ZPC_INJECT_MAX_CHARS = 6000
ZPC_INJECT_TRUNCATION_MARKER = "[zpc inject truncated]"
ZPC_AUTOINIT_TIMEOUT = 3
# The --preferences slice bounds its own output; this is the belt to that pair
# of braces.
ZPC_PREFERENCES_MAX_CHARS = 2000
ZPC_PREFERENCES_TRUNCATION_MARKER = "[zpc preferences truncated]"


def read_payload() -> dict:
    try:
        return json.load(sys.stdin)
    except Exception:
        return {}


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


def run_json(cmd: list[str], cwd: str | None = None) -> dict:
    try:
        proc = subprocess.run(
            cmd,
            cwd=cwd,
            text=True,
            capture_output=True,
            timeout=4,
            check=False,
        )
    except Exception:
        return {}
    if proc.returncode != 0 or not proc.stdout.strip():
        return {}
    try:
        return json.loads(proc.stdout)
    except Exception:
        return {}


def run_capture(cmd: list[str], cwd: str | None = None, timeout: int = 10) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(
            cmd,
            cwd=cwd,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except Exception:
        return (1, "", "")
    return (proc.returncode, proc.stdout, proc.stderr)


def native_bootstrap(agent_do: str, cwd: str | None, ask: str, root: str) -> bool:
    mode = os.environ.get("AGENT_DO_BOOTSTRAP_PROMPT_MODE", "").strip().lower()
    if not mode:
        mode = "native" if sys.platform == "darwin" and shutil.which("osascript") else "context"

    if mode == "disabled":
        return True
    if mode != "native":
        return False

    auto_response = os.environ.get("AGENT_DO_BOOTSTRAP_AUTO_RESPONSE", "").strip().lower()
    if auto_response == "bootstrap":
        response = "Bootstrap"
    elif auto_response == "not_now":
        response = "Not now"
    else:
        if not shutil.which("osascript"):
            return False
        code, stdout, _ = run_capture(
            [
                "osascript",
                "-e",
                (
                    f'display dialog {json.dumps(ask)} '
                    'with title "agent-do Bootstrap" '
                    'buttons {"Not now", "Bootstrap"} default button "Bootstrap"\n'
                    "button returned of result"
                ),
            ],
            timeout=15,
        )
        if code != 0:
            return False
        response = stdout.strip()

    if response == "Bootstrap":
        # Capture output to a log; emit a macOS notification with status; on
        # failure also surface a follow-up dialog with the option to view the
        # log. Without this the user clicks Bootstrap and sees nothing.
        log_dir = Path.home() / ".agent-do" / "logs"
        try:
            log_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            log_dir = Path("/tmp")
        timestamp = subprocess.run(
            ["date", "+%Y%m%d-%H%M%S"], capture_output=True, text=True, check=False
        ).stdout.strip() or "now"
        log_file = log_dir / f"bootstrap-{timestamp}-{os.getpid()}.log"
        project_label = Path(root).name or root

        try:
            with log_file.open("w") as fh:
                fh.write(f"agent-do bootstrap --yes\nproject: {root}\nstarted: {timestamp}\n---\n")
                fh.flush()
                completed = subprocess.run(
                    [agent_do, "bootstrap", "--yes"],
                    cwd=root,
                    stdout=fh,
                    stderr=subprocess.STDOUT,
                    timeout=60,
                    check=False,
                )
            run_exit = completed.returncode
        except subprocess.TimeoutExpired:
            run_exit = 124
        except Exception:
            run_exit = 1

        if shutil.which("osascript"):
            if run_exit == 0:
                subprocess.run(
                    [
                        "osascript",
                        "-e",
                        f'display notification "Bootstrap completed for {project_label}. Log: {log_file}" '
                        f'with title "agent-do Bootstrap" sound name "Glass"',
                    ],
                    check=False,
                )
            else:
                subprocess.run(
                    [
                        "osascript",
                        "-e",
                        f'display notification "Bootstrap FAILED for {project_label} (exit {run_exit}). Log: {log_file}" '
                        f'with title "agent-do Bootstrap" sound name "Basso"',
                    ],
                    check=False,
                )
                # Failure dialog with "Open log" option.
                failure_message = (
                    f"agent-do bootstrap failed (exit {run_exit}) for {project_label}."
                    + "\n\n"
                    + f"Log: {log_file}"
                )
                code, choice, _ = run_capture(
                    [
                        "osascript",
                        "-e",
                        (
                            f'display dialog {json.dumps(failure_message)} '
                            'with title "agent-do Bootstrap failed" '
                            'buttons {"Dismiss", "Open log"} default button "Open log"\n'
                            "button returned of result"
                        ),
                    ],
                    timeout=15,
                )
                if code == 0 and choice.strip() == "Open log" and shutil.which("open"):
                    subprocess.run(["open", str(log_file)], check=False)
        else:
            status = "completed" if run_exit == 0 else f"FAILED (exit {run_exit})"
            print(f"[agent-do bootstrap] {status} for {project_label}. Log: {log_file}", file=sys.stderr)
    return True


def is_frontend_project(cwd: str | None) -> bool:
    if not cwd:
        return False
    root = Path(cwd)
    package = root / "package.json"
    frontend_tokens = (
        "react",
        "next",
        "vue",
        "nuxt",
        "svelte",
        "astro",
        "angular",
        "remix",
        "gatsby",
        "solid-js",
    )
    if package.exists():
        text = package.read_text(errors="ignore").lower()
        if any(f'"{token}"' in text for token in frontend_tokens):
            return True
    for rel in ("src", "app", "apps", "components", "pages"):
        directory = root / rel
        if not directory.exists():
            continue
        for ext in ("*.tsx", "*.jsx", "*.vue", "*.svelte", "*.astro"):
            if next(directory.glob(f"**/{ext}"), None):
                return True
    pubspec = root / "pubspec.yaml"
    return pubspec.exists() and "flutter" in pubspec.read_text(errors="ignore").lower()


def project_tools(agent_do: str, cwd: str | None) -> str:
    if not cwd:
        return ""
    data = run_json([agent_do, "suggest", "--project", "--json", "--cwd", cwd, "--limit", "5"])
    results = data.get("results") or []
    if not results:
        return ""
    lines = []
    for item in results[:5]:
        tool = item.get("tool")
        primary = item.get("primary") or f"agent-do {tool} --help"
        if tool:
            lines.append(f"- {tool}: start with `{primary}`")
    if not lines:
        return ""
    signals = ", ".join(data.get("signals") or []) or "general"
    project = data.get("project") or cwd
    return (
        "## Project-Scoped agent-do Tools\n\n"
        f"Project root: `{project}`\n"
        f"Detected signals: `{signals}`\n\n"
        + "\n".join(lines)
        + "\n\nRefresh with `agent-do suggest --project`.\n"
    )


def bootstrap(agent_do: str, cwd: str | None) -> str:
    if not cwd:
        return ""
    data = run_json([agent_do, "bootstrap", "--recommend", "--json", "--cwd", cwd])
    if not data.get("needs_bootstrap"):
        return ""
    ask = data.get("ask_prompt") or "Run agent-do bootstrap for this project?"
    root = data.get("project_root") or cwd
    commands = "\n".join(data.get("commands") or [])
    if native_bootstrap(agent_do, cwd, ask, root):
        return ""
    return (
        "## Bootstrap Opportunity\n\n"
        "At the start of your first reply in this session, ask exactly one short yes/no question:\n"
        f"`{ask}`\n\n"
        "If the user says yes, run `agent-do bootstrap --yes` from:\n"
        f"`{root}`\n\n"
        f"Planned bootstrap:\n```text\n{commands}\n```\n"
    )


def coord(agent_do: str, cwd: str | None) -> str:
    if not cwd:
        return ""
    touch = run_json([agent_do, "coord", "touch", "--json"], cwd=cwd)
    if not touch:
        return ""

    interrupts = run_json(
        [agent_do, "coord", "interrupts", "--json", "--mark-seen", "--limit", "5"],
        cwd=cwd,
    ).get("interrupts") or []
    if interrupts:
        lines = [
            f"- {'[new] ' if item.get('new') else ''}{item.get('kind')}: {item.get('summary')}"
            for item in interrupts
        ]
        return (
            "## Coord Interrupts\n\n"
            "Relevant coordination interrupts are active in this repo:\n"
            + "\n".join(lines)
            + "\n\nUse `agent-do coord status`, `agent-do coord interrupts`, or `agent-do coord focus show`.\n"
        )

    active = touch.get("active_peers") or []
    focus_goal = ((touch.get("focus") or {}).get("goal")) or ""
    if active and not focus_goal:
        lines = []
        for peer in active:
            label = peer.get("alias") or peer.get("agent_id")
            goal = ((peer.get("focus") or {}).get("goal")) or ""
            lines.append(f"- {label}{f' goal: {goal}' if goal else ''}")
        return (
            "## Coord Focus Reminder\n\n"
            "Other active peers exist in this repo, and you have not declared focus yet.\n"
            + "\n".join(lines)
            + "\n\nSet focus before overlapping work starts:\n"
            "`agent-do coord focus set \"<goal>\" --path <path> [--path <path> ...]`\n"
        )
    return ""


def zpc_store_root(cwd: str) -> Path | None:
    """Where zpc would resolve a store from here.

    The same upward walk resolve_zpc_dir does (tools/agent-zpc/lib/common.sh),
    stopping short of /, so the hook's answer and the tool's answer are the same
    answer. Without this a session opened in a subdirectory reads as storeless
    while its project's memory sits two levels up.
    """
    probe = Path(cwd)
    while str(probe) != "/" and probe.parent != probe:
        if (probe / ".zpc").is_dir():
            return probe
        probe = probe.parent
    return None


def zpc_has_records(cwd: str) -> bool:
    """At least one recorded line under .zpc/memory/. An initialized-but-empty
    store has nothing worth embedding, so it keeps the advisory."""
    for path in (Path(cwd) / ".zpc" / "memory").glob("*.jsonl"):
        try:
            with path.open(encoding="utf-8", errors="replace") as handle:
                for line in handle:
                    if line.strip():
                        return True
        except OSError:
            continue
    return False


def zpc_autoinit(agent_do: str | None, cwd: str | None) -> None:
    """Give every project a store, without the hook ever writing a tracked file.

    Two limits make that true. A git worktree is the unit of "project", so a
    bare directory never gets one. And `zpc init` does more than create the
    store: it appends to .gitignore and writes (or appends to) the repo's agent
    instruction file, which is not something a silent session-start hook may do
    to a repo it does not own. So auto-init rides a store-only mode and stays
    home without it.
    """
    if os.environ.get("AGENT_DO_ZPC_AUTOINIT", "1") == "0":
        return
    if not agent_do or not cwd:
        return

    code, toplevel, _ = run_capture(
        ["git", "rev-parse", "--show-toplevel"], cwd=cwd, timeout=ZPC_AUTOINIT_TIMEOUT
    )
    toplevel = toplevel.strip()
    if code != 0 or not toplevel:
        return
    root = Path(toplevel)
    if not root.is_dir():
        return

    # zpc resolves a store by walking up from cwd, so a store anywhere between
    # cwd and the toplevel means this project already has one.
    probe = Path(cwd)
    while True:
        if (probe / ".zpc").exists():
            return
        if probe == root or probe.parent == probe:
            break
        probe = probe.parent
    if (root / ".zpc").exists():
        return

    # init's argument loop swallows flags it does not know, so asking an older
    # zpc for --store-only gets a full invasive init that reports success. The
    # gate has to be positive: no such flag in the help text, no auto-init.
    code, help_text, _ = run_capture(
        [agent_do, "zpc", "init", "--help"], cwd=str(root), timeout=ZPC_AUTOINIT_TIMEOUT
    )
    if code != 0 or "--store-only" not in help_text:
        return

    run_capture(
        [agent_do, "zpc", "init", "--store-only"],
        cwd=str(root),
        timeout=ZPC_AUTOINIT_TIMEOUT,
    )


def run_zpc_inject(agent_do: str, cwd: str, preferences: bool = False) -> str:
    """Inject stdout, or "" on any failure.

    Output lands in a temp file rather than a pipe: inject detaches a harvest,
    and any background writer holding the read end open would outlast the
    timeout that exists to bound this call. start_new_session isolates the
    process group so a timeout kill takes the whole spawn without reaching the
    deliberately detached harvest, which carries its own group.
    """
    # AGENT_DO_ZPC_SOURCE tags the access log; the copy keeps it out of the
    # rest of the hook's environment.
    env = dict(os.environ)
    env["AGENT_DO_ZPC_SOURCE"] = "hook"
    try:
        with tempfile.TemporaryFile("w+", encoding="utf-8", errors="replace") as out:
            # cwd must be inside the project: inject resolves the store from there.
            proc = subprocess.Popen(
                [agent_do, "zpc", "inject"] + (["--preferences"] if preferences else []),
                cwd=cwd,
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=out,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            try:
                code = proc.wait(timeout=ZPC_INJECT_TIMEOUT)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                except OSError:
                    proc.kill()
                proc.wait()
                return ""
            if code != 0:
                return ""
            out.seek(0)
            return out.read()
    except Exception:
        return ""


def bound_zpc_inject(
    text: str,
    limit: int = ZPC_INJECT_MAX_CHARS,
    marker: str = ZPC_INJECT_TRUNCATION_MARKER,
) -> str:
    if len(text) <= limit:
        return text
    clipped = text[:limit]
    head, newline, _ = clipped.rpartition("\n")
    if newline:
        clipped = head
    return f"{clipped}\n{marker}"


def zpc_preferences_section(agent_do: str | None, cwd: str) -> str:
    """Preferences are the user's, not the project's, so they travel: an empty
    store and a directory that will never have one both get them. Returns ""
    unless there is real content, which keeps every caller's fallback intact."""
    if not agent_do:
        return ""
    preferences = run_zpc_inject(agent_do, cwd, preferences=True).rstrip("\n")
    if not preferences.strip():
        return ""
    bounded = bound_zpc_inject(
        preferences, ZPC_PREFERENCES_MAX_CHARS, ZPC_PREFERENCES_TRUNCATION_MARKER
    )
    return (
        "## ZPC Preferences (global memory)\n\n"
        "Preferences recorded across earlier sessions, loaded below. They are "
        "user-level, not project-level: they hold here regardless of what this "
        "directory contains.\n\n"
        f"{bounded}\n\n"
        "Log new ones where they happen: `agent-do zpc learn` and "
        "`agent-do zpc decide`.\n"
    )


def zpc(agent_do: str | None, cwd: str | None) -> str:
    if not cwd:
        return ""

    embedding = bool(agent_do) and os.environ.get("AGENT_DO_ZPC_INJECT", "1") != "0"

    # No store anywhere up the tree, and none coming: auto-init already declined
    # this directory (not a git worktree, or it has no store-only mode to use).
    # Preferences are still his, so they still arrive.
    store_root = zpc_store_root(cwd)
    if store_root is None:
        return zpc_preferences_section(agent_do, cwd) if embedding else ""
    root = str(store_root)

    # The advisory below only *asks* the agent to go read the store, and asking
    # is not a mechanism. When there are records to show, put the memory itself
    # in context. Every failure mode (kill-switch, empty store, missing
    # dispatcher, nonzero exit, timeout) falls through to the advisory, so the
    # section degrades instead of disappearing.
    if embedding:
        if zpc_has_records(root):
            # Run from the store's own root, which is cwd for a session opened
            # at the top and the walked-up answer otherwise.
            memory = run_zpc_inject(agent_do, root).rstrip("\n")
            if memory.strip():
                return (
                    "## ZPC Project Memory\n\n"
                    "This project's recorded memory, loaded below. Read it before coding; "
                    "it is already in context, so do not re-run `agent-do zpc inject`.\n\n"
                    f"{bound_zpc_inject(memory)}\n\n"
                    "Keep the loop closed: `agent-do zpc learn` and `agent-do zpc decide` as "
                    "you work, `agent-do zpc harvest` after significant work.\n"
                )
        else:
            # A store with nothing in it yet — every project's first session,
            # now that init runs automatically. Preferences beat an advisory
            # nobody reads.
            section = zpc_preferences_section(agent_do, root)
            if section:
                return section

    return (
        "## ZPC Memory Available\n\n"
        "This project has `.zpc/` memory. Start with `agent-do zpc status` and "
        "`agent-do zpc patterns` before coding.\n"
    )


def frontend_context(cwd: str | None) -> str:
    if not is_frontend_project(cwd):
        return ""
    return (
        "## Frontend Project Detected\n\n"
        "For visual/UI work, use screenshots as visual truth and `agent-do dpt` for scoring:\n"
        "- `agent-do browse open <dev-url>`\n"
        "- `agent-do browse screenshot /tmp/before.png`\n"
        "- after edits: `agent-do browse reload && agent-do browse screenshot /tmp/after.png`\n"
        "- `agent-do dpt score /tmp/after.png`\n\n"
        "Use Codex UI skills when applicable, especially `building-ui` and `layout-rhythm-repair`.\n"
    )


def main() -> None:
    payload = read_payload()
    cwd = payload.get("cwd") or os.getcwd()
    agent_do = resolve_agent_do()

    # Auto-init first: the memory section below reads the store this may have
    # just created.
    zpc_autoinit(agent_do, cwd)

    sections = [
        "## TOOLING REMINDER - agent-do\n\n"
        "Before writing raw automation or vendor API glue, check whether `agent-do` already has the path:\n"
        "`agent-do suggest \"task\"`, `agent-do suggest --project`, `agent-do find <keyword>`, "
        "`agent-do --list`, `agent-do <tool> --help`.\n"
    ]

    if agent_do:
        sections.extend(
            part
            for part in (
                project_tools(agent_do, cwd),
                bootstrap(agent_do, cwd),
                coord(agent_do, cwd),
            )
            if part
        )
    sections.extend(part for part in (frontend_context(cwd), zpc(agent_do, cwd)) if part)

    context = "\n---\n\n".join(sections)
    json.dump(
        {
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": context,
            }
        },
        sys.stdout,
    )


if __name__ == "__main__":
    main()
