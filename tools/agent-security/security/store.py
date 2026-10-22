"""Atomic, private, append-only reports and opt-in stale HTTP cache."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import uuid
from pathlib import Path

from .model import SCHEMA_VERSION, now


def home():
    return Path(os.environ.get("AGENT_DO_HOME", str(Path.home() / ".agent-do"))) / "security"


def atomic_json(path, data):
    path = Path(path)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".pending-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(data, stream, sort_keys=True, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def new_report(command, target):
    return {"schema_version": SCHEMA_VERSION, "report_id": uuid.uuid4().hex,
            "command": command, "created_at": now(), "target": target,
            "status": "complete", "coverage": [], "findings": [], "notes": [],
            "scope": "published_advisories" if command == "find" else "source_dependencies",
            "limitations": ["Runtime, operating-system, deployed-artifact, and exploitability assessment are outside this source-scan scope."] if command == "scan" else []}


def finish(report):
    if any(x["status"] != "ok" for x in report["coverage"]):
        report["status"] = "incomplete"
    path = home() / "reports" / (report["created_at"].replace(":", "-") + "-" + report["report_id"] + ".json")
    report["saved_report"] = str(path)
    atomic_json(path, report)
    return report


def read_report(path):
    value = json.loads(Path(path).read_text())
    if value.get("schema_version") != SCHEMA_VERSION or not isinstance(value.get("findings"), list):
        raise ValueError("Unsupported report schema")
    return value


def latest_report():
    paths = sorted((home() / "reports").glob("*.json"))
    if not paths:
        raise ValueError("No saved security reports; run find or scan first")
    return read_report(paths[-1])
