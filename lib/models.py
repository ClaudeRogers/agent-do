"""Capability-driven model resolution for agent-do's internal LLM calls."""

from __future__ import annotations

import copy
import json
import os
import subprocess
from pathlib import Path
from typing import Any

try:
    import yaml
except ModuleNotFoundError:  # pragma: no cover - depends on host Python packages
    yaml = None


ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_MODELS_FILE = ROOT_DIR / "models.yaml"
VALID_ROLES = ("fast", "vision", "deep")


class ModelConfigError(RuntimeError):
    """Raised when the internal model configuration cannot resolve safely."""


def models_file() -> Path:
    override = os.environ.get("AGENT_DO_MODELS_FILE")
    return Path(override).expanduser() if override else DEFAULT_MODELS_FILE


def load_config() -> dict[str, Any]:
    path = models_file()
    try:
        if yaml is not None:
            payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        else:
            ruby = subprocess.run(
                [
                    "ruby",
                    "-e",
                    'require "yaml"; require "json"; print JSON.generate(YAML.load_file(ARGV[0]) || {})',
                    str(path),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            if ruby.returncode != 0:
                raise ModelConfigError(
                    f"could not parse YAML without PyYAML; Ruby fallback failed: {ruby.stderr.strip()}"
                )
            payload = json.loads(ruby.stdout or "{}")
    except FileNotFoundError as exc:
        raise ModelConfigError(f"model configuration not found: {path}") from exc
    except (ValueError, getattr(yaml, "YAMLError", ValueError)) as exc:
        raise ModelConfigError(f"invalid model configuration {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ModelConfigError(f"model configuration must be a mapping: {path}")
    return payload


def parse_model_ref(value: str) -> tuple[str, str]:
    ref = (value or "").strip()
    if not ref:
        raise ModelConfigError("model reference cannot be empty")
    if "/" not in ref:
        return "anthropic", ref
    provider, model = ref.split("/", 1)
    if not provider or not model:
        raise ModelConfigError(f"invalid provider/model reference: {value}")
    return provider, model


def _retired(config: dict[str, Any], provider: str, model: str) -> bool:
    retired = config.get("retired") or {}
    values = retired.get(provider) if isinstance(retired, dict) else []
    return model in (values or [])


def model_record(config: dict[str, Any], provider: str, model: str) -> dict[str, Any]:
    records = config.get("models") or {}
    if not isinstance(records, dict):
        return {}
    record = records.get(f"{provider}/{model}") or records.get(model) or {}
    return record if isinstance(record, dict) else {}


def _candidate_refs(role: str, config: dict[str, Any]) -> list[tuple[str, str]]:
    roles = config.get("roles") or {}
    role_config = roles.get(role) if isinstance(roles, dict) else None
    if not isinstance(role_config, dict):
        raise ModelConfigError(f"unknown model role '{role}'; expected one of: {', '.join(VALID_ROLES)}")

    candidates: list[str] = []
    env_name = str(role_config.get("env") or "").strip()
    env_value = os.environ.get(env_name) if env_name else None
    if not env_value and role == "fast":
        env_value = os.environ.get("AGENT_DO_AI_MODEL")
    if env_value:
        candidates.append(env_value)
    chain = role_config.get("chain") or []
    if not isinstance(chain, list):
        raise ModelConfigError(f"models role '{role}' chain must be a list")
    candidates.extend(str(item) for item in chain if str(item).strip())

    seen: set[tuple[str, str]] = set()
    refs: list[tuple[str, str]] = []
    for candidate in candidates:
        ref = parse_model_ref(candidate)
        if ref not in seen:
            seen.add(ref)
            refs.append(ref)
    return refs


def candidates(role: str) -> list[dict[str, Any]]:
    config = load_config()
    resolved: list[dict[str, Any]] = []
    for provider, model in _candidate_refs(role, config):
        if _retired(config, provider, model):
            continue
        resolved.append(
            {
                "provider": provider,
                "model": model,
                "role": role,
                "capabilities": copy.deepcopy(model_record(config, provider, model)),
            }
        )
    return resolved


def resolve(role: str) -> dict[str, Any]:
    if role not in VALID_ROLES:
        raise ModelConfigError(f"unknown model role '{role}'; expected one of: {', '.join(VALID_ROLES)}")
    available = candidates(role)
    if available:
        return available[0]
    raise ModelConfigError(
        f"no usable model configured for role '{role}'; update {models_file()} or its environment override"
    )


def generation_params(model: str, provider: str = "anthropic") -> dict[str, Any]:
    config = load_config()
    record = model_record(config, provider, model)
    configured = record.get("generation") if isinstance(record, dict) else None
    if not isinstance(configured, dict):
        return {}

    params = copy.deepcopy(configured)
    output_config = params.get("output_config")
    effort_override = os.environ.get("AGENT_DO_AI_EFFORT")
    if effort_override and isinstance(output_config, dict) and "effort" in output_config:
        output_config["effort"] = effort_override
    return params


def role_snapshot() -> dict[str, Any]:
    config = load_config()
    return {
        "version": config.get("version"),
        "file": str(models_file()),
        "roles": {
            role: {
                "resolved": resolve(role),
                "chain": (config.get("roles") or {}).get(role, {}).get("chain", []),
                "env": (config.get("roles") or {}).get(role, {}).get("env"),
            }
            for role in VALID_ROLES
        },
        "retired": config.get("retired") or {},
    }
