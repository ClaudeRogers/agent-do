#!/usr/bin/env python3
"""`agent-do manna estate`: the registered-board model without a daemon.

The HTTP estate and the CLI deliberately call the same derivation function.
Starting, probing, or even having a serve daemon is therefore irrelevant to
this read path: the registry and each registered board are the inputs.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

SERVE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SERVE_DIR))
import serve as serve_lib  # noqa: E402


def emit(payload: dict, as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, indent=2))
    else:
        print(yaml.safe_dump(payload, sort_keys=False), end="")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="agent-do manna estate",
        description=(
            "Read every board registered with manna serve and emit the same "
            "estate model as /api/boards. No daemon is started or contacted."
        ),
    )
    parser.add_argument("--json", action="store_true", help="emit JSON instead of YAML")
    args = parser.parse_args(argv)
    try:
        payload = serve_lib.boards_index()
    except Exception as error:
        message = f"estate read failed: {error}"
        if args.json:
            print(json.dumps({"success": False, "error": message}))
        else:
            print(f"error: {message}", file=sys.stderr)
        return 1
    emit(payload, args.json)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
