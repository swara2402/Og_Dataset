from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.api.auth import current_owner_id
from starlette.requests import Request

from backend.app.api import feedback


def _client(tmp_path, monkeypatch):
    monkeypatch.setattr(feedback, "DB_PATH", tmp_path / "feedback.sqlite3")
    app = FastAPI()

    @app.middleware("http")
    async def test_owner_scope(request: Request, call_next):
        owner = request.headers.get("x-test-owner", "local")
        token = current_owner_id.set(owner)
        try:
            return await call_next(request)
        finally:
            current_owner_id.reset(token)

    app.include_router(feedback.router, prefix="/api/v1")
    return TestClient(app)


def _payload(**updates):
    payload = {
        "consent": True,
        "consent_version": "v1",
        "suggestion_id": "suggestion-1",
        "action": "accepted",
        "protected_span_integrity": "passed",
    }
    payload.update(updates)
    return payload


def test_feedback_requires_explicit_consent(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    response = client.post("/api/v1/feedback", json=_payload(consent=False))
    assert response.status_code == 403
    assert not (tmp_path / "feedback.sqlite3").exists()


def test_feedback_stores_structured_event_without_document_text(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    response = client.post("/api/v1/feedback", json=_payload())
    assert response.status_code == 201
    body = response.json()
    assert body["recorded"] is True
    assert body["stored_text"] is False

    import sqlite3
    with sqlite3.connect(tmp_path / "feedback.sqlite3") as connection:
        row = connection.execute("SELECT payload FROM feedback_events").fetchone()
    assert row is not None
    assert "original_text" not in row[0]
    assert "suggested_text" not in row[0]


def test_feedback_rejects_raw_document_text_fields(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    response = client.post(
        "/api/v1/feedback",
        json=_payload(original_text="private document passage"),
    )
    assert response.status_code == 422


def test_rating_action_requires_rating(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    response = client.post("/api/v1/feedback", json=_payload(action="rated"))
    assert response.status_code == 422


def test_feedback_can_be_deleted_by_owning_account(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    created = client.post("/api/v1/feedback", json=_payload())
    event_id = created.json()["event_id"]
    deleted = client.delete(f"/api/v1/feedback/{event_id}")
    assert deleted.status_code == 200
    assert deleted.json()["deleted"] is True
    with __import__("sqlite3").connect(tmp_path / "feedback.sqlite3") as connection:
        count = connection.execute("SELECT COUNT(*) FROM feedback_events").fetchone()[0]
    assert count == 0


def test_account_can_withdraw_and_delete_all_feedback(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    client.post("/api/v1/feedback", json=_payload())
    client.post("/api/v1/feedback", json=_payload(suggestion_id="suggestion-2"))
    deleted = client.delete("/api/v1/feedback")
    assert deleted.status_code == 200
    assert deleted.json()["events_deleted"] == 2


def test_feedback_can_be_deleted_by_event_id(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    created = client.post("/api/v1/feedback", json=_payload()).json()
    deleted = client.delete(f"/api/v1/feedback/{created['event_id']}")
    assert deleted.status_code == 200
    assert deleted.json()["deleted"] is True


def test_feedback_can_be_deleted_in_bulk(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    client.post("/api/v1/feedback", json=_payload())
    client.post("/api/v1/feedback", json=_payload(suggestion_id="suggestion-2"))
    deleted = client.delete("/api/v1/feedback")
    assert deleted.status_code == 200
    assert deleted.json()["events_deleted"] == 2


def test_feedback_deletion_is_scoped_to_account_owner(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    created = client.post("/api/v1/feedback", json=_payload(), headers={"x-test-owner": "alice"})
    event_id = created.json()["event_id"]

    other_owner_delete = client.delete(
        f"/api/v1/feedback/{event_id}", headers={"x-test-owner": "bob"}
    )
    assert other_owner_delete.status_code == 404

    owner_delete = client.delete(
        f"/api/v1/feedback/{event_id}", headers={"x-test-owner": "alice"}
    )
    assert owner_delete.status_code == 200


def test_bulk_feedback_deletion_is_scoped_to_account_owner(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    client.post("/api/v1/feedback", json=_payload(), headers={"x-test-owner": "alice"})
    client.post(
        "/api/v1/feedback",
        json=_payload(suggestion_id="bob-suggestion"),
        headers={"x-test-owner": "bob"},
    )

    deleted = client.delete("/api/v1/feedback", headers={"x-test-owner": "alice"})
    assert deleted.status_code == 200
    assert deleted.json()["events_deleted"] == 1

    with __import__("sqlite3").connect(tmp_path / "feedback.sqlite3") as connection:
        rows = connection.execute(
            "SELECT owner_id FROM feedback_events"
        ).fetchall()
    assert rows == [("bob",)]
