#!/usr/bin/env python3
"""Routing consumes contracts: annotation, mode-aware destructive gate."""

from __future__ import annotations

import os
import sys
import warnings
from importlib.machinery import SourceFileLoader
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

warnings.filterwarnings("ignore", category=DeprecationWarning)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def route(tool: str, command: str) -> dict:
    return {
        "tool": tool, "command": command, "args": [], "flags": {},
        "confidence": 0.9, "explanation": "", "clarification_needed": None,
    }


def check_pattern_matcher() -> None:
    pm = SourceFileLoader("pm_test", str(ROOT / "bin" / "pattern-matcher")).load_module()

    os.environ.pop("AGENT_DO_AUTO_DESTRUCTIVE", None)
    gated = pm.annotate_route_contracts(route("manna", "delete"))
    require(gated["beats"] == ["interact"], f"beats wrong: {gated}")
    require("destructive" in gated["attributes"], f"attributes wrong: {gated}")
    require(gated["clarification_needed"], "destructive route must ask by default")
    require("AGENT_DO_AUTO_DESTRUCTIVE" in gated["clarification_needed"],
            "clarification must explain the escape hatch")

    os.environ["AGENT_DO_AUTO_DESTRUCTIVE"] = "1"
    try:
        auto = pm.annotate_route_contracts(route("manna", "delete"))
        require(not auto["clarification_needed"], "auto mode must not gate")
    finally:
        os.environ.pop("AGENT_DO_AUTO_DESTRUCTIVE", None)

    read = pm.annotate_route_contracts(route("manna", "list"))
    require(read["beats"] == ["snapshot"] and not read["clarification_needed"],
            f"read verbs must pass untouched: {read}")


def check_intent_router_annotation() -> None:
    ir = SourceFileLoader("ir_test", str(ROOT / "bin" / "intent-router")).load_module()
    annotated = ir.annotate_route_contracts(route("creds", "store"))
    require("save" in annotated["beats"], f"creds store beats: {annotated}")
    require("sensitive" in annotated["attributes"], f"creds store attrs: {annotated}")

    multiword = ir.annotate_route_contracts(route("browse", "session"))
    require(multiword["beats"], f"first-token matching must catch namespaced verbs: {multiword}")


def main() -> int:
    check_pattern_matcher()
    check_intent_router_annotation()
    print("routing contracts tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
