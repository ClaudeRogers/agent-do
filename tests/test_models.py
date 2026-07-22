#!/usr/bin/env python3
"""Regression coverage for internal model resolution."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

from models import apply_doctor_fixes, doctor_report, generation_params, load_config, parse_model_ref, resolve  # noqa: E402


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def fixture_config(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "roles": {
                    "fast": {
                        "chain": ["retired-model", "live-model"],
                        "env": "TEST_FAST_MODEL",
                        "generation": {"effort": "low", "thinking": "adaptive"},
                    },
                    "vision": {"chain": ["anthropic/live-model"], "env": "TEST_VISION_MODEL"},
                    "deep": {
                        "chain": ["deep-model"],
                        "env": "TEST_DEEP_MODEL",
                        "generation": {"effort": "max", "thinking": "adaptive"},
                    },
                },
                "models": {
                    "live-model": {
                        "provider": "anthropic",
                        "capabilities": {
                            "thinking": {"supported": True, "types": {"adaptive": {"supported": True}}},
                            "effort": {"supported": True, "low": {"supported": True}},
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
            require(parse_model_ref("openai/gpt-test") == ("openai", "gpt-test"), "provider prefix lost")
            require(parse_model_ref("claude-test") == ("anthropic", "claude-test"), "bare model must remain Anthropic")

            os.environ["TEST_FAST_MODEL"] = "env-model"
            selected = resolve("fast")
            require(selected["model"] == "env-model", f"env override did not win: {selected}")

            os.environ.pop("TEST_FAST_MODEL", None)
            params = generation_params("live-model", "anthropic", "fast")
            require(
                params == {
                    "thinking": {"type": "adaptive", "display": "omitted"},
                    "output_config": {"effort": "low"},
                },
                f"fast role generation policy was not capability-mapped: {params}",
            )
            os.environ["AGENT_DO_AI_EFFORT"] = "medium"
            overridden = generation_params("live-model", "anthropic", "fast")
            require(overridden["output_config"] == {"effort": "medium"}, f"effort env override lost: {overridden}")
            os.environ.pop("AGENT_DO_AI_EFFORT", None)

            env = old_env.copy()
            env["AGENT_DO_MODELS_FILE"] = str(config)
            env["AGENT_DO_HOME"] = str(Path(tmp) / "isolated-home")
            env["AGENT_DO_CREDS_PLATFORM"] = "unknown"
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
            require(len(payload["candidates"]) == 1, f"resolved JSON must expose fallback candidates: {payload}")

            env.pop("ANTHROPIC_API_KEY", None)
            env.pop("OPENAI_API_KEY", None)
            doctor = subprocess.run(
                [str(ROOT / "agent-do"), "models", "doctor", "--json"],
                cwd=ROOT,
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )
            require(doctor.returncode == 0, doctor.stderr or doctor.stdout)
            doctor_payload = json.loads(doctor.stdout)
            require(
                all(item["status"] == "skipped" for item in doctor_payload["providers"].values()),
                f"missing optional keys must warn-and-skip: {doctor_payload}",
            )

            eval_source = (ROOT / "tools" / "agent-eval").read_text(encoding="utf-8")
            require(
                "explicit_model = eval_config.get('model')" in eval_source
                and "os.environ['AGENT_DO_MODEL_DEEP'] = explicit_model" in eval_source,
                "agent-eval must preserve explicit model values and resolve only its default",
            )

            check_cross_provider_fallback(Path(tmp))
            check_doctor_retired_vs_unavailable(Path(tmp))
        finally:
            os.environ.clear()
            os.environ.update(old_env)

    print("model resolution tests passed")


def check_cross_provider_fallback(tmp: Path) -> None:
    import ai_router

    config = tmp / "fallback-models.yaml"
    config.write_text(
        json.dumps({
            "version": 1,
            "roles": {
                "fast": {
                    "chain": ["anthropic/missing-model", "openai/live-openai"],
                    "generation": {"effort": "low"},
                },
                "vision": {"chain": ["openai/live-openai"]},
                "deep": {"chain": ["openai/live-openai"]},
            },
            "models": {
                "openai/live-openai": {
                    "provider": "openai",
                    "max_tokens": 128,
                    "capabilities": {
                        "reasoning_effort": {"supported": True, "values": ["low", "max"]},
                    },
                    "generation": {"reasoning": {"effort": "max"}},
                }
            },
            "retired": {"anthropic": [], "openai": []},
        }),
        encoding="utf-8",
    )

    class MissingModelError(Exception):
        status_code = 404

    class FakeAnthropicClient:
        def __init__(self, **_kwargs):
            self.messages = self

        def create(self, **_kwargs):
            raise MissingModelError("missing")

    class FakeOpenAIClient:
        def __init__(self, **_kwargs):
            self.responses = self

        def create(self, **kwargs):
            require(kwargs["model"] == "live-openai", f"wrong fallback request: {kwargs}")
            require(kwargs["reasoning"] == {"effort": "low"}, f"reasoning params lost: {kwargs}")
            return SimpleNamespace(output_text="ok")

    old_anthropic, old_openai = ai_router.anthropic, ai_router.openai
    old_config = os.environ.get("AGENT_DO_MODELS_FILE")
    try:
        os.environ["AGENT_DO_MODELS_FILE"] = str(config)
        os.environ["AGENT_DO_HOME"] = str(tmp / "agent-home")
        os.environ["ANTHROPIC_API_KEY"] = "fake-anthropic"
        os.environ["OPENAI_API_KEY"] = "fake-openai"
        ai_router.anthropic = SimpleNamespace(Anthropic=FakeAnthropicClient)
        ai_router.openai = SimpleNamespace(OpenAI=FakeOpenAIClient)
        response = ai_router.llm_call("fast", [{"role": "user", "content": "hello"}], max_tokens=64)
        require(response.provider == "openai" and response.text == "ok", f"cross-provider fallback failed: {response}")
        os.environ.pop("ANTHROPIC_API_KEY", None)
        response = ai_router.llm_call("fast", [{"role": "user", "content": "hello"}], max_tokens=64)
        require(response.provider == "openai", f"unconfigured optional provider was not skipped: {response}")
    finally:
        ai_router.anthropic, ai_router.openai = old_anthropic, old_openai
        if old_config is None:
            os.environ.pop("AGENT_DO_MODELS_FILE", None)
        else:
            os.environ["AGENT_DO_MODELS_FILE"] = old_config


def check_doctor_retired_vs_unavailable(tmp: Path) -> None:
    import models as models_module

    config = {
        "roles": {
            "fast": {"chain": ["anthropic/retired-model", "openai/restricted-model"]},
            "vision": {"chain": []},
            "deep": {"chain": []},
        },
        "models": {},
        "retired": {"anthropic": [], "openai": []},
    }

    original_request = models_module._provider_request

    def forbidden_request(provider: str, _url: str):
        raise models_module.ProviderProbeError(provider, 403, "forbidden")

    models_module._provider_request = forbidden_request
    try:
        forbidden_status, _ = models_module.probe_provider_model("openai", "restricted-model")
    finally:
        models_module._provider_request = original_request
    require(forbidden_status == "unavailable", "mock 403 must classify as unavailable")

    def probe(provider: str, _model: str):
        return ("retired", None) if provider == "anthropic" else (forbidden_status, None)

    report = doctor_report(
        config,
        fetch_models=lambda _provider: [],
        probe_model=probe,
        credential_present=lambda _provider: True,
    )
    require(report["retired_candidates"] == {"anthropic": ["retired-model"]}, f"403 became retirement: {report}")
    restricted = next(item for item in report["models"] if item["provider"] == "openai")
    require(restricted["status"] == "unavailable", f"credential-scoped model misclassified: {report}")

    fix_path = tmp / "doctor-fix.yaml"
    fix_path.write_text(json.dumps(config), encoding="utf-8")
    old_path = os.environ.get("AGENT_DO_MODELS_FILE")
    try:
        os.environ["AGENT_DO_MODELS_FILE"] = str(fix_path)
        apply_doctor_fixes(report, config)
        fixed = load_config()
    finally:
        if old_path is None:
            os.environ.pop("AGENT_DO_MODELS_FILE", None)
        else:
            os.environ["AGENT_DO_MODELS_FILE"] = old_path
    require(fixed["retired"]["anthropic"] == ["retired-model"], f"verified retirement not persisted: {fixed}")
    require(fixed["retired"]["openai"] == [], f"unavailable model persisted as retired: {fixed}")


if __name__ == "__main__":
    main()
