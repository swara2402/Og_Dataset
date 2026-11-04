"""End-to-end document workflow coverage through the public API."""
import io
import time

from docx import Document
from fastapi.testclient import TestClient

from backend.app.main import app


def _upload_and_wait(client: TestClient, filename: str, text: str) -> tuple[str, dict]:
    response = client.post(
        "/api/v1/documents/upload",
        files={"file": (filename, text.encode("utf-8"), "text/plain")},
        data={"style": "preserve_voice", "auto_start": "true"},
    )
    assert response.status_code == 200, response.text
    job_id = response.json()["job_id"]

    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        status = client.get(f"/api/v1/processing/{job_id}/status")
        assert status.status_code == 200, status.text
        payload = status.json()
        if payload["status"] not in {"queued", "processing"}:
            break
        time.sleep(0.02)
    else:
        raise AssertionError("Document processing did not finish within 10 seconds.")

    assert payload["status"] == "completed", payload
    return job_id, payload


def test_text_document_upload_review_accept_and_export_round_trip():
    original = "The the model was evaluated ,and its result was recorded."
    expected = "The model was evaluated, and its result was recorded."

    with TestClient(app) as client:
        job_id, status = _upload_and_wait(client, "workflow.txt", original)
        assert status["progress"]["percent"] == 100

        document = client.get(f"/api/v1/documents/{job_id}")
        assert document.status_code == 200, document.text
        paragraph = next(
            item for item in document.json()["paragraphs"]
            if item["original"] == original
        )
        assert paragraph["proposal"] == expected
        assert paragraph["review_status"] == "pending"

        results = client.get(f"/api/v1/processing/{job_id}/results")
        assert results.status_code == 200, results.text

        review = client.post(
            f"/api/v1/processing/{job_id}/review",
            json={"paragraph_id": paragraph["id"], "action": "accept"},
        )
        assert review.status_code == 200, review.text
        assert review.json()["paragraph"]["review_status"] == "accepted"

        exported = client.get(f"/api/v1/export/{job_id}/txt")
        assert exported.status_code == 200, exported.text
        assert expected in exported.text
        assert original not in exported.text
        assert "Only accepted changes are included" in exported.headers.get(
            "x-export-notes", ""
        )


def test_rejected_document_proposal_exports_original_text():
    original = "The the model was evaluated ,and its result was recorded."
    expected = "The model was evaluated, and its result was recorded."

    with TestClient(app) as client:
        job_id, _ = _upload_and_wait(client, "rejected-workflow.txt", original)
        document = client.get(f"/api/v1/documents/{job_id}")
        paragraph = next(
            item for item in document.json()["paragraphs"]
            if item["original"] == original
        )

        review = client.post(
            f"/api/v1/processing/{job_id}/review",
            json={"paragraph_id": paragraph["id"], "action": "reject"},
        )
        assert review.status_code == 200, review.text
        assert review.json()["paragraph"]["review_status"] == "rejected"

        exported = client.get(f"/api/v1/export/{job_id}/txt")
        assert exported.status_code == 200, exported.text
        assert original in exported.text
        assert expected not in exported.text


def test_docx_document_workflow_preserves_run_formatting_after_acceptance():
    source = Document()
    paragraph = source.add_paragraph()
    first = paragraph.add_run("The ")
    first.bold = True
    second = paragraph.add_run(
        "the model was evaluated ,and its result was recorded."
    )
    second.italic = True
    buffer = io.BytesIO()
    source.save(buffer)
    original_bytes = buffer.getvalue()

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/documents/upload",
            files={
                "file": (
                    "formatted-workflow.docx",
                    original_bytes,
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
            },
            data={"style": "preserve_voice", "auto_start": "true"},
        )
        assert response.status_code == 200, response.text
        job_id = response.json()["job_id"]

        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            status = client.get(f"/api/v1/processing/{job_id}/status").json()
            if status["status"] not in {"queued", "processing"}:
                break
            time.sleep(0.02)
        assert status["status"] == "completed", status

        document = client.get(f"/api/v1/documents/{job_id}").json()
        paragraph_state = next(
            item for item in document["paragraphs"]
            if item["original"] == "The the model was evaluated ,and its result was recorded."
        )
        accepted = client.post(
            f"/api/v1/processing/{job_id}/review",
            json={"paragraph_id": paragraph_state["id"], "action": "accept"},
        )
        assert accepted.status_code == 200, accepted.text

        exported = client.get(f"/api/v1/export/{job_id}/docx")
        assert exported.status_code == 200, exported.text
        restored = Document(io.BytesIO(exported.content))
        restored_paragraph = next(
            item for item in restored.paragraphs
            if item.text.startswith("The model was evaluated")
        )
        assert restored_paragraph.text == (
            "The model was evaluated, and its result was recorded."
        )
        assert restored_paragraph.runs[0].bold is True
        assert any(run.italic is True for run in restored_paragraph.runs)


def test_paragraph_version_can_be_restored_and_persisted():
    original = "The the model was evaluated ,and its result was recorded."
    with TestClient(app) as client:
        job_id, _ = _upload_and_wait(client, "restore-version.txt", original)
        document = client.get(f"/api/v1/documents/{job_id}").json()
        paragraph = next(item for item in document["paragraphs"] if item["original"] == original)
        assert paragraph["version_count"] >= 2

        restored = client.post(
            f"/api/v1/processing/{job_id}/restore-version",
            json={"paragraph_id": paragraph["id"], "version": 0},
        )
        assert restored.status_code == 200, restored.text
        assert restored.json()["paragraph"]["revised"] == original
        assert restored.json()["paragraph"]["review_status"] == "unchanged"

        refreshed = client.get(f"/api/v1/processing/{job_id}/results").json()
        state = next(item for item in refreshed["results"] if item["id"] == paragraph["id"])
        assert state["revised"] == original


def test_restore_version_rejects_unknown_version():
    original = "The model was evaluated."
    with TestClient(app) as client:
        job_id, _ = _upload_and_wait(client, "restore-missing.txt", original)
        document = client.get(f"/api/v1/documents/{job_id}").json()
        paragraph = next(item for item in document["paragraphs"] if item["original"] == original)
        response = client.post(
            f"/api/v1/processing/{job_id}/restore-version",
            json={"paragraph_id": paragraph["id"], "version": 999},
        )
        assert response.status_code == 404



def test_analysis_report_excludes_authorship_heuristics_and_endpoint_is_removed():
    with TestClient(app) as client:
        job_id, _ = _upload_and_wait(
            client,
            "analysis-report.txt",
            "The model was evaluated on the test set. The results are reported in Table 2.",
        )
        report = client.get(f"/api/v1/analysis/{job_id}/report")
        assert report.status_code == 200, report.text
        assert "writing_quality" in report.json()
        assert "validation" in report.json()
        assert "ai_indicators" not in report.json()

        removed = client.post(
            f"/api/v1/analysis/{job_id}/ai-indicators",
            json={},
        )
        assert removed.status_code == 404
