"""Tests for the Turnitout V2 backend.

These tests use fakes and never call the live model or the public web. They
cover the safety-critical paths: classification, protected content, validation,
refinement statistics, analysis disclaimers, and document export.
"""
from __future__ import annotations

import asyncio
import io
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException
from docx import Document as DocxDocument

from backend.app.core.config import Settings
from backend.app.core.jobs import Job, ParagraphState, VersionEntry, job_store
from backend.app.document_processing.parser import (
    DocumentParagraph,
    DocumentParser,
    ParsedDocument,
)
from backend.app.export.exporter import export_document
from backend.app.humanisation.classifier import ParagraphClassifier
from backend.app.humanisation.engine import HumanisationEngine
from backend.app.protected_content.masker import ProtectedContentMasker
from backend.app.quality_analysis.ai_indicators import analyze_ai_indicators
from backend.app.quality_analysis.analyzer import analyze_text, compare_texts
from backend.app.validation.validator import validate_rewrite


def _paragraph(identifier: str, text: str, kind: str = "body") -> DocumentParagraph:
    return DocumentParagraph(
        id=identifier,
        text=text,
        paragraph_type=kind,
        location=f"body.{identifier}",
    )


def _job(paragraphs, *, filename="sample.txt", file_type="txt", original_bytes=b"") -> Job:
    states = []
    for index, item in enumerate(paragraphs):
        states.append(
            ParagraphState(
                id=item.id,
                index=index,
                original_text=item.text,
                paragraph_type=item.paragraph_type,
                category="ordinary_prose",
                section=None,
                eligible=True,
                masked_text=item.text,
            )
        )
    return Job(
        job_id="job-test",
        filename=filename,
        file_type=file_type,
        content_type="text/plain",
        created_at=datetime.now(timezone.utc).isoformat(),
        style="academic",
        options={"passes": 2},
        document=ParsedDocument(
            filename=filename, file_type=file_type, paragraphs=paragraphs
        ),
        paragraphs=states,
        original_bytes=original_bytes,
    )


def test_rejected_hybrid_suggestion_stays_in_history_but_is_not_active_proposal():
    state = ParagraphState(
        id="p-rejected",
        index=0,
        original_text="The original paragraph remains unchanged.",
        paragraph_type="body",
        category="ordinary_prose",
        section=None,
        eligible=True,
    )
    earlier_text = "An earlier suggestion that is now superseded."
    state.versions.append(
        VersionEntry(
            version=1,
            text=earlier_text,
            masked_text=earlier_text,
            pass_number=1,
            source="rule-based",
        )
    )
    rejected_text = "The rejected alternative wording."
    state.versions.append(
        VersionEntry(
            version=2,
            text=rejected_text,
            masked_text=rejected_text,
            pass_number=2,
            source="hybrid-rejected:local_llm",
        )
    )
    state.review_status = "rejected"

    serialized = state.to_dict()

    assert serialized["proposal"] is None
    assert serialized["revised"] == "The original paragraph remains unchanged."
    assert serialized["review_status"] == "rejected"
    assert serialized["versions"][-1]["text"] == rejected_text
    assert serialized["versions"][-1]["source"] == "hybrid-rejected:local_llm"
    assert serialized["versions"][-2]["text"] == earlier_text


def test_classifier_does_not_treat_prose_mention_as_heading():
    classifier = ParagraphClassifier()
    paragraph = _paragraph(
        "p1",
        "Artificial intelligence has transformed the way organizations approach data analysis.",
    )
    result = classifier.classify(paragraph)
    assert result.primary_category != "heading"
    assert result.eligible_for_refinement is True


def test_classifier_treats_short_standalone_heading_as_heading():
    classifier = ParagraphClassifier()
    heading = _paragraph("p1", "2. Data Analysis", kind="body")
    result = classifier.classify(heading)
    assert result.primary_category == "heading"
    assert result.eligible_for_refinement is False
    assert result.features["detected_section"] == "discussion"

    body = _paragraph("p2", "The findings show a clear improvement in accuracy.")
    body_result = classifier.classify(body)
    assert body_result.section_context == "discussion"
    assert body_result.eligible_for_refinement is True


def test_masker_keeps_numbers_citations_readable_and_masks_identifiers():
    text = (
        "Contact a@b.com or visit https://example.test/a?b=1. "
        "The DOI is 10.1234/abcd. Adoption reached 67% (Smith, 2023)."
    )
    masked, replacements, spans = ProtectedContentMasker().mask(text)
    span_types = {span.type for span in spans}

    assert {"email", "url", "doi", "citation"} <= span_types
    assert "number" not in span_types
    assert "67%" in masked
    assert "(Smith, 2023)" not in masked
    assert "a@b.com" not in masked
    values = set(replacements.values())
    assert "a@b.com" in values
    assert any(value.startswith("https://example.test/a?b=1") for value in values)
    assert "10.1234/abcd" in values
    assert "(Smith, 2023)" in values


def test_validator_rejects_missing_number_as_critical():
    result = validate_rewrite(
        "Adoption reached 67% in 2023.",
        "Adoption reached a majority of firms.",
        "Adoption reached 67% in 2023.",
        "Adoption reached a majority of firms.",
        [],
        semantic_similarity_override=0.9,
    )
    assert result["valid"] is False
    assert result["critical"] is True
    assert result["checks"]["numbers"] is False


def test_validator_rejects_changes_to_negation_or_uncertainty():
    result = validate_rewrite(
        "The model may not improve accuracy.",
        "The model improves accuracy.",
        "The model may not improve accuracy.",
        "The model improves accuracy.",
        [],
    )
    assert result["valid"] is False
    assert result["critical"] is True
    assert result["checks"]["modality"] is False


def test_validator_accepts_faithful_rewrite_with_semantic_override():
    original = "Adoption reached 67% in 2023 (Smith, 2023)."
    revised = "In 2023, 67% of firms had adopted the technology (Smith, 2023)."
    result = validate_rewrite(
        original,
        revised,
        original,
        revised,
        [],
        semantic_similarity_override=0.86,
    )
    assert result["valid"] is True
    assert result["critical"] is False
    assert result["checks"]["numbers"] is True
    assert result["checks"]["citations"] is True


def test_quality_and_ai_analysis_are_explicitly_heuristic():
    text = (
        "Artificial intelligence has transformed data analysis. "
        "A 2023 survey reports that 67% of firms use machine learning. "
        "This adoption improves efficiency but raises transparency concerns."
    )
    quality = analyze_text(text)
    report = analyze_ai_indicators(text)

    assert 0 <= quality["flesch_reading_ease"] <= 120
    assert quality["word_count"] > 0
    assert report["detector_available"] is False
    assert "not a verified AI-detection score" in report["detector_note"]
    assert report["indicator_score"] is None
    assert report["band"] == "not_a_detector"


def test_compare_texts_reports_real_deltas():
    comparison = compare_texts(
        "The results are good. The results are clear.",
        "The findings are strong, and the conclusions are clear.",
    )
    assert "overall_score" in comparison["deltas"]
    assert comparison["original"]["word_count"] != comparison["revised"]["word_count"]


def test_parser_round_trips_txt_and_docx():
    txt = DocumentParser.parse_bytes(b"Title\n\nThis is the body paragraph.", "sample.txt")
    assert txt.file_type == "txt"
    assert any(paragraph.paragraph_type == "body" for paragraph in txt.paragraphs)

    document = DocxDocument()
    document.add_heading("Introduction", level=1)
    document.add_paragraph("This is a body paragraph that should be refined.")
    buffer = io.BytesIO()
    document.save(buffer)
    docx = DocumentParser.parse_bytes(buffer.getvalue(), "sample.docx")
    assert docx.file_type == "docx"
    assert any(paragraph.paragraph_type == "heading" for paragraph in docx.paragraphs)


def test_exports_produce_valid_files(tmp_path):
    job = _job(
        [
            _paragraph("p1", "Introduction", kind="heading"),
            _paragraph("p2", "Artificial intelligence improves analytical efficiency."),
        ]
    )

    txt = export_document(job, "txt", str(tmp_path))
    assert txt.suffix == ".txt"
    assert "analytical efficiency" in txt.read_text(encoding="utf-8")

    md = export_document(job, "md", str(tmp_path))
    assert md.suffix == ".md"
    assert "## Introduction" in md.read_text(encoding="utf-8")

    docx = export_document(job, "docx", str(tmp_path))
    assert docx.suffix == ".docx"
    assert docx.read_bytes()[:2] == b"PK"

    pdf = export_document(job, "pdf", str(tmp_path))
    assert pdf.suffix == ".pdf"
    assert pdf.read_bytes().startswith(b"%PDF")


def test_export_uses_only_accepted_proposals(tmp_path):
    job = _job([_paragraph("p1", "The the model was evaluated.")])
    state = job.paragraphs[0]
    state.current_text = "The model was evaluated."
    state.review_status = "pending"

    pending = export_document(job, "txt", str(tmp_path)).read_text(encoding="utf-8")
    assert "The the model was evaluated." in pending

    state.review_status = "accepted"
    accepted = export_document(job, "txt", str(tmp_path)).read_text(encoding="utf-8")
    assert "The model was evaluated." in accepted
    assert "The the model was evaluated." not in accepted


def test_engine_processes_long_documents_without_dropping_paragraphs():
    paragraphs = [
        _paragraph(
            f"p{index}",
            "The the model was evaluated ,and its result was recorded."
            if index % 7 == 0
            else f"Paragraph {index} is already clear and remains unchanged.",
        )
        for index in range(175)
    ]
    job = _job(paragraphs)
    engine = HumanisationEngine(Settings())

    asyncio.run(engine.process_job(job))

    assert job.status == "completed"
    assert len(job.paragraphs) == len(paragraphs)
    assert job.progress["completed"] == len(paragraphs)
    assert job.progress["percent"] == 100
    assert job.paragraphs[0].current_text == (
        "The model was evaluated, and its result was recorded."
    )
    assert job.paragraphs[1].current_text == paragraphs[1].text
    assert job.statistics["unchanged_paragraphs"] > 0
    assert job.statistics["dataset"]["version"] == "1.1.0"


def test_engine_does_not_skip_or_truncate_a_long_paragraph():
    original = "The system remains clear. " * 1200
    job = _job([_paragraph("long", original)])
    asyncio.run(HumanisationEngine(Settings()).process_job(job))
    assert job.paragraphs[0].current_text == original
    assert job.paragraphs[0].status == "completed"
    assert job.progress["completed"] == 1


def test_engine_preserves_citations_numbers_quotes_and_technical_terms():
    original = (
        'The the CNN model was evaluated ,and achieved 67% accuracy in 2023 '
        '(Smith, 2023). The quoted phrase "the the model" remains as supplied.'
    )
    job = _job([_paragraph("p1", original)])
    engine = HumanisationEngine(Settings())

    asyncio.run(engine.process_job(job))

    state = job.paragraphs[0]
    assert state.current_text == (
        'The CNN model was evaluated, and achieved 67% accuracy in 2023 '
        '(Smith, 2023). The quoted phrase "the the model" remains as supplied.'
    )
    assert state.edit_scope == "phrase"
    assert state.applied_rule_ids == ["GRAMMAR-001"]
    assert state.validation["checks"]["numbers"] is True
    assert state.validation["checks"]["citations"] is True


def test_docx_parser_and_export_keep_interleaved_tables_in_order(tmp_path):
    document = DocxDocument()
    document.add_heading("Introduction", level=1)
    document.add_paragraph("The the first body paragraph.")
    table = document.add_table(rows=1, cols=1)
    table.cell(0, 0).text = "Table content remains protected."
    document.add_paragraph("The final body paragraph.")
    source = io.BytesIO()
    document.save(source)

    parsed = DocumentParser.parse_bytes(source.getvalue(), "ordered.docx")
    assert [item.text for item in parsed.paragraphs] == [
        "Introduction",
        "The the first body paragraph.",
        "Table content remains protected.",
        "The final body paragraph.",
    ]
    assert len({item.id for item in parsed.paragraphs}) == len(parsed.paragraphs)

    states = [
        ParagraphState(
            id=item.id,
            index=index,
            original_text=item.text,
            paragraph_type=item.paragraph_type,
            category=item.paragraph_type,
            section=None,
            eligible=item.paragraph_type == "body",
            masked_text=item.text,
        )
        for index, item in enumerate(parsed.paragraphs)
    ]
    job = Job(
        job_id="docx-order",
        filename=parsed.filename,
        file_type="docx",
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        created_at=datetime.now(timezone.utc).isoformat(),
        style="academic",
        options={},
        document=parsed,
        paragraphs=states,
        original_bytes=source.getvalue(),
    )
    asyncio.run(HumanisationEngine(Settings()).process_job(job))
    states[1].review_status = "accepted"
    exported = export_document(job, "docx", str(tmp_path))
    round_trip = DocumentParser.parse_bytes(exported.read_bytes(), "round-trip.docx")
    assert [item.text for item in round_trip.paragraphs] == [
        "Introduction",
        "The first body paragraph.",
        "Table content remains protected.",
        "The final body paragraph.",
    ]


def test_pdf_extraction_and_reconstruction_cover_all_pages():
    fitz = pytest.importorskip("fitz")
    source = fitz.open()
    first = source.new_page()
    first.insert_text((72, 72), "Abstract")
    first.insert_text((72, 100), "The complete abstract remains available.")
    second = source.new_page()
    second.insert_text((72, 72), "Conclusion")
    second.insert_text((72, 100), "The final conclusion remains available.")
    parsed = DocumentParser.parse_bytes(source.tobytes(), "paper.pdf")
    assert len(parsed.paragraphs) >= 4
    assert any("complete abstract" in item.text for item in parsed.paragraphs)
    assert any("final conclusion" in item.text for item in parsed.paragraphs)

    job = _job(parsed.paragraphs, filename="paper.pdf", file_type="pdf")
    asyncio.run(HumanisationEngine(Settings()).process_job(job))
    from backend.app.export.exporter import _pdf_bytes

    reconstructed = fitz.open(stream=_pdf_bytes(job), filetype="pdf")
    extracted = "\n".join(page.get_text() for page in reconstructed)
    assert "complete abstract" in extracted
    assert "final conclusion" in extracted


def test_review_endpoint_accepts_and_rejects_proposals():
    from backend.app.api import router
    from backend.app.api.router import ReviewRequest

    job = _job([_paragraph("p1", "The the model was evaluated.")])
    engine = HumanisationEngine(Settings())
    asyncio.run(engine.process_job(job))
    job_store.create(job)

    rejected = asyncio.run(
        router.review_paragraph(job.job_id, ReviewRequest(paragraph_id="p1", action="reject"))
    )
    assert rejected["paragraph"]["revised"] == "The the model was evaluated."
    assert rejected["paragraph"]["review_status"] == "rejected"

    accepted = asyncio.run(
        router.review_paragraph(job.job_id, ReviewRequest(paragraph_id="p1", action="accept"))
    )
    assert accepted["paragraph"]["revised"] == "The model was evaluated."
    assert accepted["paragraph"]["review_status"] == "accepted"


def test_hybrid_proposal_review_persists_acceptance_and_rejects_protected_changes():
    from backend.app.api import router
    from backend.app.api.router import HybridProposalReviewRequest

    original = "The model reports 67% accuracy and cites Smith (2023)."
    engine = HumanisationEngine(Settings())

    accepted_job = _job([_paragraph("hybrid-p1", original)])
    accepted_job.job_id = "hybrid-review-accept-test"
    asyncio.run(engine.process_job(accepted_job))
    job_store.create(accepted_job)
    accepted_state = accepted_job.paragraphs[0]
    current = accepted_state.current_text
    with pytest.raises(HTTPException) as stale_exc:
        asyncio.run(
            router.review_hybrid_proposal(
                accepted_job.job_id,
                HybridProposalReviewRequest(
                    paragraph_id="hybrid-p1",
                    proposal_id="proposal-stale",
                    original_text="An outdated paragraph snapshot.",
                    suggested_text="A stale alternative paragraph.",
                    source_engine="rule_engine",
                    action="accept",
                ),
            )
        )
    assert stale_exc.value.status_code == 409
    accepted = asyncio.run(
        router.review_hybrid_proposal(
            accepted_job.job_id,
            HybridProposalReviewRequest(
                paragraph_id="hybrid-p1",
                proposal_id="proposal-1",
                original_text=current,
                suggested_text="The model achieves 67% accuracy, as reported by Smith (2023).",
                source_engine="rule_engine",
                explanation="Clarifies the result statement.",
                action="accept",
            ),
        )
    )
    assert accepted["decision"] == "accept"
    assert accepted["paragraph"]["review_status"] == "accepted"
    assert accepted["paragraph"]["revised"] == "The model achieves 67% accuracy, as reported by Smith (2023)."
    assert accepted["paragraph"]["versions"][-1]["source"] == "hybrid:rule_engine"

    rejected_job = _job([_paragraph("hybrid-p2", original)])
    rejected_job.job_id = "hybrid-review-reject-test"
    asyncio.run(engine.process_job(rejected_job))
    job_store.create(rejected_job)
    rejected_state = rejected_job.paragraphs[0]
    rejected_original = rejected_state.current_text
    rejected = asyncio.run(
        router.review_hybrid_proposal(
            rejected_job.job_id,
            HybridProposalReviewRequest(
                paragraph_id="hybrid-p2",
                proposal_id="proposal-2",
                original_text=rejected_original,
                suggested_text="The model reports 67% accuracy and cites Smith (2023) clearly.",
                source_engine="local_llm",
                action="reject",
            ),
        )
    )
    assert rejected["decision"] == "reject"
    assert rejected["paragraph"]["review_status"] == "rejected"
    assert rejected["paragraph"]["revised"] == rejected_original
    assert rejected["paragraph"]["versions"][-1]["source"] == "hybrid-rejected:local_llm"
    assert rejected["paragraph"]["proposal"] is None

    with pytest.raises(HTTPException) as reaccept_exc:
        asyncio.run(
            router.review_paragraph(
                rejected_job.job_id,
                router.ReviewRequest(paragraph_id="hybrid-p2", action="accept"),
            )
        )
    assert reaccept_exc.value.status_code == 409

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            router.review_hybrid_proposal(
                rejected_job.job_id,
                HybridProposalReviewRequest(
                    paragraph_id="hybrid-p2",
                    proposal_id="proposal-3",
                    original_text=rejected_original,
                    suggested_text=rejected_original.replace("67%", "99%"),
                    source_engine="local_llm",
                    action="accept",
                ),
            )
        )
    assert exc.value.status_code == 422


def test_upload_api_processes_full_document_and_exports_after_review(tmp_path):
    from fastapi.testclient import TestClient

    from backend.app.core.config import settings as app_settings
    from backend.app.main import app

    original_export_dir = app_settings.export_dir
    app_settings.export_dir = str(tmp_path)
    content = (
        "Abstract\n\n"
        "The the abstract reports 67% accuracy in 2023.\n\n"
        "Introduction\n\n"
        "This introduction is already clear."
    )
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/documents/upload",
                files={"file": ("paper.txt", content.encode(), "text/plain")},
                data={"auto_start": "true"},
            )
            assert response.status_code == 200
            job_id = response.json()["job_id"]

            for _ in range(100):
                status = client.get(f"/api/v1/processing/{job_id}/status").json()
                if status["status"] in {"completed", "failed"}:
                    break
                asyncio.run(asyncio.sleep(0.02))
            assert status["status"] == "completed", status

            results = client.get(f"/api/v1/processing/{job_id}/results").json()
            assert len(results["results"]) == 4
            assert results["statistics"]["dataset"]["version"] == "1.1.0"
            assert results["results"][1]["proposal"] == (
                "The abstract reports 67% accuracy in 2023."
            )
            assert results["results"][3]["revised"] == "This introduction is already clear."

            review = client.post(
                f"/api/v1/processing/{job_id}/review",
                json={"paragraph_id": results["results"][1]["id"], "action": "accept"},
            )
            assert review.status_code == 200
            exported = client.post(
                f"/api/v1/export/{job_id}", params={"format": "txt"}
            )
            assert exported.status_code == 200
            assert "The abstract reports 67% accuracy in 2023." in exported.text
            assert "Introduction" in exported.text
    finally:
        app_settings.export_dir = original_export_dir
