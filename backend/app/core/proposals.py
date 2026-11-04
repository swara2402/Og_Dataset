"""Shared, engine-neutral contract for reviewable editing proposals.

Analysis engines may detect and suggest changes, but only the review workflow
may apply them to a document. This model deliberately contains provenance,
source offsets, risk, and validation metadata so suggestions remain auditable.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ProposalSource(str, Enum):
    RULE_ENGINE = "rule_engine"
    NLP_ENGINE = "nlp_engine"
    LOCAL_LLM = "local_llm"
    HUMAN = "human"


class ProposalStatus(str, Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"


class SemanticRisk(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    UNKNOWN = "unknown"


class SuggestionProposal(BaseModel):
    """A proposed edit; constructing one never mutates source document text."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    proposal_id: str = Field(min_length=1)
    paragraph_id: str = Field(min_length=1)
    source_engine: ProposalSource
    rule_id: Optional[str] = None
    original_text: str
    suggested_text: str
    category: str = Field(min_length=1)
    explanation: str = ""
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    semantic_risk: SemanticRisk = SemanticRisk.UNKNOWN
    requires_review: bool = True
    status: ProposalStatus = ProposalStatus.PENDING

    # Character offsets are relative to the paragraph's original text.
    start_offset: Optional[int] = Field(default=None, ge=0)
    end_offset: Optional[int] = Field(default=None, ge=0)

    document_version: Optional[str] = None
    dataset_version: Optional[str] = None
    model_version: Optional[str] = None
    protected_span_ids: list[str] = Field(default_factory=list)
    validation: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_offsets(self) -> "SuggestionProposal":
        if (self.start_offset is None) != (self.end_offset is None):
            raise ValueError("start_offset and end_offset must be supplied together")
        if self.start_offset is not None:
            if self.end_offset < self.start_offset:
                raise ValueError("end_offset must not precede start_offset")
            if self.end_offset > len(self.original_text):
                raise ValueError("proposal offsets exceed original_text length")
        if self.status != ProposalStatus.PENDING and self.requires_review:
            # Review is still required for a recorded decision; status records
            # the user's decision and must not be inferred from this flag.
            return self
        return self
