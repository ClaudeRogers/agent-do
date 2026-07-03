#!/usr/bin/env python3
"""Audit engine: bounded behavioral grading of the declared read surface."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

from contracts_audit import audit_registry, eligible  # noqa: E402


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


REGISTRY = {
    "tools": {
        "demo": {
            "commands": {
                "status": "Show status",
                "list": "List things",
                "show": "Show one thing: show <id>",
                "wait": "Block until ready",
                "set": "Set a value",
                "watch": "Watch forever",
                "secrets": "List secrets",
            },
            "contracts": {
                "snapshot": ["status", "list", "show", "secrets"],
                "verify": ["wait"],
                "interact": ["set"],
                "attributes": {
                    "watch": ["long_running"],
                    "secrets": ["sensitive"],
                },
            },
        },
        "cloudy": {
            "commands": {"projects": "List projects"},
            "contracts": {"snapshot": ["projects"]},
            "credentials": {"required": ["CLOUDY_API_KEY"]},
        },
    }
}


def check_eligibility() -> None:
    tools = REGISTRY["tools"]

    def action(tool, verb):
        info = tools[tool]
        return eligible(tool, verb, info, include_network=False)

    require(action("demo", "status") == "probe", "no-arg snapshot must probe")
    require(action("demo", "set").startswith("skip:write"), "interact verb must skip")
    require(action("demo", "show").startswith("skip:needs-args"),
            "placeholder/denylist verb must skip")
    require(action("demo", "wait").startswith("skip:hang"), "wait must skip as hang risk")
    require(action("demo", "secrets").startswith("skip:attributed"),
            "sensitive verb must skip")
    require(action("cloudy", "projects").startswith("skip:network"),
            "credentialed tool must skip without --include-network")
    info = tools["cloudy"]
    require(eligible("cloudy", "projects", info, include_network=True) == "probe",
            "--include-network unlocks credentialed tools")


class FakeRunner:
    """Scripted CompletedProcess-alikes per (verb, json?) invocation."""

    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def __call__(self, *args, timeout=15):
        self.calls.append(args)
        tool, verb = args[0], args[1]

        class R:
            returncode = 0
            stdout = ""
            stderr = ""

        r = R()
        if verb == "status":
            r.stdout = '{"ok": true}' if "--json" in args else "all good"
        elif verb == "list":
            if "--json" in args:
                r.stdout = "prose despite --json"  # the manna-list class
            else:
                r.stdout = "items"
        elif verb == "projects":
            r.returncode = 1
            r.stdout = '{"error": "CLOUDY_API_KEY not set"}'
        return r


def check_grading() -> None:
    runner = FakeRunner()
    report = audit_registry(REGISTRY, runner, include_network=True)
    results = {(r["tool"], r["verb"]): r for r in report["results"]}

    ok = results[("demo", "status")]
    require(ok["outcome"] == "ok", f"healthy verb should grade ok: {ok}")

    liar = results[("demo", "list")]
    require(liar["outcome"] == "fail" and "json" in liar["reason"],
            f"--json liar must fail: {liar}")

    clean = results[("cloudy", "projects")]
    require(clean["outcome"] == "clean-skip",
            f"structured no-creds error is a clean skip: {clean}")

    skipped = results[("demo", "set")]
    require(skipped["outcome"].startswith("skip"), f"write verb recorded as skip: {skipped}")

    require(report["summary"]["fail"] == 1, f"exactly one failure expected: {report['summary']}")
    require(report["ok"] is False, "report not ok while failures exist")


def check_schema_stability() -> None:
    """--schema-check flags snapshot verbs whose JSON shape drifts between calls."""
    calls = {"n": 0}

    class DriftRunner:
        def __call__(self, *args, timeout=15):
            verb = args[1]

            class R:
                returncode = 0
                stderr = ""
            r = R()
            if "--json" not in args:
                r.stdout = "plain"
                return r
            if verb == "stable":
                r.stdout = '{"a": 1, "b": 2}'
            elif verb == "drifty":
                calls["n"] += 1
                r.stdout = '{"a": 1}' if calls["n"] % 2 else '{"a": 1, "extra": 9}'
            return r

    registry = {"tools": {"demo": {
        "commands": {"stable": "Stable read", "drifty": "Shifting read"},
        "contracts": {"snapshot": ["stable", "drifty"]},
    }}}
    report = audit_registry(registry, DriftRunner(), schema_check=True)
    results = {r["verb"]: r for r in report["results"]}
    require(results["stable"]["outcome"] == "ok", f"stable stays ok: {results['stable']}")
    require(results["stable"].get("schema_stable") is True,
            f"stable schema flagged stable: {results['stable']}")
    require(results["drifty"].get("schema_stable") is False,
            f"drifting top-level keys must be flagged: {results['drifty']}")
    require(report["summary"].get("schema_unstable") == 1,
            f"one schema-unstable verb expected: {report['summary']}")
    # Stability is a warning, not a failure — the gate must stay green.
    require(report["ok"] is True, f"schema drift must not fail the audit: {report['summary']}")

    # Without the flag, no extra probing and no schema key.
    plain = audit_registry(registry, DriftRunner())
    require("schema_stable" not in plain["results"][0],
            "schema check must be opt-in")


def check_timeout_grading() -> None:
    class HangRunner:
        def __call__(self, *args, timeout=15):
            class R:
                returncode = 124
                stdout = ""
                stderr = f"Command timed out after {timeout}s"
            return R()

    registry = {"tools": {"demo": {
        "commands": {"status": "Show status"},
        "contracts": {"snapshot": ["status"]},
    }}}
    report = audit_registry(registry, HangRunner())
    result = report["results"][0]
    require(result["outcome"] == "fail" and "timeout" in result["reason"],
            f"timeout must grade fail: {result}")


def check_plist() -> None:
    from contracts_audit import build_launchd_plist

    plist = build_launchd_plist("/repo/agent-do", "/home/.agent-do/audit/report.md", "weekly")
    require("com.agent-do.contracts-audit" in plist, "plist label missing")
    require("<string>--notify</string>" in plist, "notify flag missing from plist")
    require("<key>Weekday</key><integer>1</integer>" in plist, "weekly schedule missing")
    daily = build_launchd_plist("/repo/agent-do", "/r.md", "daily")
    require("Weekday" not in daily and "<key>Hour</key><integer>9</integer>" in daily,
            "daily schedule wrong")


def main() -> int:
    check_eligibility()
    check_grading()
    check_schema_stability()
    check_timeout_grading()
    check_plist()
    print("contracts audit tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
