"""End-to-end document workflow coverage through the public API."""
import time

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
        assert paragraph["review_status"] == "unchanged"

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
