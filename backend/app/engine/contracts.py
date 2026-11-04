"""Engine-neutral contracts used by deterministic and optional model providers."""
from __future__ import annotations

from typing import Any, Protocol, Sequence

from backend.app.core.proposals import SuggestionProposal


class AnalysisEngine(Protocol):
    """An analysis engine proposes edits; it never mutates a document."""

    name: str

    def analyze(self, paragraph_id: str, text: str, **context: Any) -> Sequence[SuggestionProposal]:
        ...


class ContextProvider(Protocol):
    """Optional context provider (for example, a local NLP model)."""

    name: str

    def analyze_context(self, text: str) -> dict[str, Any]:
        ...
