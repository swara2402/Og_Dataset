from types import SimpleNamespace

from backend.app.engine.pipeline import HybridAnalysisPipeline


class FakeRuleEngine:
    dataset_version = "test"

    def _apply_rules_to_text(self, text, profile, **kwargs):
        revised = text.replace("The the ", "The ")
        return {"revised_text": revised, "applied_rule_ids": ["GRAMMAR-001"] if revised != text else [],
                "edit_rationale": "Removed a repeated function word.",
                "change_summary": ["Removed repeated function word."]}


class FakeContextProvider:
    name = "fake_nlp"

    def analyze_context(self, text):
        return {"token_count": len(text.split())}


def test_pipeline_returns_reviewable_proposals_and_never_applies_them():
    pipeline = HybridAnalysisPipeline(FakeRuleEngine(), context_providers=[FakeContextProvider()])
    result = pipeline.analyze_paragraph("p1", "The the model was evaluated.")
    assert result["applied"] is False
    assert result["review_required"] is True
    assert result["proposals"][0]["suggested_text"] == "The model was evaluated."
    assert result["proposals"][0]["source_engine"] == "rule_engine"
    assert result["context"]["fake_nlp"]["token_count"] > 0


def test_pipeline_returns_no_proposal_when_rule_engine_makes_no_change():
    pipeline = HybridAnalysisPipeline(FakeRuleEngine())
    result = pipeline.analyze_paragraph("p1", "The model was evaluated.")
    assert result["proposals"] == []
    assert result["applied"] is False
