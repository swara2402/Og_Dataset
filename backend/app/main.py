"""FastAPI application entry point for Turnitout V2."""
from __future__ import annotations
import logging
from contextlib import asynccontextmanager
from typing import Any, Dict
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from backend.app.api.router import api_router, health as api_health, set_global_services
from backend.app.core.config import settings
from backend.app.core.jobs import job_store
from backend.app.api.auth import current_owner_id, is_rate_limited, resolve_owner
from backend.app.humanisation.engine import HumanisationEngine
from backend.app.retrieval.api import retrieval_router

logging.basicConfig(level=logging.INFO,format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger=logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Turnitout V2 backend...")
    engine=HumanisationEngine(settings=settings)
    set_global_services(engine,settings)
    logger.info("Deterministic editor ready with OG Dataset version %s (%s rules)",engine.dataset_version,len(engine.master_rules))
    try: yield
    finally:
        for job in job_store.list():
            if job.task and not job.task.done():
                job.cancel_event.set(); job.task.cancel()
        logger.info("Turnitout V2 backend stopped.")

app=FastAPI(title="Turnitout V2 API",description="Offline-first academic document editing with deterministic writing-quality suggestions, protected-content validation, local history and exports.",version="2.0.0",lifespan=lifespan,docs_url="/docs",redoc_url="/redoc")

@app.middleware("http")
async def authenticate_api_request(request: Request,call_next):
    try:
        owner_id=resolve_owner(request.headers.get("authorization"),settings.api_tokens,settings.api_auth_required)
    except ValueError as exc: return JSONResponse(status_code=503,content={"detail":str(exc)})
    except PermissionError:
        return JSONResponse(status_code=401,content={"detail":"A valid bearer token is required."},headers={"WWW-Authenticate":"Bearer"})
    client_host=request.client.host if request.client else "unknown"
    if is_rate_limited(f"{owner_id}:{client_host}",max(1,int(settings.api_rate_limit_per_minute))):
        return JSONResponse(status_code=429,content={"detail":"Rate limit exceeded. Please retry shortly."},headers={"Retry-After":"60"})
    token=current_owner_id.set(owner_id)
    try: return await call_next(request)
    finally: current_owner_id.reset(token)

app.add_middleware(CORSMiddleware,allow_origins=settings.cors_origin_list,allow_credentials=True,allow_methods=["*"],allow_headers=["*"],expose_headers=["X-Export-Notes","Content-Disposition"])
app.include_router(api_router,prefix="/api/v1")
app.include_router(retrieval_router,prefix="/api/v1")

@app.get("/api/health")
async def legacy_health() -> Dict[str,Any]: return await api_health()

if __name__=="__main__":
    import uvicorn
    uvicorn.run("backend.app.main:app",host="127.0.0.1",port=8000,reload=True)
