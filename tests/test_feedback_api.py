from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.api import feedback


def _client(tmp_path, monkeypatch):
    monkeypatch.setattr(feedback, "DB_PATH", tmp_path / "feedback.sqlite3")
    app = FastAPI()
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
