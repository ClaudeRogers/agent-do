#!/usr/bin/env python3
"""Tests for agent-coderabbit plugin."""

from __future__ import annotations

import json
import os
import stat
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AGENT_DO = ROOT / "agent-do"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def make_exec(path: Path, contents: str) -> None:
    path.write_text(contents)
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def run(
    cmd: list[str],
    *,
    cwd: Path = ROOT,
    env: dict[str, str],
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=cwd, env=env, text=True, capture_output=True, check=False)


# ---------------------------------------------------------------------------
# Fake JSON review payload returned by cr --agent
# ---------------------------------------------------------------------------
FAKE_AGENT_JSON = json.dumps({
    "findings": [
        {
            "file": "src/main.py",
            "line": 42,
            "severity": "warning",
            "message": "Unused variable 'x'",
        }
    ],
    "summary": "1 issue found",
})

FAKE_DOCTOR_OUTPUT = "✓ Installation OK\n✓ Authentication OK\n✓ Git state OK\n✓ Service connectivity OK"
FAKE_FINDINGS_OUTPUT = "No new findings since last review."


def main() -> int:
    passed = 0
    failed = 0

    def check(label: str, condition: bool, detail: str = "") -> None:
        nonlocal passed, failed
        if condition:
            passed += 1
        else:
            failed += 1
            snippet = f": {detail[:200]}" if detail else ""
            print(f"  FAIL  {label}{snippet}")

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        fake_bin = tmp / "bin"
        fake_bin.mkdir()
        log_path = tmp / "cr-calls.jsonl"

        # ---------------------------------------------------------------
        # Fake `cr` binary — logs every invocation, responds by args
        # ---------------------------------------------------------------
        make_exec(
            fake_bin / "cr",
            f"""#!/usr/bin/env python3
import json
import sys
from pathlib import Path

log = Path({str(log_path)!r})
args = sys.argv[1:]

# Strip --api-key <value> pairs for routing logic (still log them)
with log.open("a") as f:
    f.write(json.dumps(args) + "\\n")

# Consume --api-key <value> before routing
clean = []
i = 0
while i < len(args):
    if args[i] == "--api-key":
        i += 2  # skip key + value
    else:
        clean.append(args[i])
        i += 1

if clean[:1] == ["--version"] or clean == ["--version"]:
    print("cr version 1.0.0-test")
    sys.exit(0)

if clean[:1] == ["doctor"]:
    print({FAKE_DOCTOR_OUTPUT!r})
    sys.exit(0)

if clean[:2] == ["review", "findings"]:
    print({FAKE_FINDINGS_OUTPUT!r})
    sys.exit(0)

if "--agent" in clean:
    print({FAKE_AGENT_JSON!r})
    sys.exit(0)

if "--plain" in clean:
    print("Plain review output: no issues found.")
    sys.exit(0)

if clean[:2] == ["auth", "login"]:
    print("Authenticated successfully (browser)")
    sys.exit(0)

if clean[:2] == ["auth", "org"]:
    print("Organization: test-org")
    sys.exit(0)

# Unknown — exit 1
print(f"fake cr: unrecognised args: {{args}}", file=__import__("sys").stderr)
sys.exit(1)
""",
        )

        base_env: dict[str, str] = {
            **os.environ,
            "PATH": f"{fake_bin}:{os.environ.get('PATH', '')}",
            "CODERABBIT_API_KEY": "",  # cleared by default; set per-test when needed
        }

        # ------------------------------------------------------------------
        # 1. --help exits 0 and contains usage text
        # ------------------------------------------------------------------
        r = run([str(AGENT_DO), "coderabbit", "--help"], env=base_env)
        check("--help exits 0", r.returncode == 0, r.stderr)
        check("--help contains REVIEW section", "REVIEW" in r.stdout, r.stdout[:200])
        check("--help mentions review command", "review" in r.stdout)
        check("--help mentions auth login", "auth login" in r.stdout)

        # ------------------------------------------------------------------
        # 2. doctor exits 0
        # ------------------------------------------------------------------
        r = run([str(AGENT_DO), "coderabbit", "doctor"], env=base_env)
        check("doctor exits 0", r.returncode == 0, r.stderr)
        check("doctor output contains OK", "OK" in r.stdout, r.stdout[:200])

        # ------------------------------------------------------------------
        # 3. review (plain mode) exits 0
        # ------------------------------------------------------------------
        r = run([str(AGENT_DO), "coderabbit", "review"], env=base_env)
        check("review (plain) exits 0", r.returncode == 0, r.stderr)
        check("review (plain) produces output", len(r.stdout.strip()) > 0, r.stdout[:200])

        # ------------------------------------------------------------------
        # 4. review --json exits 0 and stdout is valid JSON
        # ------------------------------------------------------------------
        r = run([str(AGENT_DO), "coderabbit", "review", "--json"], env=base_env)
        check("review --json exits 0", r.returncode == 0, r.stderr)
        parsed = None
        try:
            parsed = json.loads(r.stdout)
        except json.JSONDecodeError:
            pass
        check("review --json produces valid JSON", parsed is not None, r.stdout[:200])
        check("review --json has findings key", isinstance(parsed, dict) and "findings" in parsed, str(parsed))

        # ------------------------------------------------------------------
        # 5. review --base develop passes --base develop to cr
        # ------------------------------------------------------------------
        log_path.write_text("")  # reset log
        r = run([str(AGENT_DO), "coderabbit", "review", "--base", "develop"], env=base_env)
        check("review --base develop exits 0", r.returncode == 0, r.stderr)
        calls = [json.loads(line) for line in log_path.read_text().splitlines() if line.strip()]
        base_passed = any("--base" in call and "develop" in call for call in calls)
        check("review --base develop passes --base develop to cr", base_passed, str(calls))

        # ------------------------------------------------------------------
        # 6. findings exits 0
        # ------------------------------------------------------------------
        r = run([str(AGENT_DO), "coderabbit", "findings"], env=base_env)
        check("findings exits 0", r.returncode == 0, r.stderr)
        check("findings produces output", len(r.stdout.strip()) > 0, r.stdout[:200])

        # ------------------------------------------------------------------
        # 7. snapshot --json exits 0 and has required fields
        # ------------------------------------------------------------------
        r = run([str(AGENT_DO), "coderabbit", "snapshot", "--json"], env=base_env)
        check("snapshot --json exits 0", r.returncode == 0, r.stderr)
        snap = None
        try:
            snap = json.loads(r.stdout)
        except json.JSONDecodeError:
            pass
        check("snapshot --json produces valid JSON", snap is not None, r.stdout[:300])
        check("snapshot has tool field", isinstance(snap, dict) and snap.get("tool") == "agent-coderabbit", str(snap))
        check("snapshot has auth_mode field", snap is not None and "auth_mode" in snap, str(snap))
        check("snapshot has doctor_ok field", snap is not None and "doctor_ok" in snap, str(snap))
        check("snapshot has api_key_present field", snap is not None and "api_key_present" in snap, str(snap))

        # ------------------------------------------------------------------
        # 8. snapshot (human-readable) exits 0
        # ------------------------------------------------------------------
        r = run([str(AGENT_DO), "coderabbit", "snapshot"], env=base_env)
        check("snapshot (plain) exits 0", r.returncode == 0, r.stderr)
        check("snapshot (plain) shows auth mode", "auth" in r.stdout.lower(), r.stdout[:200])

        # ------------------------------------------------------------------
        # 9. Missing cr binary → exits 1 with install hint
        # ------------------------------------------------------------------
        # Build a PATH that has neither the fake bin nor any real cr/coderabbit binary
        import shutil as _shutil
        real_cr_dirs = set()
        for _name in ("cr", "coderabbit"):
            _p = _shutil.which(_name)
            if _p:
                real_cr_dirs.add(str(Path(_p).parent))
        safe_path = ":".join(
            p for p in os.environ.get("PATH", "").split(":")
            if p and p != str(fake_bin) and p not in real_cr_dirs
        )
        no_cr_env = {**base_env, "PATH": safe_path}
        r = run([str(AGENT_DO), "coderabbit", "doctor"], env=no_cr_env)
        check("missing cr binary exits 1", r.returncode == 1, f"rc={r.returncode}")
        check("missing cr binary prints install hint", "brew" in r.stderr.lower() or "install" in r.stderr.lower(), r.stderr[:200])

        # ------------------------------------------------------------------
        # 10. auth login exits 0
        # ------------------------------------------------------------------
        r = run([str(AGENT_DO), "coderabbit", "auth", "login"], env=base_env)
        check("auth login exits 0", r.returncode == 0, r.stderr)

        # ------------------------------------------------------------------
        # 11. CODERABBIT_API_KEY set → --api-key passed to cr
        # ------------------------------------------------------------------
        log_path.write_text("")
        key_env = {**base_env, "CODERABBIT_API_KEY": "cr-test-key-12345"}
        r = run([str(AGENT_DO), "coderabbit", "review"], env=key_env)
        check("review with API key exits 0", r.returncode == 0, r.stderr)
        calls = [json.loads(line) for line in log_path.read_text().splitlines() if line.strip()]
        api_key_passed = any("--api-key" in call and "cr-test-key-12345" in call for call in calls)
        check("CODERABBIT_API_KEY injected as --api-key", api_key_passed, str(calls))

        # ------------------------------------------------------------------
        # 12. CODERABBIT_API_KEY absent → no --api-key arg passed to cr
        # ------------------------------------------------------------------
        log_path.write_text("")
        r = run([str(AGENT_DO), "coderabbit", "review"], env=base_env)
        calls = [json.loads(line) for line in log_path.read_text().splitlines() if line.strip()]
        no_api_key = not any("--api-key" in call for call in calls)
        check("no CODERABBIT_API_KEY → no --api-key arg", no_api_key, str(calls))

        # ------------------------------------------------------------------
        # 13. Unknown command exits 1
        # ------------------------------------------------------------------
        r = run([str(AGENT_DO), "coderabbit", "notacommand"], env=base_env)
        check("unknown command exits 1", r.returncode == 1, f"rc={r.returncode}")
        check("unknown command prints error", "Unknown command" in r.stderr, r.stderr[:200])

    total = passed + failed
    print(f"coderabbit: {passed}/{total} passed" + ("" if failed == 0 else f"  ({failed} FAILED)"))
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
