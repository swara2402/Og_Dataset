"""Heuristic AI-writing indicators.

Important: this module does NOT run an AI detector and does not output a
"percent AI" score. It identifies stylistic patterns that are common in
machine-generated prose (low burstiness, cliche phrasing, uniform structure).
Those patterns have many innocent explanations and are not proof of AI use.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any, Dict, List

from backend.app.quality_analysis.analyzer import (
    _coefficient_of_variation,
    _sentences,
    _words,
    _clamp,
)

AI_CLICHES = {
    "delve", "delves", "delving", "tapestry", "realm", "landscape", "navigate",
    "navigating", "foster", "fostering", "underscore", "underscores", "pivotal",
    "intricate", "multifaceted", "testament", "profound", "crucial", "seamless",
    "seamlessly", "robust", "leverage", "leveraging", "harness", "harnessing",
    "illuminate", "illuminates", "paramount", "meticulous", "holistic",
    "transformative", "synergy", "paradigm", "endeavor", "embark", "unveil",
    "crucially", "notably", "importantly", "in today's", "in the realm of",
    "plays a crucial role", "plays a vital role", "serves as a", "a testament to",
    "it is important to note", "it is worth noting", "not only", "but also",
    "in conclusion", "overall,", "ultimately,", "at its core", "the fact that",
}

HEDGES = {
    "arguably", "potentially", "relatively", "somewhat", "largely", "generally",
    "typically", "often", "various", "numerous", "significant", "substantial",
}

NOMINALISATION_RE = re.compile(r"\b[A-Za-z]{4,}(?:tion|tions|ment|ments|ness|ity|ities)\b", re.I)


def analyze_ai_indicators(text: str) -> Dict[str, Any]:
    text = (text or "").strip()
    words = [word.lower() for word in _words(text)]
    sentences = _sentences(text)
    word_count = max(1, len(words))
    sentence_count = max(1, len(sentences))
    sentence_lengths = [len(_words(sentence)) for sentence in sentences] or [word_count]

    indicators: List[Dict[str, Any]] = []

    def add(key: str, label: str, score: float, description: str, evidence: List[str]) -> None:
        score = _clamp(score)
        indicators.append(
            {
                "id": key,
                "label": label,
                "score": score,
                "severity": "high" if score >= 70 else "moderate" if score >= 40 else "low",
                "description": description,
                "evidence": evidence[:8],
            }
        )

    cv = _coefficient_of_variation([float(length) for length in sentence_lengths])
    low_burstiness = _clamp((0.55 - min(cv, 0.55)) / 0.55 * 100) if sentence_count > 2 else 0
    add(
        "low_burstiness",
        "Uniform sentence rhythm",
        low_burstiness,
        "Machine-generated prose often has unusually even sentence lengths.",
        [f"Sentence-length variation (CV) = {cv:.2f}"],
    )

    content = [word for word in words if len(word) > 2]
    root_ttr = len(set(content)) / math.sqrt(max(1, len(content)))
    low_diversity = _clamp((4.2 - min(root_ttr, 4.2)) / 4.2 * 100) if content else 0
    add(
        "low_lexical_diversity",
        "Limited vocabulary range",
        low_diversity,
        "A small working vocabulary can indicate templated or generated text.",
        [f"Root type-token ratio = {root_ttr:.2f}"],
    )

    cliche_hits = [phrase for phrase in AI_CLICHES if phrase in text.lower()]
    cliche_density = len(cliche_hits) / max(1, sentence_count)
    cliche_score = _clamp(cliche_density * 220)
    add(
        "ai_cliches",
        "Predictable AI-style phrasing",
        cliche_score,
        "The text uses stock phrases frequently over-represented in AI writing.",
        cliche_hits,
    )

    hedge_hits = [word for word in words if word in HEDGES]
    hedge_score = _clamp(len(hedge_hits) / max(1, word_count) * 1600)
    add(
        "hedging_density",
        "High hedging density",
        hedge_score,
        "Excessive generic hedging can make prose sound evasive and formulaic.",
        sorted(set(hedge_hits))[:8],
    )

    transitions = {
        "however", "moreover", "furthermore", "additionally", "consequently",
        "therefore", "notably", "overall", "in conclusion", "ultimately",
    }
    transition_hits = [word for word in words if word in transitions]
    transition_density = len(transition_hits) / max(1, sentence_count)
    transition_score = _clamp(transition_density * 260)
    add(
        "formulaic_transitions",
        "Formulaic connective density",
        transition_score,
        "A high rate of generic connectives can produce a mechanical rhythm.",
        sorted(set(transition_hits)),
    )

    openers = []
    for sentence in sentences:
        match = re.match(r"[A-Za-z][A-Za-z'-]*", sentence)
        if match:
            openers.append(match.group(0).lower())
    opener_counts = Counter(openers)
    repeated_openers = [opener for opener, count in opener_counts.most_common() if count > 1 and opener not in {"the", "this", "these", "a", "an", "it"}]
    opener_score = _clamp((len(repeated_openers) / max(1, sentence_count)) * 300)
    add(
        "repeated_openers",
        "Repeated sentence openers",
        opener_score,
        "Starting many sentences the same way reduces perceived naturalness.",
        repeated_openers[:8],
    )

    nominalisations = NOMINALISATION_RE.findall(text)
    nominal_score = _clamp(len(nominalisations) / max(1, word_count) * 1200)
    add(
        "nominalisation_density",
        "Heavy nominalisation",
        nominal_score,
        "Dense abstract nouns can make prose feel institutional and generated.",
        sorted({word.lower() for word in nominalisations})[:8],
    )

    paragraph_lengths = [len(_words(part)) for part in re.split(r"\n\s*\n", text) if part.strip()]
    if len(paragraph_lengths) >= 3:
        paragraph_cv = _coefficient_of_variation([float(length) for length in paragraph_lengths])
        uniform_paragraphs = _clamp((0.5 - min(paragraph_cv, 0.5)) / 0.5 * 100)
    else:
        uniform_paragraphs = 0
    add(
        "uniform_paragraphs",
        "Uniform paragraph structure",
        uniform_paragraphs,
        "Paragraphs of nearly identical length often indicate templated generation.",
        [f"{len(paragraph_lengths)} paragraph(s) measured"],
    )

    weighted = sum(
        indicator["score"] * weight
        for indicator, weight in zip(
            indicators,
            [0.24, 0.16, 0.18, 0.10, 0.12, 0.08, 0.06, 0.06],
        )
    )
    overall = _clamp(weighted)

    if overall >= 65:
        band = "strong stylistic indicators"
        summary = (
            "Several stylistic patterns commonly found in AI-generated text are present. "
            "This is not a detector result and does not establish that AI was used."
        )
    elif overall >= 40:
        band = "moderate stylistic indicators"
        summary = (
            "Some formulaic phrasing and rhythm patterns were detected. "
            "Review them as editing suggestions, not as a verdict."
        )
    else:
        band = "few stylistic indicators"
        summary = (
            "Few heuristic AI-writing patterns were detected. "
            "Absence of these patterns is not proof that text is human-written."
        )

    return {
        "detector_available": False,
        "detector_note": (
            "No AI detector is integrated. This report is a local stylistic heuristic, "
            "not a verified AI-detection score. Different detectors produce different results "
            "and none are reliable enough to treat as fact."
        ),
        "indicator_score": overall,
        "band": band,
        "summary": summary,
        "indicators": sorted(indicators, key=lambda item: item["score"], reverse=True),
        "metrics": {
            "word_count": word_count,
            "sentence_count": sentence_count,
            "sentence_length_cv": round(cv, 3),
            "root_type_token_ratio": round(root_ttr, 3),
            "cliche_hits": len(cliche_hits),
        },
    }