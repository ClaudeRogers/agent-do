"""File snapshots, explicit JVM build resolution, and OSV-Scanner assessment."""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import tempfile
import urllib.parse
from pathlib import Path, PurePosixPath

from .model import cvss_scores, ecosystem, finding

FORMATS = {"package-lock.json": "npm", "npm-shrinkwrap.json": "npm", "yarn.lock": "npm",
           "pnpm-lock.yaml": "npm", "bun.lock": "npm", "composer.lock": "composer",
           "requirements.txt": "pip", "Pipfile.lock": "pip", "poetry.lock": "pip",
           "pdm.lock": "pip", "uv.lock": "pip", "pylock.toml": "pip", "pom.xml": "maven",
           "gradle.lockfile": "maven", "buildscript-gradle.lockfile": "maven",
           "Cargo.lock": "rust", "go.mod": "go", "Gemfile.lock": "rubygems",
           "packages.lock.json": "nuget", "pubspec.lock": "pub", "mix.lock": "erlang"}
MANIFESTS = {"package.json", "composer.json", "pyproject.toml", "Pipfile", "build.gradle",
             "build.gradle.kts", "Cargo.toml", "Gemfile", "setup.py", "setup.cfg"}
SKIP = {".git", ".gradle", "node_modules", ".venv", "venv", "vendor", "target", "dist", "build", "__pycache__", ".agent-do"}


def run(argv, args, *, cwd=None):
    env = {**os.environ, "GH_PROMPT_DISABLED": "1", "GIT_TERMINAL_PROMPT": "0", "GIT_OPTIONAL_LOCKS": "0"}
    try:
        result = subprocess.run(argv, cwd=cwd, env=env, capture_output=True, timeout=args.scan_timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError(Path(argv[0]).name + ": unavailable or timed out") from exc
    if len(result.stdout) > args.max_bytes or len(result.stderr) > args.max_bytes:
        raise ValueError(Path(argv[0]).name + " output exceeds --max-bytes")
    return result


def github(args, endpoint):
    result = run(["gh", "api", "--hostname", "github.com", endpoint], args)
    if result.returncode:
        raise ValueError("GitHub read failed; check gh authentication, repository access, and ref")
    return json.loads(result.stdout)


def repo_name(value):
    value = value.removesuffix("/").removesuffix(".git")
    if value.startswith("https://github.com/"):
        value = value[len("https://github.com/"):]
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", value) or any(x in {".", ".."} for x in value.split("/")):
        raise ValueError("--repo must be owner/repo or https://github.com/owner/repo")
    return value


def safe_relative(name):
    path = PurePosixPath(name)
    if path.is_absolute() or any(x in {".", ".."} for x in path.parts) or "\\" in name:
        raise ValueError("Unsafe repository file path")
    return path


def acquire(args, report, stage):
    files, digest = [], hashlib.sha256()
    if args.repo:
        repo = repo_name(args.repo)
        meta = github(args, "repos/" + repo)
        ref = args.ref or meta["default_branch"]
        commit = github(args, "repos/" + repo + "/commits/" + urllib.parse.quote(ref, safe=""))
        sha = commit["sha"]
        if not re.fullmatch(r"[0-9a-f]{40}", sha):
            raise ValueError("GitHub returned an invalid commit identity")
        report["target"] = {"kind": "github", "repository": repo, "requested_ref": ref,
                            "commit": sha, "default_branch": meta["default_branch"]}
        tree = github(args, "repos/" + repo + "/git/trees/" + sha + "?recursive=1")
        if tree.get("truncated"):
            raise ValueError("GitHub tree is truncated; scan an authorized local checkout instead")
        for entry in tree["tree"]:
            path = safe_relative(entry["path"])
            if any(p in SKIP for p in path.parts[:-1]) or entry["type"] != "blob":
                continue
            if path.name not in FORMATS and path.name not in MANIFESTS:
                continue
            if entry["mode"] not in {"100644", "100755"}:
                report["coverage"].append({"source": str(path), "status": "unsupported", "reason": "Symlinks are not followed"})
                continue
            if entry.get("size", 0) > args.max_bytes:
                raise ValueError("Repository manifest exceeds --max-bytes: " + str(path))
            blob = github(args, "repos/" + repo + "/git/blobs/" + entry["sha"])
            if blob.get("encoding") != "base64":
                raise ValueError("Unsupported GitHub blob encoding")
            content = base64.b64decode(blob["content"])
            files.append((str(path), content))
    else:
        root = Path(args.path).expanduser().resolve(strict=True)
        if not root.is_dir():
            raise ValueError("--path must name a directory")
        report["target"] = {"kind": "local", "path": str(root), "commit": None, "dirty": None}
        if shutil.which("git"):
            commit = run(["git", "-C", str(root), "rev-parse", "HEAD"], args)
            if commit.returncode == 0:
                report["target"]["commit"] = commit.stdout.decode().strip()
                status = run(["git", "-c", "core.fsmonitor=false", "-c", "core.hooksPath=/dev/null", "-C", str(root), "status", "--porcelain", "--untracked-files=normal", "--ignore-submodules=all"], args)
                report["target"]["dirty"] = bool(status.stdout) if status.returncode == 0 else None
                report["target"]["dirty_scope"] = "superproject; submodule status not executed"
        for directory, dirs, names in os.walk(root, followlinks=False, onerror=lambda exc: (_ for _ in ()).throw(exc)):
            for name in dirs[:]:
                p = Path(directory) / name
                if name in SKIP or p.is_symlink():
                    dirs.remove(name)
                    if p.is_symlink():
                        report["coverage"].append({"source": str(p.relative_to(root)), "status": "unsupported", "reason": "Symlink directory not followed"})
            for name in sorted(names):
                if name not in FORMATS and name not in MANIFESTS:
                    continue
                p = Path(directory) / name
                rel = str(p.relative_to(root))
                if p.is_symlink():
                    report["coverage"].append({"source": rel, "status": "unsupported", "reason": "Symlink file not followed"})
                    continue
                # O_NOFOLLOW closes the final-component symlink race where supported.
                fd = os.open(p, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
                with os.fdopen(fd, "rb") as stream:
                    if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                        report["coverage"].append({"source": rel, "status": "unsupported", "reason": "Not a regular dependency file"})
                        continue
                    content = stream.read(args.max_bytes + 1)
                files.append((rel, content))
    inventory = []
    for rel, content in sorted(files):
        if len(content) > args.max_bytes:
            raise ValueError("Manifest exceeds --max-bytes: " + rel)
        dest = stage / safe_relative(rel)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(content)
        digest.update(rel.encode() + b"\0" + hashlib.sha256(content).digest())
        kind = "candidate" if dest.name in FORMATS else "manifest_only"
        inventory.append({"path": rel, "ecosystem": FORMATS.get(dest.name), "sha256": hashlib.sha256(content).hexdigest(), "status": kind})
    report["target"]["inventory_sha256"] = digest.hexdigest()
    report["inventory"] = inventory
    report["notes"].append("Scanned an isolated copy of recognized dependency files. Excluded directories: " + ", ".join(sorted(SKIP)))
    return inventory


def assess_inventory(inventory, stage, report, *, allow_empty=False):
    candidates = []
    for entry in inventory:
        name = Path(entry["path"]).name
        parent = str(Path(entry["path"]).parent)
        siblings = {Path(x["path"]).name for x in inventory if str(Path(x["path"]).parent) == parent}
        if entry["status"] == "manifest_only":
            related = {"package.json": {"package-lock.json", "npm-shrinkwrap.json", "pnpm-lock.yaml", "yarn.lock", "bun.lock"},
                       "composer.json": {"composer.lock"}, "pyproject.toml": {"poetry.lock", "uv.lock", "pdm.lock", "pylock.toml", "requirements.txt"},
                       "Pipfile": {"Pipfile.lock"}, "Cargo.toml": {"Cargo.lock"}, "Gemfile": {"Gemfile.lock"},
                       "build.gradle": {"gradle.lockfile"}, "build.gradle.kts": {"gradle.lockfile"}}
            if not siblings & related.get(name, set()):
                report["coverage"].append({"source": entry["path"], "status": "unresolved", "reason": "Manifest has no supported resolved dependency inventory in the same directory"})
            continue
        candidates.append(entry)
        if name == "pom.xml":
            report["coverage"].append({"source": entry["path"], "status": "unresolved", "reason": "POM alone does not prove resolved transitive versions; use --resolve maven on a trusted local checkout"})
        if name == "requirements.txt":
            lines = (stage / entry["path"]).read_text(errors="replace").splitlines()
            unresolved = [line for line in lines if line.strip() and not line.lstrip().startswith("#")
                          and not re.match(r"^\s*[A-Za-z0-9_.-]+(?:\[[^\]]+\])?==[^\s*;]+(?:\s*;.*)?\s*$", line)]
            if unresolved:
                report["coverage"].append({"source": entry["path"], "status": "unresolved", "reason": "Requirements include ranges, URLs, includes, or other unresolved entries", "unresolved_entries": len(unresolved)})
    if not candidates and not allow_empty:
        report["coverage"].append({"source": "inventory", "status": "unsupported", "reason": "No supported dependency inventories found"})
    return candidates


def osv_rows(body, stage):
    if not isinstance(body, dict) or not isinstance(body.get("results"), list):
        raise ValueError("OSV-Scanner returned an unsupported JSON schema")
    rows, packages, sources = [], [], set()
    for result in body["results"]:
        original = Path(result["source"]["path"])
        path = str(original.relative_to(stage)) if original.is_absolute() else str(original)
        safe_relative(path)
        sources.add(path)
        for item in result.get("packages", []):
            package = item["package"]
            packages.append({**package, "path": path})
            for advisory in item.get("vulnerabilities", []):
                if advisory.get("withdrawn"):
                    continue
                affected = []
                for a in advisory.get("affected", []):
                    p = a.get("package", {})
                    if p.get("name") != package.get("name") or ecosystem(p.get("ecosystem")) != ecosystem(package.get("ecosystem")):
                        continue
                    fixes = sorted({e["fixed"] for r in a.get("ranges", []) for e in r.get("events", []) if "fixed" in e})
                    affected.append({"package": p, "ranges": a.get("ranges", []), "fixed_versions": fixes})
                scores = cvss_scores(advisory.get("severity", []), "OSV:" + advisory["id"])
                row = finding([advisory["id"]] + advisory.get("aliases", []), advisory.get("summary") or advisory.get("details"),
                              "OSV-Scanner", "https://osv.dev/" + advisory["id"], scores=scores,
                              severity=(advisory.get("database_specific") or {}).get("severity"),
                              published=advisory.get("published"), modified=advisory.get("modified"),
                              package=package, affected=affected,
                              evidence=[{"path": path, "basis": "scanner_version_match", "dependency_scope": "unknown", "dependency_path": None}])
                rows.append(row)
    return rows, packages, sources


def scan(args, report):
    with tempfile.TemporaryDirectory(prefix="agent-security-") as directory:
        stage = Path(directory) / "source"
        stage.mkdir()
        inventory = acquire(args, report, stage)
        if args.resolve:
            from .resolve import resolve
            inventory = resolve(args, report, stage, inventory)
            report['scanner_inventory'] = inventory
        candidates = assess_inventory(inventory, stage, report, allow_empty=bool(args.resolve))
        if not candidates and args.resolve:
            report['packages'] = []
            return
        executable = shutil.which(args.scanner)
        if not executable:
            report["coverage"].append({"source": "OSV-Scanner", "status": "unavailable", "reason": "Install OSV-Scanner v2 or select it with --scanner"})
            return
        executable = str(Path(executable).resolve())
        version = run([executable, "--version"], args)
        version_text = version.stdout.decode(errors="replace").strip()
        report["scanner"] = {"name": "OSV-Scanner", "version": version_text}
        if version.returncode or not re.search(r"(?:version[: ]+|v)2\.", version_text, re.I):
            raise ValueError("OSV-Scanner v2 is required; version probe did not identify v2")
        if not candidates:
            return
        # The isolated source contains manifests only, and no repository-provided scanner config.
        # Run from its empty parent so no checkout or user config can suppress findings.
        config = Path(directory) / "empty.toml"
        config.write_text("")
        # JSON mode routes INFO logs to stderr without level labels. Ask the
        # scanner to suppress INFO before assessing remaining diagnostics;
        # message keywords cannot reliably reconstruct the original log level.
        argv = [executable, "scan", "source", "--recursive", "--format=json", "--all-packages", "--verbosity=warn", "--config=" + str(config), str(stage)]
        result = run(argv, args, cwd=directory)
        if result.returncode not in {0, 1}:
            report["coverage"].append({"source": "OSV-Scanner", "status": "error", "exit_code": result.returncode, "reason": "Scanner failed; run doctor and inspect scanner directly"})
            return
        scanner_body = json.loads(result.stdout)
        rows, packages, assessed = osv_rows(scanner_body, stage)
        if args.resolve:
            from .resolve import SBOM_NAME, attach_evidence
            attach_evidence(rows, report)
            expected = {(x['package']['name'], x['package']['version']) for x in report['resolution']['occurrences']}
            returned = {(x['name'], x['version']) for x in packages if x['path'] == SBOM_NAME and ecosystem(x.get('ecosystem')) == 'maven'}
            if expected - returned:
                report['coverage'].append({'source': 'resolved SBOM', 'status': 'unresolved',
                    'reason': 'Scanner did not assess every resolved component',
                    'missing': [{'name': name, 'version': version} for name, version in sorted(expected - returned)]})
        report["scanner"]["output_sha256"] = hashlib.sha256(result.stdout).hexdigest()
        report["scanner"]["raw_output"] = scanner_body
        report["findings"] += rows
        report["packages"] = packages
        warnings = bool(result.stderr.strip())
        report['scanner']['verbosity'] = 'warn'
        scanner_coverage = {"source": "OSV-Scanner", "status": "warning" if warnings else "ok", "packages_examined": len(packages),
                                   "advisory_data_freshness": "online lookup; upstream database publication time unavailable",
                                   "warnings": warnings, "data_disclosure": "Package identities and versions are sent to OSV by the scanner"}
        if warnings:
            scanner_coverage['reason'] = 'Scanner emitted diagnostics with --verbosity=warn (informational logs suppressed). Remaining diagnostics may affect coverage; raw text is omitted because it may contain private data.'
            scanner_coverage['diagnostic_detection'] = 'nonempty_stderr_at_warn_verbosity'
            scanner_coverage['diagnostic_lines'] = sum(bool(line.strip()) for line in result.stderr.splitlines())
            scanner_coverage['stderr_sha256'] = hashlib.sha256(result.stderr).hexdigest()
        report["coverage"].append(scanner_coverage)
        for entry in candidates:
            if entry["path"] not in assessed:
                report["coverage"].append({"source": entry["path"], "status": "unresolved", "reason": "Scanner did not report package inventory for this file"})
        if any(s.get("score") is None and s.get("vector") for row in rows for s in row["scores"]):
            report["notes"].append("Some CVSS vectors could not be scored; install the optional cvss Python package. Raw vectors are preserved.")


def dependabot(args, report, tool):
    """Reuse PR #51's provider. Default-branch alert evidence stays separately scoped."""
    if report["target"].get("kind") != "github":
        raise ValueError("--dependabot requires --repo; local checkout identity is not inferred")
    result = run([str(tool), "alerts", report["target"]["repository"], "--details", "--json"], args)
    if result.returncode not in {0, 1}:
        report["coverage"].append({"source": "Dependabot", "status": "unavailable", "reason": "gh alerts requires PR #51 or its successor"})
        return
    try:
        body = json.loads(result.stdout)
        repos = body["repos"]
    except (ValueError, KeyError, TypeError):
        report["coverage"].append({"source": "Dependabot", "status": "unavailable", "reason": "Provider lacks the PR #51 alerts schema"})
        return
    # Do not conflate default-branch findings with findings at the scanned commit.
    report["dependabot"] = {"scope": "github_default_branch_alerts", "scanned_commit_equivalence": "not_established", "repos": repos}
    for repo in repos:
        report["coverage"].append({"source": "Dependabot", "status": repo["status"], "repository": repo["repo"], "count": repo["count"], "scope": "github_default_branch_alerts"})
