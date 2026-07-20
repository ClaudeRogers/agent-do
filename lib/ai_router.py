"""Small optional AI helpers for routing and hook gating."""

from __future__ import annotations

import json
import os
import sys
from base64 import b64encode
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import anthropic
except ModuleNotFoundError:  # pragma: no cover - exercised through fallbacks
    anthropic = None

try:
    import openai
except ModuleNotFoundError:  # pragma: no cover - exercised through fallbacks
    openai = None

from models import candidates, generation_params, load_config, model_record, resolve

DEFAULT_MAX_TOKENS = 64000
DEFAULT_CLIENT_TIMEOUT_SECONDS = 30.0
DEFAULT_CLIENT_RETRIES = 2


def _flag_value(name: str, override: str | None = None) -> str:
    value = override
    if value is None:
        value = os.environ.get(name)
    if value is None:
        value = os.environ.get("AGENT_DO_AI")
    return (value or "auto").strip().lower()


def ai_requested(name: str, override: str | None = None) -> bool:
    """Return whether an optional AI path should attempt a model call."""
    value = _flag_value(name, override)
    if value in {"0", "false", "no", "off", "never", "disabled"}:
        return False
    available = (
        (anthropic is not None and bool(os.environ.get("ANTHROPIC_API_KEY")))
        or (openai is not None and bool(os.environ.get("OPENAI_API_KEY")))
    )
    if value in {"1", "true", "yes", "on", "always"}:
        return available
    return available


def ai_model() -> str:
    return resolve("fast")["model"]


def ai_max_tokens() -> int:
    value = os.environ.get("AGENT_DO_AI_MAX_TOKENS")
    if value:
        try:
            parsed = int(value)
            if parsed > 0:
                return parsed
        except ValueError:
            pass
    return DEFAULT_MAX_TOKENS


def ai_effort() -> str:
    return os.environ.get("AGENT_DO_AI_EFFORT", "max")


def _message_text(response: Any) -> str:
    chunks = getattr(response, "content", None) or []
    texts: list[str] = []
    for chunk in chunks:
        if isinstance(chunk, dict):
            text = chunk.get("text")
        else:
            text = getattr(chunk, "text", None)
        if text:
            texts.append(str(text))
    return "\n".join(texts)


@dataclass
class LLMResponse:
    text: str
    provider: str
    model: str
    raw: Any


def _plain_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return str(content or "")
    texts: list[str] = []
    for item in content:
        if not isinstance(item, dict):
            continue
        if item.get("type") in {"text", "input_text", "output_text"} and item.get("text"):
            texts.append(str(item["text"]))
    return "\n".join(texts)


def _image_payload(image: Any) -> tuple[str, str]:
    if isinstance(image, (str, Path)):
        path = Path(image)
        suffix = path.suffix.lower()
        mime = "image/jpeg" if suffix in {".jpg", ".jpeg"} else "image/png"
        return mime, b64encode(path.read_bytes()).decode("ascii")
    if not isinstance(image, dict):
        raise ValueError("images must be paths or mappings")
    if image.get("path"):
        return _image_payload(image["path"])
    data = image.get("data") or image.get("base64")
    if not data:
        raise ValueError("image mapping requires path, data, or base64")
    return str(image.get("mime_type") or image.get("media_type") or "image/png"), str(data)


def _cap_tokens(provider: str, model: str, requested: int) -> int:
    configured = model_record(load_config(), provider, model).get("max_tokens")
    if isinstance(configured, int) and configured > 0:
        return min(requested, configured)
    return requested


def _anthropic_call(
    role: str,
    model: str,
    messages: list[dict[str, Any]],
    *,
    json_schema: dict[str, Any] | None,
    images: list[Any],
    max_tokens: int,
    timeout_seconds: float,
    max_retries: int,
) -> LLMResponse:
    if anthropic is None or not os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError("ANTHROPIC_API_KEY or Anthropic SDK is unavailable")
    system_parts = [_plain_content(item.get("content")) for item in messages if item.get("role") == "system"]
    vendor_messages = [
        {"role": item.get("role", "user"), "content": _plain_content(item.get("content"))}
        for item in messages
        if item.get("role") in {"user", "assistant"}
    ]
    if images:
        blocks = [
            {
                "type": "image",
                "source": {"type": "base64", "media_type": mime, "data": data},
            }
            for mime, data in (_image_payload(image) for image in images)
        ]
        if vendor_messages and vendor_messages[-1]["role"] == "user":
            text = _plain_content(vendor_messages[-1]["content"])
            vendor_messages[-1]["content"] = [*blocks, {"type": "text", "text": text}]
        else:
            vendor_messages.append({"role": "user", "content": blocks})
    kwargs: dict[str, Any] = {
        "model": model,
        "max_tokens": _cap_tokens("anthropic", model, max_tokens),
        "messages": vendor_messages,
    }
    kwargs.update(generation_params(model, "anthropic", role))
    if system_parts:
        kwargs["system"] = "\n\n".join(part for part in system_parts if part)
    if json_schema:
        output_config = kwargs.setdefault("output_config", {})
        output_config["format"] = {"type": "json_schema", "schema": json_schema}
    response = anthropic.Anthropic(timeout=timeout_seconds, max_retries=max_retries).messages.create(**kwargs)
    return LLMResponse(_message_text(response), "anthropic", model, response)


def _openai_call(
    role: str,
    model: str,
    messages: list[dict[str, Any]],
    *,
    json_schema: dict[str, Any] | None,
    images: list[Any],
    max_tokens: int,
    timeout_seconds: float,
    max_retries: int,
) -> LLMResponse:
    if openai is None or not os.environ.get("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY or OpenAI SDK is unavailable")
    vendor_messages: list[dict[str, Any]] = []
    for item in messages:
        message_role = item.get("role", "user")
        if message_role == "system":
            message_role = "developer"
        vendor_messages.append({"role": message_role, "content": _plain_content(item.get("content"))})
    if images:
        blocks = [
            {"type": "input_image", "image_url": f"data:{mime};base64,{data}"}
            for mime, data in (_image_payload(image) for image in images)
        ]
        if vendor_messages and vendor_messages[-1]["role"] == "user":
            text = _plain_content(vendor_messages[-1]["content"])
            vendor_messages[-1]["content"] = [{"type": "input_text", "text": text}, *blocks]
        else:
            vendor_messages.append({"role": "user", "content": blocks})
    kwargs: dict[str, Any] = {
        "model": model,
        "input": vendor_messages,
        "max_output_tokens": _cap_tokens("openai", model, max_tokens),
        "store": False,
    }
    kwargs.update(generation_params(model, "openai", role))
    if json_schema:
        kwargs["text"] = {
            "format": {
                "type": "json_schema",
                "name": "agent_do_response",
                "schema": json_schema,
                "strict": True,
            }
        }
    response = openai.OpenAI(timeout=timeout_seconds, max_retries=max_retries).responses.create(**kwargs)
    return LLMResponse(str(response.output_text or ""), "openai", model, response)


def _model_not_found(exc: Exception) -> bool:
    return getattr(exc, "status_code", getattr(exc, "status", None)) == 404


def _report_fallback(role: str, failed: dict[str, Any], selected: dict[str, Any]) -> None:
    print(
        f"agent-do models: {failed['provider']}/{failed['model']} was not found; "
        f"falling back to {selected['provider']}/{selected['model']}",
        file=sys.stderr,
    )
    try:
        from telemetry import append_event

        append_event(
            "model_fallback",
            "models",
            role=role,
            failed_provider=failed["provider"],
            failed_model=failed["model"],
            selected_provider=selected["provider"],
            selected_model=selected["model"],
        )
    except Exception:
        pass


def llm_call(
    role: str,
    messages: list[dict[str, Any]],
    *,
    json_schema: dict[str, Any] | None = None,
    images: list[Any] | None = None,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    timeout_seconds: float = DEFAULT_CLIENT_TIMEOUT_SECONDS,
    max_retries: int = DEFAULT_CLIENT_RETRIES,
) -> LLMResponse:
    """Call an internal role, crossing providers only on model-not-found."""
    chain = [
        selected
        for selected in candidates(role)
        if (
            selected["provider"] == "anthropic"
            and anthropic is not None
            and os.environ.get("ANTHROPIC_API_KEY")
        ) or (
            selected["provider"] == "openai"
            and openai is not None
            and os.environ.get("OPENAI_API_KEY")
        )
    ]
    if not chain:
        raise RuntimeError(f"no configured provider credential and SDK can serve model role '{role}'")
    last_error: Exception | None = None
    failed: dict[str, Any] | None = None
    for selected in chain:
        if failed is not None:
            _report_fallback(role, failed, selected)
            failed = None
        try:
            if selected["provider"] == "anthropic":
                return _anthropic_call(
                    role, selected["model"], messages, json_schema=json_schema,
                    images=images or [], max_tokens=max_tokens,
                    timeout_seconds=timeout_seconds, max_retries=max_retries,
                )
            if selected["provider"] == "openai":
                return _openai_call(
                    role, selected["model"], messages, json_schema=json_schema,
                    images=images or [], max_tokens=max_tokens,
                    timeout_seconds=timeout_seconds, max_retries=max_retries,
                )
            raise RuntimeError(f"unsupported model provider: {selected['provider']}")
        except Exception as exc:
            if not _model_not_found(exc):
                raise
            last_error = exc
            failed = selected
    raise RuntimeError(f"model chain exhausted for role '{role}'") from last_error


def _extract_json(text: str) -> dict | None:
    stripped = text.strip()
    if "```json" in stripped:
        stripped = stripped.split("```json", 1)[1].split("```", 1)[0].strip()
    elif stripped.startswith("```") and "```" in stripped[3:]:
        stripped = stripped.split("```", 1)[1].split("```", 1)[0].strip()

    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            payload = json.loads(stripped[start : end + 1])
        except json.JSONDecodeError:
            return None

    return payload if isinstance(payload, dict) else None


def call_json_model(
    prompt: str,
    *,
    flag_name: str,
    flag_override: str | None = None,
    max_tokens: int | None = None,
    system: str | None = None,
    timeout_seconds: float = DEFAULT_CLIENT_TIMEOUT_SECONDS,
    max_retries: int = DEFAULT_CLIENT_RETRIES,
) -> dict | None:
    """Call the configured fast model and parse a JSON object, returning None on fallback-worthy failure."""
    if not ai_requested(flag_name, flag_override):
        return None

    messages: list[dict[str, Any]] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    try:
        response = llm_call(
            "fast",
            messages,
            max_tokens=max_tokens or ai_max_tokens(),
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
        )
    except Exception:
        return None

    payload = _extract_json(response.text)
    if payload is not None:
        payload.setdefault("_model", response.model)
        payload.setdefault("_provider", response.provider)
    return payload
