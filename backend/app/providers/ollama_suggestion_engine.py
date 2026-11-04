"""Explicitly invoked local Ollama proposal engine with preservation validation."""
from __future__ import annotations

import hashlib
import json
from difflib import SequenceMatcher
from typing import Any, Sequence

from backend.app.core.proposals import ProposalSource, SemanticRisk, SuggestionProposal
from backend.app.protected_content.masker import ProtectedContentMasker
from backend.app.validation.validator import validate_rewrite


class OllamaSuggestionEngine:
    name = "local_llm"

    def __init__(self, adapter: Any) -> None:
        self.adapter = adapter
        self.masker = ProtectedContentMasker()

    def analyze(self, paragraph_id: str, text: str, **context: Any) -> Sequence[SuggestionProposal]:
        masked, replacements, spans = self.masker.mask(text)
        system = (
            "You are a conservative academic writing assistant. Return JSON only with keys "
            "suggested_text, category, explanation. Propose at most one minimal edit. "
            "Do not change facts, claims, certainty, negation, numbers, citations, equations, "
            "technical terms or protected placeholders. If no safe improvement exists, return "
            "the original text unchanged. Never add information."
        )
        user = json.dumps({"paragraph": masked, "document_context": context.get("document_context", ""),
                           "paragraph_type": context.get("paragraph_type", "body")}, ensure_ascii=False)
        raw, _elapsed = self.adapter.suggest_json(system, user)
        try:
            payload = json.loads(raw)
            candidate_masked = payload["suggested_text"]
            category = payload["category"]
            explanation = payload["explanation"]
            if not all(isinstance(value, str) for value in (candidate_masked, category, explanation)):
                return []
        except (ValueError, TypeError, KeyError):
            return []
        if candidate_masked == masked:
            return []
        restored, _error = self.masker.restore_and_validate(text, candidate_masked, replacements)
        if restored is None:
            return []
        protected = [{"type": span.type, "value": span.value} for span in spans]
        validation = validate_rewrite(text, restored, masked, candidate_masked, protected)
        if not validation["valid"]:
            return []
        changed = [op for op in SequenceMatcher(a=text, b=restored, autojunk=False).get_opcodes()
                   if op[0] != "equal"]
        start = min(op[1] for op in changed)
        end = max(op[2] for op in changed)
        proposal_id = "llm_" + hashlib.sha256(
            f"{paragraph_id}\\0{text}\\0{restored}".encode("utf-8")
        ).hexdigest()[:16]
        return [SuggestionProposal(
            proposal_id=proposal_id, paragraph_id=paragraph_id,
            source_engine=ProposalSource.LOCAL_LLM, original_text=text,
            suggested_text=restored, category=category, explanation=explanation,
            confidence=None, semantic_risk=SemanticRisk.UNKNOWN, requires_review=True,
            start_offset=start, end_offset=end,
            model_version=getattr(self.adapter, "model", None),
            protected_span_ids=[f"{span.type}:{span.start}:{span.end}" for span in spans],
            validation={"checks": validation["checks"], "metrics": validation["metrics"],
                        "warnings": validation["warnings"]},
        )]
