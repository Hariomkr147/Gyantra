"""
Provider-agnostic LLM client.

Behaviour that matters:
 - Providers are tried in configured order; Gemini is the default primary.
 - A *permanent* failure (dead model ID, bad key) fails over immediately
   instead of burning retries. This was the cause of the pipeline appearing to
   hang at 10%: every stage retried a 404 three times with backoff before
   moving on.
 - A *transient* failure (429, 5xx, timeout) retries with backoff.
 - Every attempt is logged with provider, model, status and elapsed time, so a
   stall is visible in the log rather than silent.
 - Responses are cached on disk by (provider, model, prompt).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

from app.config import settings
from app.services.model_registry import role_for_stage
from app.services.providers import (
    BaseProvider,
    ErrorKind,
    ProviderError,
    build_providers,
    classify_status,
    parse_retry_delay,
)

logger = logging.getLogger("gyantra.llm")


class LLMError(RuntimeError):
    """Raised when every provider/model attempt has failed.

    Carries a user-facing summary so the API can surface something actionable
    rather than a stack trace.
    """

    def __init__(self, message: str, attempts: list[str] | None = None):
        super().__init__(message)
        self.attempts = attempts or []

    def user_message(self) -> str:
        if not self.attempts:
            return str(self)
        return f"{self}\n\nAttempts:\n" + "\n".join(f"  - {a}" for a in self.attempts)


@dataclass
class LLMUsage:
    calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cache_hits: int = 0
    failures: int = 0
    by_model: dict[str, int] = field(default_factory=dict)

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    def record(self, model: str, prompt_t: int, completion_t: int) -> None:
        self.calls += 1
        self.prompt_tokens += prompt_t
        self.completion_tokens += completion_t
        self.by_model[model] = self.by_model.get(model, 0) + 1


# Reasoning models wrap their chain-of-thought in these before the real answer.
_REASONING_BLOCK = re.compile(
    r"<(think|thinking|reasoning|scratchpad)>.*?</\1>", re.DOTALL | re.IGNORECASE
)
# An unterminated opening tag means the model ran out of tokens mid-thought.
_UNCLOSED_REASONING = re.compile(
    r"<(?:think|thinking|reasoning|scratchpad)>", re.IGNORECASE
)


def _extract_json(text: str) -> Any:
    """Best-effort JSON extraction from a model response.

    Handles fenced blocks, leading prose, and reasoning-model preambles. The
    last one matters in practice: several open-weight models emit a <think>
    block before the JSON, which makes a naive json.loads fail on otherwise
    perfectly good output.
    """
    text = (text or "").strip()
    if not text:
        raise ValueError("empty response")

    text = _REASONING_BLOCK.sub("", text).strip()

    # Unclosed reasoning tag: keep only what follows the last one.
    if _UNCLOSED_REASONING.search(text):
        parts = _UNCLOSED_REASONING.split(text)
        text = parts[-1].strip()

    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Find the outermost balanced object or array.
    for opener, closer in (("{", "}"), ("[", "]")):
        start = text.find(opener)
        if start == -1:
            continue
        depth = 0
        in_str = False
        escape = False
        for i in range(start, len(text)):
            ch = text[i]
            if escape:
                escape = False
                continue
            if ch == "\\":
                escape = True
                continue
            if ch == '"':
                in_str = not in_str
                continue
            if in_str:
                continue
            if ch == opener:
                depth += 1
            elif ch == closer:
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start : i + 1])
                    except json.JSONDecodeError:
                        break

    raise ValueError(f"could not parse JSON from response: {text[:300]}")


class LLMClient:
    """Async client that routes a stage to the right provider and model."""

    def __init__(self, usage: LLMUsage | None = None, telemetry: Any | None = None):
        self.usage = usage or LLMUsage()
        self.telemetry = telemetry
        self._client: httpx.AsyncClient | None = None
        self._providers: list[BaseProvider] = build_providers(settings)
        self._cache_dir = Path(settings.cache_dir)
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        # Providers that returned a permanent error this run — skipped from then
        # on so one dead provider doesn't cost latency on every later stage.
        self._dead: set[str] = set()
        # Per-provider request rate limiting. Free tiers quote small per-minute
        # request budgets (e.g. Gemini flash = 20/min); a pipeline that fires
        # ten calls in rapid succession trips them even though the key is fine.
        # A token bucket spaces requests out instead of failing.
        self._last_request_at: dict[str, float] = {}
        self._throttle_lock = asyncio.Lock()

    async def _throttle(self, provider_name: str) -> None:
        """Wait so requests to *provider_name* stay inside its per-minute budget.

        Free tiers enforce a request-per-minute cap: gemini-flash-latest allows
        20/min. The pipeline's parallel stages fire faster than that, which
        produced 429s and cascaded into "all providers failed" even though every
        key was valid. Spacing requests out fixes the cause rather than
        retrying into the same wall.
        """
        budget = getattr(settings, f"{provider_name}_requests_per_minute", 0)
        if not budget:
            return

        async with self._throttle_lock:
            interval = 60.0 / budget
            prev = self._last_request_at.get(provider_name, 0.0)
            wait = interval - (time.monotonic() - prev)
            if wait > 0:
                # asyncio.sleep, not time.sleep — blocking here would freeze the
                # event loop and with it the SSE progress stream.
                await asyncio.sleep(wait)
            self._last_request_at[provider_name] = time.monotonic()

    async def __aenter__(self) -> "LLMClient":
        timeout = httpx.Timeout(
            settings.llm_timeout_seconds,
            connect=15.0,
            read=settings.llm_timeout_seconds,
        )
        self._client = httpx.AsyncClient(timeout=timeout)
        return self

    async def __aexit__(self, *exc) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    def available_providers(self) -> list[str]:
        return [p.name for p in self._providers]

    def describe_routing(self) -> dict[str, str]:
        """Which model each role resolves to, for logging and /api/health."""
        if not self._providers:
            return {}
        primary = self._providers[0]
        return {
            role: f"{primary.name}/{primary.model_for_role(role)}"
            for role in ("fast", "extract", "plan", "generate", "validate")
        }

    # ── caching ──────────────────────────────────────────────────────────

    def _cache_key(self, provider: str, model: str, system: str, user: str) -> str:
        blob = json.dumps(
            {"p": provider, "m": model, "s": system, "u": user}, sort_keys=True
        )
        return hashlib.sha256(blob.encode()).hexdigest()[:32]

    def _cache_read(self, key: str) -> Any | None:
        if not settings.llm_cache_enabled:
            return None
        path = self._cache_dir / f"{key}.json"
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None

    def _cache_write(self, key: str, value: Any) -> None:
        if not settings.llm_cache_enabled:
            return
        try:
            (self._cache_dir / f"{key}.json").write_text(
                json.dumps(value, ensure_ascii=False), encoding="utf-8"
            )
        except OSError as exc:
            logger.debug("cache write failed: %s", exc)

    # ── single attempt ───────────────────────────────────────────────────

    async def _attempt(
        self,
        provider: BaseProvider,
        model: str,
        system_prompt: str,
        user_prompt: str,
        json_schema: dict | None,
        max_tokens: int,
        temperature: float,
    ):
        assert self._client is not None, "LLMClient must be used as a context manager"

        url, headers, body = provider.build_request(
            model, system_prompt, user_prompt, json_schema, max_tokens, temperature
        )

        # Space this request out from the previous one to the same provider.
        # Free tiers quota per-minute requests; without this the pipeline's
        # parallel stages trip the limit and fail over to exhausted providers.
        await self._throttle(provider.name)

        started = time.monotonic()
        try:
            resp = await self._client.post(url, json=body, headers=headers)
        except httpx.TimeoutException as exc:
            raise ProviderError(
                message=f"timed out after {settings.llm_timeout_seconds}s",
                kind=ErrorKind.RETRY,
                provider=provider.name,
                model=model,
            ) from exc
        except httpx.HTTPError as exc:
            raise ProviderError(
                message=f"connection error: {exc}",
                kind=ErrorKind.RETRY,
                provider=provider.name,
                model=model,
            ) from exc

        elapsed = time.monotonic() - started

        if resp.status_code >= 400:
            message = provider.extract_error(resp.status_code, resp.text)
            kind = classify_status(resp.status_code)

            delay = None
            if resp.status_code == 429:
                delay = parse_retry_delay(message)
                if delay is not None and delay > settings.rate_limit_wait_ceiling:
                    kind = ErrorKind.FAILOVER
                    message = (
                        f"rate limited for {delay:.0f}s "
                        f"(over the {settings.rate_limit_wait_ceiling}s ceiling) — "
                        f"{message}"
                    )

            raise ProviderError(
                message=f"HTTP {resp.status_code}: {message}",
                kind=kind,
                status=resp.status_code,
                provider=provider.name,
                model=model,
                retry_after=delay,
            )

        try:
            payload = resp.json()
        except (json.JSONDecodeError, ValueError) as exc:
            raise ProviderError(
                message=f"non-JSON response body: {resp.text[:200]}",
                kind=ErrorKind.RETRY,
                provider=provider.name,
                model=model,
            ) from exc

        result = provider.parse_response(payload)
        result_elapsed = elapsed
        return result, result_elapsed

    # ── public API ───────────────────────────────────────────────────────

    async def complete_json(
        self,
        stage: str,
        system_prompt: str,
        user_prompt: str,
        json_schema: dict | None = None,
        max_tokens: int = 2400,
        temperature: float | None = None,
    ) -> Any:
        """Run a stage-appropriate model and return parsed JSON."""
        temp = settings.llm_temperature if temperature is None else temperature
        role = role_for_stage(stage)

        if not self._providers:
            raise LLMError(
                "No LLM provider is configured. Set GEMINI_API_KEY (recommended), "
                "OPENROUTER_API_KEY, or GROQ_API_KEY — or set DEMO_MODE=true to "
                "run offline."
            )

        attempts: list[str] = []
        current_user_prompt = user_prompt

        for provider in self._providers:
            if provider.name in self._dead:
                continue

            model = provider.model_for_role(role)

            cached = self._cache_read(
                self._cache_key(provider.name, model, system_prompt, user_prompt)
            )
            if cached is not None:
                self.usage.cache_hits += 1
                if self.telemetry:
                    self.telemetry.record_llm_call(stage, provider.name, model, 0, 0, 0, True, 1)
                logger.info("[%s] cache hit  %s/%s", stage, provider.name, model)
                return cached

            for attempt in range(settings.llm_max_retries + 1):
                try:
                    response, elapsed = await self._attempt(
                        provider,
                        model,
                        system_prompt,
                        current_user_prompt,
                        json_schema,
                        max_tokens,
                        temp,
                    )
                    parsed = _extract_json(response.text)

                    self.usage.record(
                        f"{provider.name}/{model}",
                        response.prompt_tokens,
                        response.completion_tokens,
                    )
                    self._cache_write(
                        self._cache_key(provider.name, model, system_prompt, user_prompt),
                        parsed,
                    )
                    if self.telemetry:
                        self.telemetry.record_llm_call(
                            stage, provider.name, model, int(elapsed * 1000),
                            response.prompt_tokens, response.completion_tokens,
                            False, attempt + 1
                        )
                    logger.info(
                        "[%s] ok  %s/%s  %.1fs  %s+%s tok",
                        stage, provider.name, model, elapsed,
                        response.prompt_tokens, response.completion_tokens,
                    )
                    return parsed

                except ProviderError as exc:
                    self.usage.failures += 1
                    attempts.append(str(exc))
                    if self.telemetry:
                        self.telemetry.record_llm_call(
                            stage, provider.name, model, 0,
                            0, 0, False, attempt + 1, status=f"failed: {exc.message}"
                        )

                    if exc.kind == ErrorKind.FAILOVER:
                        # Dead model or bad credentials — no point retrying.
                        logger.warning(
                            "[%s] %s/%s permanent failure, failing over: %s",
                            stage, provider.name, model, exc.message,
                        )
                        if exc.status in (401, 403):
                            self._dead.add(provider.name)
                        break

                    last = attempt >= settings.llm_max_retries
                    logger.warning(
                        "[%s] %s/%s attempt %s/%s failed: %s%s",
                        stage, provider.name, model,
                        attempt + 1, settings.llm_max_retries + 1,
                        exc.message,
                        "" if last else " — retrying",
                    )
                    if last:
                        break
                    sleep_time = min(2.0 * (attempt + 1), 8.0)
                    if getattr(exc, "retry_after", None) is not None:
                        sleep_time = exc.retry_after + 0.5
                    await asyncio.sleep(sleep_time)

                except ValueError as exc:
                    # JSON parse failure: worth one more try with a firmer nudge.
                    self.usage.failures += 1
                    attempts.append(f"{provider.name}/{model} parse error: {exc}")
                    if self.telemetry:
                        self.telemetry.record_llm_call(
                            stage, provider.name, model, 0,
                            0, 0, False, attempt + 1, status=f"parse_error: {exc}"
                        )
                    last = attempt >= settings.llm_max_retries
                    logger.warning(
                        "[%s] %s/%s returned unparseable JSON%s",
                        stage, provider.name, model, "" if last else " — retrying",
                    )
                    if last:
                        break
                    current_user_prompt = (
                        user_prompt
                        + "\n\nIMPORTANT: Respond with a single valid JSON object "
                        "only. No prose, no explanation, no markdown fences."
                    )
                    await asyncio.sleep(1.0)

            current_user_prompt = user_prompt  # reset for the next provider

        raise LLMError(
            f"All providers failed for stage '{stage}'. "
            f"Tried: {', '.join(p.name for p in self._providers)}.",
            attempts=attempts,
        )

    async def complete_text(
        self,
        stage: str,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 1200,
        temperature: float | None = None,
    ) -> str:
        """Plain-text completion. Returns '' if every provider fails."""
        temp = settings.llm_temperature if temperature is None else temperature
        role = role_for_stage(stage)

        for provider in self._providers:
            if provider.name in self._dead:
                continue
            model = provider.model_for_role(role)
            try:
                response, _ = await self._attempt(
                    provider, model, system_prompt, user_prompt, None, max_tokens, temp
                )
                self.usage.record(
                    f"{provider.name}/{model}",
                    response.prompt_tokens,
                    response.completion_tokens,
                )
                if self.telemetry:
                    self.telemetry.record_llm_call(
                        stage, provider.name, model, int(_ * 1000),
                        response.prompt_tokens, response.completion_tokens,
                        False, 1
                    )
                return response.text.strip()
            except ProviderError as exc:
                self.usage.failures += 1
                if self.telemetry:
                    self.telemetry.record_llm_call(
                        stage, provider.name, model, 0,
                        0, 0, False, 1, status=f"failed: {exc.message}"
                    )
                logger.warning("[%s] text completion failed: %s", stage, exc)
        return ""


async def probe_providers() -> list[dict]:
    """Send a tiny request to each configured provider.

    Used at startup and by /api/health so a dead model ID or bad key is visible
    immediately rather than surfacing mid-pipeline.
    """
    results: list[dict] = []
    providers = build_providers(settings)
    if not providers:
        return results

    timeout = httpx.Timeout(20.0, connect=10.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        for provider in providers:
            model = provider.model_for_role("fast")
            entry = {"provider": provider.name, "model": model, "ok": False, "detail": ""}
            try:
                url, headers, body = provider.build_request(
                    model,
                    "Reply with JSON only.",
                    'Return exactly: {"ok":true}',
                    {"type": "object"},
                    32,
                    0.0,
                )
                resp = await client.post(url, json=body, headers=headers)
                if resp.status_code >= 400:
                    entry["detail"] = (
                        f"HTTP {resp.status_code}: "
                        f"{provider.extract_error(resp.status_code, resp.text)}"
                    )
                else:
                    provider.parse_response(resp.json())
                    entry["ok"] = True
                    entry["detail"] = "reachable"
            except (httpx.HTTPError, ProviderError, ValueError, KeyError) as exc:
                entry["detail"] = str(exc)[:200]
            results.append(entry)

    return results
