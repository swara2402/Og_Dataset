"""Offline-first hybrid analysis pipeline; all outputs remain proposals."""
from __future__ import annotations

from typing import Any, Sequence

from backend.app.core.proposals import SuggestionProposal
from backend.app.engine.orchestrator import SuggestionOrchestrator
from backend.app.engine.rule_adapter import RuleBasedProposalEngine


class HybridAnalysisPipeline:
    def __init__(self, rule_engine: Any, *, context_providers: Sequence[Any] = (),
                 proposal_engines: Sequence[Any] = ()) -> None:
        self.rule_engine = RuleBasedProposalEngine(rule_engine)
        self.context_providers = list(context_providers)
        self.proposal_engines = list(proposal_engines)

    def analyze_paragraph(self, paragraph_id: str, text: str, **context: Any) -> dict[str, Any]:
        proposals: list[SuggestionProposal] = list(
            self.rule_engine.analyze(paragraph_id, text, **context)
        )
        for engine in self.proposal_engines:
            proposals.extend(engine.analyze(paragraph_id, text, **context))
        aggregated = SuggestionOrchestrator.aggregate(proposals)
        observations = {
            provider.name: provider.analyze_context(text)
            for provider in self.context_providers
        }
        return {
            "paragraph_id": paragraph_id,
            "proposals": [proposal.model_dump(mode="json") for proposal in aggregated],
            "context": observations,
            "applied": False,
            "review_required": bool(aggregated),
        }
