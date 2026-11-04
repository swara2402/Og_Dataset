"""Small authenticated gateway for a hosted Ollama instance.

Run behind HTTPS. Keep the Ollama container private; expose only this gateway.
"""
from __future__ import annotations

import os
import secrets
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse
import httpx

OLLAMA_UPSTREAM_URL = os.getenv("OLLAMA_UPSTREAM_URL", "http://ollama:11434").rstrip("/")
GATEWAY_API_KEY = os.getenv("TURNITOUT_GATEWAY_API_KEY", "")
if not GATEWAY_API_KEY:
    raise RuntimeError("TURNITOUT_GATEWAY_API_KEY must be set.")

app = FastAPI(title="Turnitout Model Gateway", docs_url=None, redoc_url=None)


def authorize(authorization: str | None):
    expected = f"Bearer {GATEWAY_API_KEY}"
    if not authorization or not secrets.compare_digest(authorization, expected):
        raise HTTPException(status_code=401, detail="Unauthorized")


@app.get("/health")
async def health(authorization: str | None = Header(default=None)):
    authorize(authorization)
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(f"{OLLAMA_UPSTREAM_URL}/api/tags")
        response.raise_for_status()
    return {"ok": True}


@app.get("/api/tags")
async def tags(authorization: str | None = Header(default=None)):
    authorize(authorization)
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.get(f"{OLLAMA_UPSTREAM_URL}/api/tags")
        return JSONResponse(status_code=response.status_code, content=response.json())


@app.post("/api/chat")
async def chat(payload: dict, authorization: str | None = Header(default=None)):
    authorize(authorization)
    # Keep this gateway deliberately narrow: only non-streaming chat is needed.
    payload["stream"] = False
    async with httpx.AsyncClient(timeout=240) as client:
        response = await client.post(f"{OLLAMA_UPSTREAM_URL}/api/chat", json=payload)
        try:
            body = response.json()
        except Exception:
            body = {"error": response.text[:1000]}
        return JSONResponse(status_code=response.status_code, content=body)
