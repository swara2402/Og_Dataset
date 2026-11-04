from backend.app.core.proposals import ProposalSource, SemanticRisk, SuggestionProposal
from backend.app.engine.orchestrator import SuggestionOrchestrator


def proposal(identifier, revision, source=ProposalSource.RULE_ENGINE):
    return SuggestionProposal(
        proposal_id=identifier, paragraph_id="p1", source_engine=source,
        original_text="The the model works.", suggested_text=revision,
        category="grammar", semantic_risk=SemanticRisk.LOW,
    )


def test_aggregator_deduplicates_same_revision_and_keeps_provenance():
    result = SuggestionOrchestrator.aggregate([
        proposal("a", "The model works."),
        proposal("b", "The model works.", ProposalSource.NLP_ENGINE),
    ])
    assert len(result) == 1
    assert result[0].validation["contributing_engines"] == ["nlp_engine", "rule_engine"]


def test_aggregator_flags_conflicting_engine_suggestions():
    result = SuggestionOrchestrator.aggregate([
        proposal("a", "The model works."),
        proposal("b", "The model functions.", ProposalSource.NLP_ENGINE),
    ])
    assert len(result) == 2
    assert all(item.requires_review for item in result)
    assert all(item.semantic_risk == SemanticRisk.HIGH for item in result)
    assert all(item.validation["conflict_detected"] for item in result)
