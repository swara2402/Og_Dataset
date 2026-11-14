import json

from fastapi.testclient import TestClient

from backend.app.core.config import settings
from backend.app.main import app
import backend.app.retrieval.api as retrieval_api


def _configure_auth():
    previous = (settings.api_tokens, settings.api_auth_required)
    settings.api_tokens = json.dumps({"tester": "tester-secret-012345678901234567890123456789"})
    settings.api_auth_required = True
    return previous


def _restore_auth(previous):
    settings.api_tokens, settings.api_auth_required = previous


def test_academic_retrieval_endpoint_requires_bearer_auth(tmp_path, monkeypatch):
    previous = _configure_auth()
    dataset = tmp_path / "revision_pairs.jsonl"
    dataset.write_text("", encoding="utf-8")
    monkeypatch.setattr(retrieval_api, "DEFAULT_DATASET", dataset)
    monkeypatch.setattr(retrieval_api, "_cached_signature", None)
    monkeypatch.setattr(retrieval_api, "_cached_corpus", None)
    try:
        with TestClient(app) as client:
            assert client.get("/api/v1/retrieval/examples", params={"query": "academic"}).status_code == 401
            response = client.get(
                "/api/v1/retrieval/examples",
                params={"query": "academic"},
                headers={"Authorization": "Bearer tester-secret-012345678901234567890123456789"},
            )
            assert response.status_code == 200, response.text
            payload = response.json()
            assert payload["count"] == 0
            assert payload["examples"] == []
            assert payload["retrieval"] == "local-bm25"
            assert payload["applies_edits"] is False
    finally:
        _restore_auth(previous)


def test_academic_retrieval_endpoint_rejects_short_queries(tmp_path, monkeypatch):
    previous = _configure_auth()
    dataset = tmp_path / "revision_pairs.jsonl"
    dataset.write_text("", encoding="utf-8")
    monkeypatch.setattr(retrieval_api, "DEFAULT_DATASET", dataset)
    monkeypatch.setattr(retrieval_api, "_cached_signature", None)
    monkeypatch.setattr(retrieval_api, "_cached_corpus", None)
    try:
        with TestClient(app) as client:
            response = client.get(
                "/api/v1/retrieval/examples",
                params={"query": "x"},
                headers={"Authorization": "Bearer tester-secret-012345678901234567890123456789"},
            )
            assert response.status_code == 422
    finally:
        _restore_auth(previous)


def test_academic_retrieval_endpoint_fails_closed_for_invalid_corpus(tmp_path, monkeypatch):
    previous = _configure_auth()
    dataset = tmp_path / "revision_pairs.jsonl"
    dataset.write_text("{invalid json}\n", encoding="utf-8")
    monkeypatch.setattr(retrieval_api, "DEFAULT_DATASET", dataset)
    monkeypatch.setattr(retrieval_api, "_cached_signature", None)
    monkeypatch.setattr(retrieval_api, "_cached_corpus", None)
    try:
        with TestClient(app) as client:
            response = client.get(
                "/api/v1/retrieval/examples",
                params={"query": "academic"},
                headers={"Authorization": "Bearer tester-secret-012345678901234567890123456789"},
            )
            assert response.status_code == 503
    finally:
        _restore_auth(previous)
