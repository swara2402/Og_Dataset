"""Deterministic suggestion aggregation with explicit conflict reporting."""
from __future__ import annotations

from collections import defaultdict
from typing import Iterable

from backend.app.core.proposals import SemanticRisk, SuggestionProposal


class SuggestionOrchestrator:
    """Combine proposals without applying them to source document text."""

    @staticmethod
    def aggregate(proposals: Iterable[SuggestionProposal]) -> list[SuggestionProposal]:
        grouped: dict[tuple[str, str], list[SuggestionProposal]] = defaultdict(list)
        for proposal in proposals:
            grouped[(proposal.paragraph_id, proposal.original_text)].append(proposal)

        output: list[SuggestionProposal] = []
        for group in grouped.values():
            # Identical outputs from multiple engines are one suggestion with
            # all provenance retained in validation metadata.
            by_revision: dict[str, list[SuggestionProposal]] = defaultdict(list)
            for item in group:
                by_revision[item.suggested_text].append(item)
            conflict = len(by_revision) > 1
            for same_revision in by_revision.values():
                primary = same_revision[0].model_copy(deep=True)
                primary.validation = {
                    **primary.validation,
                    "contributing_engines": sorted({p.source_engine.value for p in same_revision}),
                    "contributing_rule_ids": sorted({p.rule_id for p in same_revision if p.rule_id}),
                    "conflict_detected": conflict,
                }
                if conflict:
                    primary.requires_review = True
                    primary.semantic_risk = SemanticRisk.HIGH
                    primary.validation["review_reason"] = "Engines proposed different revisions for the same source text."
                output.append(primary)
        return output
