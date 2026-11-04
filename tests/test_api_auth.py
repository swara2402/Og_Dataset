"""Bearer authentication and per-user document ownership tests."""
import json

from fastapi.testclient import TestClient

from backend.app.core.config import settings
from backend.app.main import app


def test_configured_tokens_require_authentication_and_isolate_jobs():
    previous_tokens = settings.api_tokens
    previous_required = settings.api_auth_required
    settings.api_tokens = json.dumps({"alice": "alice-test-secret", "bob": "bob-test-secret"})
    settings.api_auth_required = True
    alice = {"Authorization": "Bearer alice-test-secret"}
    bob = {"Authorization": "Bearer bob-test-secret"}

    try:
        with TestClient(app) as client:
            unauthenticated = client.get("/api/v1/jobs")
            assert unauthenticated.status_code == 401

            uploaded = client.post(
                "/api/v1/documents/upload",
                headers=alice,
                files={"file": ("private.txt", b"A private document belongs to Alice.", "text/plain")},
                data={"auto_start": "false"},
            )
            assert uploaded.status_code == 200, uploaded.text
            job_id = uploaded.json()["job_id"]

            alice_jobs = client.get("/api/v1/jobs", headers=alice)
            bob_jobs = client.get("/api/v1/jobs", headers=bob)
            assert any(item["job_id"] == job_id for item in alice_jobs.json()["jobs"])
            assert all(item["job_id"] != job_id for item in bob_jobs.json()["jobs"])

            assert client.get(f"/api/v1/documents/{job_id}", headers=alice).status_code == 200
            assert client.get(f"/api/v1/documents/{job_id}", headers=bob).status_code == 404
            assert client.get(
                f"/api/v1/processing/{job_id}/status",
                headers={"Authorization": "Bearer invalid-token"},
            ).status_code == 401

    finally:
        settings.api_tokens = previous_tokens
        settings.api_auth_required = previous_required


def test_auth_required_without_token_configuration_fails_closed():
    previous_tokens = settings.api_tokens
    previous_required = settings.api_auth_required
    settings.api_tokens = ""
    settings.api_auth_required = True
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/jobs")
            assert response.status_code == 503
    finally:
        settings.api_tokens = previous_tokens
        settings.api_auth_required = previous_required
