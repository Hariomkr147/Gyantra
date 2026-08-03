"""
LLM provider adapters.

Each provider knows how to:
  - report whether it is configured,
  - build a request for a chat completion with forced JSON output,
  - parse the response into (text, prompt_tokens, completion_tokens),
  - classify an HTTP error as retryable or permanent.

That last point matters. The original client retried every failure, so a
permanently dead model ID (HTTP 404) burned three attempts with backoff on every
stage before failing over — which is what made the pipeline appear to hang.
Permanent errors now fail over immediately.
"""

from __future__ import annotations

import json
import logging
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger("gyantra.providers")


class ErrorKind:
    """How the client should react to a failed call."""

    RETRY = "retry"          # transient: rate limit, 5xx, timeout
    FAILOVER = "failover"    # permanent for this model/provider: 404, 401, 403
    FATAL = "fatal"          # misconfiguration the user must fix


@dataclass
class ProviderResponse:
    text: str
    prompt_tokens: int = 0
    completion_tokens: int = 0


@dataclass
class ProviderError(Exception):
    message: str
    kind: str = ErrorKind.RETRY
    status: int | None = None
    provider: str = ""
    model: str = ""

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"{self.provider}/{self.model} [{self.kind}] {self.message}"


def classify_status(status: int) -> str:
    """Map an HTTP status onto a reaction.

    404 → the model ID does not exist on this provider. Retrying is pointless.
    401/403 → the key is missing, invalid, or lacks access. Also pointless.
    429 → rate limited; the caller refines this using the stated retry delay.
    5xx → provider-side hiccup; worth a retry.
    """
    if status == 429:
        return ErrorKind.RETRY
    if status in (401, 403):
        return ErrorKind.FAILOVER
    if status == 404:
        return ErrorKind.FAILOVER
    if status == 400:
        # Usually an unsupported parameter for this model (e.g. response_format).
        return ErrorKind.FAILOVER
    if 500 <= status < 600:
        return ErrorKind.RETRY
    return ErrorKind.RETRY


# "Please try again in 25m37.056s" / "try again in 41.2s" / "retry after 30 seconds"
_RETRY_AFTER = re.compile(
    r"(?:try again|retry(?:\s+after)?)\s+in\s+"
    r"(?:(\d+)\s*m)?\s*(?:([\d.]+)\s*s)?",
    re.IGNORECASE,
)


def parse_retry_delay(message: str) -> float | None:
    """Seconds the provider asked us to wait, if it said.

    Rate-limit bodies frequently carry a concrete delay. Honouring it turns a
    blind retry loop into an informed decision: wait if it's short, fail over to
    another provider if it's minutes away.
    """
    match = _RETRY_AFTER.search(message or "")
    if not match:
        return None
    minutes, seconds = match.groups()
    if minutes is None and seconds is None:
        return None
    total = 0.0
    if minutes:
        total += float(minutes) * 60
    if seconds:
        total += float(seconds)
    return total or None


class BaseProvider(ABC):
    """Common interface for every LLM backend."""

    name: str = "base"
    #: Whether this provider supports a JSON-schema-constrained response.
    supports_json_schema: bool = False

    def __init__(self, settings):
        self.settings = settings

    @abstractmethod
    def is_configured(self) -> bool:
        """True when the provider has credentials and can be called."""

    @abstractmethod
    def model_for_role(self, role: str) -> str:
        """Concrete model ID for a logical role."""

    @abstractmethod
    def build_request(
        self,
        model: str,
        system_prompt: str,
        user_prompt: str,
        json_schema: dict | None,
        max_tokens: int,
        temperature: float,
    ) -> tuple[str, dict, dict]:
        """Return (url, headers, json_body)."""

    @abstractmethod
    def parse_response(self, payload: dict) -> ProviderResponse:
        """Extract text and token counts from a successful response body."""

    def extract_error(self, status: int, body: str) -> str:
        """Pull a human-readable message out of an error body."""
        try:
            data = json.loads(body)
            err = data.get("error")
            if isinstance(err, dict):
                return str(err.get("message") or err)
            if isinstance(err, str):
                return err
            if isinstance(data.get("message"), str):
                return data["message"]
        except (json.JSONDecodeError, TypeError):
            pass
        return body[:300] or f"HTTP {status}"


# ── Gemini (Google AI Studio) ────────────────────────────────────────────────


class GeminiProvider(BaseProvider):
    """Google AI Studio / Gemini generative-language API.

    Uses a different wire format from the OpenAI-compatible providers: the
    system prompt is `systemInstruction`, messages are `contents`, and JSON mode
    is requested via `responseMimeType` plus an optional `responseSchema`.
    """

    name = "gemini"
    supports_json_schema = True

    def is_configured(self) -> bool:
        return bool(self.settings.gemini_api_key)

    def model_for_role(self, role: str) -> str:
        return getattr(
            self.settings, f"gemini_model_{role}", self.settings.gemini_model_generate
        )

    def build_request(
        self,
        model: str,
        system_prompt: str,
        user_prompt: str,
        json_schema: dict | None,
        max_tokens: int,
        temperature: float,
    ) -> tuple[str, dict, dict]:
        base = self.settings.gemini_base_url.rstrip("/")
        url = f"{base}/models/{model}:generateContent"

        # Gemini's newer flash models reason before answering, and those
        # thinking tokens come out of maxOutputTokens. A stage asking for 300
        # tokens can spend 284 on thoughts and return a truncated answer, so
        # grant headroom on top of what the caller requested.
        budget = max_tokens + self.settings.gemini_thinking_headroom

        generation_config: dict[str, Any] = {
            "temperature": temperature,
            "maxOutputTokens": budget,
        }
        if json_schema is not None:
            generation_config["responseMimeType"] = "application/json"
            cleaned = _to_gemini_schema(json_schema)
            if cleaned:
                generation_config["responseSchema"] = cleaned

        body = {
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
            "generationConfig": generation_config,
        }

        headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": self.settings.gemini_api_key,
        }
        return url, headers, body

    def parse_response(self, payload: dict) -> ProviderResponse:
        candidates = payload.get("candidates") or []
        if not candidates:
            # A prompt blocked by safety filters comes back with no candidates.
            feedback = payload.get("promptFeedback") or {}
            reason = feedback.get("blockReason")
            raise ProviderError(
                message=f"no candidates returned{f' (blocked: {reason})' if reason else ''}",
                kind=ErrorKind.RETRY,
                provider=self.name,
            )

        candidate = candidates[0]
        finish = candidate.get("finishReason")

        parts = (candidate.get("content") or {}).get("parts") or []
        text = "".join(p.get("text", "") for p in parts)

        if not text.strip():
            # MAX_TOKENS with no text means the model spent its whole budget on
            # reasoning and never reached the answer. A retry with the same
            # budget does the same thing, but the budget only grows on retry, so
            # classify as retryable — the caller will resend with headroom.
            raise ProviderError(
                message=f"empty response (finishReason={finish}) — "
                "model spent its output budget on reasoning",
                kind=ErrorKind.RETRY,
                provider=self.name,
            )

        usage = payload.get("usageMetadata") or {}
        return ProviderResponse(
            text=text,
            prompt_tokens=int(usage.get("promptTokenCount", 0) or 0),
            completion_tokens=int(usage.get("candidatesTokenCount", 0) or 0),
        )


# Keys that Gemini's responseSchema does not accept.
_GEMINI_SCHEMA_DROP = {
    "title", "$schema", "$defs", "definitions", "additionalProperties",
    "default", "examples", "const", "$ref", "anyOf", "oneOf", "allOf",
    "exclusiveMinimum", "exclusiveMaximum", "patternProperties",
}


def _to_gemini_schema(schema: dict) -> dict | None:
    """Strip JSON-Schema keywords Gemini rejects, or return None if unusable.

    Two failure modes to avoid:

    1. Gemini accepts only a restricted OpenAPI subset — a full JSON Schema gets
       the request rejected with a 400, so unsupported keys are removed.
    2. A schema with no `properties` (e.g. a bare `{"type": "object"}`) is
       *satisfied by an empty object*, and Gemini duly returns `{}`. That is
       worse than sending no schema at all, because the prompts already specify
       the shape in prose. Such schemas are dropped.
    """
    if not isinstance(schema, dict):
        return None

    def clean(node: Any) -> Any:
        if isinstance(node, list):
            return [clean(n) for n in node]
        if not isinstance(node, dict):
            return node

        out: dict[str, Any] = {}
        for key, value in node.items():
            if key in _GEMINI_SCHEMA_DROP:
                continue
            if key == "properties" and isinstance(value, dict):
                out[key] = {k: clean(v) for k, v in value.items()}
            else:
                out[key] = clean(value)
        return out

    cleaned = clean(schema)
    node_type = cleaned.get("type")

    # An object schema is only useful if it names properties.
    if node_type == "object" or "properties" in cleaned:
        properties = cleaned.get("properties")
        if not isinstance(properties, dict) or not properties:
            return None
        return cleaned

    # An array schema is only useful if it describes its items.
    if node_type == "array":
        items = cleaned.get("items")
        if not isinstance(items, dict) or not items:
            return None
        return cleaned

    return cleaned if node_type else None


# ── OpenAI-compatible providers (OpenRouter, Groq) ───────────────────────────


class OpenAICompatProvider(BaseProvider):
    """Shared implementation for providers that speak the OpenAI chat format."""

    supports_json_schema = True

    #: settings attribute names, filled in by subclasses
    key_attr: str = ""
    base_url_attr: str = ""
    model_prefix: str = ""

    def is_configured(self) -> bool:
        return bool(getattr(self.settings, self.key_attr, ""))

    def model_for_role(self, role: str) -> str:
        return getattr(
            self.settings,
            f"{self.model_prefix}_{role}",
            getattr(self.settings, f"{self.model_prefix}_generate"),
        )

    def extra_headers(self) -> dict:
        return {}

    def build_request(
        self,
        model: str,
        system_prompt: str,
        user_prompt: str,
        json_schema: dict | None,
        max_tokens: int,
        temperature: float,
    ) -> tuple[str, dict, dict]:
        base = getattr(self.settings, self.base_url_attr).rstrip("/")
        url = f"{base}/chat/completions"

        body: dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if json_schema is not None:
            # json_object is far more widely supported than json_schema across
            # open-weight models, and the prompts already specify the shape.
            body["response_format"] = {"type": "json_object"}

        headers = {
            "Authorization": f"Bearer {getattr(self.settings, self.key_attr)}",
            "Content-Type": "application/json",
            **self.extra_headers(),
        }
        return url, headers, body

    def parse_response(self, payload: dict) -> ProviderResponse:
        choices = payload.get("choices") or []
        if not choices:
            # Some gateways return {"error": ...} with HTTP 200.
            err = payload.get("error")
            msg = (
                str(err.get("message")) if isinstance(err, dict) else str(err or "no choices")
            )
            raise ProviderError(message=msg, kind=ErrorKind.RETRY, provider=self.name)

        message = choices[0].get("message") or {}
        text = message.get("content") or ""

        if not text.strip():
            raise ProviderError(
                message=f"empty content (finish_reason={choices[0].get('finish_reason')})",
                kind=ErrorKind.RETRY,
                provider=self.name,
            )

        usage = payload.get("usage") or {}
        return ProviderResponse(
            text=text,
            prompt_tokens=int(usage.get("prompt_tokens", 0) or 0),
            completion_tokens=int(usage.get("completion_tokens", 0) or 0),
        )


class OpenRouterProvider(OpenAICompatProvider):
    name = "openrouter"
    key_attr = "openrouter_api_key"
    base_url_attr = "openrouter_base_url"
    model_prefix = "openrouter_model"

    def extra_headers(self) -> dict:
        # OpenRouter uses these for attribution on the dashboard.
        return {
            "HTTP-Referer": "https://gyantra.local",
            "X-Title": "Gyantra",
        }


class GroqProvider(OpenAICompatProvider):
    name = "groq"
    key_attr = "groq_api_key"
    base_url_attr = "groq_base_url"
    model_prefix = "groq_model"


class RoutesMeProvider(OpenAICompatProvider):
    """Generic OpenAI-compatible gateway (routesme.online and similar).

    Kept separate from OpenRouter because the base URL and model naming differ.
    Dormant unless ROUTESME_API_KEY is set, so an unconfigured gateway costs
    nothing.
    """

    name = "routesme"
    key_attr = "routesme_api_key"
    base_url_attr = "routesme_base_url"
    model_prefix = "routesme_model"


class NvidiaProvider(OpenAICompatProvider):
    name = "nvidia"
    key_attr = "nvidia_api_key"
    base_url_attr = "nvidia_base_url"
    model_prefix = "nvidia_model"


# ── registry ─────────────────────────────────────────────────────────────────

PROVIDER_CLASSES: dict[str, type[BaseProvider]] = {
    "gemini": GeminiProvider,
    "openrouter": OpenRouterProvider,
    "groq": GroqProvider,
    "routesme": RoutesMeProvider,
    "nvidia": NvidiaProvider,
}


def build_providers(settings) -> list[BaseProvider]:
    """Instantiate configured providers in the order given by LLM_PROVIDER.

    Unknown names are logged and skipped rather than raising, so a typo in the
    env var degrades to the remaining providers instead of breaking startup.
    """
    ordered: list[BaseProvider] = []
    seen: set[str] = set()

    for name in settings.provider_order:
        cls = PROVIDER_CLASSES.get(name)
        if cls is None:
            logger.warning(
                "unknown provider %r in LLM_PROVIDER; valid options: %s",
                name, ", ".join(PROVIDER_CLASSES),
            )
            continue
        if name in seen:
            continue
        seen.add(name)
        provider = cls(settings)
        if provider.is_configured():
            ordered.append(provider)

    # Any provider with a key but absent from LLM_PROVIDER still gets used as a
    # last-resort fallback — having a key set should be enough to be useful.
    for name, cls in PROVIDER_CLASSES.items():
        if name in seen:
            continue
        provider = cls(settings)
        if provider.is_configured():
            ordered.append(provider)

    return ordered
