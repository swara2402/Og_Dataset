"""Upload preflight regression tests."""

from fastapi.testclient import TestClient

from backend.app.main import app


def test_upload_does_not_persist_when_engine_is_unavailable(monkeypatch):
    import backend.app.api.router as router_module

    with TestClient(app) as client:
        monkeypatch.setattr(router_module, "_engine", None)
        before = {
            item["job_id"]
            for item in client.get("/api/v1/jobs").json()["jobs"]
        }

        response = client.post(
            "/api/v1/documents/upload",
            files={"file": ("unprocessed.txt", b"Keep this document private.", "text/plain")},
            data={"auto_start": "true"},
        )

        assert response.status_code == 503
        after = {
            item["job_id"]
            for item in client.get("/api/v1/jobs").json()["jobs"]
        }
        assert after == before


def test_oversized_upload_is_rejected_without_creating_a_job(monkeypatch):
    import backend.app.api.router as router_module

    with TestClient(app) as client:
        monkeypatch.setattr(router_module._settings, "max_file_size_mb", 0)
        before = {
            item["job_id"]
            for item in client.get("/api/v1/jobs").json()["jobs"]
        }

        response = client.post(
            "/api/v1/documents/upload",
            files={"file": ("too-large.txt", b"X", "text/plain")},
            data={"auto_start": "false"},
        )

        assert response.status_code == 413
        after = {
            item["job_id"]
            for item in client.get("/api/v1/jobs").json()["jobs"]
        }
        assert after == before
