"""Consent-gated, metadata-minimal human feedback endpoint.

Raw document passages are deliberately not accepted or stored by this endpoint.
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.app.api.auth import current_owner_id

router = APIRouter(tags=["human-feedback"])
DB_PATH = Path(os.getenv(
    "OG_FEEDBACK_DB_PATH",
    str(Path(__file__).resolve().parents[2] / "data" / "feedback.sqlite3"),
))


class FeedbackEvent(BaseModel):
    model_config = {"extra": "forbid"}
    consent: bool = Field(description="Must be true for this event to be retained.")
    consent_version: str = Field(min_length=1, max_length=40)
    suggestion_id: str = Field(min_length=1, max_length=200)
    job_id: Optional[str] = Field(default=None, max_length=80)
    paragraph_id: Optional[str] = Field(default=None, max_length=200)
    action: Literal["accepted", "rejected", "edited_then_accepted", "rated"]
    reason: Optional[Literal[
        "grammar", "clarity", "tone", "terminology", "factual_drift",
        "citation_issue", "verbosity", "formatting", "other"
    ]] = None
    rating: Optional[int] = Field(default=None, ge=1, le=5)
    task: Optional[str] = Field(default=None, max_length=80)
    discipline: Optional[str] = Field(default=None, max_length=120)
    section: Optional[str] = Field(default=None, max_length=120)
    style: Optional[str] = Field(default=None, max_length=80)
    rule_version: Optional[str] = Field(default=None, max_length=80)
    dataset_version: Optional[str] = Field(default=None, max_length=80)
    protected_span_integrity: Optional[Literal["passed", "failed", "not_checked"]] = None

    @classmethod
    def validate_rating(cls, values):
        return values


def _connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        DB_PATH.parent.chmod(0o700)
    except OSError:
        pass
    connection = sqlite3.connect(str(DB_PATH), timeout=10)
    try:
        DB_PATH.chmod(0o600)
    except OSError:
        pass
    connection.execute("""
        CREATE TABLE IF NOT EXISTS feedback_events (
            event_id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            owner_id TEXT NOT NULL,
            consent_version TEXT NOT NULL,
            payload TEXT NOT NULL
        )
    """)
    return connection


@router.post("/feedback", status_code=201)
async def record_feedback(event: FeedbackEvent):
    if not event.consent:
        raise HTTPException(status_code=403, detail="Explicit feedback consent is required.")
    if event.action == "rated" and event.rating is None:
        raise HTTPException(status_code=422, detail="A 1-5 rating is required for rated events.")
    if event.action != "rated" and event.rating is not None:
        raise HTTPException(status_code=422, detail="Rating is only valid for rated events.")

    # Persist only structured feedback. Never accept original, suggested, final,
    # or whole-document text fields; Pydantic rejects undeclared fields.
    event_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).isoformat()
    owner_id = current_owner_id.get()
    payload = event.model_dump(exclude={"consent"})
    with _connect() as connection:
        connection.execute(
            "INSERT INTO feedback_events(event_id, created_at, owner_id, consent_version, payload) VALUES(?,?,?,?,?)",
            (event_id, created_at, owner_id, event.consent_version,
             json.dumps(payload, ensure_ascii=False, separators=(",", ":"))),
        )
    return {
        "event_id": event_id,
        "recorded": True,
        "stored_text": False,
        "message": "Structured feedback recorded; document passages were not stored.",
    }
