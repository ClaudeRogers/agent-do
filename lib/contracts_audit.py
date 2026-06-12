"""Behavioral audit of the declared read surface — bounded, tri-state, safe.

Policy (Erik-approved 2026-06-12): only verbs whose beat-union is a subset
of {snapshot, verify} with NO attributes are invoked, and only when they
need no arguments. Credentialed tools make live network calls when creds
are present, so they sit behind include_network (default off). Outcomes
are tri-state because results are host-dependent:

  ok         — ran clean; if --json was attempted, stdout parsed as JSON
  clean-skip — refused with a structured/explanatory error (no creds, no
               session, no target): the contract held, the host didn't
  fail       — hung (rc 124), crashed, emitted nothing, or lied about --json

The runner is injected (the harness passes agent_do_cmd) so tests stay
hermetic and no tool is ever invoked except through a bounded subprocess.
"""

from __future__ import annotations

import json
import re

from registry import get_tool_contract_attributes, get_tool_contracts

# Verbs whose required argument is stated in prose, with no <placeholder>.
_NEEDS_TARGET = {
    "read", "show", "describe", "inspect", "get", "diff",
    "code", "link", "search", "load", "pr",
}
_HANG_RISK = {"wait", "scan"}
_REQUIRED_ARG = re.compile(r"<[^>]+>")


def _beat_union(info: dict) -> dict:
    union: dict[str, set] = {}
    for beat, verbs in get_tool_contracts(info).items():
        for verb in verbs:
            union.setdefault(verb, set()).add(beat)
    return union


def eligible(tool: str, verb: str, info: dict, include_network: bool = False) -> str:
    """Return 'probe' or 'skip:<reason>' for one declared verb."""
    union = _beat_union(info).get(verb, set())
    if not union or not union <= {"snapshot", "verify"}:
        return "skip:write-surface"
    if get_tool_contract_attributes(info).get(verb):
        return "skip:attributed"
    first = verb.split()[0]
    if first in _HANG_RISK:
        return "skip:hang-risk"
    description = str((info.get("commands") or {}).get(verb, ""))
    bare = re.sub(r"\[[^\]]*\]", "", description)
    if _REQUIRED_ARG.search(bare) or first in _NEEDS_TARGET:
        return "skip:needs-args"
    credentials = info.get("credentials") or {}
    if (credentials.get("required") or credentials.get("one_of")) and not include_network:
        return "skip:network"
    return "probe"


def _structured_error(stdout: str, stderr: str) -> bool:
    text = (stdout + stderr).strip()
    if not text:
        return False
    try:
        json.loads(stdout.strip() or "null")
        return True
    except (ValueError, TypeError):
        pass
    lowered = text.lower()
    return any(marker in lowered for marker in (
        "error", "usage:", "not set", "required", "not initialized",
        "no session", "not found", "not connected", "no responsive",
    ))


def _grade(verb_args: list, bare, jsonful) -> tuple[str, str]:
    if 124 in (bare.returncode, jsonful.returncode if jsonful else 0):
        return "fail", "timeout: verb never returned within the probe bound"
    if bare.returncode == 0:
        if jsonful is not None:
            payload = (jsonful.stdout or "").strip()
            if jsonful.returncode != 0 and not payload:
                return "fail", "--json exited nonzero with empty output"
            try:
                json.loads(payload)
            except (ValueError, TypeError):
                return "fail", "--json emitted non-JSON output"
        if not (bare.stdout or "").strip() and not (bare.stderr or "").strip():
            return "fail", "exited 0 with no output at all"
        return "ok", "ran clean"
    if _structured_error(bare.stdout or "", bare.stderr or ""):
        return "clean-skip", "refused with a structured/explanatory error"
    return "fail", f"exit {bare.returncode} with unexplained output"


def audit_registry(registry: dict, runner, include_network: bool = False,
                   only_tool: str | None = None, timeout: int = 15) -> dict:
    """Audit every declared verb; runner(*args, timeout=) -> CompletedProcess."""
    results = []
    counts = {"ok": 0, "clean-skip": 0, "fail": 0, "skip": 0}
    for name, info in sorted((registry.get("tools") or {}).items()):
        if only_tool and name != only_tool:
            continue
        if not isinstance(info, dict):
            continue
        for verb in sorted(_beat_union(info)):
            action = eligible(name, verb, info, include_network)
            if action != "probe":
                counts["skip"] += 1
                results.append({"tool": name, "verb": verb,
                                "outcome": action, "reason": action})
                continue
            verb_args = verb.split()
            bare = runner(name, *verb_args, timeout=timeout)
            jsonful = runner(name, *verb_args, "--json", timeout=timeout)
            outcome, reason = _grade(verb_args, bare, jsonful)
            counts[outcome] += 1
            results.append({"tool": name, "verb": verb,
                            "outcome": outcome, "reason": reason})
    return {
        "ok": counts["fail"] == 0,
        "summary": counts,
        "include_network": include_network,
        "results": results,
    }


def build_launchd_plist(agent_do_path: str, report_path: str, frequency: str = "weekly") -> str:
    """launchd agent XML for the scheduled audit. Weekly = Monday 09:00."""
    if frequency == "daily":
        interval = "    <key>StartCalendarInterval</key>\n    <dict>\n      <key>Hour</key><integer>9</integer>\n      <key>Minute</key><integer>0</integer>\n    </dict>"
    else:
        interval = "    <key>StartCalendarInterval</key>\n    <dict>\n      <key>Weekday</key><integer>1</integer>\n      <key>Hour</key><integer>9</integer>\n      <key>Minute</key><integer>0</integer>\n    </dict>"
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
  <dict>
    <key>Label</key><string>com.agent-do.contracts-audit</string>
    <key>ProgramArguments</key>
    <array>
      <string>{agent_do_path}</string>
      <string>harness</string>
      <string>contracts</string>
      <string>audit</string>
      <string>--out</string>
      <string>{report_path}</string>
      <string>--notify</string>
    </array>
{interval}
    <key>StandardErrorPath</key><string>/tmp/agent-do-contracts-audit.err</string>
  </dict>
</plist>
"""


def render_report(payload: dict, generated_at: str = "") -> str:
    """Markdown audit report for --out."""
    lines = [
        "# Contracts Behavioral Audit",
        "",
        f"Generated: {generated_at}",
        f"Network probing: {'ON' if payload['include_network'] else 'off'}",
        "",
        "| outcome | count |",
        "|---|---|",
    ]
    for key in ("ok", "clean-skip", "fail", "skip"):
        lines.append(f"| {key} | {payload['summary'][key]} |")
    fails = [r for r in payload["results"] if r["outcome"] == "fail"]
    lines += ["", f"## Failures ({len(fails)})", ""]
    if fails:
        for r in fails:
            lines.append(f"- **{r['tool']} {r['verb']}** — {r['reason']}")
    else:
        lines.append("none — every probed verb honored its contract")
    lines += ["", "## Probed ok", ""]
    lines.append(", ".join(
        f"`{r['tool']} {r['verb']}`" for r in payload["results"] if r["outcome"] == "ok"
    ) or "none")
    return "\n".join(lines) + "\n"
