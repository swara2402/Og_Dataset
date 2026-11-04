"""Context-qualified terminology consistency proposals from reviewed JSON data."""
from __future__ import annotations

import hashlib
import re
from difflib import SequenceMatcher
from typing import Any, Sequence

from backend.app.core.proposals import ProposalSource, SemanticRisk, SuggestionProposal
from backend.app.protected_content.masker import ProtectedContentMasker
from backend.app.validation.validator import validate_rewrite


class TerminologyProposalEngine:
    """Suggest only explicitly curated equivalent variants; never guess synonyms."""

    name = "terminology_rules"

    def __init__(self, entries: Sequence[dict[str, Any]]) -> None:
        self.entries = [entry for entry in entries if entry.get("review_status") == "reviewed"]
        self.masker = ProtectedContentMasker()

    def analyze(self, paragraph_id: str, text: str, **context: Any) -> Sequence[SuggestionProposal]:
        domain = str(context.get("academic_domain") or "general").casefold()
        masked, replacements, spans = self.masker.mask(text)
        token_set = {token.casefold() for token in re.findall(r"[A-Za-z][A-Za-z'-]*", masked)}
        proposals: list[SuggestionProposal] = []
        for entry in self.entries:
            disciplines = {str(value).casefold() for value in entry.get("disciplines", [])}
            if "general" not in disciplines and domain not in disciplines:
                continue
            required_context = {str(value).casefold() for value in entry.get("context_terms", [])}
            if not required_context or not required_context.issubset(token_set):
                continue
            preferred = entry["preferred_form"]
            for variant in entry.get("variants", []):
                if not isinstance(variant, str) or not variant.strip():
                    continue
                for match in re.finditer(r"(?<!\w)" + re.escape(variant) + r"(?!\w)", masked, re.I):
                    if match.group(0).casefold() == preferred.casefold():
                        continue
                    replacement = preferred
                    if match.group(0).isupper():
                        replacement = preferred.upper()
                    elif match.group(0)[:1].isupper():
                        replacement = preferred[:1].upper() + preferred[1:]
                    candidate_masked = masked[:match.start()] + replacement + masked[match.end():]
                    restored, error = self.masker.restore_and_validate(text, candidate_masked, replacements)
                    if restored is None or restored == text:
                        continue
                    protected = [{"type": span.type, "value": span.value} for span in spans]
                    validation = validate_rewrite(text, restored, masked, candidate_masked, protected)
                    if not validation["valid"]:
                        continue
                    opcodes = [op for op in SequenceMatcher(a=text, b=restored, autojunk=False).get_opcodes()
                               if op[0] != "equal"]
                    if not opcodes:
                        continue
                    start = min(op[1] for op in opcodes)
                    end = max(op[2] for op in opcodes)
                    seed = f"{paragraph_id}\0{text}\0{restored}\0{entry['term_id']}"
                    proposal_id = "term_" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]
                    proposals.append(SuggestionProposal(
                        proposal_id=proposal_id,
                        paragraph_id=paragraph_id,
                        source_engine=ProposalSource.RULE_ENGINE,
                        rule_id="TERMINOLOGY-002",
                        original_text=text,
                        suggested_text=restored,
                        category="terminology",
                        explanation=(
                            f"'{match.group(0)}' is a reviewed variant of '{preferred}' "
                            f"for {', '.join(entry['disciplines'])}. Confirm the intended term."
                        ),
                        semantic_risk=SemanticRisk.MEDIUM,
                        requires_review=True,
                        start_offset=start,
                        end_offset=end,
                        dataset_version=entry.get("term_id"),
                        protected_span_ids=[f"{span.type}:{span.start}:{span.end}" for span in spans],
                        validation={
                            "checks": validation["checks"],
                            "metrics": validation["metrics"],
                            "warnings": validation["warnings"],
                            "terminology_entry_id": entry["term_id"],
                            "usage_note": entry.get("usage_note", ""),
                        },
                    ))
        return proposals
