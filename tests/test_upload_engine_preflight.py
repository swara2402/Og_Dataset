"""Upload preflight regression tests."""


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
