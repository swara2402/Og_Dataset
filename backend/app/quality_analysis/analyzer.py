"""Explainable writing-quality analysis.

These are heuristic, local metrics. They are useful for measuring whether a
rewrite improved flow and readability, but they are not an AI detector and do
not produce a "percent human" score.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any, Dict, List, Tuple

WORD_RE = re.compile(r"[A-Za-z][A-Za-z'-]*")
SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
PARAGRAPH_SPLIT_RE = re.compile(r"\n\s*\n")

TRANSITIONS = {
    "however", "therefore", "moreover", "furthermore", "consequently", "nevertheless",
    "meanwhile", "subsequently", "additionally", "similarly", "conversely", "finally",
    "first", "second", "third", "next", "then", "overall", "in contrast", "as a result",
    "for example", "for instance", "in addition", "in particular", "on the other hand",
    "in conclusion", "by contrast", "at the same time", "in summary",
}

FILLERS = {
    "very", "really", "quite", "just", "actually", "basically", "literally", "simply",
    "extremely", "definitely", "absolutely", "totally", "completely", "a lot", "kind of",
    "sort of", "in order to", "due to the fact that", "it is important to note",
    "it should be noted", "needless to say",
}

CONTRACTIONS = {"can't", "won't", "don't", "doesn't", "isn't", "aren't", "it's", "we're",
                "they're", "i'm", "you're", "couldn't", "shouldn't", "wouldn't", "let's"}

FIRST_PERSON = {"i", "me", "my", "mine", "we", "us", "our", "ours"}

PASSIVE_RE = re.compile(r"\b(?:is|are|was|were|be|been|being)\s+\w+(?:ed|en)\b", re.I)

VOWELS = set("aeiouy")


def _words(text: str) -> List[str]:
    return WORD_RE.findall(text)


def _sentences(text: str) -> List[str]:
    return [part.strip() for part in SENTENCE_SPLIT_RE.split(text.strip()) if part.strip()]


def _syllables(word: str) -> int:
    word = word.lower()
    count = 0
    previous_vowel = False
    for char in word:
        is_vowel = char in VOWELS
        if is_vowel and not previous_vowel:
            count += 1
        previous_vowel = is_vowel
    if word.endswith("e") and count > 1:
        count -= 1
    return max(1, count)


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return round(max(low, min(high, value)), 1)


def _coefficient_of_variation(values: List[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    if mean == 0:
        return 0.0
    variance = sum((value - mean) ** 2 for value in values) / len(values)
    return math.sqrt(variance) / mean


def _repeated_ngrams(words: List[str], n: int = 4) -> Tuple[List[str], int]:
    if len(words) < n:
        return [], 0
    grams = [" ".join(words[index : index + n]).lower() for index in range(len(words) - n + 1)]
    counts = Counter(grams)
    repeated = [(gram, count) for gram, count in counts.items() if count > 1]
    repeated.sort(key=lambda item: item[1], reverse=True)
    total_repeated = sum(count - 1 for _, count in repeated)
    return [gram for gram, _ in repeated[:8]], total_repeated


def analyze_text(text: str) -> Dict[str, Any]:
    text = (text or "").strip()
    words = _words(text)
    sentences = _sentences(text)
    paragraphs = [part for part in PARAGRAPH_SPLIT_RE.split(text) if part.strip()]
    word_count = len(words)
    sentence_count = max(1, len(sentences))
    word_lengths = [len(word) for word in words]
    sentence_lengths = [len(_words(sentence)) for sentence in sentences] or [word_count]

    syllables = sum(_syllables(word) for word in words) if words else 1
    words_per_sentence = word_count / sentence_count
    flesch = 206.835 - 1.015 * words_per_sentence - 84.6 * (syllables / max(1, word_count))
    flesch = max(0.0, min(120.0, flesch))

    cv = _coefficient_of_variation([float(length) for length in sentence_lengths])
    sentence_variety = _clamp(cv * 125)

    lower_words = [word.lower() for word in words]
    content = [word for word in lower_words if len(word) > 2]
    root_ttr = len(set(content)) / math.sqrt(max(1, len(content)))
    vocabulary_diversity = _clamp(root_ttr * 42)

    repeated_phrases, repeated_count = _repeated_ngrams(lower_words, 4)
    repetition_score = _clamp(100 - (repeated_count / max(1, len(words))) * 900)

    text_lower = text.lower()
    transition_count = sum(text_lower.count(phrase) for phrase in TRANSITIONS)
    transition_density = transition_count / max(1, sentence_count)
    transition_usage = _clamp(35 + transition_density * 55)

    contraction_count = sum(text_lower.count(phrase) for phrase in CONTRACTIONS)
    first_person_count = sum(1 for word in lower_words if word in FIRST_PERSON)
    filler_count = sum(text_lower.count(phrase) for phrase in FILLERS)
    formality = _clamp(100 - (contraction_count * 5) - (first_person_count * 2) - (filler_count * 4))

    passive_count = len(PASSIVE_RE.findall(text))
    long_sentences = sum(1 for length in sentence_lengths if length > 35)
    clarity = _clamp(
        100
        - (filler_count / max(1, word_count)) * 700
        - (long_sentences / sentence_count) * 45
        - (passive_count / max(1, sentence_count)) * 18
    )

    coherence = _clamp(transition_usage * 0.55 + min(100, len(paragraphs) * 12) * 0.15 + 25)

    ideal_deviation = abs(words_per_sentence - 19)
    verbosity = _clamp(100 - ideal_deviation * 4 - (filler_count / max(1, word_count)) * 800)

    terminology_consistency = _terminology_consistency(text)
    readability_score = _clamp(flesch)

    overall = _clamp(
        readability_score * 0.16
        + sentence_variety * 0.16
        + vocabulary_diversity * 0.14
        + repetition_score * 0.14
        + transition_usage * 0.12
        + clarity * 0.12
        + coherence * 0.08
        + formality * 0.08
    )

    metrics = {
        "overall_score": overall,
        "readability_score": readability_score,
        "flesch_reading_ease": round(flesch, 1),
        "sentence_variety": sentence_variety,
        "vocabulary_diversity": vocabulary_diversity,
        "repetition_score": repetition_score,
        "transition_usage": transition_usage,
        "formality": formality,
        "clarity": clarity,
        "coherence": coherence,
        "verbosity": verbosity,
        "terminology_consistency": terminology_consistency,
        "word_count": word_count,
        "sentence_count": len(sentences),
        "paragraph_count": len(paragraphs),
        "average_sentence_length": round(words_per_sentence, 1),
        "average_word_length": round(sum(word_lengths) / max(1, len(word_lengths)), 2),
        "repeated_phrases": repeated_phrases,
        "passive_constructions": passive_count,
        "transition_count": transition_count,
        "filler_count": filler_count,
    }
    metrics["recommendations"] = _recommendations(metrics, words_per_sentence)
    return metrics


def _terminology_consistency(text: str) -> float:
    # Look for acronyms and flag inconsistent expansion/casing.
    acronyms = re.findall(r"\b[A-Z]{2,6}\b", text)
    if not acronyms:
        return 100.0
    counts = Counter(acronyms)
    most_common = counts.most_common(1)[0][0]
    variants = {acronym for acronym in acronyms if acronym.lower() == most_common.lower()}
    penalty = max(0, len(variants) - 1) * 8
    return _clamp(100 - penalty)


def _recommendations(metrics: Dict[str, Any], words_per_sentence: float) -> List[Dict[str, str]]:
    recommendations: List[Dict[str, str]] = []

    def add(kind: str, category: str, message: str, suggestion: str) -> None:
        recommendations.append(
            {
                "type": kind,
                "category": category,
                "message": message,
                "suggestion": suggestion,
            }
        )

    if metrics["sentence_variety"] < 45:
        add("warning", "sentence_variety", "Sentence lengths are uniform.",
            "Mix short, direct sentences with longer explanatory ones to create a natural rhythm.")
    if metrics["repetition_score"] < 60:
        add("warning", "repetition", "Frequently repeated phrases were detected.",
            f"Vary or remove repeated phrases such as: {', '.join(metrics['repeated_phrases'][:4]) or 'repeated n-grams'}.")
    if metrics["readability_score"] < 35:
        add("warning", "readability", "The text is dense and hard to read.",
            "Split long sentences and reduce nested clauses while keeping technical precision.")
    if metrics["transition_usage"] < 40:
        add("info", "transitions", "Few explicit transitions connect ideas.",
            "Add transitions only where the logical relationship is clear (e.g. however, consequently).")
    if metrics["formality"] < 65:
        add("warning", "formality", "The tone is informal for academic/professional writing.",
            "Remove contractions, slang and unnecessary first-person constructions unless required.")
    if metrics["clarity"] < 55:
        add("warning", "clarity", "Filler words or overlong constructions reduce clarity.",
            "Remove hedges and filler and prefer direct verbs.")
    if metrics["verbosity"] < 50:
        add("info", "verbosity", "Sentences are unusually long or padded.",
            "Aim for roughly 15-22 words per sentence and remove redundant qualifiers.")
    if words_per_sentence > 30:
        add("warning", "sentence_length", "Average sentence length is very high.",
            "Break sentences over 35 words into smaller units.")
    if not recommendations:
        add("info", "quality", "No major writing-quality problems detected.",
            "Review the text manually; heuristic metrics cannot judge factual correctness.")
    return recommendations


def compare_texts(original: str, revised: str) -> Dict[str, Any]:
    before = analyze_text(original)
    after = analyze_text(revised)
    deltas = {
        key: round(after.get(key, 0) - before.get(key, 0), 1)
        for key in (
            "overall_score", "readability_score", "sentence_variety",
            "vocabulary_diversity", "repetition_score", "clarity", "coherence",
        )
        if isinstance(after.get(key), (int, float))
    }
    return {"original": before, "revised": after, "deltas": deltas}
