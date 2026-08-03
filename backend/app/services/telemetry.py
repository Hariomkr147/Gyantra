from __future__ import annotations

import logging
import time
from typing import Any

from app.models.schemas import TelemetryRecord, LLMCallMetric

logger = logging.getLogger("gyantra.telemetry")


# Simplified cost estimation based on common provider pricing per 1M tokens (USD)
_COST_RATES = {
    "gemini": {"prompt": 0.075, "completion": 0.30},  # Flash approx
    "groq": {"prompt": 0.50, "completion": 0.50},
    "openrouter": {"prompt": 0.15, "completion": 0.15},
    "routesme": {"prompt": 0.10, "completion": 0.10}
}


def estimate_cost(provider: str, model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Estimates the cost of an LLM call in USD."""
    rates = _COST_RATES.get(provider.lower(), {"prompt": 0.10, "completion": 0.20})
    cost = (prompt_tokens / 1_000_000) * rates["prompt"] + (completion_tokens / 1_000_000) * rates["completion"]
    return round(cost, 6)


class JobTelemetry:
    def __init__(self, job_id: str):
        self.job_id = job_id
        self.start_time = time.time()
        self.stage_timings: dict[str, dict[str, Any]] = {}
        self.llm_calls: list[LLMCallMetric] = []
        
    def begin_stage(self, stage: str):
        self.stage_timings[stage] = {"start": time.time(), "end": None, "duration_ms": 0}
        
    def end_stage(self, stage: str):
        if stage in self.stage_timings:
            end_t = time.time()
            self.stage_timings[stage]["end"] = end_t
            self.stage_timings[stage]["duration_ms"] = int((end_t - self.stage_timings[stage]["start"]) * 1000)

    def record_llm_call(
        self,
        stage: str,
        provider: str,
        model: str,
        latency_ms: int,
        prompt_tokens: int,
        completion_tokens: int,
        cached: bool,
        attempt: int,
        status: str = "success"
    ):
        cost = estimate_cost(provider, model, prompt_tokens, completion_tokens) if not cached else 0.0
        
        call = LLMCallMetric(
            stage=stage,
            provider=provider,
            model=model,
            latency_ms=latency_ms,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cached=cached,
            attempt=attempt,
            cost_estimate=cost,
            status=status
        )
        self.llm_calls.append(call)

    def summarize(self) -> TelemetryRecord:
        total_duration_ms = int((time.time() - self.start_time) * 1000)
        
        # Calculate derived metrics
        total_cost = sum(call.cost_estimate for call in self.llm_calls if call.status == "success")
        
        provider_stats = {}
        for call in self.llm_calls:
            if call.provider not in provider_stats:
                provider_stats[call.provider] = {"calls": 0, "failures": 0, "total_latency_ms": 0}
            
            provider_stats[call.provider]["calls"] += 1
            if call.status != "success":
                provider_stats[call.provider]["failures"] += 1
            provider_stats[call.provider]["total_latency_ms"] += call.latency_ms

        retry_count = sum(1 for call in self.llm_calls if call.attempt > 1)
        
        total_calls = len(self.llm_calls)
        cache_hits = sum(1 for call in self.llm_calls if call.cached)
        cache_hit_rate = (cache_hits / total_calls) if total_calls > 0 else 0.0

        return TelemetryRecord(
            total_duration_ms=total_duration_ms,
            stage_timings={k: v["duration_ms"] for k, v in self.stage_timings.items()},
            llm_calls=self.llm_calls,
            total_cost_estimate=total_cost,
            provider_stats=provider_stats,
            retry_count=retry_count,
            cache_hit_rate=cache_hit_rate
        )

