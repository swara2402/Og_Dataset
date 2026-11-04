"""Turn optional spaCy morphology observations into reviewable rule proposals."""
from __future__ import annotations

import hashlib
from difflib import SequenceMatcher
from typing import Any, Sequence

from backend.app.core.proposals import ProposalSource, SemanticRisk, SuggestionProposal
from backend.app.protected_content.masker import ProtectedContentMasker
from backend.app.validation.validator import validate_rewrite


class SpacyMorphologyProposalEngine:
    """Convert explicit morphology findings into proposals; never apply edits."""

    name = "spacy_morphology"

    def __init__(self, provider: Any) -> None:
        self.provider = provider
        self.masker = ProtectedContentMasker()

    def analyze(self, paragraph_id: str, text: str, **context: Any) -> Sequence[SuggestionProposal]:
        masked, replacements, spans = self.masker.mask(text)
        proposals: list[SuggestionProposal] = []
        for edit in self.provider.suggest_agreement_edits(masked):
            start, end = edit["start"], edit["end"]
            candidate_masked = masked[:start] + edit["replacement"] + masked[end:]
            restored, error = self.masker.restore_and_validate(text, candidate_masked, replacements)
            if restored is None or restored == text:
                continue
            protected = [{"type": span.type, "value": span.value} for span in spans]
            validation = validate_rewrite(text, restored, masked, candidate_masked, protected)
            if not validation["valid"]:
                continue
            changes = [op for op in SequenceMatcher(a=text, b=restored, autojunk=False).get_opcodes()
                       if op[0] != "equal"]
            if not changes:
                continue
            offset_start = min(op[1] for op in changes)
            offset_end = max(op[2] for op in changes)
            proposal_id = "spacy_" + hashlib.sha256(
                f"{paragraph_id}\\0{text}\\0{restored}".encode("utf-8")
            ).hexdigest()[:16]
            proposals.append(SuggestionProposal(
                proposal_id=proposal_id,
                paragraph_id=paragraph_id,
                source_engine=ProposalSource.NLP_ENGINE,
                rule_id="MORPHOLOGY-AGREEMENT-001",
                original_text=text,
                suggested_text=restored,
                category="grammar",
                explanation=(
                    f"spaCy parsed '{edit['subject']}' as the grammatical subject and "
                    f"identified a possible finite-verb agreement mismatch. "
                    "Review the suggestion in context."
                ),
                semantic_risk=SemanticRisk.MEDIUM,
                requires_review=True,
                start_offset=offset_start,
                end_offset=offset_end,
                model_version=self.provider.model_name,
                protected_span_ids=[f"{span.type}:{span.start}:{span.end}" for span in spans],
                validation={
                    "checks": validation["checks"],
                    "metrics": validation["metrics"],
                    "warnings": validation["warnings"],
                    "morphology_observation": edit,
                },
            ))
        return proposals
