from fastapi.testclient import TestClient

from backend.app.main import app


def test_hybrid_analysis_api_returns_proposals_without_applying_edits():
    with TestClient(app) as client:
        status = client.get("/api/v1/engines/status")
        assert status.status_code == 200
        assert status.json()["offline_basic_available"] is True

        response = client.post(
            "/api/v1/analysis/paragraph",
            json={
                "paragraph_id": "p1",
                "text": "The the model was evaluated.",
                "paragraph_type": "body",
            },
        )
        assert response.status_code == 200, response.text
        result = response.json()
        assert result["applied"] is False
        assert result["review_required"] is True
        assert result["proposals"][0]["suggested_text"] == "The model was evaluated."
        assert result["proposals"][0]["status"] == "pending"


def test_hybrid_analysis_api_rejects_disabled_spacy_context():
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/analysis/paragraph",
            json={
                "paragraph_id": "p1",
                "text": "The model was evaluated.",
                "include_nlp": True,
            },
        )
        assert response.status_code == 409
