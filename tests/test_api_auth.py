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
        OG_API_ADMIN_USERS="alice,bob",
        OG_API_RATE_LIMIT_PER_MINUTE=17,
    )
    assert configured.api_tokens.startswith('{')
    assert configured.api_auth_required is True
    assert configured.api_admin_users == "alice,bob"
    assert configured.api_rate_limit_per_minute == 17


def test_sqlite_job_storage_uses_private_posix_permissions(tmp_path):
    import os
    import stat
    import pytest
    from backend.app.core.jobs import SQLiteJobStore

    if os.name == "nt":
        pytest.skip("POSIX file permissions are not available on Windows")
    database = tmp_path / "private-data" / "jobs.sqlite3"
    SQLiteJobStore(db_path=str(database))
    assert stat.S_IMODE(database.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(database.stat().st_mode) == 0o600


def test_duplicate_bearer_tokens_are_rejected():
    import pytest
    from backend.app.api.auth import resolve_owner

    shared = "same-secret-012345678901234567890123456789"
    with pytest.raises(ValueError, match="unique bearer token"):
        resolve_owner("Bearer " + shared, json.dumps({"alice": shared, "bob": shared}), True)


def test_global_settings_and_cache_actions_require_admin_token():
    previous_tokens = settings.api_tokens
    previous_required = settings.api_auth_required
    previous_admins = settings.api_admin_users
    settings.api_tokens = json.dumps({
        "alice": "alice-admin-secret-012345678901234567890123456789",
        "bob": "bob-user-secret-012345678901234567890123456789",
    })
    settings.api_auth_required = True
    settings.api_admin_users = "alice"
    alice = {"Authorization": "Bearer alice-admin-secret-012345678901234567890123456789"}
    bob = {"Authorization": "Bearer bob-user-secret-012345678901234567890123456789"}
    try:
        with TestClient(app) as client:
            assert client.patch("/api/v1/config/settings", headers=bob, json={"rule_verbose_logging": True}).status_code == 403
            assert client.post("/api/v1/config/cache/clear", headers=bob).status_code == 403
            assert client.patch("/api/v1/config/settings", headers=alice, json={"rule_verbose_logging": False}).status_code == 200
            assert client.post("/api/v1/config/cache/clear", headers=alice).status_code == 200
    finally:
        settings.api_tokens = previous_tokens
        settings.api_auth_required = previous_required
        settings.api_admin_users = previous_admins


def test_originality_request_rejects_oversized_inputs():
    with TestClient(app) as client:
        too_much_text = client.post(
            "/api/v1/originality/check",
            json={"confirm_search": False, "text": "x" * 100001},
        )
        too_many_paragraphs = client.post(
            "/api/v1/originality/check",
            json={"confirm_search": False, "text": "sample", "paragraph_ids": [str(i) for i in range(13)]},
        )
        assert too_much_text.status_code == 422
        assert too_many_paragraphs.status_code == 422


def test_token_parser_rejects_duplicate_json_user_keys_and_oversized_config():
    import pytest
    from backend.app.api.auth import resolve_owner

    token = "user-secret-012345678901234567890123456789"
    duplicate_keys = '{"alice":"' + token + '","alice":"' + token + 'x"}'
    with pytest.raises(ValueError, match="duplicate user IDs"):
        resolve_owner("Bearer " + token, duplicate_keys, True)

    too_many_users = json.dumps({
        "user-" + str(index): ("secret-" + str(index) + "-" + "x" * 40)
        for index in range(501)
    })
    with pytest.raises(ValueError, match="500 users"):
        resolve_owner("Bearer " + token, too_many_users, True)
