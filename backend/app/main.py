"""FastAPI application entry point for Turnitout V2."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any, Dict

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.api.router import api_router, health as api_health, set_global_services
from backend.app.core.config import settings
from backend.app.core.jobs import job_store
from backend.app.humanisation.engine import HumanisationEngine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Turnitout V2 backend...")
    # Initialize rule-based editing engine (no LLM provider required)
    engine = HumanisationEngine(settings=settings)
    set_global_services(engine, settings)

    logger.info(
        "Deterministic editor ready with OG Dataset version %s (%s rules)",
        engine.dataset_version,
        len(engine.master_rules),
    )
    try:
        yield
    finally:
        for job in job_store.list():
            if job.task and not job.task.done():
                job.cancel_event.set()
                job.task.cancel()
        logger.info("Turnitout V2 backend stopped.")


app = FastAPI(
    title="Turnitout V2 API",
    description=(
        "Local-first document humanisation, writing-quality analysis and sampled "
        "originality checking. No document content is sent to a hosted LLM."
    ),
    version="2.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Export-Notes", "Content-Disposition"],
)

app.include_router(api_router, prefix="/api/v1")


@app.get("/api/health")
async def legacy_health() -> Dict[str, Any]:
    return await api_health()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("backend.app.main:app", host="127.0.0.1", port=8000, reload=True)