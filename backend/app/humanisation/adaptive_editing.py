"""Load the canonical OG Dataset and detect conservative edit opportunities."""
from __future__ import annotations

import json
import os
import re
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List

from jsonschema import Draft202012Validator, SchemaError

from backend.app.text.sentences import split_sentences


_DATASET_ROOT = Path(
    os.environ.get(
        "OG_DATASET_DIR",
        str(Path(__file__).resolve().parents[3] / "knowledge_base"),
    )
).expanduser()
_REPEAT_WORD_RE = re.compile(r"\b([A-Za-z]{2,})[ \t]+\1\b", re.I)
_PLURAL_SUBJECTS = (
    "results", "findings", "methods", "models", "systems", "participants",
    "experiments", "observations", "analyses", "variables", "features",
    "approaches", "studies", "datasets", "measurements", "samples",
    "responses", "outcomes", "factors", "authors", "researchers", "algorithms",
    "parameters", "values", "records", "documents", "papers",
)
_SINGULAR_VERBS = (
    "is", "was", "has", "does", "shows", "indicates", "demonstrates",
    "suggests", "provides", "reports", "reveals", "remains", "increases",
    "decreases", "affects", "leads", "contains", "includes", "requires",
    "uses", "produces", "improves",
)
_SUBJECT_VERB_RE = re.compile(
    rf"\b({'|'.join(_PLURAL_SUBJECTS)})\s+({'|'.join(_SINGULAR_VERBS)})\b",
    re.I,
)
_SAFE_REPEAT_WORDS = {"a", "an", "and", "in", "of", "the", "to"}
_COMMON_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "been", "by", "for", "from",
    "has", "have", "in", "is", "it", "of", "on", "or", "that", "the", "this",
    "to", "was", "were", "with",
}


def _read_json(relative_path: str) -> Any:
    path = _DATASET_ROOT / relative_path
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise RuntimeError(f"OG Dataset file is unavailable: {path}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"OG Dataset file contains invalid JSON: {path}") from exc


def load_quality_rules() -> List[Dict[str, Any]]:
    """Load rule packs listed by the single canonical master manifest."""
    data = _read_json("rules/master_rules.json")
    if not isinstance(data, dict):
        raise RuntimeError("OG Dataset master rules manifest must be a JSON object.")
    rules = data.get("rules")
    if isinstance(rules, list):
        # Backward compatibility for externally supplied older datasets.
        packs = [rules]
    else:
        filenames = data.get("rule_sets")
        if not isinstance(filenames, list) or not filenames:
            raise RuntimeError("OG Dataset master rules manifest has no rule_sets.")
        packs = []
        for filename in filenames:
            if not isinstance(filename, str) or Path(filename).name != filename or not filename.endswith(".json"):
                raise RuntimeError("OG Dataset rule pack entries must be plain JSON filenames.")
            pack = _read_json(f"rules/{filename}")
            pack_rules = pack.get("rules") if isinstance(pack, dict) else None
            if not isinstance(pack_rules, list) or not pack_rules:
                raise RuntimeError(f"OG Dataset rule pack {filename} has an invalid rules array.")
            packs.append(pack_rules)
    flattened = [rule for pack in packs for rule in pack]
    if not flattened or not all(
        isinstance(rule, dict) and isinstance(rule.get("id"), str) for rule in flattened
    ):
        raise RuntimeError("OG Dataset rule packs have an invalid structure.")
    identifiers = [rule["id"] for rule in flattened]
    if len(identifiers) != len(set(identifiers)):
        raise RuntimeError("OG Dataset rule IDs must be unique across all rule packs.")
    return flattened


def load_editing_policy() -> Dict[str, Any]:
    policy = _read_json("rules/adaptive_editing_policy.json")
    if not isinstance(policy, dict):
        raise RuntimeError("OG Dataset editing policy must be a JSON object.")
    scopes = policy.get("edit_scope_priority")
    if not isinstance(scopes, list) or not scopes:
        raise RuntimeError("OG Dataset editing policy is missing edit_scope_priority.")
    return policy


def load_examples() -> List[Dict[str, Any]]:
    path = _DATASET_ROOT / "datasets" / "examples.jsonl"
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise RuntimeError(f"OG Dataset examples are unavailable: {path}") from exc
    examples: List[Dict[str, Any]] = []
    seen_ids = set()
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            example = json.loads(line)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"Invalid OG Dataset example on line {line_number}."
            ) from exc
        if not isinstance(example, dict) or not isinstance(example.get("example_id"), str):
            raise RuntimeError(f"Invalid OG Dataset example structure on line {line_number}.")
        if example["example_id"] in seen_ids:
            raise RuntimeError(f"Duplicate OG Dataset example ID: {example['example_id']}")
        if example.get("edit_scope") not in {"none", "word", "phrase", "sentence", "paragraph"}:
            raise RuntimeError(
                f"OG Dataset example {example['example_id']} has an invalid edit_scope."
            )
        if example.get("intervention_level") not in {
            "none", "minimal", "moderate", "substantial"
        }:
            raise RuntimeError(
                f"OG Dataset example {example['example_id']} has an invalid intervention_level."
            )
        seen_ids.add(example["example_id"])
        examples.append(example)
    return examples


def load_terminology() -> List[Dict[str, Any]]:
    """Load only explicitly reviewed terminology records for proposal use."""
    path = _DATASET_ROOT / "datasets" / "terminology.jsonl"
    schema = _read_json("schemas/terminology.schema.json")
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as exc:
        raise RuntimeError("OG Dataset terminology schema is invalid.") from exc
    validator = Draft202012Validator(schema)
    entries: List[Dict[str, Any]] = []
    seen_ids: set[str] = set()
    seen_terms: set[tuple[str, str]] = set()
    allowed_licenses = {"CC-BY-4.0", "CC0-1.0", "CC-BY-SA-4.0", "CC-BY-3.0", "CC-BY-SA-3.0"}
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError as exc:
                raise RuntimeError(f"Invalid terminology JSONL at line {line_number}.") from exc
            errors = sorted(validator.iter_errors(item), key=lambda error: list(error.absolute_path))
            if errors:
                raise RuntimeError(
                    f"Terminology entry on line {line_number} does not match schema: {errors[0].message}"
                )
            if item["term_id"] in seen_ids:
                raise RuntimeError(f"Duplicate terminology ID: {item['term_id']}")
            seen_ids.add(item["term_id"])
            source = item["source"]
            if source["kind"] == "synthetic":
                if source["license"] != "SYNTHETIC":
                    raise RuntimeError(f"Terminology entry {item['term_id']} has invalid synthetic provenance.")
            elif source["license"] not in allowed_licenses:
                raise RuntimeError(f"Terminology entry {item['term_id']} has an unapproved licence.")
            normalized_term = re.sub(r"[^a-z0-9]+", " ", item["term"].casefold()).strip()
            for discipline in item["disciplines"]:
                key = (discipline.casefold(), normalized_term)
                if key in seen_terms:
                    raise RuntimeError(f"Duplicate terminology term for discipline: {item['term']}")
                seen_terms.add(key)
            if item["review_status"] == "reviewed":
                entries.append(item)
    return entries


def load_dataset() -> Dict[str, Any]:
    """Read and validate the canonical knowledge base for each document job."""
    from backend.app.engine.dataset_validation import validate_dataset

    validate_dataset(_DATASET_ROOT)
    profile_path = _DATASET_ROOT / "docs" / "reference-writing-profile.md"
    try:
        profile = profile_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise RuntimeError(f"OG Dataset reference profile is unavailable: {profile_path}") from exc
    rules = load_quality_rules()
    policy = load_editing_policy()
    examples = load_examples()
    terminology = load_terminology()
    rules_data = _read_json("rules/master_rules.json")
    schema = _read_json("schemas/example.schema.json")
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as exc:
        raise RuntimeError("OG Dataset example schema is invalid.") from exc
    validator = Draft202012Validator(schema)
    for index, example in enumerate(examples, start=1):
        errors = sorted(validator.iter_errors(example), key=lambda error: list(error.absolute_path))
        if errors:
            raise RuntimeError(
                f"OG Dataset example {example.get('example_id', index)} does not match "
                f"the schema: {errors[0].message}"
            )
    return {
        "version": str(rules_data.get("version", "unknown")),
        "rules": rules,
        "policy": policy,
        "examples": examples,
        "terminology": terminology,
        "reference_profile": profile,
    }


def assess_editing_needs(text: str) -> Dict[str, Any]:
    """Report observable issues without treating style preferences as errors."""
    value = text or ""
    sentences = split_sentences(value)
    words = re.findall(r"\b[\w'-]+\b", value)
    issues: List[str] = []
    if _REPEAT_WORD_RE.search(value):
        issues.append("accidental_repeated_word")
    if _SUBJECT_VERB_RE.search(value):
        issues.append("subject_verb_agreement")
    punctuation_probe = re.sub(r"\b(?:e\.g|i\.e)\.", "ABBREVIATION", value, flags=re.I)
    punctuation_probe = re.sub(r"\b(?:[A-Z]\.){2,}", "INITIALISM", punctuation_probe)
    missing_abbreviation_space = re.search(
        r"\b(?:e\.g|i\.e)\.(?=[A-Za-z])", value, re.I
    )
    if (
        re.search(r"[ \t]+[,.!?;:]", value)
        or missing_abbreviation_space
        or re.search(r"(?<!\d)[.!?;:,](?=[A-Za-z])", punctuation_probe)
    ):
        issues.append("punctuation_spacing")
    if re.search(r"[ \t]{2,}", value):
        issues.append("repeated_whitespace")

    long_sentences = sum(
        len(re.findall(r"\b[\w'-]+\b", sentence)) > 35 for sentence in sentences
    )
    if long_sentences:
        issues.append("long_sentence")

    content_words = [
        word.casefold()
        for word in re.findall(r"\b[A-Za-z][A-Za-z'-]{2,}\b", value)
        if word.casefold() not in _COMMON_WORDS
    ]
    if any(count >= 4 for count in Counter(content_words).values()):
        issues.append("repeated_vocabulary")

    safe_duplicate = bool(
        re.search(
            r"\b(a|an|and|in|of|the|to)[ \t]+\1\b",
            value,
            re.IGNORECASE,
        )
    )
    review_required = bool(long_sentences) or "repeated_vocabulary" in issues or (
        "accidental_repeated_word" in issues and not safe_duplicate
    )
    return {
        "level": "minimal",
        "issues": issues,
        "sentence_count": len(sentences),
        "word_count": len(words),
        "average_sentence_words": round(len(words) / max(1, len(sentences)), 1),
        "long_sentence_count": long_sentences,
        "requires_human_review": review_required,
        "edit_scope_priority": ["word", "phrase", "sentence", "paragraph"],
    }
