from backend.app.providers.spacy_provider import SpacyContextProvider


def test_spacy_provider_is_optional_and_never_auto_downloads(monkeypatch):
    provider = SpacyContextProvider("model-that-does-not-exist")
    result = provider.analyze_context("The model was evaluated.")
    assert result["available"] is False
    assert provider.status()["available"] is False
