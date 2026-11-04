"""Deterministic, dataset-driven academic editing."""
from __future__ import annotations

import asyncio
import logging
import re
import time
from collections import OrderedDict
from typing import Any, Dict, List, Optional, Sequence, Tuple

from backend.app.core.config import Settings
from backend.app.core.jobs import Job, ParagraphState
from backend.app.humanisation.adaptive_editing import (
    assess_editing_needs,
    load_dataset,
)
from backend.app.protected_content.masker import ProtectedContentMasker
from backend.app.validation.validator import validate_rewrite

logger = logging.getLogger(__name__)

PLACEHOLDER_RE = re.compile(r"__TURNITOUT_PROTECTED_\d{4}__")
SAFE_DUPLICATE_WORDS = {"a", "an", "and", "in", "of", "the", "to"}
NON_EDITABLE_TYPES = {
    "caption", "code", "empty", "equation", "front_matter", "heading",
    "reference", "references", "table",
}


class ContextualSynonymSelector:
    """Select only explicit, context-qualified alternatives; otherwise abstain."""

    @staticmethod
    def select(
        source: str,
        candidates: Sequence[Dict[str, Any]],
        context: str,
        *,
        source_part_of_speech: Optional[str] = None,
        source_meaning: Optional[str] = None,
        academic_domain: Optional[str] = None,
        sentence_structure: Optional[str] = None,
        protected_terms: Sequence[str] = (),
        document_vocabulary: Sequence[str] = (),
    ) -> Optional[str]:
        if not source or source.casefold() in {term.casefold() for term in protected_terms}:
            return None

        context_words = set(re.findall(r"[A-Za-z][A-Za-z'-]*", context.casefold()))
        vocabulary = {word.casefold() for word in document_vocabulary}
        ranked: List[Tuple[int, str]] = []
        for item in candidates:
            if not isinstance(item, dict):
                continue
            alternative = item.get("word")
            if not isinstance(alternative, str) or not alternative.strip():
                continue
            alternative = alternative.strip()
            if alternative.casefold() == source.casefold():
                continue
            if alternative.casefold() in {term.casefold() for term in protected_terms}:
                continue
            part_of_speech = item.get("part_of_speech")
            if source_part_of_speech and part_of_speech != source_part_of_speech:
                continue
            if source_meaning and item.get("meaning") != source_meaning:
                continue
            domains = item.get("domains", [])
            if domains and (
                not isinstance(domains, list) or academic_domain not in domains
            ):
                continue
            structures = item.get("sentence_structures", [])
            if structures and (
                not isinstance(structures, list) or sentence_structure not in structures
            ):
                continue
            required_context = item.get("context_terms", [])
            excluded_context = item.get("exclude_context_terms", [])
            if not isinstance(required_context, list) or not isinstance(excluded_context, list):
                continue
            required = {str(word).casefold() for word in required_context}
            excluded = {str(word).casefold() for word in excluded_context}
            if not required.issubset(context_words) or excluded.intersection(context_words):
                continue
            score = len(required)
            if alternative.casefold() in vocabulary:
                score += 1
            ranked.append((score, alternative))

        if not ranked:
            return None
        highest = max(score for score, _ in ranked)
        best = {word for score, word in ranked if score == highest}
        return next(iter(best)) if highest > 0 and len(best) == 1 else None


class ResultCache:
    """Small bounded LRU cache for deterministic processing results."""

    def __init__(self, max_size: int = 1000):
        self.max_size = max_size
        self._cache: "OrderedDict[str, str]" = OrderedDict()

    def get(self, key: str) -> Optional[str]:
        if key not in self._cache:
            return None
        self._cache.move_to_end(key)
        return self._cache[key]

    def put(self, key: str, value: str) -> None:
        self._cache[key] = value
        self._cache.move_to_end(key)
        while len(self._cache) > self.max_size:
            self._cache.popitem(last=False)

    def clear(self) -> None:
        self._cache.clear()

    def __len__(self) -> int:
        return len(self._cache)


def _restore_placeholders(
    masked_text: str, replacements: Dict[str, str]
) -> Tuple[Optional[str], Optional[str]]:
    found = PLACEHOLDER_RE.findall(masked_text)
    expected = list(replacements)
    if found != expected:
        return None, "Protected content placeholders were missing, altered, or duplicated."
    restored = masked_text
    for token, value in replacements.items():
        restored = restored.replace(token, value)
    return restored, None


class RuleBasedEditingEngine:
    def __init__(
        self,
        settings: Settings,
        cache: Optional[ResultCache] = None,
        max_passes: Optional[int] = None,
    ):
        self.settings = settings
        self.cache = cache or ResultCache(settings.cache_max_size)
        self.max_passes = max_passes or settings.turnitout_max_passes
        self._cache_hits = 0
        self._load_dataset()

    def _load_dataset(self) -> None:
        dataset = load_dataset()
        self.master_rules = dataset["rules"]
        self.editing_policy = dataset["policy"]
        self.examples = dataset["examples"]
        self.reference_profile = dataset["reference_profile"]
        self.dataset_version = dataset["version"]
        self.rule_by_id = {rule["id"]: rule for rule in self.master_rules}
        required_rule_ids = {"GRAMMAR-001"}
        if not required_rule_ids.issubset(self.rule_by_id):
            raise RuntimeError(
                "OG Dataset is missing required deterministic rules: "
                + ", ".join(sorted(required_rule_ids - self.rule_by_id.keys()))
            )
        if self.editing_policy.get("edit_scope_priority") != [
            "word", "phrase", "sentence", "paragraph"
        ]:
            raise RuntimeError("OG Dataset edit scope priority is unsupported.")

    def dataset_status(self) -> Dict[str, Any]:
        return {
            "version": self.dataset_version,
            "rules_loaded": len(self.master_rules),
            "examples_loaded": len(self.examples),
            "approved_examples": sum(
                example.get("review_status") == "approved" for example in self.examples
            ),
            "reference_profile_loaded": bool(self.reference_profile.strip()),
        }

    def _apply_rules_to_text(
        self,
        text: str,
        editing_profile: Dict[str, Any],
        paragraph_type: str = "",
        category: str = "",
        context: str = "",
        academic_domain: Optional[str] = None,
        document_vocabulary: Sequence[str] = (),
    ) -> Dict[str, Any]:
        original = text
        if paragraph_type in NON_EDITABLE_TYPES or category in NON_EDITABLE_TYPES:
            return {
                "original_text": original,
                "revised_text": original,
                "applied_rule_ids": [],
                "edit_rationale": "Protected document content was left unchanged.",
                "change_summary": [],
                "edit_scope": "none",
                "editing_level_applied": "none",
                "issues_found": ["protected_content"],
                "requires_human_review": False,
            }

        revised = text
        rules: List[str] = []
        changes: List[str] = []
        issues = list(editing_profile.get("issues", []))

        # Word-level corrections are attempted before any broader edit.
        if "accidental_repeated_word" in issues:
            repeated_word = re.compile(r"\b([A-Za-z]+)[ \t]+\1\b", re.IGNORECASE)

            def remove_safe_duplicate(match: re.Match[str]) -> str:
                word = match.group(1)
                return word if word.casefold() in SAFE_DUPLICATE_WORDS else match.group(0)

            candidate = repeated_word.sub(remove_safe_duplicate, revised)
            if candidate != revised:
                revised = candidate
                rules.append("GRAMMAR-001")
                changes.append("Removed an accidental repeated function word.")

        # Punctuation and spacing corrections remain local and do not rewrite sentences.
        if "punctuation_spacing" in issues:
            candidate = re.sub(r"[ \t]+([,.;:!?])", r"\1", revised)
            candidate = re.sub(r"([,;:!?])(?=[A-Za-z])", r"\1 ", candidate)
            candidate = re.sub(r"(?<!\d)\.(?=[A-Za-z])", ". ", candidate)
            if candidate != revised:
                revised = candidate
                if "GRAMMAR-001" not in rules:
                    rules.append("GRAMMAR-001")
                changes.append("Corrected whitespace before punctuation.")

        if "repeated_whitespace" in issues:
            candidate = re.sub(r"[ \t]{2,}", " ", revised)
            if candidate != revised:
                revised = candidate
                if "GRAMMAR-001" not in rules:
                    rules.append("GRAMMAR-001")
                changes.append("Collapsed repeated horizontal whitespace.")

        # Dataset additions may define explicitly contextualized word choices.
        # Draft examples and unqualified rule guidance are never treated as synonym lists.
        word_choices = []
        for rule in self.master_rules:
            configured_choices = rule.get("word_choices", [])
            if not isinstance(configured_choices, list):
                raise RuntimeError(f"Rule {rule['id']} has invalid word_choices.")
            word_choices.extend(
                choice for choice in configured_choices if isinstance(choice, dict)
            )
        profile_terms = re.findall(
            r"\b(?:[A-Z]{2,}[A-Z0-9-]*|[A-Z][a-z]+[A-Z][A-Za-z0-9]*)\b",
            self.reference_profile,
        )
        protected_terms = set(profile_terms)
        protected_terms.update(
            re.findall(r"\b[A-Z]{2,}[A-Z0-9-]*\b", revised)
        )
        if word_choices:
            for choice in word_choices:
                source = choice.get("source")
                alternatives = choice.get("alternatives", [])
                if not isinstance(source, str) or not isinstance(alternatives, list):
                    continue
                match = re.search(rf"\b{re.escape(source)}\b", revised, re.IGNORECASE)
                if not match:
                    continue
                alternative = ContextualSynonymSelector.select(
                    match.group(0),
                    alternatives,
                    context or revised,
                    source_part_of_speech=choice.get("part_of_speech"),
                    source_meaning=choice.get("meaning"),
                    academic_domain=academic_domain,
                    protected_terms=(
                        list(protected_terms)
                        + choice.get("protected_terms", [])
                    ),
                    document_vocabulary=document_vocabulary,
                )
                if alternative:
                    if match.group(0)[:1].isupper():
                        alternative = alternative[:1].upper() + alternative[1:]
                    revised = revised[:match.start()] + alternative + revised[match.end():]
                    rules.append(str(choice.get("rule_id", "WORDCHOICE-001")))
                    changes.append(
                        f"Replaced '{match.group(0)}' with '{alternative}' using its stated context."
                    )

        needs_review = bool(editing_profile.get("requires_human_review")) and revised == original
        if "accidental_repeated_word" in issues and not rules:
            needs_review = True
        if revised == original:
            rationale = (
                "No edit was needed; the text was preserved."
                if not needs_review
                else "A possible issue needs author review; no change was guessed."
            )
            scope = "none"
            level = "none"
            changes = []
            rules = []
        else:
            rationale = " ".join(changes)
            scope = (
                "word"
                if all("repeated function word" in item for item in changes)
                else "phrase"
            )
            level = "minimal"

        return {
            "original_text": original,
            "revised_text": revised,
            "applied_rule_ids": list(dict.fromkeys(rules)),
            "edit_rationale": rationale,
            "change_summary": changes,
            "edit_scope": scope,
            "editing_level_applied": level,
            "issues_found": issues,
            "requires_human_review": needs_review or revised != original,
        }

    async def process_job(self, job: Job) -> None:
        self._load_dataset()
        job.started_at = time.time()
        job.finished_at = None
        job.status = "processing"
        job.error = None
        job.cancel_event.clear()
        self._cache_hits = 0
        total = len(job.paragraphs)
        job.progress = {
            "phase": "processing",
            "pass": 1,
            "total_passes": 1,
            "total": total,
            "completed": 0,
            "processed_count": 0,
            "failed": 0,
            "skipped": 0,
            "pending": total,
            "work_completed": 0,
            "work_total": total,
            "percent": 0.0 if total else 100.0,
            "elapsed_seconds": 0.0,
            "estimated_remaining": None,
        }

        try:
            for state in job.paragraphs:
                if job.cancel_event.is_set():
                    state.status = "skipped"
                    continue
                if not state.eligible:
                    state.status = "protected"
                    state.review_status = "unchanged"
                    state.edit_scope = "none"
                    state.requires_human_review = False
                else:
                    await self._process_state(job, state, 1)
                self._refresh_progress(job)
                await asyncio.sleep(0)

            if job.cancel_event.is_set():
                job.status = "cancelled"
            else:
                job.status = "completed"
        except asyncio.CancelledError:
            job.cancel_event.set()
            job.status = "cancelled"
            raise
        except Exception as exc:
            job.status = "failed"
            job.error = str(exc)
            logger.exception("Document processing failed for job %s", job.job_id)
            raise
        finally:
            job.finished_at = time.time()
            self._finalise_statistics(job)
            self._refresh_progress(job, finished=True)

    async def _process_state(self, job: Job, state: ParagraphState, pass_number: int) -> None:
        started = time.time()
        state.status = "processing"
        source_text = state.current_text
        masked, replacements, spans = ProtectedContentMasker().mask(source_text)
        state.current_masked_text = masked
        state.replacements = replacements
        state.protected_items = [
            {
                "start": span.start,
                "end": span.end,
                "value": span.value,
                "type": span.type,
                "placeholder": span.placeholder,
            }
            for span in spans
        ]
        profile = assess_editing_needs(masked)
        result = self._apply_rules_to_text(
            masked, profile, state.paragraph_type, state.category,
            context=self._paragraph_context(job, state),
            academic_domain=state.section or state.category,
            document_vocabulary=re.findall(
                r"\b[A-Za-z][A-Za-z'-]*\b",
                " ".join(paragraph.current_text for paragraph in job.paragraphs),
            ),
        )
        state.applied_rule_ids = result["applied_rule_ids"]
        state.edit_rationale = result["edit_rationale"]
        state.editing_level_applied = result["editing_level_applied"]
        state.issues_found = result["issues_found"]
        state.edit_scope = result["edit_scope"]
        state.change_summary = result["change_summary"]
        state.requires_human_review = result["requires_human_review"]
        if self.settings.rule_verbose_logging:
            logger.info(
                "Paragraph %s: issues=%s rules=%s changed=%s",
                state.id,
                state.issues_found,
                state.applied_rule_ids,
                result["revised_text"] != result["original_text"],
            )

        candidate = result["revised_text"]
        restored, restore_error = _restore_placeholders(candidate, replacements)
        if restored is None:
            state.status = "needs_review"
            state.review_status = "pending"
            state.warnings = [restore_error or "Protected content could not be restored."]
            return

        validation = validate_rewrite(
            source_text,
            restored,
            masked,
            candidate,
            state.protected_items,
        )
        state.validation = validation
        if not validation["valid"]:
            state.status = "needs_review"
            state.review_status = "pending"
            state.warnings = validation["issues"] + validation["warnings"]
            state.requires_human_review = True
            return

        state.warnings = validation["warnings"]
        if restored == state.current_text:
            state.status = "completed"
            state.review_status = "unchanged"
            state.requires_human_review = bool(profile.get("requires_human_review"))
            state.edit_scope = "none"
            if state.requires_human_review:
                state.warnings.append(
                    "A possible repetition or structural issue was left unchanged for author review."
                )
            return

        state.add_version(
            text=restored,
            masked_text=candidate,
            pass_number=pass_number,
            source="rule-based",
            validation=validation,
            elapsed_seconds=time.time() - started,
            applied_rule_ids=state.applied_rule_ids,
            edit_rationale=state.edit_rationale,
            editing_level_applied=state.editing_level_applied,
            issues_found=state.issues_found,
            edit_scope=state.edit_scope,
            change_summary=state.change_summary,
            requires_human_review=True,
        )
        state.elapsed_seconds = time.time() - started
        state.status = "completed"
        state.review_status = "pending"

    def _paragraph_context(self, job: Job, state: ParagraphState) -> str:
        before = job.paragraphs[state.index - 1].current_text if state.index > 0 else ""
        after = (
            job.paragraphs[state.index + 1].current_text
            if state.index + 1 < len(job.paragraphs)
            else ""
        )
        return "\n".join(part for part in (before, state.current_text, after) if part)

    def _refresh_progress(self, job: Job, finished: bool = False) -> None:
        total = len(job.paragraphs)
        done = sum(
            state.status in {"completed", "protected", "needs_review", "failed", "skipped"}
            for state in job.paragraphs
        )
        elapsed = max(0.0, time.time() - (job.started_at or time.time()))
        job.progress.update(
            {
                "phase": "finished" if finished else "processing",
                "total": total,
                "completed": done,
                "processed_count": done,
                "failed": sum(state.status == "failed" for state in job.paragraphs),
                "skipped": sum(state.status in {"protected", "skipped"} for state in job.paragraphs),
                "pending": total - done,
                "work_completed": done,
                "work_total": total,
                "percent": 100.0 if finished or not total else round(done / total * 100, 1),
                "elapsed_seconds": round(elapsed, 1),
                "estimated_remaining": None,
            }
        )

    def _finalise_statistics(self, job: Job) -> None:
        changed = [state for state in job.paragraphs if state.current_text != state.original_text]
        job.statistics = {
            "total_paragraphs": len(job.paragraphs),
            "eligible_paragraphs": sum(state.eligible for state in job.paragraphs),
            "skipped_paragraphs": sum(not state.eligible for state in job.paragraphs),
            "successfully_processed": sum(
                state.status == "completed" for state in job.paragraphs
            ),
            "failed_paragraphs": sum(state.status == "failed" for state in job.paragraphs),
            "unchanged_paragraphs": sum(
                state.eligible and state.current_text == state.original_text
                for state in job.paragraphs
            ),
            "changed_paragraphs": len(changed),
            "pending_review": sum(state.review_status == "pending" for state in job.paragraphs),
            "applied_rule_count": len(
                {rule for state in changed for rule in state.applied_rule_ids}
            ),
            "cache_hits": self._cache_hits,
            "passes": 1,
            "dataset": self.dataset_status(),
            "elapsed_seconds": round(job.elapsed_seconds, 3),
            "warnings": [
                f"{state.id}: {warning}"
                for state in job.paragraphs
                for warning in state.warnings
            ][:50],
        }

    async def refine_paragraph(
        self,
        job: Job,
        state: ParagraphState,
        instruction: str = "",
        style: Optional[str] = None,
        pass_number: Optional[int] = None,
    ) -> ParagraphState:
        self._load_dataset()
        if state.paragraph_type != "body" or not state.eligible:
            raise RuntimeError("Only eligible body paragraphs can be refined.")
        if instruction:
            logger.info("User instruction is recorded; edits remain constrained by OG Dataset rules.")
        await self._process_state(job, state, pass_number or max(2, len(state.versions)))
        self._finalise_statistics(job)
        return state


class HumanisationEngine(RuleBasedEditingEngine):
    """Compatibility name used by the API; no LLM provider is required."""
