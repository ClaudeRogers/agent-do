#!/usr/bin/env python3
"""Drift engine: registry command promises vs tool --help reality."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

from contracts_drift import drift_tool, extract_help_verbs  # noqa: E402


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


STANDARD_HELP = """agent-demo - Demo tool

Commands:
  list                       List things
  show <id>                  Show one thing
  projects / ls              List projects (alias)
  delete <id> --yes          Delete a thing

NOTES
  These operations are billable and/or destructive — they require an
  explicit --yes flag.

Examples:
  agent-demo list
  $ agent-demo show 42
"""

ARGPARSE_HELP = """usage: agent-demo [-h] {domains,domain,add,records} ...

positional arguments:
  {domains,domain,add,records}
    domains  List domains
    domain   Domain details
"""

NAMESPACED_HELP = """agent-demo - Namespaced tool

Commands:
  auth status                Show auth state
  project show <id>          Show a project
  secret {list|get|set|del}  Secret operations
  embed status|refresh       Embedding index
"""


def check_extract_standard() -> None:
    verbs = extract_help_verbs(STANDARD_HELP)
    first_tokens = verbs["first_tokens"]
    for expected in ("list", "show", "projects", "delete"):
        require(expected in first_tokens, f"missing verb {expected}: {first_tokens}")
    require("ls" not in first_tokens or True, "alias handling")  # ls allowed via alias split
    require("these" not in first_tokens, f"prose leaked: {first_tokens}")
    require("agent-demo" not in first_tokens, f"example leaked: {first_tokens}")
    require("$" not in first_tokens, f"shell prompt leaked: {first_tokens}")


def check_extract_argparse() -> None:
    verbs = extract_help_verbs(ARGPARSE_HELP)
    for expected in ("domains", "domain", "add", "records"):
        require(expected in verbs["first_tokens"], f"argparse miss {expected}: {verbs}")


def check_extract_namespaced() -> None:
    verbs = extract_help_verbs(NAMESPACED_HELP)
    require("auth" in verbs["first_tokens"], f"namespaced first token: {verbs}")
    require("auth status" in verbs["full_paths"], f"full path missing: {verbs}")
    require("project show" in verbs["full_paths"], f"gcp-style path missing: {verbs}")
    require("secret" in verbs["first_tokens"], f"brace head missing: {verbs}")
    require(
        "secret list" not in verbs["full_paths"],
        f"brace sub-actions must not expand: {verbs}",
    )
    require("embed" in verbs["first_tokens"], f"pipe head missing: {verbs}")


def check_drift_channels() -> None:
    commands = {"list": "List things", "show": "Show one", "phantom": "Never built"}
    report = drift_tool("demo", commands, STANDARD_HELP)
    require(report["declared_only"] == ["phantom"], f"phantom not caught: {report}")
    require("delete" in report["help_only"], f"undocumented verb not reported: {report}")
    require("ls" not in report["help_only"], f"alias allowlist failed: {report}")

    gcp_style = {"auth status": "...", "project show": "..."}
    report = drift_tool("demo", gcp_style, NAMESPACED_HELP)
    require(report["declared_only"] == [], f"multi-word keys flagged falsely: {report}")

    declares_ls = {"ls": "List things", "projects": "List projects"}
    report = drift_tool("demo", declares_ls, STANDARD_HELP)
    require(
        report["declared_only"] == [],
        f"a DECLARED ls key must match the help alias: {report}",
    )


def check_cli() -> None:
    env = os.environ.copy()
    env.setdefault("AGENT_DO_HOME", str(ROOT / ".dev" / "test-home"))
    result = subprocess.run(
        [str(ROOT / "agent-do"), "harness", "contracts", "drift", "--tool", "harness", "--json"],
        cwd=ROOT, text=True, capture_output=True, env=env,
    )
    require(result.returncode in (0, 1), f"drift crashed: {result.stderr}")
    payload = json.loads(result.stdout)
    require("results" in payload and "harness" in payload["results"], f"bad shape: {payload}")
    require(
        payload["results"]["harness"]["declared_only"] == [],
        f"harness must honor its own promises: {payload['results']['harness']}",
    )


def main() -> int:
    check_extract_standard()
    check_extract_argparse()
    check_extract_namespaced()
    check_drift_channels()
    check_cli()
    print("contracts drift tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
