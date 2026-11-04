"""Post-rewrite validation.

The humanisation engine is not allowed to silently accept a rewrite that loses
protected content, changes numbers or citations, or drifts away from the
original meaning. This module produces structured, explainable checks.
"""
from __future__ import annotations

import re
from collections import Counter
from difflib import SequenceMatcher
from typing import Any, Dict, Iterable, List, Optional, Tuple

from backend.app.text.sentences import split_sentences as _split_sentences

PLACEHOLDER_RE = re.compile(r"__TURNITOUT_PROTECTED_\d{4}__")
NUMBER_RE = re.compile(r"(?<![A-Za-z_])[-+]?\d+(?:[.,]\d+)*(?:\s?%)?")
CITATION_RE = re.compile(
    r"\[\s*\d+(?:\s*[,;–-]\s*\d+)*\s*\]|"
    r"\([A-Z][A-Za-z .'-]+,\s*\d{4}[a-z]?\)|"
    r"\b(?:doi:\s*10\.\d{4,9}/[^\s,;]+|https?://[^\s)\]}>,;]+)"
)
MEANING_MARKER_RE = re.compile(
    r"\b(?:not|no|never|may|might|could|would|should|must|possibly|probably|"
    r"likely|unlikely|suggest(?:s|ed)?|approximately|about|all|any|some|most|"
    r"many|few|several|each|every|none|only|exclusively|because|therefore|thus|"
    r"consequently|although|however|whereas|despite|unless|associated|correlated|"
    r"caused|causes|cause|causally|before|after|during|until|since)\b",
    re.I,
)
STOPWORDS = {
    "the", "and", "that", "this", "with", "from", "have", "has", "had", "were",
    "was", "are", "is", "been", "being", "for", "not", "but", "they", "their",
    "there", "which", "would", "could", "should", "into", "than", "then",
    "them", "these", "those", "such", "also", "more", "most", "some", "can",
    "may", "might", "will", "shall", "our", "your", "its", "it's", "about",
    "when", "where", "what", "who", "whom", "while", "because", "however",
    "therefore", "thus", "using", "used", "use", "within", "between", "through",
}


def split_sentences(text: str) -> List[str]:
    return _split_sentences(text)


def content_tokens(text: str) -> List[str]:
    return [
        token
        for token in re.findall(r"[A-Za-z][A-Za-z'-]+", text.lower())
        if len(token) > 2 and token not in STOPWORDS
    ]


def _meaning_marker_signature(text: str) -> List[Tuple[str, Tuple[str, ...], Tuple[str, ...]]]:
    """Capture local lexical context around negation and uncertainty markers."""
    words = list(re.finditer(r"\b[\w'-]+\b", text))
    signatures = []
    for marker in MEANING_MARKER_RE.finditer(text):
        index = next(
            (i for i, word in enumerate(words) if word.start() <= marker.start() < word.end()),
            None,
        )
        if index is None:
            continue
        before = tuple(word.group(0) for word in words[max(0, index - 3):index])
        after = tuple(word.group(0) for word in words[index + 1:index + 4])
        signatures.append((marker.group(0).casefold(), before, after))
    return signatures


def _normalise_number(value: str) -> str:
    return value.replace(" ", "").replace(",", "").replace("%", "")


def extract_numbers(text: str) -> List[str]:
    return [_normalise_number(match.group(0)) for match in NUMBER_RE.finditer(text)]


def _counter_diff(original: Iterable[str], revised: Iterable[str]) -> Tuple[List[str], List[str]]:
    original_counter = Counter(original)
    revised_counter = Counter(revised)
    missing = list((original_counter - revised_counter).elements())
    added = list((revised_counter - original_counter).elements())
    return missing, added


def _semantic_similarity(original: str, revised: str) -> float:
    original_tokens = content_tokens(original)
    revised_tokens = content_tokens(revised)
    if not original_tokens and not revised_tokens:
        return 1.0
    if not original_tokens or not revised_tokens:
        return 0.0
    original_set = set(original_tokens)
    revised_set = set(revised_tokens)
    jaccard = len(original_set & revised_set) / max(1, len(original_set | revised_set))
    sequence = SequenceMatcher(None, " ".join(original_tokens), " ".join(revised_tokens)).ratio()
    return round((jaccard * 0.55) + (sequence * 0.45), 4)


def validate_rewrite(
    original_text: str,
    revised_text: str,
    masked_original: str,
    masked_revised: str,
    protected_items: List[Dict[str, Any]],
    min_length_ratio: float = 0.6,
    max_length_ratio: float = 1.5,
    min_semantic_similarity: float = 0.42,
    semantic_similarity_override: Optional[float] = None,
) -> Dict[str, Any]:
    issues: List[str] = []
    warnings: List[str] = []
    critical = False

    original_placeholders = PLACEHOLDER_RE.findall(masked_original)
    revised_placeholders = PLACEHOLDER_RE.findall(masked_revised)
    placeholders_ok = Counter(original_placeholders) == Counter(revised_placeholders)
    if not placeholders_ok:
        missing, added = _counter_diff(original_placeholders, revised_placeholders)
        if missing:
            issues.append(f"Protected placeholders missing: {', '.join(sorted(set(missing)))}")
        if added:
            issues.append(f"Unknown or duplicated placeholders: {', '.join(sorted(set(added)))}")
        critical = True

    protected_ok = True
    for item in protected_items:
        value = item.get("value", "")
        if value and value not in revised_text:
            kind = item.get("type", "protected content")
            if kind in {"number", "citation", "doi", "url", "equation", "technical_id"}:
                issues.append(f"Critical {kind} missing after rewrite: {value}")
                critical = True
            else:
                warnings.append(f"{kind} may have changed: {value}")
            protected_ok = False

    original_numbers = extract_numbers(original_text)
    revised_numbers = extract_numbers(revised_text)
    missing_numbers, added_numbers = _counter_diff(original_numbers, revised_numbers)
    numbers_ok = not missing_numbers
    if missing_numbers:
        issues.append(f"Numbers missing after rewrite: {', '.join(missing_numbers[:8])}")
        critical = True
    if added_numbers:
        issues.append(f"New numbers introduced: {', '.join(added_numbers[:8])}")
        critical = True

    original_citations = CITATION_RE.findall(original_text)
    revised_citations = CITATION_RE.findall(revised_text)
    missing_citations, added_citations = _counter_diff(original_citations, revised_citations)
    citations_ok = not missing_citations
    if missing_citations:
        issues.append(f"Citations/links missing after rewrite: {', '.join(missing_citations[:5])}")
        critical = True
    if added_citations:
        issues.append(f"New citations/links introduced: {', '.join(added_citations[:5])}")
        critical = True

    original_modality = _meaning_marker_signature(original_text)
    revised_modality = _meaning_marker_signature(revised_text)
    modality_ok = original_modality == revised_modality
    if not modality_ok:
        issues.append("A qualifier, relationship marker, negation or uncertainty marker, or its local scope, changed.")
        critical = True

    original_length = len(original_text.strip())
    revised_length = len(revised_text.strip())
    ratio = (revised_length / original_length) if original_length else 1.0
    if not (min_length_ratio <= ratio <= max_length_ratio):
        warnings.append(
            f"Length changed from {original_length} to {revised_length} characters "
            f"(ratio {ratio:.2f})"
        )

    semantic_similarity = (
        semantic_similarity_override
        if semantic_similarity_override is not None
        else _semantic_similarity(original_text, revised_text)
    )
    semantic_ok = semantic_similarity >= min_semantic_similarity
    if not semantic_ok:
        issues.append(
            "Semantic overlap is low "
            f"({semantic_similarity:.2f}); the rewrite may have changed the meaning."
        )
        critical = True

    original_sentence_count = len(split_sentences(original_text))
    revised_sentence_count = len(split_sentences(revised_text))
    if original_sentence_count >= 2 and revised_sentence_count < max(1, original_sentence_count // 2):
        warnings.append(
            f"Sentence count dropped sharply ({original_sentence_count} -> {revised_sentence_count})."
        )

    meaningful_change = revised_text.strip() != original_text.strip()
    if not meaningful_change:
        warnings.append("No meaningful change was produced.")

    new_proper_nouns = _new_proper_nouns(original_text, revised_text)
    if new_proper_nouns:
        warnings.append(f"New capitalised terms introduced: {', '.join(new_proper_nouns[:8])}")

    valid = not critical and (meaningful_change or revised_text == original_text)
    return {
        "valid": valid,
        "critical": critical,
        "meaningful_change": meaningful_change,
        "issues": issues,
        "warnings": warnings,
        "checks": {
            "protected_placeholders": placeholders_ok,
            "protected_values": protected_ok,
            "numbers": numbers_ok,
            "citations": citations_ok,
            "modality": modality_ok,
            "meaning_markers": modality_ok,
            "semantic": semantic_ok,
        },
        "metrics": {
            "semantic_similarity": semantic_similarity,
            "length_ratio": round(ratio, 3),
            "sentence_count_original": original_sentence_count,
            "sentence_count_revised": revised_sentence_count,
        },
    }


def _new_proper_nouns(original: str, revised: str) -> List[str]:
    original_words = set(re.findall(r"\b[A-Z][A-Za-z'-]{2,}\b", original))
    revised_words = set(re.findall(r"\b[A-Z][A-Za-z'-]{2,}\b", revised))
    # Ignore sentence-initial words, which are capitalised for grammar.
    sentence_initial = set()
    for sentence in split_sentences(revised):
        if sentence and sentence[0].isupper():
            first = re.match(r"[A-Z][A-Za-z'-]{2,}", sentence)
            if first:
                sentence_initial.add(first.group(0))
    return sorted((revised_words - original_words) - sentence_initial)


def summarise_validation(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    critical = sum(1 for result in results if result.get("critical"))
    warnings = sum(len(result.get("warnings", [])) for result in results)
    return {
        "checked": len(results),
        "critical_issues": critical,
        "warnings": warnings,
    }