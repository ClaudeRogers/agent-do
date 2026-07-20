#!/usr/bin/env python3
"""Regression coverage for internal model resolution."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

from models import generation_params, resolve  # noqa: E402


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def fixture_config(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "roles": {
                    "fast": {"chain": ["retired-model", "live-model"], "env": "TEST_FAST_MODEL"},
                    "vision": {"chain": ["live-model"], "env": "TEST_VISION_MODEL"},
                    "deep": {"chain": ["deep-model"], "env": "TEST_DEEP_MODEL"},
                },
                "models": {
                    "live-model": {
                        "provider": "anthropic",
                        "generation": {
                            "thinking": {"type": "adaptive"},
                            "output_config": {"effort": "high"},
                        },
                    },
                    "deep-model": {"provider": "anthropic"},
                },
                "retired": {"anthropic": ["retired-model"]},
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        config = Path(tmp) / "models.yaml"
        fixture_config(config)
        old_env = os.environ.copy()
        try:
            os.environ["AGENT_DO_MODELS_FILE"] = str(config)
            os.environ.pop("TEST_FAST_MODEL", None)
            selected = resolve("fast")
            require(selected["model"] == "live-model", f"retired entry was not skipped: {selected}")

            os.environ["TEST_FAST_MODEL"] = "env-model"
            selected = resolve("fast")
            require(selected["model"] == "env-model", f"env override did not win: {selected}")

            os.environ.pop("TEST_FAST_MODEL", None)
            params = generation_params("live-model")
            require(params["thinking"] == {"type": "adaptive"}, f"capability params missing: {params}")

            env = old_env.copy()
            env["AGENT_DO_MODELS_FILE"] = str(config)
            result = subprocess.run(
                [str(ROOT / "agent-do"), "models", "resolve", "vision", "--json"],
                cwd=ROOT,
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )
            require(result.returncode == 0, result.stderr or result.stdout)
            payload = json.loads(result.stdout)
            require(payload["model"] == "live-model", f"unexpected CLI resolution: {payload}")

            eval_source = (ROOT / "tools" / "agent-eval").read_text(encoding="utf-8")
            require(
                "eval_config.get('model') or resolve('deep')['model']" in eval_source,
                "agent-eval must preserve explicit model values and resolve only its default",
            )
        finally:
            os.environ.clear()
            os.environ.update(old_env)

    print("model resolution tests passed")


if __name__ == "__main__":
    main()
