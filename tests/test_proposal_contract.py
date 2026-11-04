import pytest
from pydantic import ValidationError

from backend.app.core.proposals import (
    ProposalSource,
    ProposalStatus,
    SemanticRisk,
    SuggestionProposal,
)


def _proposal(**overrides):
    values = {
        "proposal_id": "edit_0001",
        "paragraph_id": "p_001",
        "source_engine": ProposalSource.RULE_ENGINE,
        "rule_id": "GRAMMAR-001",
        "original_text": "The the model was evaluated.",
        "suggested_text": "The model was evaluated.",
        "category": "grammar",
        "explanation": "Removed an accidental repeated function word.",
        "confidence": None,
        "semantic_risk": SemanticRisk.LOW,
        "requires_review": True,
        "status": ProposalStatus.PENDING,
        "start_offset": 0,
        "end_offset": 7,
        "document_version": "v1",
        "dataset_version": "1.1.0",
        "model_version": None,
        "protected_span_ids": [],
        "validation": {"valid": True},
    }
    values.update(overrides)
    return SuggestionProposal(**values)


def test_proposal_contract_carries_provenance_and_review_state():
    proposal = _proposal()
    assert proposal.source_engine == ProposalSource.RULE_ENGINE
    assert proposal.status == ProposalStatus.PENDING
    assert proposal.dataset_version == "1.1.0"
    assert proposal.confidence is None
    assert proposal.model_dump()["paragraph_id"] == "p_001"


def test_proposal_contract_rejects_unpaired_offsets():
    with pytest.raises(ValidationError, match="must be supplied together"):
        _proposal(end_offset=None)


def test_proposal_contract_rejects_offsets_outside_original_text():
    with pytest.raises(ValidationError, match="exceed original_text"):
        _proposal(start_offset=0, end_offset=1000)


def test_proposal_contract_rejects_invalid_confidence_and_extra_fields():
    with pytest.raises(ValidationError):
        _proposal(confidence=1.2)
    with pytest.raises(ValidationError):
        _proposal(detector_score=99)


def test_proposal_decisions_are_explicit_states():
    accepted = _proposal(status=ProposalStatus.ACCEPTED)
    rejected = _proposal(status=ProposalStatus.REJECTED)
    assert accepted.status != rejected.status
