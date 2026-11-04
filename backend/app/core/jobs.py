"""In-memory job and paragraph state for Turnitout V2.

The application is a local, single-user tool. Jobs live in memory and original
uploads are retained only for the lifetime of the process so DOCX export can
preserve the source structure. Nothing is written to a database or remote
service.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from backend.app.document_processing.parser import ParsedDocument


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class VersionEntry:
    version: int
    text: str
    masked_text: str
    pass_number: int
    source: str
    created_at: str = field(default_factory=now_iso)
    instruction: Optional[str] = None
    validation: Dict[str, Any] = field(default_factory=dict)
    elapsed_seconds: float = 0.0
    # Traceability fields for rule-based editing
    applied_rule_ids: List[str] = field(default_factory=list)
    edit_rationale: str = ""
    editing_level_applied: str = "minimal"
    issues_found: List[str] = field(default_factory=list)
    edit_scope: str = "none"
    change_summary: List[str] = field(default_factory=list)
    requires_human_review: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "text": self.text,
            "pass_number": self.pass_number,
            "source": self.source,
            "created_at": self.created_at,
            "instruction": self.instruction,
            "validation": self.validation,
            "elapsed_seconds": round(self.elapsed_seconds, 3),
            "applied_rule_ids": self.applied_rule_ids,
            "edit_rationale": self.edit_rationale,
            "editing_level_applied": self.editing_level_applied,
            "issues_found": self.issues_found,
            "edit_scope": self.edit_scope,
            "change_summary": self.change_summary,
            "requires_human_review": self.requires_human_review,
        }


@dataclass
class ParagraphState:
    id: str
    index: int
    original_text: str
    paragraph_type: str
    category: str
    section: Optional[str]
    eligible: bool
    masked_text: str = ""
    replacements: Dict[str, str] = field(default_factory=dict)
    protected_items: List[Dict[str, Any]] = field(default_factory=list)
    current_text: str = ""
    current_masked_text: str = ""
    status: str = "pending"
    warnings: List[str] = field(default_factory=list)
    validation: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    attempts: int = 0
    elapsed_seconds: float = 0.0
    versions: List[VersionEntry] = field(default_factory=list)
    # Traceability fields for rule-based editing
    applied_rule_ids: List[str] = field(default_factory=list)
    edit_rationale: str = ""
    editing_level_applied: str = "minimal"
    issues_found: List[str] = field(default_factory=list)
    edit_scope: str = "none"
    change_summary: List[str] = field(default_factory=list)
    requires_human_review: bool = False
    review_status: str = "unchanged"

    def __post_init__(self) -> None:
        if not self.current_text:
            self.current_text = self.original_text
        if not self.current_masked_text:
            self.current_masked_text = self.masked_text or self.original_text
        if not self.versions:
            self.versions.append(
                VersionEntry(
                    version=0,
                    text=self.original_text,
                    masked_text=self.masked_text or self.original_text,
                    pass_number=0,
                    source="original",
                )
            )

    def add_version(
        self,
        text: str,
        masked_text: str,
        pass_number: int,
        source: str = "rule-based",
        instruction: Optional[str] = None,
        validation: Optional[Dict[str, Any]] = None,
        elapsed_seconds: float = 0.0,
        applied_rule_ids: Optional[List[str]] = None,
        edit_rationale: str = "",
        editing_level_applied: str = "minimal",
        issues_found: Optional[List[str]] = None,
        edit_scope: str = "none",
        change_summary: Optional[List[str]] = None,
        requires_human_review: bool = False,
    ) -> VersionEntry:
        entry = VersionEntry(
            version=len(self.versions),
            text=text,
            masked_text=masked_text,
            pass_number=pass_number,
            source=source,
            instruction=instruction,
            validation=validation or {},
            elapsed_seconds=elapsed_seconds,
            applied_rule_ids=applied_rule_ids or [],
            edit_rationale=edit_rationale,
            editing_level_applied=editing_level_applied,
            issues_found=issues_found or [],
            edit_scope=edit_scope,
            change_summary=change_summary or [],
            requires_human_review=requires_human_review,
        )
        self.versions.append(entry)
        self.current_text = text
        self.current_masked_text = masked_text
        return entry

    @property
    def processed(self) -> bool:
        return self.current_text != self.original_text

    def to_dict(self, include_versions: bool = True) -> Dict[str, Any]:
        # Rejected hybrid suggestions remain in version history for audit, but
        # must never be exposed as the paragraph's active proposal after reload.
        proposal = next(
            (
                version.text
                for version in reversed(self.versions)
                if version.source != "original"
                and not version.source.startswith("hybrid-rejected:")
            ),
            None,
        )
        data: Dict[str, Any] = {
            "id": self.id,
            "index": self.index,
            "original": self.original_text,
            "revised": self.current_text,
            "proposal": proposal,
            "type": self.paragraph_type,
            "category": self.category,
            "section": self.section,
            "eligible": self.eligible,
            "processed": self.processed,
            "status": self.status,
            "warnings": self.warnings,
            "validation": self.validation,
            "error": self.error,
            "attempts": self.attempts,
            "elapsed_seconds": round(self.elapsed_seconds, 3),
            "version_count": len(self.versions),
            "protected_items": [
                {"type": item["type"], "value": item["value"]}
                for item in self.protected_items
            ],
            # Traceability fields
            "applied_rule_ids": self.applied_rule_ids,
            "edit_rationale": self.edit_rationale,
            "editing_level_applied": self.editing_level_applied,
            "issues_found": self.issues_found,
            "edit_scope": self.edit_scope,
            "change_summary": self.change_summary,
            "requires_human_review": self.requires_human_review,
            "review_status": self.review_status,
        }
        if include_versions:
            data["versions"] = [version.to_dict() for version in self.versions]
        return data


@dataclass
class Job:
    job_id: str
    filename: str
    file_type: str
    content_type: str
    created_at: str
    style: str
    options: Dict[str, Any]
    document: ParsedDocument
    paragraphs: List[ParagraphState]
    original_bytes: bytes = b""
    status: str = "queued"
    progress: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    statistics: Dict[str, Any] = field(default_factory=dict)
    writing_quality: Optional[Dict[str, Any]] = None
    ai_indicators: Optional[Dict[str, Any]] = None
    originality: Optional[Dict[str, Any]] = None
    cancel_event: asyncio.Event = field(default_factory=asyncio.Event)
    task: Optional[asyncio.Task] = None

    @property
    def elapsed_seconds(self) -> float:
        end = self.finished_at or time.time()
        start = self.started_at or (self.created_at and _iso_to_epoch(self.created_at)) or end
        return max(0.0, end - start)

    def summary(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "filename": self.filename,
            "file_type": self.file_type,
            "style": self.style,
            "status": self.status,
            "created_at": self.created_at,
            "progress": self.progress,
            "error": self.error,
            "statistics": self.statistics,
            "elapsed_seconds": round(self.elapsed_seconds, 3),
        }

    def to_results(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "filename": self.filename,
            "file_type": self.file_type,
            "style": self.style,
            "status": self.status,
            "processing_time": round(self.elapsed_seconds, 3),
            "options": self.options,
            "results": [paragraph.to_dict() for paragraph in self.paragraphs],
            "statistics": self.statistics,
            "warnings": self.statistics.get("warnings", []),
        }


def _iso_to_epoch(value: str) -> float:
    try:
        return datetime.fromisoformat(value).timestamp()
    except Exception:
        return time.time()


class JobStore:
    def __init__(self, max_jobs: int = 50):
        self.max_jobs = max_jobs
        self._jobs: Dict[str, Job] = {}

    def create(self, job: Job) -> Job:
        self._jobs[job.job_id] = job
        self._prune()
        return job

    def get(self, job_id: str) -> Optional[Job]:
        return self._jobs.get(job_id)

    def require(self, job_id: str) -> Job:
        job = self.get(job_id)
        if job is None:
            raise KeyError(job_id)
        return job

    def list(self) -> List[Job]:
        return sorted(self._jobs.values(), key=lambda item: item.created_at, reverse=True)

    def delete(self, job_id: str) -> bool:
        return self._jobs.pop(job_id, None) is not None

    def _prune(self) -> None:
        if len(self._jobs) <= self.max_jobs:
            return
        removable = sorted(self._jobs.values(), key=lambda item: item.created_at)
        for job in removable[: len(self._jobs) - self.max_jobs]:
            if job.status not in {"processing", "queued"}:
                self._jobs.pop(job.job_id, None)


class SQLiteJobStore(JobStore):
    """SQLite-backed local job history with JSON snapshots (no executable serialization)."""

    def __init__(self, max_jobs: int = 50, db_path: Optional[str] = None):
        import os
        import sqlite3
        from pathlib import Path
        self.max_jobs = max_jobs
        self._jobs = {}
        configured = db_path or os.getenv("OG_DATASET_DB_PATH")
        self.db_path = Path(configured) if configured else Path(__file__).resolve().parents[2] / "data" / "jobs.sqlite3"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._sqlite3 = sqlite3
        with self._connect() as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS jobs (job_id TEXT PRIMARY KEY, created_at TEXT NOT NULL, payload TEXT NOT NULL)"
            )
            rows = connection.execute("SELECT payload FROM jobs ORDER BY created_at DESC LIMIT ?", (self.max_jobs,)).fetchall()
        for (payload,) in rows:
            try:
                job = self._decode(payload)
                if job.status in {"queued", "processing"}:
                    job.status = "failed"
                    job.error = "Processing was interrupted by an application restart. The saved document and edits are available for review."
                    job.finished_at = time.time()
                    self.save(job)
                self._jobs[job.job_id] = job
            except Exception:
                # A corrupt snapshot must not prevent the local editor from starting.
                continue

    def _connect(self):
        connection = self._sqlite3.connect(str(self.db_path), timeout=10)
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    @staticmethod
    def _encode(job: Job) -> str:
        import base64
        import json
        from dataclasses import asdict
        document = {
            "filename": job.document.filename,
            "file_type": job.document.file_type,
            "metadata": job.document.metadata,
            "paragraphs": [
                {"id": p.id, "text": p.text, "paragraph_type": p.paragraph_type,
                 "location": p.location, "metadata": p.metadata}
                for p in job.document.paragraphs
            ],
        }
        paragraphs = []
        for state in job.paragraphs:
            paragraphs.append({
                "id": state.id, "index": state.index, "original_text": state.original_text,
                "paragraph_type": state.paragraph_type, "category": state.category,
                "section": state.section, "eligible": state.eligible, "masked_text": state.masked_text,
                "replacements": state.replacements, "protected_items": state.protected_items,
                "current_text": state.current_text, "current_masked_text": state.current_masked_text,
                "status": state.status, "warnings": state.warnings, "validation": state.validation,
                "error": state.error, "attempts": state.attempts, "elapsed_seconds": state.elapsed_seconds,
                "versions": [asdict(v) for v in state.versions],
                "applied_rule_ids": state.applied_rule_ids, "edit_rationale": state.edit_rationale,
                "editing_level_applied": state.editing_level_applied, "issues_found": state.issues_found,
                "edit_scope": state.edit_scope, "change_summary": state.change_summary,
                "requires_human_review": state.requires_human_review, "review_status": state.review_status,
            })
        payload = {
            "job_id": job.job_id, "filename": job.filename, "file_type": job.file_type,
            "content_type": job.content_type, "created_at": job.created_at, "style": job.style,
            "options": job.options, "document": document, "paragraphs": paragraphs,
            "original_bytes": base64.b64encode(job.original_bytes).decode("ascii"),
            "status": job.status, "progress": job.progress, "error": job.error,
            "started_at": job.started_at, "finished_at": job.finished_at,
            "statistics": job.statistics, "writing_quality": job.writing_quality,
            "ai_indicators": job.ai_indicators, "originality": job.originality,
        }
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))

    @staticmethod
    def _decode(payload: str) -> Job:
        import base64
        import json
        from backend.app.document_processing.parser import ParsedDocument, DocumentParagraph
        data = json.loads(payload)
        document_data = data["document"]
        document = ParsedDocument(
            filename=document_data["filename"], file_type=document_data["file_type"],
            metadata=document_data.get("metadata", {}),
            paragraphs=[DocumentParagraph(**p) for p in document_data.get("paragraphs", [])],
        )
        states = []
        for item in data["paragraphs"]:
            state_data = dict(item)
            state_data["versions"] = [VersionEntry(**v) for v in state_data.get("versions", [])]
            states.append(ParagraphState(**state_data))
        job = Job(
            job_id=data["job_id"], filename=data["filename"], file_type=data["file_type"],
            content_type=data["content_type"], created_at=data["created_at"], style=data["style"],
            options=data.get("options", {}), document=document, paragraphs=states,
            original_bytes=base64.b64decode(data.get("original_bytes", "")),
            status=data.get("status", "failed"), progress=data.get("progress", {}),
            error=data.get("error"), started_at=data.get("started_at"),
            finished_at=data.get("finished_at"), statistics=data.get("statistics", {}),
            writing_quality=data.get("writing_quality"), ai_indicators=data.get("ai_indicators"),
            originality=data.get("originality"),
        )
        # Rehydrate format-specific source elements from the original upload where possible.
        if job.original_bytes:
            try:
                from backend.app.document_processing.parser import DocumentParser
                job.document = DocumentParser.parse_bytes(job.original_bytes, job.filename)
            except Exception:
                pass
        return job

    def save(self, job: Job) -> Job:
        payload = self._encode(job)
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO jobs(job_id, created_at, payload) VALUES(?,?,?) "
                "ON CONFLICT(job_id) DO UPDATE SET created_at=excluded.created_at, payload=excluded.payload",
                (job.job_id, job.created_at, payload),
            )
        self._jobs[job.job_id] = job
        return job

    def create(self, job: Job) -> Job:
        self.save(job)
        self._prune()
        return job

    def get(self, job_id: str) -> Optional[Job]:
        job = self._jobs.get(job_id)
        if job is not None:
            return job
        with self._connect() as connection:
            row = connection.execute("SELECT payload FROM jobs WHERE job_id=?", (job_id,)).fetchone()
        if not row:
            return None
        try:
            job = self._decode(row[0])
            self._jobs[job_id] = job
            return job
        except Exception:
            return None

    def list(self) -> List[Job]:
        return sorted(self._jobs.values(), key=lambda item: item.created_at, reverse=True)

    def delete(self, job_id: str) -> bool:
        self._jobs.pop(job_id, None)
        with self._connect() as connection:
            cursor = connection.execute("DELETE FROM jobs WHERE job_id=?", (job_id,))
        return cursor.rowcount > 0

    def _prune(self) -> None:
        removable = sorted(
            (job for job in self._jobs.values() if job.status not in {"processing", "queued"}),
            key=lambda item: item.created_at,
        )
        while len(self._jobs) > self.max_jobs and removable:
            job = removable.pop(0)
            self.delete(job.job_id)


job_store = SQLiteJobStore()