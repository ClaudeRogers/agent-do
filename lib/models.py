"""Capability-driven model resolution for agent-do's internal LLM calls."""

from __future__ import annotations

import copy
import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

try:
    import yaml
except ModuleNotFoundError:  # pragma: no cover - depends on host Python packages
    yaml = None


ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_MODELS_FILE = ROOT_DIR / "models.yaml"
VALID_ROLES = ("fast", "vision", "deep")
PROVIDER_KEYS = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
}
PROVIDER_TIMEOUT_SECONDS = 15


class ModelConfigError(RuntimeError):
    """Raised when the internal model configuration cannot resolve safely."""


class ProviderProbeError(RuntimeError):
    """Bounded provider-list or model-status failure."""

    def __init__(self, provider: str, status: int | None, message: str):
        super().__init__(message)
        self.provider = provider
        self.status = status


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


def generation_params(model: str, provider: str = "anthropic", role: str | None = None) -> dict[str, Any]:
    """Map role-level generation policy onto one model's advertised capabilities."""
    config = load_config()
    record = model_record(config, provider, model)
    configured = record.get("generation") if isinstance(record, dict) else None
    params = copy.deepcopy(configured) if isinstance(configured, dict) else {}

    roles = config.get("roles") or {}
    role_config = roles.get(role) if role and isinstance(roles, dict) else None
    policy = role_config.get("generation") if isinstance(role_config, dict) else None
    if not isinstance(policy, dict):
        policy = {}

    capabilities = record.get("capabilities") if isinstance(record, dict) else None
    if not isinstance(capabilities, dict):
        capabilities = {}

    effort = os.environ.get("AGENT_DO_AI_EFFORT") or policy.get("effort")
    thinking = policy.get("thinking")
    if provider == "anthropic":
        thinking_caps = capabilities.get("thinking") or {}
        thinking_types = thinking_caps.get("types") if isinstance(thinking_caps, dict) else {}
        selected_thinking = thinking_types.get(thinking) if isinstance(thinking_types, dict) and thinking else None
        if isinstance(selected_thinking, dict) and selected_thinking.get("supported") is True:
            params["thinking"] = {"type": thinking, "display": "omitted"}

        effort_caps = capabilities.get("effort") or {}
        selected_effort = effort_caps.get(effort) if isinstance(effort_caps, dict) and effort else None
        if effort_caps.get("supported") is True and (
            selected_effort is None or not isinstance(selected_effort, dict) or selected_effort.get("supported") is True
        ):
            params.setdefault("output_config", {})["effort"] = effort
    elif provider == "openai":
        effort_caps = capabilities.get("reasoning_effort") or {}
        supported_values = effort_caps.get("values") if isinstance(effort_caps, dict) else None
        if effort_caps.get("supported") is True and effort and (
            not isinstance(supported_values, list) or effort in supported_values
        ):
            params.setdefault("reasoning", {})["effort"] = effort

    return params


def role_snapshot() -> dict[str, Any]:
    config = load_config()
    return {
        "version": config.get("version"),
        "file": str(models_file()),
        "roles": {
            role: {
                "resolved": resolve(role),
                "candidates": candidates(role),
                "chain": (config.get("roles") or {}).get(role, {}).get("chain", []),
                "env": (config.get("roles") or {}).get(role, {}).get("env"),
                "generation": (config.get("roles") or {}).get(role, {}).get("generation", {}),
            }
            for role in VALID_ROLES
        },
        "retired": config.get("retired") or {},
    }


def configured_refs(config: dict[str, Any]) -> list[tuple[str, str]]:
    """Return unique provider/model references declared in role chains."""
    seen: set[tuple[str, str]] = set()
    refs: list[tuple[str, str]] = []
    roles = config.get("roles") or {}
    if not isinstance(roles, dict):
        return refs
    for role in VALID_ROLES:
        role_config = roles.get(role) or {}
        chain = role_config.get("chain") if isinstance(role_config, dict) else []
        for value in chain or []:
            ref = parse_model_ref(str(value))
            if ref not in seen:
                seen.add(ref)
                refs.append(ref)
    return refs


def provider_key_present(provider: str) -> bool:
    env_name = PROVIDER_KEYS.get(provider)
    return bool(env_name and os.environ.get(env_name))


def _provider_request(provider: str, url: str) -> dict[str, Any]:
    env_name = PROVIDER_KEYS.get(provider)
    key = os.environ.get(env_name or "")
    if not key:
        raise ProviderProbeError(provider, None, f"{env_name or provider + ' key'} is not configured")
    if provider == "anthropic":
        headers = {
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
        }
    elif provider == "openai":
        headers = {"Authorization": f"Bearer {key}"}
    else:
        raise ProviderProbeError(provider, None, f"unsupported provider: {provider}")
    request = Request(url, headers=headers)
    try:
        with urlopen(request, timeout=PROVIDER_TIMEOUT_SECONDS) as response:
            payload = json.load(response)
    except HTTPError as exc:
        raise ProviderProbeError(provider, exc.code, f"{provider} returned HTTP {exc.code}") from exc
    except (URLError, TimeoutError, ValueError) as exc:
        raise ProviderProbeError(provider, None, f"{provider} request failed: {exc}") from exc
    if not isinstance(payload, dict):
        raise ProviderProbeError(provider, None, f"{provider} returned a non-object response")
    return payload


def fetch_provider_models(provider: str) -> list[dict[str, Any]]:
    """Fetch a complete, bounded model listing from one provider."""
    if provider == "openai":
        payload = _provider_request(provider, "https://api.openai.com/v1/models")
        values = payload.get("data") or []
        return [item for item in values if isinstance(item, dict)]
    if provider != "anthropic":
        raise ProviderProbeError(provider, None, f"unsupported provider: {provider}")

    values: list[dict[str, Any]] = []
    after_id: str | None = None
    while True:
        url = "https://api.anthropic.com/v1/models?limit=1000"
        if after_id:
            url += f"&after_id={quote(after_id)}"
        payload = _provider_request(provider, url)
        values.extend(item for item in (payload.get("data") or []) if isinstance(item, dict))
        if not payload.get("has_more"):
            return values
        after_id = payload.get("last_id")
        if not after_id:
            raise ProviderProbeError(provider, None, "Anthropic pagination said has_more without last_id")


def probe_provider_model(provider: str, model: str) -> tuple[str, dict[str, Any] | None]:
    """Classify one list-missing model without turning a 403 into retirement."""
    if provider == "anthropic":
        url = f"https://api.anthropic.com/v1/models/{quote(model, safe='')}"
    elif provider == "openai":
        url = f"https://api.openai.com/v1/models/{quote(model, safe='')}"
    else:
        return "error", None
    try:
        return "available", _provider_request(provider, url)
    except ProviderProbeError as exc:
        if exc.status == 404:
            return "retired", None
        if exc.status == 403:
            return "unavailable", None
        return "error", None


def _anthropic_capability_record(item: dict[str, Any], previous: dict[str, Any]) -> dict[str, Any]:
    record = {
        "provider": "anthropic",
        "endpoint": "messages",
        "modalities": ["text", "image", "pdf"],
        "max_input_tokens": item.get("max_input_tokens"),
        "max_tokens": item.get("max_tokens"),
        "capabilities": copy.deepcopy(item.get("capabilities") or {}),
    }
    if previous.get("generation"):
        record["generation"] = copy.deepcopy(previous["generation"])
    return {key: value for key, value in record.items() if value is not None}


def doctor_report(
    config: dict[str, Any] | None = None,
    *,
    fetch_models: Any = fetch_provider_models,
    probe_model: Any = probe_provider_model,
    credential_present: Any = provider_key_present,
) -> dict[str, Any]:
    """Inspect configured models while preserving unavailable-vs-retired semantics."""
    config = copy.deepcopy(config or load_config())
    refs = configured_refs(config)
    providers: dict[str, Any] = {}
    models: list[dict[str, Any]] = []
    retired_candidates: dict[str, list[str]] = {}
    capability_updates: dict[str, dict[str, Any]] = {}
    warnings: list[str] = []

    for provider in sorted(set(PROVIDER_KEYS) | {item[0] for item in refs}):
        provider_refs = [model for item_provider, model in refs if item_provider == provider]
        env_name = PROVIDER_KEYS.get(provider, f"{provider.upper()}_API_KEY")
        if not credential_present(provider):
            message = f"{provider}: {env_name} absent; optional provider skipped"
            providers[provider] = {"status": "skipped", "models": 0, "warning": message}
            warnings.append(message)
            for model in provider_refs:
                models.append({"provider": provider, "model": model, "status": "unchecked"})
            continue
        try:
            listing = fetch_models(provider)
        except ProviderProbeError as exc:
            status = "unavailable" if exc.status == 403 else "error"
            message = f"{provider}: {exc}"
            providers[provider] = {"status": status, "models": 0, "warning": message}
            warnings.append(message)
            for model in provider_refs:
                models.append({"provider": provider, "model": model, "status": status})
            continue

        by_id = {
            str(item.get("id")): item
            for item in listing
            if isinstance(item, dict) and item.get("id")
        }
        providers[provider] = {"status": "ok", "models": len(by_id)}
        for model in provider_refs:
            item = by_id.get(model)
            status = "available"
            if item is None:
                status, item = probe_model(provider, model)
            models.append({"provider": provider, "model": model, "status": status})
            if status == "retired":
                retired_candidates.setdefault(provider, []).append(model)
            elif status == "unavailable":
                warnings.append(f"{provider}/{model}: unavailable to these credentials; not retired")
            elif status == "available" and provider == "anthropic" and item:
                key = f"{provider}/{model}"
                previous = model_record(config, provider, model)
                capability_updates[key] = _anthropic_capability_record(item, previous)

    return {
        "ok": (
            not any(item.get("status") == "error" for item in providers.values())
            and not any(item.get("status") == "error" for item in models)
        ),
        "providers": providers,
        "models": models,
        "retired_candidates": retired_candidates,
        "capability_updates": capability_updates,
        "warnings": warnings,
    }


def apply_doctor_fixes(report: dict[str, Any], config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Persist only verified retirements plus provider-published capability refreshes."""
    config = copy.deepcopy(config or load_config())
    retired = config.setdefault("retired", {})
    for provider, values in (report.get("retired_candidates") or {}).items():
        current = retired.setdefault(provider, [])
        for model in values:
            if model not in current:
                current.append(model)
    records = config.setdefault("models", {})
    for key, record in (report.get("capability_updates") or {}).items():
        records[key] = record
    write_config(config)
    return config


def write_config(config: dict[str, Any]) -> None:
    """Atomically persist model configuration; JSON remains valid YAML as a fallback."""
    path = models_file()
    if yaml is not None:
        content = yaml.safe_dump(config, sort_keys=False, width=100)
    else:
        content = json.dumps(config, indent=2) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        handle.write(content)
        temp_path = Path(handle.name)
    temp_path.replace(path)
