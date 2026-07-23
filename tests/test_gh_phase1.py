#!/usr/bin/env python3

from __future__ import annotations

import json
import os
import stat
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AGENT_DO = ROOT / "agent-do"
FIXTURES = ROOT / "tools" / "agent-gh" / "fixtures"

def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)

def make_exec(path: Path, contents: str) -> None:
    path.write_text(contents)
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

def run(cmd: list[str], *, cwd: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=cwd, env=env, text=True, capture_output=True, check=False, timeout=30)

ISSUE_LIST = (FIXTURES / "issue_list.json").read_text()
ISSUE_VIEW = (FIXTURES / "issue_view.json").read_text()
RELEASE_LIST = (FIXTURES / "release_list.json").read_text()
RELEASE_VIEW = (FIXTURES / "release_view.json").read_text()

def main() -> int:
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        fake_bin = tmp / "bin"
        fake_bin.mkdir()
        fake_home = tmp / "home"
        fake_home.mkdir()
        log_path = tmp / "gh-calls.jsonl"

        make_exec(
            fake_bin / "gh",
            f"""#!/usr/bin/env python3
import json
import sys
from pathlib import Path

log = Path({str(log_path)!r})
args = sys.argv[1:]
with log.open("a") as f:
    f.write(json.dumps(args) + "\\n")

issue_list = {ISSUE_LIST!r}
issue_view = {ISSUE_VIEW!r}
release_list = {RELEASE_LIST!r}
release_view = {RELEASE_VIEW!r}

# identity (needed by test env setup reused from Phase 0)
if args[:2] == ["api", "user"]:
    print(json.dumps({{"login": "ovachiever", "id": 1, "name": "Erik", "html_url": "https://github.com/ovachiever"}}))

# repos (needed for env init)
elif args[:3] == ["api", "--paginate", "--slurp"]:
    print(json.dumps([[{{"name": "agent-do", "full_name": "ovachiever/agent-do", "owner": {{"login": "ovachiever"}}, "private": False, "visibility": "public", "archived": False, "default_branch": "main", "html_url": "https://github.com/ovachiever/agent-do"}}]]))

# issue list
elif args[:2] == ["issue", "list"] and "--json" in args:
    print(issue_list)

# issue view
elif args[:2] == ["issue", "view"] and "--json" in args:
    print(issue_view)

# issue create
elif args[:2] == ["issue", "create"]:
    print("https://github.com/ovachiever/agent-do/issues/44")

# issue comment / close / reopen / edit (mutations — no output needed)
elif args[:2] in [["issue", "comment"], ["issue", "close"], ["issue", "reopen"], ["issue", "edit"]]:
    sys.exit(0)

# release list
elif args[:2] == ["release", "list"] and "--json" in args:
    print(release_list)

# release view
elif args[:2] == ["release", "view"] and "--json" in args:
    print(release_view)

# release create
elif args[:2] == ["release", "create"]:
    print("https://github.com/ovachiever/agent-do/releases/tag/v1.3.0")

# release edit / delete / upload / download (mutations — no output needed)
elif args[:2] in [["release", "edit"], ["release", "delete"], ["release", "upload"], ["release", "download"]]:
    sys.exit(0)

# issue search (used by triage for related issues)
elif args[:2] == ["search", "issues"]:
    print(json.dumps([]))

else:
    print("unexpected gh args: " + " ".join(args), file=sys.stderr)
    sys.exit(2)
""",
        )

        env = dict(os.environ)
        env["AGENT_DO_HOME"] = str(fake_home)
        env["PATH"] = f"{fake_bin}:{env['PATH']}"

        # ── issue list ─────────────────────────────────────────────────────────
        issue_list_r = run(
            [str(AGENT_DO), "gh", "issue", "list", "ovachiever/agent-do", "--json"],
            cwd=ROOT, env=env,
        )
        require(issue_list_r.returncode == 0, f"issue list failed: {issue_list_r.stderr}")
        il = json.loads(issue_list_r.stdout)
        require(il["command"] == "issue list", f"bad command in envelope: {il}")
        require(il["ref"] == "ovachiever/agent-do", f"bad ref: {il}")
        require(il["data"]["issues"][0]["number"] == 42, f"bad issue number: {il}")
        require(il["data"]["issues"][1]["title"] == "Add support for GitLab", f"bad issue title: {il}")

        # ── issue list --state closed ──────────────────────────────────────────
        il_closed = run(
            [str(AGENT_DO), "gh", "issue", "list", "ovachiever/agent-do", "--state", "closed", "--json"],
            cwd=ROOT, env=env,
        )
        require(il_closed.returncode == 0, f"issue list --state failed: {il_closed.stderr}")
        calls = [json.loads(line) for line in log_path.read_text().splitlines()]
        require(
            any("closed" in c for c in calls if isinstance(c, list)),
            f"--state closed not passed to gh: {calls}",
        )

        # ── issue view ─────────────────────────────────────────────────────────
        issue_view_r = run(
            [str(AGENT_DO), "gh", "issue", "view", "ovachiever/agent-do#42", "--json"],
            cwd=ROOT, env=env,
        )
        require(issue_view_r.returncode == 0, f"issue view failed: {issue_view_r.stderr}")
        iv = json.loads(issue_view_r.stdout)
        require(iv["command"] == "issue view", f"bad command: {iv}")
        require(iv["ref"] == "ovachiever/agent-do#42", f"bad ref: {iv}")
        require(iv["data"]["title"] == "Crash on empty input to parse_ref", f"bad title: {iv}")
        require("bug" in [label["name"] for label in iv["data"]["labels"]], f"missing bug label: {iv}")

        def call_count() -> int:
            return len(log_path.read_text().splitlines()) if log_path.exists() else 0

        # ── issue create --dry-run ─────────────────────────────────────────────
        before = call_count()
        ic_dry = run(
            [str(AGENT_DO), "gh", "issue", "create", "ovachiever/agent-do",
             "--title", "Test issue", "--dry-run"],
            cwd=ROOT, env=env,
        )
        require(ic_dry.returncode == 0, f"issue create --dry-run failed: {ic_dry.stderr}")
        require("[dry-run]" in ic_dry.stdout, f"expected dry-run output: {ic_dry.stdout}")
        require(call_count() == before, "issue create --dry-run should not invoke gh")

        # ── issue create (real) ────────────────────────────────────────────────
        ic_r = run(
            [str(AGENT_DO), "gh", "issue", "create", "ovachiever/agent-do",
             "--title", "Test issue", "--json"],
            cwd=ROOT, env=env,
        )
        require(ic_r.returncode == 0, f"issue create failed: {ic_r.stderr}")
        ic = json.loads(ic_r.stdout)
        require(ic["command"] == "issue create", f"bad command: {ic}")
        require("issues/44" in (ic["data"].get("url") or ""), f"bad url: {ic}")

        # ── issue close --dry-run ──────────────────────────────────────────────
        before = call_count()
        icl_dry = run(
            [str(AGENT_DO), "gh", "issue", "close", "ovachiever/agent-do#42", "--dry-run"],
            cwd=ROOT, env=env,
        )
        require(icl_dry.returncode == 0, f"issue close --dry-run failed: {icl_dry.stderr}")
        require("[dry-run]" in icl_dry.stdout, f"expected dry-run output: {icl_dry.stdout}")
        require(call_count() == before, "issue close --dry-run should not invoke gh")

        # ── issue close (real) ─────────────────────────────────────────────────
        icl_r = run(
            [str(AGENT_DO), "gh", "issue", "close", "ovachiever/agent-do#42",
             "--reason", "completed", "--json"],
            cwd=ROOT, env=env,
        )
        require(icl_r.returncode == 0, f"issue close failed: {icl_r.stderr}")
        icl = json.loads(icl_r.stdout)
        require(icl["data"]["closed"] is True, f"expected closed=true: {icl}")
        require(icl["data"]["reason"] == "completed", f"expected reason=completed: {icl}")

        # ── issue reopen --dry-run ─────────────────────────────────────────────
        before = call_count()
        iro_dry = run(
            [str(AGENT_DO), "gh", "issue", "reopen", "ovachiever/agent-do#42", "--dry-run"],
            cwd=ROOT, env=env,
        )
        require(iro_dry.returncode == 0, f"issue reopen --dry-run failed: {iro_dry.stderr}")
        require(call_count() == before, "issue reopen --dry-run should not invoke gh")

        # ── issue reopen (real) ────────────────────────────────────────────────
        iro_r = run(
            [str(AGENT_DO), "gh", "issue", "reopen", "ovachiever/agent-do#42", "--json"],
            cwd=ROOT, env=env,
        )
        require(iro_r.returncode == 0, f"issue reopen failed: {iro_r.stderr}")
        iro = json.loads(iro_r.stdout)
        require(iro["data"]["reopened"] is True, f"expected reopened=true: {iro}")

        # ── issue label --dry-run ──────────────────────────────────────────────
        before = call_count()
        ilb_dry = run(
            [str(AGENT_DO), "gh", "issue", "label", "ovachiever/agent-do#42",
             "--add", "confirmed", "--dry-run"],
            cwd=ROOT, env=env,
        )
        require(ilb_dry.returncode == 0, f"issue label --dry-run failed: {ilb_dry.stderr}")
        require(call_count() == before, "issue label --dry-run should not invoke gh")

        # ── issue label (real) ─────────────────────────────────────────────────
        ilb_r = run(
            [str(AGENT_DO), "gh", "issue", "label", "ovachiever/agent-do#42",
             "--add", "confirmed", "--json"],
            cwd=ROOT, env=env,
        )
        require(ilb_r.returncode == 0, f"issue label failed: {ilb_r.stderr}")
        ilb = json.loads(ilb_r.stdout)
        require(ilb["data"]["add"] == ["confirmed"], f"expected label add: {ilb}")

        # ── issue triage ───────────────────────────────────────────────────────
        triage_r = run(
            [str(AGENT_DO), "gh", "issue", "triage", "ovachiever/agent-do#42", "--json"],
            cwd=ROOT, env=env,
        )
        require(triage_r.returncode == 0, f"issue triage failed: {triage_r.stderr}")
        tr = json.loads(triage_r.stdout)
        require(tr["command"] == "issue triage", f"bad command: {tr}")
        require(tr["data"]["classification"] == "bug", f"expected bug classification: {tr}")
        require(tr["data"]["confidence"] > 0, f"expected non-zero confidence: {tr}")
        require("bug" in tr["data"]["suggested_labels"], f"expected bug label: {tr}")
        require("first_response_draft" in tr["data"], f"missing first_response_draft: {tr}")

        # ── issue snapshot ─────────────────────────────────────────────────────
        isnap_r = run(
            [str(AGENT_DO), "gh", "issue", "snapshot", "ovachiever/agent-do", "--json"],
            cwd=ROOT, env=env,
        )
        require(isnap_r.returncode == 0, f"issue snapshot failed: {isnap_r.stderr}")
        isnap = json.loads(isnap_r.stdout)
        require(len(isnap["data"]["issues"]) == 2, f"expected 2 issues: {isnap}")

        # ── release list ───────────────────────────────────────────────────────
        rl_r = run(
            [str(AGENT_DO), "gh", "release", "list", "ovachiever/agent-do", "--json"],
            cwd=ROOT, env=env,
        )
        require(rl_r.returncode == 0, f"release list failed: {rl_r.stderr}")
        rl = json.loads(rl_r.stdout)
        require(rl["command"] == "release list", f"bad command: {rl}")
        require(rl["ref"] == "ovachiever/agent-do", f"bad ref: {rl}")
        require(rl["data"]["releases"][0]["tagName"] == "v1.2.0", f"bad tag: {rl}")

        # ── release view ───────────────────────────────────────────────────────
        rv_r = run(
            [str(AGENT_DO), "gh", "release", "view", "ovachiever/agent-do", "v1.2.0", "--json"],
            cwd=ROOT, env=env,
        )
        require(rv_r.returncode == 0, f"release view failed: {rv_r.stderr}")
        rv = json.loads(rv_r.stdout)
        require(rv["command"] == "release view", f"bad command: {rv}")
        require(rv["ref"] == "ovachiever/agent-do@v1.2.0", f"bad ref: {rv}")
        require(rv["data"]["tagName"] == "v1.2.0", f"bad tagName: {rv}")
        require("Issue management" in rv["data"]["body"], f"bad body: {rv}")

        # ── release latest ─────────────────────────────────────────────────────
        rlat_r = run(
            [str(AGENT_DO), "gh", "release", "latest", "ovachiever/agent-do", "--json"],
            cwd=ROOT, env=env,
        )
        require(rlat_r.returncode == 0, f"release latest failed: {rlat_r.stderr}")
        rlat = json.loads(rlat_r.stdout)
        require(rlat["command"] == "release latest", f"bad command: {rlat}")
        require(rlat["data"]["tagName"] == "v1.2.0", f"bad tagName: {rlat}")

        # ── release create --dry-run ───────────────────────────────────────────
        before = call_count()
        rc_dry = run(
            [str(AGENT_DO), "gh", "release", "create", "ovachiever/agent-do", "v1.3.0", "--dry-run"],
            cwd=ROOT, env=env,
        )
        require(rc_dry.returncode == 0, f"release create --dry-run failed: {rc_dry.stderr}")
        require("[dry-run]" in rc_dry.stdout, f"expected dry-run output: {rc_dry.stdout}")
        require(call_count() == before, "release create --dry-run should not invoke gh")

        # ── release create (real) ──────────────────────────────────────────────
        rc_r = run(
            [str(AGENT_DO), "gh", "release", "create", "ovachiever/agent-do", "v1.3.0",
             "--title", "v1.3.0", "--generate-notes", "--json"],
            cwd=ROOT, env=env,
        )
        require(rc_r.returncode == 0, f"release create failed: {rc_r.stderr}")
        rc = json.loads(rc_r.stdout)
        require(rc["command"] == "release create", f"bad command: {rc}")
        require(rc["data"]["tag"] == "v1.3.0", f"bad tag: {rc}")
        require("releases/tag/v1.3.0" in (rc["data"].get("url") or ""), f"bad url: {rc}")

        # verify --generate-notes was passed to gh
        calls_after_create = [json.loads(line) for line in log_path.read_text().splitlines()]
        require(
            any("--generate-notes" in c for c in calls_after_create if isinstance(c, list)),
            f"--generate-notes not passed to gh: {calls_after_create}",
        )

        # ── release delete requires --confirm ──────────────────────────────────
        rdel_no_confirm = run(
            [str(AGENT_DO), "gh", "release", "delete", "ovachiever/agent-do", "v1.3.0"],
            cwd=ROOT, env=env,
        )
        require(rdel_no_confirm.returncode != 0, f"release delete should require --confirm: {rdel_no_confirm.stdout}")

        before = call_count()
        rdel_dry = run(
            [str(AGENT_DO), "gh", "release", "delete", "ovachiever/agent-do", "v1.3.0", "--dry-run"],
            cwd=ROOT, env=env,
        )
        require(rdel_dry.returncode == 0, f"release delete --dry-run failed: {rdel_dry.stderr}")
        require("[dry-run]" in rdel_dry.stdout, f"expected dry-run output: {rdel_dry.stdout}")
        require(call_count() == before, "release delete --dry-run should not invoke gh")

        rdel_r = run(
            [str(AGENT_DO), "gh", "release", "delete", "ovachiever/agent-do", "v1.3.0",
             "--confirm", "--json"],
            cwd=ROOT, env=env,
        )
        require(rdel_r.returncode == 0, f"release delete --confirm failed: {rdel_r.stderr}")
        rdel = json.loads(rdel_r.stdout)
        require(rdel["data"]["deleted"] is True, f"expected deleted=true: {rdel}")

        # ── release publish --dry-run ──────────────────────────────────────────
        before = call_count()
        rpub_dry = run(
            [str(AGENT_DO), "gh", "release", "publish", "ovachiever/agent-do", "v1.3.0", "--dry-run"],
            cwd=ROOT, env=env,
        )
        require(rpub_dry.returncode == 0, f"release publish --dry-run failed: {rpub_dry.stderr}")
        require(call_count() == before, "release publish --dry-run should not invoke gh")

        # ── release publish (real) ─────────────────────────────────────────────
        rpub_r = run(
            [str(AGENT_DO), "gh", "release", "publish", "ovachiever/agent-do", "v1.3.0", "--json"],
            cwd=ROOT, env=env,
        )
        require(rpub_r.returncode == 0, f"release publish failed: {rpub_r.stderr}")
        rpub = json.loads(rpub_r.stdout)
        require(rpub["command"] == "release edit", f"publish should use release edit envelope: {rpub}")
        require(rpub["data"]["tag"] == "v1.3.0", f"bad publish tag: {rpub}")

    print("gh phase1 tests passed")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
