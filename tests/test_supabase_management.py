#!/usr/bin/env python3
"""Regression tests for agent-supabase Management API write commands.

Stubs `curl` so no network call is made; captures the outgoing request
(method, URL, body) and asserts it matches the Supabase Management API
spec. Also verifies confirmation guards on destructive/billable ops.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "agent-supabase"

PASS = 0
FAIL = 0


def require(cond: bool, msg: str) -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  FAIL: {msg}")


def run(args, *, capture_dir: Path, token: str = "test-token"):
    """Run agent-supabase with a stubbed curl. Returns (proc, captured_request)."""
    cap_file = capture_dir / "curl_args"
    if cap_file.exists():
        cap_file.unlink()

    env = dict(os.environ)
    env["PATH"] = f"{capture_dir}{os.pathsep}{env['PATH']}"
    env["SB_CAPTURE"] = str(cap_file)
    if token:
        env["SUPABASE_ACCESS_TOKEN"] = token
    else:
        env.pop("SUPABASE_ACCESS_TOKEN", None)

    proc = subprocess.run(
        ["bash", str(TOOL), *args],
        capture_output=True, text=True, env=env,
    )

    captured = None
    if cap_file.exists():
        lines = cap_file.read_text().splitlines()
        method, url, body = "", "", ""
        i = 0
        while i < len(lines):
            if lines[i] == "-X":
                method = lines[i + 1]; i += 2; continue
            if lines[i] == "-d":
                body = lines[i + 1]; i += 2; continue
            if lines[i].startswith("https://"):
                url = lines[i]
            i += 1
        captured = {"method": method, "url": url, "body": body}
    return proc, captured


def main() -> int:
    stub = tempfile.mkdtemp()
    stub_dir = Path(stub)
    # Fake curl: record argv, emit empty JSON object.
    curl = stub_dir / "curl"
    curl.write_text('#!/usr/bin/env bash\nprintf "%s\\n" "$@" > "$SB_CAPTURE"\necho "{}"\n')
    curl.chmod(0o755)

    # --- create: POST /projects with required body fields ---
    proc, cap = run(["create", "myproj", "--org", "myslug", "--region", "us-east-1", "--yes"], capture_dir=stub_dir)
    require(cap is not None, "create issued an HTTP request")
    if cap:
        require(cap["method"] == "POST", f"create uses POST (got {cap['method']})")
        require(cap["url"].endswith("/v1/projects"), f"create hits /v1/projects (got {cap['url']})")
        body = json.loads(cap["body"]) if cap["body"] else {}
        require(body.get("name") == "myproj", "create body.name set")
        require(body.get("organization_slug") == "myslug", "create body.organization_slug set (NOT organization_id)")
        require(body.get("region") == "us-east-1", "create body.region set")
        require(bool(body.get("db_pass")), "create auto-generates db_pass when omitted")

    # --- create refuses without --yes (no curl call) ---
    proc, cap = run(["create", "myproj", "--org", "myslug"], capture_dir=stub_dir)
    require(proc.returncode == 1, "create without --yes exits 1")
    require(cap is None, "create without --yes makes no HTTP call")

    # --- delete: DELETE /projects/{ref}, guarded ---
    proc, cap = run(["delete", "ref123", "--yes"], capture_dir=stub_dir)
    require(cap is not None and cap["method"] == "DELETE", "delete uses DELETE")
    require(cap is not None and cap["url"].endswith("/v1/projects/ref123"), "delete hits /v1/projects/{ref}")
    proc, cap = run(["delete", "ref123"], capture_dir=stub_dir)
    require(proc.returncode == 1 and cap is None, "delete without --yes refuses and makes no call")

    # --- update: PATCH /projects/{ref} ---
    proc, cap = run(["update", "ref123", "--name", "newname"], capture_dir=stub_dir)
    require(cap is not None and cap["method"] == "PATCH", "update uses PATCH")
    if cap and cap["body"]:
        require(json.loads(cap["body"]).get("name") == "newname", "update body.name set")

    # --- branch-create: POST /projects/{ref}/branches ---
    proc, cap = run(["branch-create", "ref123", "feature-x", "--persistent"], capture_dir=stub_dir)
    require(cap is not None and cap["method"] == "POST", "branch-create uses POST")
    require(cap is not None and cap["url"].endswith("/v1/projects/ref123/branches"), "branch-create endpoint")
    if cap and cap["body"]:
        b = json.loads(cap["body"])
        require(b.get("branch_name") == "feature-x", "branch-create body.branch_name set")
        require(b.get("persistent") is True, "branch-create persistent flag set")

    # --- compute-scale: PATCH billing/addons with ci_ variant ---
    proc, cap = run(["compute-scale", "ref123", "--size", "large", "--yes"], capture_dir=stub_dir)
    require(cap is not None and cap["method"] == "PATCH", "compute-scale uses PATCH")
    require(cap is not None and cap["url"].endswith("/v1/projects/ref123/billing/addons"), "compute-scale endpoint")
    if cap and cap["body"]:
        b = json.loads(cap["body"])
        require(b.get("addon_type") == "compute_instance", "compute-scale addon_type")
        require(b.get("addon_variant") == "ci_large", "compute-scale addon_variant ci_large")

    # --- network-restrict: POST network-restrictions/apply with dbAllowedCidrs ---
    proc, cap = run(["network-restrict", "ref123", "--cidr", "1.2.3.4/32", "--cidr", "5.6.7.8/32"], capture_dir=stub_dir)
    require(cap is not None and cap["url"].endswith("/v1/projects/ref123/network-restrictions/apply"), "network-restrict endpoint")
    if cap and cap["body"]:
        b = json.loads(cap["body"])
        require(b.get("dbAllowedCidrs") == ["1.2.3.4/32", "5.6.7.8/32"], "network-restrict dbAllowedCidrs array")

    # --- replica-setup: guarded, POST read-replicas/setup ---
    proc, cap = run(["replica-setup", "ref123", "--region", "us-west-1", "--yes"], capture_dir=stub_dir)
    require(cap is not None and cap["url"].endswith("/v1/projects/ref123/read-replicas/setup"), "replica-setup endpoint")
    if cap and cap["body"]:
        require(json.loads(cap["body"]).get("read_replica_region") == "us-west-1", "replica-setup region")
    proc, cap = run(["replica-setup", "ref123", "--region", "us-west-1"], capture_dir=stub_dir)
    require(proc.returncode == 1 and cap is None, "replica-setup without --yes refuses")

    # --- function-deploy: reads file into body ---
    fn = stub_dir / "edge.ts"
    fn.write_text("export default () => new Response('hi')\n")
    proc, cap = run(["function-deploy", "ref123", "hello", "--file", str(fn)], capture_dir=stub_dir)
    require(cap is not None and cap["url"].endswith("/v1/projects/ref123/functions"), "function-deploy endpoint")
    if cap and cap["body"]:
        b = json.loads(cap["body"])
        require(b.get("slug") == "hello", "function-deploy slug")
        require("new Response" in b.get("body", ""), "function-deploy reads source file into body")

    # --- upgrade: guarded, POST upgrade with target_version ---
    proc, cap = run(["upgrade", "ref123", "--version", "15", "--yes"], capture_dir=stub_dir)
    require(cap is not None and cap["url"].endswith("/v1/projects/ref123/upgrade"), "upgrade endpoint")
    if cap and cap["body"]:
        require(json.loads(cap["body"]).get("target_version") == "15", "upgrade target_version")

    # --- read-only GET wrappers ---
    proc, cap = run(["branches", "ref123"], capture_dir=stub_dir)
    require(cap is not None and cap["method"] == "GET" and cap["url"].endswith("/v1/projects/ref123/branches"),
            "branches GET endpoint")
    proc, cap = run(["upgrade-eligibility", "ref123"], capture_dir=stub_dir)
    require(cap is not None and cap["url"].endswith("/v1/projects/ref123/upgrade/eligibility"),
            "upgrade-eligibility endpoint")

    # --- missing-token path errors cleanly ---
    proc, cap = run(["branches", "ref123"], capture_dir=stub_dir, token="")
    require(proc.returncode != 0, "missing token causes non-zero exit")

    print(f"\nsupabase management tests: {PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
