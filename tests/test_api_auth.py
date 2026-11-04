"""Bearer authentication and per-user document ownership tests."""
import json

from fastapi.testclient import TestClient

from backend.app.core.config import settings
from backend.app.main import app


def test_configured_tokens_require_authentication_and_isolate_jobs():
    previous_tokens = settings.api_tokens
    previous_required = settings.api_auth_required
    settings.api_tokens = json.dumps({"alice": "alice-test-secret-012345678901234567890123456789", "bob": "bob-test-secret-012345678901234567890123456789"})
    settings.api_auth_required = True
    alice = {"Authorization": "Bearer alice-test-secret-012345678901234567890123456789"}
    bob = {"Authorization": "Bearer bob-test-secret-012345678901234567890123456789"}

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
            # Every job-scoped route must enforce ownership before returning
            # status, results, review, analysis, cancellation, or export data.
            assert client.get(f"/api/v1/processing/{job_id}/status", headers=bob).status_code == 404
            assert client.get(f"/api/v1/processing/{job_id}/results", headers=bob).status_code == 404
            assert client.post(f"/api/v1/processing/{job_id}/cancel", headers=bob).status_code == 404
            assert client.post(
                f"/api/v1/processing/{job_id}/review",
                headers=bob,
                json={"paragraph_id": "not-owned", "action": "accept"},
            ).status_code == 404
            assert client.get(f"/api/v1/analysis/{job_id}/report", headers=bob).status_code == 404
            assert client.get(f"/api/v1/export/{job_id}/txt", headers=bob).status_code == 404
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


def test_in_process_rate_limiter_enforces_budget_and_can_reset():
    from backend.app.api.auth import is_rate_limited, reset_rate_limits
    reset_rate_limits()
    try:
        assert is_rate_limited("owner:127.0.0.1", 1) is False
        assert is_rate_limited("owner:127.0.0.1", 1) is True
        assert is_rate_limited("another-owner:127.0.0.1", 1) is False
    finally:
        reset_rate_limits()


def test_api_middleware_returns_429_when_request_budget_is_exhausted():
    from backend.app.api.auth import reset_rate_limits
    previous_limit = settings.api_rate_limit_per_minute
    previous_tokens = settings.api_tokens
    previous_required = settings.api_auth_required
    settings.api_rate_limit_per_minute = 1
    settings.api_tokens = ""
    settings.api_auth_required = False
    reset_rate_limits()
    try:
        with TestClient(app) as client:
            first = client.get("/api/v1/health")
            second = client.get("/api/v1/health")
            assert first.status_code == 200
            assert second.status_code == 429
            assert second.headers["Retry-After"] == "60"
    finally:
        settings.api_rate_limit_per_minute = previous_limit
        settings.api_tokens = previous_tokens
        settings.api_auth_required = previous_required
        reset_rate_limits()


def test_documented_environment_variable_names_are_loaded():
    from backend.app.core.config import Settings

    configured = Settings(
        _env_file=None,
        OG_API_TOKENS='{"user":"test-secret-012345678901234567890123456789"}',
        OG_API_AUTH_REQUIRED=True,
        OG_API_RATE_LIMIT_PER_MINUTE=17,
    )
    assert configured.api_tokens.startswith('{')
    assert configured.api_auth_required is True
    assert configured.api_rate_limit_per_minute == 17
