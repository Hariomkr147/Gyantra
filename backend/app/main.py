"""FastAPI application entry point."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import router
from app.config import settings
from app.services.job_store import job_store

logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)-24s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("gyantra")

# httpx logs every request at INFO, which drowns out pipeline progress.
logging.getLogger("httpx").setLevel(logging.WARNING)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.ensure_dirs()
    await job_store.init()

    from app.services.llm_client import LLMClient, probe_providers

    if settings.demo_mode:
        logger.warning(
            "DEMO_MODE is on — the pipeline will use the offline stub. "
            "Output is illustrative, not real model output."
        )
    else:
        client = LLMClient()
        providers = client.available_providers()

        if not providers:
            logger.error(
                "No LLM provider configured. Set GEMINI_API_KEY (recommended), "
                "GROQ_API_KEY, or OPENROUTER_API_KEY in backend/.env — or set "
                "DEMO_MODE=true. Uploads will fail at the classification stage."
            )
        else:
            logger.info("LLM providers (in order): %s", ", ".join(providers))
            for role, model in client.describe_routing().items():
                logger.info("  %-9s -> %s", role, model)

            # Probing at startup turns a dead model ID or revoked key into a
            # log line now, instead of a stalled job later.
            if settings.llm_probe_on_startup:
                logger.info("probing providers...")
                for result in await probe_providers():
                    if result["ok"]:
                        logger.info(
                            "  OK   %s (%s)", result["provider"], result["model"]
                        )
                    else:
                        logger.warning(
                            "  FAIL %s (%s): %s",
                            result["provider"], result["model"], result["detail"],
                        )

    # Docling pulls several hundred MB of layout models on first use. Warming
    # it here means that cost lands at boot instead of inside a teacher's first
    # upload, where it would look like the pipeline had hung.
    if settings.docling_enabled and not settings.demo_mode:
        from app.parsers import docling_parser

        if docling_parser.is_available():
            if settings.docling_warmup_on_startup:
                logger.info("warming up docling (first run downloads models)...")
                ok, detail = await asyncio.to_thread(docling_parser.warmup)
                if ok:
                    logger.info("docling ready (%s)", detail)
                else:
                    logger.warning(
                        "docling unavailable, using built-in parsers: %s", detail
                    )
            else:
                logger.info("docling installed; warmup deferred to first upload")
        else:
            logger.info(
                "docling not installed — using built-in parsers. "
                "Install with: pip install docling"
            )

    logger.info("%s API started", settings.app_name)
    yield
    logger.info("%s API shutting down", settings.app_name)


app = FastAPI(
    title="Gyantra API",
    description=(
        "Converts educational documents into a structured, grounded "
        "Teacher Knowledge Package."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix=settings.api_prefix)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Return a clean JSON error instead of an HTML traceback page."""
    logger.exception("unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={
            "detail": "An unexpected error occurred.",
            "error": str(exc) if settings.debug else None,
        },
    )


@app.get("/")
async def root() -> dict:
    return {
        "name": settings.app_name,
        "tagline": "From Chapter to Classroom",
        "docs": "/docs",
        "health": f"{settings.api_prefix}/health",
    }
