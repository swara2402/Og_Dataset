"""Adapter that turns existing conservative rule edits into reviewable proposals."""
from __future__ import annotations

import hashlib
from difflib import SequenceMatcher
from typing import Any, Sequence

from backend.app.core.proposals import ProposalSource, SemanticRisk, SuggestionProposal
from backend.app.humanisation.adaptive_editing import assess_editing_needs
from backend.app.protected_content.masker import ProtectedContentMasker
from backend.app.validation.validator import validate_rewrite


class RuleBasedProposalEngine:
    name = "rule_engine"

    def __init__(self, engine: Any) -> None:
        self.engine = engine
        self.masker = ProtectedContentMasker()

    def analyze(self, paragraph_id: str, text: str, **context: Any) -> Sequence[SuggestionProposal]:
        masked, replacements, spans = self.masker.mask(text)
        profile = assess_editing_needs(masked)
        result = self.engine._apply_rules_to_text(
            masked, profile,
            paragraph_type=str(context.get("paragraph_type", "body")),
            category=str(context.get("category", "")),
            context=str(context.get("document_context", text)),
            academic_domain=context.get("academic_domain"),
            document_vocabulary=context.get("document_vocabulary", ()),
        )
        candidate_masked = result["revised_text"]
        if candidate_masked == masked:
            return []
        restored, restore_error = self.masker.restore_and_validate(text, candidate_masked, replacements)
        if restored is None:
            return []
        protected = [{"type": span.type, "value": span.value} for span in spans]
        validation = validate_rewrite(text, restored, masked, candidate_masked, protected)
        if not validation["valid"]:
            return []

        opcodes = [op for op in SequenceMatcher(a=text, b=restored, autojunk=False).get_opcodes()
                   if op[0] != "equal"]
        start = min((op[1] for op in opcodes), default=None)
        end = max((op[2] for op in opcodes), default=None)
        seed = f"{paragraph_id}\\0{text}\\0{restored}"
        proposal_id = "rule_" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]
        return [SuggestionProposal(
            proposal_id=proposal_id,
            paragraph_id=paragraph_id,
            source_engine=ProposalSource.RULE_ENGINE,
            rule_id=(result.get("applied_rule_ids") or [None])[0],
            original_text=text,
            suggested_text=restored,
            category=(profile.get("issues") or ["editing"])[0],
            explanation=result.get("edit_rationale", "A conservative rule-based correction was identified."),
            confidence=None,
            semantic_risk=SemanticRisk.UNKNOWN,
            requires_review=True,
            start_offset=start,
            end_offset=end,
            dataset_version=getattr(self.engine, "dataset_version", None),
            protected_span_ids=[f"{span.type}:{span.start}:{span.end}" for span in spans],
            validation={"checks": validation["checks"], "metrics": validation["metrics"],
                        "warnings": validation["warnings"], "change_summary": result.get("change_summary", [])},
        )]
