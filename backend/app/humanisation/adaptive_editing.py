"""Load the canonical OG Dataset and detect conservative edit opportunities."""
from __future__ import annotations

import json
import os
import re
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List

from jsonschema import Draft202012Validator, SchemaError


# The repository currently carries its runtime dataset in tracked, in-repo files.
# The historical nested Og_Dataset gitlink is not a usable source: it points to
# an older snapshot and has no .gitmodules URL. An explicit OG_DATASET_DIR still
# lets a developer supply a separately maintained dataset checkout.
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_DATASET_ROOT = Path(os.environ["OG_DATASET_DIR"]).expanduser() if os.environ.get("OG_DATASET_DIR") else _PROJECT_ROOT
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")
_REPEAT_WORD_RE = re.compile(r"\b([A-Za-z]{2,})[ \t]+\1\b", re.I)
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
    data = _read_json("rules/master_rules.json")
    rules = data.get("rules") if isinstance(data, dict) else None
    if not isinstance(rules, list) or not all(
        isinstance(rule, dict) and isinstance(rule.get("id"), str) for rule in rules
    ):
        raise RuntimeError("OG Dataset master rules have an invalid structure.")
    return rules


def load_editing_policy() -> Dict[str, Any]:
    policy = _read_json("rules/adaptive_editing_policy.json")
    if not isinstance(policy, dict):
        raise RuntimeError("OG Dataset editing policy must be a JSON object.")
    scopes = policy.get("edit_scope_priority")
    if not isinstance(scopes, list) or not scopes:
        raise RuntimeError("OG Dataset editing policy is missing edit_scope_priority.")
    return policy


def load_examples() -> List[Dict[str, Any]]:
    candidates = (
        _DATASET_ROOT / "datasets" / "examples.jsonl",
        _DATASET_ROOT / "backend" / "app" / "datasets" / "examples.jsonl",
    )
    path = next((candidate for candidate in candidates if candidate.is_file()), candidates[0])
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise RuntimeError(
            "OG Dataset examples are unavailable. Checked: "
            + ", ".join(str(candidate) for candidate in candidates)
        ) from exc
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


def load_dataset() -> Dict[str, Any]:
    """Read the repository source at runtime so local dataset updates take effect."""
    # A style profile is optional reference material, never a runtime
    # requirement. The editor must remain available when no verified profile
    # corpus has been supplied.
    profile_path = _DATASET_ROOT / "docs" / "reference-writing-profile.md"
    profile = profile_path.read_text(encoding="utf-8") if profile_path.is_file() else ""
    rules = load_quality_rules()
    policy = load_editing_policy()
    examples = load_examples()
    rules_data = _read_json("rules/master_rules.json")
    schema_candidates = (
        _DATASET_ROOT / "schemas" / "example.schema.json",
        _DATASET_ROOT / "backend" / "app" / "schemas" / "example.schema.json",
    )
    schema_path = next(
        (candidate for candidate in schema_candidates if candidate.is_file()),
        schema_candidates[0],
    )
    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"OG Dataset example schema is unavailable or invalid: {schema_path}") from exc
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
        "reference_profile": profile,
    }


def assess_editing_needs(text: str) -> Dict[str, Any]:
    """Report observable issues without treating style preferences as errors."""
    value = text or ""
    sentences = [part.strip() for part in _SENTENCE_RE.split(value.strip()) if part.strip()]
    words = re.findall(r"\b[\w'-]+\b", value)
    issues: List[str] = []
    if _REPEAT_WORD_RE.search(value):
        issues.append("accidental_repeated_word")
    if re.search(r"[ \t]+[,.!?;:]", value) or re.search(
        r"(?<!\d)[.!?;:,](?=[A-Za-z])", value
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
