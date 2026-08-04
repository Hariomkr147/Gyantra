"""Application configuration loaded from environment variables."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central settings object. All values are overridable via env vars."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        # Our per-role settings are named model_fast / model_validate / etc.
        # Pydantic protects the "model_" prefix by default, so clear it.
        protected_namespaces=(),
    )

    # --- Core ---
    app_name: str = "Gyantra"
    debug: bool = False
    api_prefix: str = "/api"

    # --- Storage ---
    database_url: str = "sqlite+aiosqlite:///./data/gyantra.db"
    upload_dir: Path = Path("./uploads")
    export_dir: Path = Path("./exports")
    cache_dir: Path = Path("./data/cache")
    max_file_size_mb: int = 25

    # --- LLM providers ---
    # Comma-separated priority order. Gemini first by default: the free tier of
    # Google AI Studio is the most reliable of the three, and its model IDs are
    # stable (OpenRouter rotates free models in and out without notice).
    llm_provider: str = "nvidia,routesme,gemini,groq,openrouter"

    gemini_api_key: str = ""
    openrouter_api_key: str = ""
    groq_api_key: str = ""
    # Generic OpenAI-compatible gateway (agentrouter.org and similar). Dormant
    # unless set; add it to LLM_PROVIDER to use it.
    routesme_api_key: str = ""
    nvidia_api_key: str = ""

    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    groq_base_url: str = "https://api.groq.com/openai/v1"
    routesme_base_url: str = "https://routesme.online/v1"
    nvidia_base_url: str = "https://integrate.api.nvidia.com/v1"

    llm_temperature: float = 0.3
    llm_timeout_seconds: int = 120
    llm_max_retries: int = 2
    llm_cache_enabled: bool = True
    # Probe each provider at startup so a dead model or bad key is reported
    # before a teacher uploads anything.
    llm_probe_on_startup: bool = True
    # When a 429 states a retry delay longer than this, fail over to the next
    # provider instead of waiting. Free tiers routinely quote minutes.
    rate_limit_wait_ceiling: float = 20.0

    # Per-minute request budgets per provider. Free tiers enforce these hard;
    # gemini-flash-latest is gemini-3.6-flash with a 20 req/min cap. The client
    # spaces requests out to stay under the budget rather than tripping it.
    # Set to 0 to disable throttling for a provider.
    gemini_requests_per_minute: int = 10
    groq_requests_per_minute: int = 25
    openrouter_requests_per_minute: int = 15
    routesme_requests_per_minute: int = 20

    # --- Per-role model IDs, per provider ---
    # Roles map to stages in model_registry.py.
    #
    # gemini-flash-latest is a *thinking* model: it spends output tokens on
    # internal reasoning before the answer (thoughtsTokenCount in the response).
    # gemini_thinking_headroom below compensates so the answer is never starved.
    gemini_model_fast: str = "gemini-flash-latest"
    gemini_model_extract: str = "gemini-flash-latest"
    gemini_model_plan: str = "gemini-flash-latest"
    gemini_model_generate: str = "gemini-flash-latest"
    gemini_model_validate: str = "gemini-flash-lite-latest"

    # Extra output tokens granted to Gemini on top of what a stage asks for, to
    # cover reasoning. Without it a 300-token request can spend 284 on thoughts
    # and return a truncated answer.
    gemini_thinking_headroom: int = 1200

    groq_model_fast: str = "llama-3.1-8b-instant"
    groq_model_extract: str = "llama-3.3-70b-versatile"
    groq_model_plan: str = "llama-3.3-70b-versatile"
    groq_model_generate: str = "llama-3.3-70b-versatile"
    groq_model_validate: str = "llama-3.1-8b-instant"

    # Instruction-tuned models are chosen deliberately over reasoning models
    # here: reasoning models emit chain-of-thought before the JSON, which costs
    # output tokens and frequently truncates the actual answer.
    openrouter_model_fast: str = "google/gemma-4-31b-it:free"
    openrouter_model_extract: str = "google/gemma-4-31b-it:free"
    openrouter_model_plan: str = "google/gemma-4-31b-it:free"
    openrouter_model_generate: str = "google/gemma-4-31b-it:free"
    openrouter_model_validate: str = "openai/gpt-oss-20b:free"

    # routesme.online model names, used only if ROUTESME_API_KEY is set.
    routesme_model_fast: str = "GLM5.2R"
    routesme_model_extract: str = "GLM5.2R"
    routesme_model_plan: str = "GLM5.2R"
    routesme_model_generate: str = "GLM5.2R"
    routesme_model_validate: str = "GLM5.2R"

    # nvidia NIM models
    nvidia_model_fast: str = "meta/llama-3.1-8b-instruct"
    nvidia_model_extract: str = "meta/llama-3.1-70b-instruct"
    nvidia_model_plan: str = "meta/llama-3.1-70b-instruct"
    nvidia_model_generate: str = "meta/llama-3.1-70b-instruct"
    nvidia_model_validate: str = "meta/llama-3.1-8b-instruct"

    # --- Optional demo mode ---
    # When true the pipeline runs with a deterministic stub LLM so the app is
    # demonstrable without any API key. Never enable this for real output.
    demo_mode: bool = False

    # --- Token budget guardrails ---
    # Conservative defaults so the pipeline survives small free-tier contexts.
    chunk_target_tokens: int = 700
    chunk_overlap_tokens: int = 80
    # Upper bound on chunks per document, which bounds extraction LLM calls.
    max_chunks: int = 40
    # Sections below this are stubs (a bare heading, a one-line fragment) and
    # get folded into a neighbour. Anything above keeps its own chunk so
    # extraction stays section-scoped and citable.
    min_chunk_tokens: int = 60
    max_context_tokens_per_call: int = 6000
    max_source_snippets_per_stage: int = 8

    # --- Parsing ---
    # Docling is the primary parser for PDF/DOCX/PPTX: it gives real reading
    # order, table structure and heading hierarchy instead of font-size guesses.
    # Set false to force the lightweight built-in parsers.
    docling_enabled: bool = True
    # Download docling's models at boot rather than during the first upload.
    # Costs a slower startup once; avoids a multi-minute stall mid-job.
    docling_warmup_on_startup: bool = True
    # Docling runs its layout models on this many threads; keep it modest so it
    # does not starve the pipeline's LLM calls.
    docling_threads: int = 2
    # Docling's models need roughly this much free RAM. Below it we skip docling
    # and use the built-in parser rather than crash mid-upload.
    docling_min_memory_mb: int = 1500
    ocr_enabled: bool = False
    ocr_language: str = "eng"
    ocr_max_pages: int = 40
    # Below this ratio of extractable text per page, treat the PDF as scanned.
    scanned_text_threshold: int = 120

    # --- Pipeline ---
    job_timeout_seconds: int = 900
    parallel_period_generation: int = 2
    min_periods: int = 1
    max_periods: int = 12
    supported_languages: str = "en,hi,bn,ta,te,mr,gu,kn,ml,pa"

    # --- CORS ---
    cors_origins: str = "http://localhost:5173,http://localhost:3000,http://localhost:8501"

    @property
    def provider_order(self) -> list[str]:
        return [p.strip() for p in self.llm_provider.split(",") if p.strip()]

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip().rstrip("/") for o in self.cors_origins.split(",") if o.strip()]

    @property
    def max_file_size_bytes(self) -> int:
        return self.max_file_size_mb * 1024 * 1024

    def ensure_dirs(self) -> None:
        for d in (self.upload_dir, self.export_dir, self.cache_dir):
            Path(d).mkdir(parents=True, exist_ok=True)
        Path("./data").mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_dirs()
    return settings


settings = get_settings()
