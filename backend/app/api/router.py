"""Turnitout V2 API.

Separates document ingestion, humanisation, validation, writing-quality
analysis, originality checking and export.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from backend.app.core.config import Settings, settings
from backend.app.core.jobs import Job, ParagraphState, job_store, now_iso
from backend.app.document_processing.parser import DocumentParser
from backend.app.export.exporter import export_document, export_notes
from backend.app.humanisation.classifier import ParagraphClassifier
from backend.app.humanisation.engine import HumanisationEngine

from backend.app.originality.detector import check_originality
from backend.app.originality.providers import DuckDuckGoProvider
from backend.app.protected_content.masker import ProtectedContentMasker
from backend.app.quality_analysis.ai_indicators import analyze_ai_indicators
from backend.app.quality_analysis.analyzer import compare_texts

logger = logging.getLogger(__name__)
api_router = APIRouter()

_engine: Optional[HumanisationEngine] = None
_settings: Settings = settings


def set_global_services(
    engine: HumanisationEngine,
    app_settings: Settings,
) -> None:
    global _engine, _settings
    _engine = engine
    _settings = app_settings





def _require_engine() -> HumanisationEngine:
    if _engine is None:
        raise HTTPException(status_code=503, detail="Humanisation engine is not initialized.")
    return _engine


def _get_job(job_id: str) -> Job:
    job = job_store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    return job


def _get_state(job: Job, paragraph_id: str) -> ParagraphState:
    for state in job.paragraphs:
        if state.id == paragraph_id:
            return state
    raise HTTPException(status_code=404, detail=f"Paragraph {paragraph_id} not found.")


# --------------------------------------------------------------------- schemas
class UploadResponse(BaseModel):
    job_id: str
    filename: str
    file_size: int
    upload_time: str
    style: str
    status: str
    statistics: Dict[str, Any]
    warnings: List[str] = Field(default_factory=list)


class StatusResponse(BaseModel):
    job_id: str
    status: str
    progress: Dict[str, Any]
    elapsed_time: float
    estimated_remaining: Optional[float] = None
    error: Optional[str] = None


class CancelResponse(BaseModel):
    job_id: str
    cancelled: bool
    message: str


class ModelsResponse(BaseModel):
    available: bool
    models: List[Dict[str, Any]]
    current_model: str


class SettingsUpdate(BaseModel):
    rule_verbose_logging: Optional[bool] = None


class RefineRequest(BaseModel):
    paragraph_id: str
    instruction: str = ""
    style: Optional[str] = None
    pass_number: Optional[int] = Field(default=None, ge=1, le=10)


class ReviewRequest(BaseModel):
    paragraph_id: str
    action: Literal["accept", "reject"]


class OriginalityRequest(BaseModel):
    confirm_search: bool = False
    job_id: Optional[str] = None
    text: Optional[str] = None
    paragraph_ids: Optional[List[str]] = None
    max_sentences: int = Field(default=6, ge=1, le=12)
    fetch_pages: bool = True


class AnalysisRequest(BaseModel):
    text: Optional[str] = None


# ------------------------------------------------------------------- health
@api_router.get("/health")
async def health() -> Dict[str, Any]:
    dataset_status = _engine.dataset_status() if _engine else {}
    return {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "services": {
            "api": "online",
            "processor": "online" if _engine else "unavailable",
            "cache": "online",
            "rule_engine": "online" if _engine and dataset_status else "unavailable",
        },
        "engine_type": "deterministic-rule-based",
        "engine_status": "ready" if _engine and dataset_status else "unavailable",
        "installed_rule_count": dataset_status.get("rules_loaded", 0),
        "rules_loaded": bool(dataset_status),
        "dataset": dataset_status,
    }


@api_router.get("/config/settings")
async def get_settings() -> Dict[str, Any]:
    return {
        "engine_type": "deterministic-rule-based",
        "engine_status": "ready" if _engine else "unavailable",
        "dataset": _engine.dataset_status() if _engine else {},
        "batch_size": _settings.turnitout_batch_size,
        "max_workers": _settings.turnitout_max_workers,
        "max_retries": _settings.turnitout_max_retries,
        "passes": _settings.turnitout_max_passes,
        "rule_engine_enabled": _settings.rule_engine_enabled,
        "rule_verbose_logging": _settings.rule_verbose_logging,
        "privacy": {
            "local_only": True,
            "hosted_llm": False,
            "originality_search": _settings.enable_web_originality,
            "originality_note": (
                "Originality search is opt-in. Only selected sentences are sent to the "
                "public search provider; the document itself is never uploaded."
            ),
        },
        "cache_entries": len(_engine.cache) if _engine else 0,
        "styles": ["academic", "professional", "natural", "concise", "executive", "preserve_voice"],
    }


@api_router.patch("/config/settings")
async def update_settings(update: SettingsUpdate) -> Dict[str, Any]:
    if update.rule_verbose_logging is not None:
        _settings.rule_verbose_logging = update.rule_verbose_logging
    return await get_settings()


@api_router.post("/config/cache/clear")
async def clear_cache() -> Dict[str, Any]:
    if _engine:
        _engine.cache.clear()
    return {"cleared": True, "cache_entries": len(_engine.cache) if _engine else 0}


# ---------------------------------------------------------------------- jobs
@api_router.get("/jobs")
async def list_jobs() -> Dict[str, Any]:
    return {"jobs": [job.summary() for job in job_store.list()]}


@api_router.delete("/jobs/{job_id}")
async def delete_job(job_id: str) -> Dict[str, Any]:
    job = _get_job(job_id)
    if job.status in {"processing", "queued"}:
        raise HTTPException(status_code=409, detail="Cancel the job before deleting it.")
    job_store.delete(job_id)
    return {"deleted": True, "job_id": job_id}


# ------------------------------------------------------------------ documents
@api_router.post("/documents/upload", response_model=UploadResponse)
async def upload_document(
    file: UploadFile = File(...),
    style: str = Form("academic"),
    passes: int = Form(0),
    batch_size: int = Form(0),
    auto_start: bool = Form(True),
) -> UploadResponse:
    filename = file.filename or "document.txt"
    suffix = Path(filename).suffix.lower()
    allowed = {".docx", ".pdf", ".txt", ".md", ".markdown", ".text"}
    if suffix not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file format '{suffix or 'unknown'}'. Allowed: DOCX, PDF, TXT, MD.",
        )
    try:
        data = await file.read()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not read upload: {exc}") from exc
    size = len(data)
    if size == 0:
        raise HTTPException(status_code=400, detail="The uploaded file is empty.")
    if size > _settings.max_file_size_mb * 1024 * 1024:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds the {_settings.max_file_size_mb} MB limit.",
        )

    try:
        document = DocumentParser.parse_bytes(data, filename)
    except Exception as exc:
        logger.exception("Document parsing failed")
        raise HTTPException(status_code=400, detail=f"Document parsing failed: {exc}") from exc

    if not document.paragraphs:
        raise HTTPException(status_code=400, detail="No readable text was found in the document.")

    classifier = ParagraphClassifier()
    classifications = classifier.classify_all(document.paragraphs)
    masker = ProtectedContentMasker()
    states: List[ParagraphState] = []
    warnings: List[str] = []
    if document.file_type == "pdf":
        warnings.append(
            "PDF extraction recovers text and paragraph order but may lose complex layout, "
            "columns and embedded tables."
        )

    for index, (paragraph, classification) in enumerate(zip(document.paragraphs, classifications)):
        eligible = classification.eligible_for_refinement
        masked_text, replacements, spans = masker.mask(paragraph.text)
        protected_items = [
            {
                "start": span.start,
                "end": span.end,
                "value": span.value,
                "type": span.type,
                "placeholder": span.placeholder,
            }
            for span in spans
        ]
        states.append(
            ParagraphState(
                id=paragraph.id,
                index=index,
                original_text=paragraph.text,
                paragraph_type=paragraph.paragraph_type,
                category=classification.primary_category,
                section=classification.section_context,
                eligible=eligible,
                masked_text=masked_text,
                replacements=replacements,
                protected_items=protected_items,
            )
        )

    job_id = str(uuid.uuid4())
    eligible_count = sum(1 for state in states if state.eligible)
    options = {
        "passes": 1,
        "batch_size": batch_size if 1 <= batch_size <= 8 else _settings.turnitout_batch_size,
    }
    job = Job(
        job_id=job_id,
        filename=filename,
        file_type=document.file_type,
        content_type=file.content_type or "application/octet-stream",
        created_at=now_iso(),
        style=style if style in {
            "academic", "professional", "natural", "concise", "executive", "preserve_voice"
        } else "academic",
        options=options,
        document=document,
        paragraphs=states,
        original_bytes=data,
        statistics={
            "total_paragraphs": len(states),
            "eligible_paragraphs": eligible_count,
            "skipped_paragraphs": len(states) - eligible_count,
            "successfully_processed": 0,
            "warnings": warnings,
        },
    )
    job.progress = {
        "phase": "queued",
        "pass": 0,
        "total_passes": options["passes"],
        "total": len(states),
        "completed": 0,
        "failed": 0,
        "skipped": len(states) - eligible_count,
        "pending": eligible_count,
        "work_completed": 0,
        "work_total": len(states),
        "percent": 0.0,
        "elapsed_seconds": 0.0,
        "estimated_remaining": None,
    }
    job_store.create(job)

    if auto_start:
        if _engine is None:
            raise HTTPException(status_code=503, detail="Humanisation engine is not initialized.")
        job.status = "queued"
        job.task = asyncio.create_task(_engine.process_job(job))

    return UploadResponse(
        job_id=job.job_id,
        filename=job.filename,
        file_size=size,
        upload_time=job.created_at,
        style=job.style,
        status=job.status,
        statistics=job.statistics,
        warnings=warnings,
    )


@api_router.get("/documents/{job_id}")
async def get_document(job_id: str) -> Dict[str, Any]:
    job = _get_job(job_id)
    return {
        "job_id": job.job_id,
        "filename": job.filename,
        "file_type": job.file_type,
        "status": job.status,
        "style": job.style,
        "created_at": job.created_at,
        "statistics": job.statistics,
        "paragraphs": [state.to_dict() for state in job.paragraphs],
    }


# ----------------------------------------------------------------- processing
@api_router.get("/processing/{job_id}/status", response_model=StatusResponse)
async def processing_status(job_id: str) -> StatusResponse:
    job = _get_job(job_id)
    return StatusResponse(
        job_id=job.job_id,
        status=job.status,
        progress=job.progress,
        elapsed_time=round(job.elapsed_seconds, 1),
        estimated_remaining=job.progress.get("estimated_remaining"),
        error=job.error,
    )


@api_router.post("/processing/{job_id}/cancel", response_model=CancelResponse)
async def cancel_processing(job_id: str) -> CancelResponse:
    job = _get_job(job_id)
    if job.status not in {"queued", "processing"}:
        return CancelResponse(
            job_id=job_id,
            cancelled=False,
            message=f"Job is already {job.status}.",
        )
    job.cancel_event.set()
    if job.task and not job.task.done():
        job.task.cancel()
    job.status = "cancelled"
    job.progress["phase"] = "cancelled"
    return CancelResponse(job_id=job_id, cancelled=True, message="Processing cancellation requested.")


@api_router.get("/processing/{job_id}/results")
async def processing_results(job_id: str) -> Dict[str, Any]:
    job = _get_job(job_id)
    if job.status in {"queued", "processing"}:
        raise HTTPException(status_code=409, detail="Job has not finished yet.")
    return job.to_results()


@api_router.post("/processing/{job_id}/refine")
async def refine_paragraph(job_id: str, request: RefineRequest) -> Dict[str, Any]:
    job = _get_job(job_id)
    if job.status in {"queued", "processing"}:
        raise HTTPException(status_code=409, detail="Wait for the current processing to finish.")
    state = _get_state(job, request.paragraph_id)
    if state.paragraph_type != "body":
        raise HTTPException(status_code=400, detail="Only body paragraphs can be refined.")
    engine = _require_engine()
    try:
        await engine.refine_paragraph(
            job,
            state,
            instruction=request.instruction,
            style=request.style or job.style,
            pass_number=request.pass_number,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    job.writing_quality = None
    job.ai_indicators = None
    job.originality = None
    return {
        "job_id": job.job_id,
        "paragraph": state.to_dict(),
        "statistics": job.statistics,
    }


@api_router.post("/processing/{job_id}/review")
async def review_paragraph(job_id: str, request: ReviewRequest) -> Dict[str, Any]:
    job = _get_job(job_id)
    if job.status in {"queued", "processing"}:
        raise HTTPException(status_code=409, detail="Wait for document processing to finish.")
    state = _get_state(job, request.paragraph_id)
    if request.action == "accept":
        if state.review_status == "rejected":
            proposal = next(
                (version for version in reversed(state.versions) if version.source != "original"),
                None,
            )
            if proposal is None:
                raise HTTPException(status_code=409, detail="No proposed change is available.")
            state.current_text = proposal.text
            state.current_masked_text = proposal.masked_text
            state.validation = proposal.validation
            state.applied_rule_ids = proposal.applied_rule_ids
            state.edit_rationale = proposal.edit_rationale
        elif not state.processed:
            raise HTTPException(status_code=409, detail="There is no proposed change to accept.")
        state.review_status = "accepted"
    else:
        if not state.processed:
            raise HTTPException(status_code=409, detail="There is no proposed change to reject.")
        state.current_text = state.original_text
        state.current_masked_text = state.masked_text or state.original_text
        state.review_status = "rejected"

    if _engine:
        _engine._finalise_statistics(job)
    job.writing_quality = None
    job.ai_indicators = None
    job.originality = None
    return {
        "job_id": job.job_id,
        "paragraph": state.to_dict(),
        "statistics": job.statistics,
    }


# ------------------------------------------------------------------- analysis
def _combined_text(job: Job, revised: bool) -> str:
    return "\n\n".join(
        state.current_text if revised else state.original_text for state in job.paragraphs
    )


def _validation_summary(job: Job) -> Dict[str, Any]:
    processed = [state for state in job.paragraphs if state.eligible]
    critical = []
    warnings = []
    for state in processed:
        for issue in state.validation.get("issues", []):
            critical.append({"paragraph_id": state.id, "issue": issue})
        for warning in state.validation.get("warnings", []):
            warnings.append({"paragraph_id": state.id, "warning": warning})
    protected_ok = all(
        state.validation.get("checks", {}).get("protected_placeholders", True)
        and state.validation.get("checks", {}).get("protected_values", True)
        for state in processed
        if state.validation
    )
    numbers_ok = all(
        state.validation.get("checks", {}).get("numbers", True)
        for state in processed
        if state.validation
    )
    citations_ok = all(
        state.validation.get("checks", {}).get("citations", True)
        for state in processed
        if state.validation
    )
    return {
        "protected_content_preserved": protected_ok,
        "numbers_preserved": numbers_ok,
        "citations_preserved": citations_ok,
        "critical_issues": critical,
        "warnings": warnings,
        "checked_paragraphs": len([state for state in processed if state.validation]),
    }


def _build_analysis(job: Job) -> Dict[str, Any]:
    quality = compare_texts(_combined_text(job, False), _combined_text(job, True))
    ai_report = analyze_ai_indicators(_combined_text(job, True))
    return {
        "job_id": job.job_id,
        "filename": job.filename,
        "style": job.style,
        "status": job.status,
        "statistics": job.statistics,
        "writing_quality": quality,
        "ai_indicators": ai_report,
        "validation": _validation_summary(job),
        "originality": job.originality,
        "disclaimer": (
            "Writing-quality and AI-indicator values are local heuristics, not a verified "
            "AI-detector result. Originality results are a sampled public-web search and "
            "must be reviewed manually."
        ),
    }


@api_router.get("/analysis/{job_id}/report")
async def analysis_report(job_id: str) -> Dict[str, Any]:
    job = _get_job(job_id)
    report = _build_analysis(job)
    job.writing_quality = report["writing_quality"]
    job.ai_indicators = report["ai_indicators"]
    return report


@api_router.post("/analysis/{job_id}/writing-quality")
async def writing_quality(job_id: str, request: AnalysisRequest) -> Dict[str, Any]:
    job = _get_job(job_id)
    original = request.text if request.text else _combined_text(job, False)
    revised = request.text if request.text else _combined_text(job, True)
    result = compare_texts(original, revised)
    job.writing_quality = result
    return result


@api_router.post("/analysis/{job_id}/ai-indicators")
async def ai_indicators(job_id: str, request: AnalysisRequest) -> Dict[str, Any]:
    job = _get_job(job_id)
    text = request.text if request.text else _combined_text(job, True)
    result = analyze_ai_indicators(text)
    job.ai_indicators = result
    return result


# ---------------------------------------------------------------- originality
@api_router.post("/originality/check")
async def originality_check(request: OriginalityRequest) -> Dict[str, Any]:
    if not request.confirm_search:
        raise HTTPException(
            status_code=400,
            detail=(
                "Explicit confirmation is required. Only selected sentences are sent to "
                "the public search provider; set confirm_search=true to proceed."
            ),
        )
    if not _settings.enable_web_originality:
        raise HTTPException(status_code=503, detail="Web originality search is disabled in settings.")

    job: Optional[Job] = None
    if request.text:
        text = request.text
    elif request.job_id:
        job = _get_job(request.job_id)
        if request.paragraph_ids:
            selected = []
            for paragraph_id in request.paragraph_ids:
                selected.append(_get_state(job, paragraph_id).current_text)
            text = "\n\n".join(selected)
        else:
            text = _combined_text(job, True)
    else:
        raise HTTPException(status_code=400, detail="Provide text or job_id.")

    provider = DuckDuckGoProvider(
        timeout=_settings.web_timeout,
        user_agent=_settings.web_user_agent,
        max_pages=_settings.web_pages_per_query,
    )
    try:
        report = await check_originality(
            text,
            provider,
            max_queries=min(request.max_sentences, _settings.web_max_queries),
            pages_per_query=_settings.web_pages_per_query,
            fetch_pages=request.fetch_pages,
        )
    except Exception as exc:
        logger.exception("Originality search failed")
        raise HTTPException(status_code=502, detail=f"Source search failed: {exc}") from exc

    if job is not None:
        job.originality = report
    return report


# --------------------------------------------------------------------- export
def _export_response(job_id: str, fmt: str) -> FileResponse:
    job = _get_job(job_id)
    if job.status in {"queued", "processing"}:
        raise HTTPException(status_code=409, detail="Wait for processing to finish before exporting.")
    try:
        path = export_document(job, fmt, _settings.export_dir)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    notes = export_notes(job, fmt)
    media_types = {
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "pdf": "application/pdf",
        "md": "text/markdown",
        "txt": "text/plain",
    }
    headers = {"X-Export-Notes": " | ".join(notes)[:900]} if notes else None
    return FileResponse(path, filename=path.name, media_type=media_types.get(fmt, "application/octet-stream"), headers=headers)


@api_router.post("/export/{job_id}")
async def export_post(job_id: str, format: str = Query("docx")) -> FileResponse:
    return _export_response(job_id, format)


@api_router.get("/export/{job_id}/{format}")
async def export_get(job_id: str, format: str) -> FileResponse:
    return _export_response(job_id, format)