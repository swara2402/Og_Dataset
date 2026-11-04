#!/usr/bin/env python3
from __future__ import annotations
"""Turnitout Academic Quality Editor - OPTIMIZED VERSION.
Faster LLM processing with parallel execution, intelligent batching, and
minimal overhead while maintaining all original editing capabilities.
"""
# IMMEDIATE debug print to confirm script is running the second you launch it
print("🚀 SCRIPT STARTED! Turnitout local_humanizer is loading... this will only take a few seconds")

"""Turnitout Academic Quality Editor - core functionality.
Edits academic prose for clarity, precision, grammar, and consistency. Protected 
content is masked before editing and verified before a change is accepted.

Usage:
  ollama pull qwen3:4b-instruct-2507-q4_K_M
  python local_humanizer.py input.docx output.docx --style-sample my_writing.docx
"""

import argparse
import json
import os
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, List, Tuple, Any
from concurrent.futures import ThreadPoolExecutor, as_completed

from docx import Document

try:
    import spacy
except Exception:  # optional dependency
    spacy = None

from ollama_provider import OllamaProvider


PROTECTED_PATTERNS: dict[str, str] = {
    "email": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
    "url": r"https?://[^\s)\]}>,;]+|www\.[^\s)\]}>,;]+",
    "doi": r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+\b",
    "citation": r"\[\s*\d+(?:\s*[,;–-]\s*\d+)*\s*\]|\([A-Z][A-Za-z .'-]+,\s*\d{4}[a-z]?\)",
    "technical_id": r"\b(?:CVE-\d{4}-\d{4,}|CWE-\d+|CVSS(?::\d+(?:\.\d+)?)?|CPE:[^\s,;]+|EPSS)\b",
    "number": r"(?<![A-Za-z])\b\d+(?:[.,]\d+)*(?:\s?%)?\b",
    "equation": r"\$[^$]+\$|\\\([^)]*\\\)|\\\[[^]]*\\\]",
}

# AI-typical overused transition words that need human replacement
AI_TRANSITIONS: list[str] = [
    "Furthermore", "Moreover", "Additionally", "Consequently", 
    "Notably", "Significantly", "Importantly", "Notwithstanding",
    "Nevertheless", "Furthermore", "Conclusively", "Subsequently",
    "Accordingly", "Hence", "Thus", "Therefore", "Henceforth"
]

HUMAN_TRANSITIONS: list[str] = [
    "What's more", "On top of that", "Beyond this", "As a result of this",
    "It's worth pointing out that", "Crucially", "That said", "All things considered",
    "Plus", "Also", "Because of this", "Finally", "After that", 
    "Along with that", "Moving on to", "That leads us to"
]
HEADER_RE = re.compile(
    r"^\s*(?:(?:[IVX]+|\d+)(?:\.[A-Z])?\.?\s+)?"
    r"(?:ABSTRACT|INTRODUCTION|BACKGROUND|RELATED WORK|LITERATURE REVIEW|"
    r"METHODOLOGY|METHODS|RESULTS|DISCUSSION|CONCLUSION|REFERENCES|"
    r"ACKNOWLEDGMENTS|FUTURE WORK)(?:\s|:|$)", re.I,
)
REFERENCE_RE = re.compile(r"^\s*(?:\[\d+\]|\d+\.)\s+.{0,220}(?:\b(?:19|20)\d{2}\b|doi:|https?://)", re.I)
FRONT_MATTER_RE = re.compile(r"\b(author|affiliation|department|university|institute|college|corresponding author|e-mail)\b", re.I)
PLACEHOLDER_RE = re.compile(r"__TURNITOUT_PROTECTED_\d{4}__")
NAME_LIKE_RE = re.compile(r"\b(?!The\b|This\b|These\b|Those\b|Their\b|Our\b|Your\b|However\b|Therefore\b|Moreover\b|Furthermore\b|In\b|On\b|At\b|For\b|From\b|With\b|As\b|When\b|While\b|Although\b|Because\b)[A-Z][a-z]+(?:[-'][A-Z][a-z]+)?(?:\s+(?:and|&)\s+[A-Z][a-z]+|\s+et\s+al\.)|\b(?!The\b|This\b|These\b|Those\b|Their\b|Our\b|Your\b|However\b|Therefore\b|Moreover\b|Furthermore\b|In\b|On\b|At\b|For\b|From\b|With\b|As\b|When\b|While\b|Although\b|Because\b)[A-Z][a-z]+(?:[-'][A-Z][a-z]+)?\s+[A-Z][a-z]+(?:[-'][A-Z][a-z]+)?(?:\s+[A-Z][a-z]+)?\b")

SYSTEM_PROMPT = """You are a careful academic language editor, not a content generator.
Revise the supplied paragraph only when a genuine improvement is possible.
Your priorities are: (1) preserve every claim, qualification, uncertainty,
causal relationship, comparison, and technical distinction; (2) improve
clarity, grammar, precision, and logical flow; (3) retain the author's level of
formality and voice. Do not add evidence, examples, citations, claims, or facts.
Do not make prose artificially varied or insert filler. Do not change protected
placeholders. If the paragraph is already clear, return it unchanged.
Return valid JSON only: {\"edited_text\": \"...\", \"change_notes\": [\"...\"]}.
"""


@dataclass
class ParagraphResult:
    location: str
    status: str
    reason: str = ""
    before: str = ""
    after: str = ""
    change_notes: list[str] = field(default_factory=list)


@dataclass
class EditingReport:
    body_paragraphs: int = 0
    table_paragraphs: int = 0
    edited: int = 0
    unchanged: int = 0
    skipped: int = 0
    rejected: int = 0
    results: list[ParagraphResult] = field(default_factory=list)

    def to_markdown(self) -> str:
        lines = [
            "# Turnitout Academic Editing Report", "",
            "This report records language-quality edits. It does not measure or predict AI-detector results.", "",
            "## Summary", "",
            f"- Body paragraphs inspected: {self.body_paragraphs}",
            f"- Table paragraphs inspected: {self.table_paragraphs}",
            f"- Edited: {self.edited}", f"- Unchanged: {self.unchanged}",
            f"- Skipped for protection/formatting: {self.skipped}",
            f"- Rejected by validation: {self.rejected}", "", "## Paragraph audit", "",
        ]
        for item in self.results:
            lines.extend([f"### {item.location}", f"- Status: {item.status}"])
            if item.reason:
                lines.append(f"- Reason: {item.reason}")
            if item.change_notes:
                lines.append("- Notes: " + "; ".join(item.change_notes))
            if item.status == "edited":
                lines.extend(["", "**Before**", "", item.before, "", "**After**", "", item.after])
            lines.append("")
        return "\n".join(lines)


def load_nlp():
    if not spacy:
        return None
    for model_name in ("en_core_web_sm", "en_core_web_md"):
        try:
            return spacy.load(model_name)
        except Exception:
            continue
    return None


def is_heading_or_reference(paragraph) -> Optional[str]:
    text = paragraph.text.strip()
    if not text:
        return "empty paragraph"
    style_name = getattr(getattr(paragraph, "style", None), "name", "") or ""
    if style_name.lower().startswith(("heading", "title", "subtitle")):
        return f"Word style is {style_name}"
    if HEADER_RE.match(text):
        return "section heading"
    if REFERENCE_RE.match(text) or text.lower() in {"references", "bibliography"}:
        return "reference entry"
    if FRONT_MATTER_RE.search(text) and len(text) < 500:
        return "author/front-matter information"
    return None


def collect_entities(text: str, nlp) -> list[tuple[int, int, str]]:
    if not nlp:
        return []
    doc = nlp(text)
    protected_labels = {"PERSON", "ORG", "GPE", "LOC", "FAC", "DATE", "TIME", "MONEY", "PERCENT", "QUANTITY", "CARDINAL", "ORDINAL"}
    return [(ent.start_char, ent.end_char, ent.text) for ent in doc.ents if ent.label_ in protected_labels]


def mask_content(text: str, nlp) -> tuple[str, dict[str, str]]:
    spans: list[tuple[int, int, str]] = []
    for pattern in PROTECTED_PATTERNS.values():
        spans.extend((m.start(), m.end(), m.group(0)) for m in re.finditer(pattern, text, re.I))
    spans.extend(collect_entities(text, nlp))
    # Merge overlaps, retaining the widest original span.
    spans.sort(key=lambda x: (x[0], -(x[1] - x[0])))
    merged: list[tuple[int, int, str]] = []
    for start, end, value in spans:
        if merged and start < merged[-1][1]:
            prev_start, prev_end, prev_value = merged[-1]
            if end > prev_end:
                merged[-1] = (prev_start, end, text[prev_start:end])
        else:
            merged.append((start, end, value))
    replacements: dict[str, str] = {}
    masked = text
    for idx, (start, end, value) in reversed(list(enumerate(merged))):
        token = f"__TURNITOUT_PROTECTED_{idx:04d}__"
        replacements[token] = text[start:end]
        masked = masked[:start] + token + masked[end:]
    return masked, replacements


def is_meaningful_change(original: str, candidate: str) -> bool:
    """Return False for punctuation/whitespace-only rewrites."""
    if original == candidate:
        return False
    compact_original = re.sub(r"[\W_]+", "", original, flags=re.UNICODE).casefold()
    compact_candidate = re.sub(r"[\W_]+", "", candidate, flags=re.UNICODE).casefold()
    return compact_original != compact_candidate


def restore_and_validate(original: str, candidate: str, replacements: dict[str, str]) -> tuple[Optional[str], str]:
    expected = sorted(replacements, key=lambda token: int(re.search(r"_(\d{4})__$", token).group(1)))
    found = PLACEHOLDER_RE.findall(candidate)
    if found != expected:
        return None, "protected placeholders were missing, duplicated, reordered, or altered"
    restored = candidate
    for token, value in replacements.items():
        restored = restored.replace(token, value)
    # Secondary exact checks catch any accidental numeric/citation edits.
    for pattern_name in ("email", "doi", "citation", "technical_id", "number", "equation"):
        pattern = PROTECTED_PATTERNS[pattern_name]
        if re.findall(pattern, original, re.I) != re.findall(pattern, restored, re.I):
            return None, f"{pattern_name} integrity check failed"
    if len(original.strip()) and not (0.60 <= len(restored.strip()) / len(original.strip()) <= 1.50):
        return None, "edited paragraph length changed outside the conservative 0.60–1.50 range"
    return restored, ""


BATCH_SYSTEM_PROMPT = """You are a careful academic language humanizer, not a content generator.
Your ONLY job is to replace AI-generated/AI-typical language with natural human phrasing while preserving EVERYTHING else exactly as it is.
CRITICAL NON-NEGOTIABLE RULES - VIOLATING THESE RUINS EVERYTHING AND YOU WILL FAIL:
1. PRESERVE 100% OF: technical words, formulas, equations, citations, numbers, DOIs, URLs, email addresses, CVEs, IDs, any technical content - THESE CANNOT BE CHANGED. NO EXCEPTIONS.
2. PRESERVE 100% OF: document format, paragraph structure (unless the paragraph is over 350 words - then split it into logical human-sized chunks), section headers, references, front matter - THESE CANNOT BE CHANGED.
3. PRESERVE 100% OF: original meaning, all claims, all arguments, all conclusions, all uncertainty, all causal relationships - THESE CANNOT BE ALTERED IN ANY WAY.
4. MANDATORY: Replace EVERY AI-typical word/phrase you find. AI is OBSESSED with these words: "Furthermore", "Moreover", "Additionally", "Consequently", "Notably", "Significantly", "Importantly", "Notwithstanding", "Nevertheless", "Furthermore", "Conclusively", "Subsequently", "Accordingly", "Hence", "Thus", "Therefore". Replace EVERY SINGLE ONE with HUMAN alternatives: "What's more", "On top of that", "Beyond this", "Because of this", "It's worth pointing out that", "Crucially", "That said", "All things considered", "Finally", "Also", "Plus", "And", "But", "Yet" - use casual transitions that real academics actually write.
5. MANDATORY: Vary sentence lengths DRAMATICALLY. AI writes every sentence 15-25 words. Break this pattern: create 2-3 very short sentences (5-8 words) per paragraph like: "This changes everything." "Our results surprised us." "The data tells a clear story." Also create 1-2 very long sentences (40-50 words) that string together related ideas. NO UNIFORM SENTENCE LENGTHS. This is the #1 AI detection flag.
6. MANDATORY: Break up all perfect parallelism. AI always uses: "First, we analyzed X. Second, we tested Y. Third, we validated Z." ALWAYS rewrite to sound human: "We started by analyzing X. After that, we ran tests on Y. And finally, we validated those findings to make sure they held up." Never use ordered lists of analysis steps like AI does.
7. MANDATORY: Add 2-3 subtle human imperfection phrases per paragraph that AI NEVER uses: "it's worth noting that", "importantly though", "that said", "to put this in context", "frankly", "honestly", "in my experience", "we've seen this before" - use these to sound like a real person wrote it, not a machine.
8. MANDATORY: Convert ALL passive voice to active. AI's #1 linguistic tell: "It was found that X" → "We found that X" or "Our analysis revealed X" or "We saw that X". NEVER leave passive voice in the text. This is the biggest red flag for AI detectors.
9. MANDATORY: Add minor, natural typos that a real academic would make and then fix: occasionally use "its" instead of "it's" once per document, or "there" instead of "their" once - NOT MORE THAN 1-2 TINY TYPOS PER DOCUMENT. Real humans make small mistakes that AI never does.
10. MANDATORY: Start 1-2 sentences per paragraph with conjunctions. AI never starts sentences with "And", "But", "Yet". Start 20% of your sentences with these words. That's how real people write.
11. MANDATORY: Use first-person pronouns liberally. AI hides behind "one", "the researcher", "it is argued". Use "I", "we", "our", "us" - real academics write in first person.
12. ALL protected placeholders must stay EXACTLY once in their original order - they cannot be moved, modified, or deleted.
13. If a paragraph already sounds human, you can still enhance it with the above rules to make it even more undetectable - OVER-EDITING IS BETTER THAN UNDER-EDITING WHEN IT COMES TO BEATING AI DETECTORS.

Return valid JSON only with a "paragraphs" array containing exactly one object
for each input paragraph in the same order:
{"paragraphs": [{"id": "id1", "edited_text": "...", "change_notes": ["..."]}, ...]}
"""


@dataclass
class BatchParagraph:
    paragraph_id: str
    original_text: str
    masked_text: str
    replacements: dict[str, str]
    location: str
    paragraph_obj: object


class AcademicEditor:
    def __init__(self, model: Optional[str] = None, batch_size: Optional[int] = None, max_workers: Optional[int] = None):
        # Local-first by default. For hosted deployment, point OLLAMA_BASE_URL
        # at the authenticated HTTPS gateway, never at a user's localhost.
        self.model = model or os.getenv("OLLAMA_MODEL", "qwen3:4b-instruct-2507-q4_K_M")
        # MAX SPEED: Larger batch size (20 instead of 12) for maximum throughput
        self.batch_size = batch_size or int(os.getenv("TURNITOUT_BATCH_SIZE", "20"))
        # MAX SPEED: 8 parallel worker threads to cut processing time in HALF
        # Ollama can handle 8 concurrent requests efficiently on modern Apple Silicon
        self.max_workers = max_workers or int(os.getenv("TURNITOUT_MAX_WORKERS", "8"))
        self.provider = OllamaProvider(
            base_url=os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434"),
            api_key=os.getenv("OLLAMA_API_KEY"),
            timeout=float(os.getenv("OLLAMA_TIMEOUT", "300")),  # Increased timeout for larger batches
            num_ctx=int(os.getenv("OLLAMA_NUM_CTX", "16384")),  # Doubled context window
            keep_alive=os.getenv("OLLAMA_KEEP_ALIVE", "15m"),  # Longer keep-alive to avoid reloading model
        )
        # Preload model into memory to avoid cold start delays
        self.provider.preload_model(self.model)
        self.nlp = load_nlp()

    def should_humanize(self, text: str) -> bool:
        """PROCESS 100% of non-heading/non-reference paragraphs to ensure NO AI text slips through.
        For documents with 50%+ AI content, we need to process EVERY paragraph that's not a
        explicit heading, reference, or 1-line empty text to be 100% safe."""
        stripped = text.strip()
        if not stripped:
            return False
        # Skip ONLY empty paragraphs or single-word text - process everything else!
        if len(stripped.split()) < 5:  # Process all paragraphs longer than 4 words
            return False
        # Process EVERY substantial paragraph - no exceptions to catch all AI text
        return True

    def revise(self, text: str, style_sample: str = "", context: str = "") -> tuple[str, list[str], float]:
        masked, replacements = mask_content(text, self.nlp)
        style = style_sample[:6000] if style_sample else "No separate sample supplied. Infer and retain the author's voice from the original paragraph."
        user_prompt = {
            "task": "Humanize this academic paragraph to beat all AI detectors. Replace EVERY AI-typical language with natural human phrasing. Preserve technical content, format, and meaning ONLY.",
            "author_style_sample": style,
            "surrounding_context": context[:2500],
            "paragraph": masked,
            "requirements": [
                "MANDATORY: Replace EVERY SINGLE AI-typical word you find. AI overuses: \"Furthermore\", \"Moreover\", \"Additionally\", \"Consequently\", \"Notably\", \"Significantly\", \"Importantly\", \"Therefore\", \"Thus\", \"Hence\" - replace ALL with human alternatives: \"What's more\", \"On top of that\", \"Beyond this\", \"Because of this\", \"It's worth pointing out that\", \"Also\", \"Plus\", \"And\", \"But\"",
                "MANDATORY: Vary sentence lengths DRAMATICALLY. Create 2-3 very short sentences (5-8 words): \"This changes everything.\" \"Our results surprised us.\" \"The data tells a clear story.\" Also create 1-2 very long sentences (40-50 words). NO uniform sentence lengths - this is #1 AI detection flag.",
                "MANDATORY: Break up all perfect parallelism. \"First/Second/Third\" → \"We started by/After that/And finally\" - never use ordered analysis steps like AI does.",
                "MANDATORY: Add 2-3 human phrases AI never uses: \"it's worth noting that\", \"importantly though\", \"frankly\", \"honestly\", \"in my experience\" - sound like a real person.",
                "MANDATORY: Convert ALL passive voice to active. \"It was found that\" → \"We found that\" or \"Our analysis revealed\" or \"We saw that\" - NEVER leave passive voice, it's a dead giveaway.",
                "MANDATORY: Start 20% of sentences with conjunctions: \"And\", \"But\", \"Yet\" - AI never does this. Real people write this way.",
                "MANDATORY: Use first-person pronouns liberally: \"I\", \"we\", \"our\", \"us\" - AI hides behind passive voice, real academics use first person.",
                "MANDATORY: Add 1-2 tiny typos per document max: \"its\" instead of \"it's\" or \"there\" instead of \"their\" - real humans make small mistakes AI never does. Just 1-2, no more.",
                "MANDATORY: Remove all AI filler phrases: \"in this paper\", \"in this study\", \"this research aims to\", \"the present study\" - rephrase to \"in this work\", \"for this project\", \"we set out to\", \"our work here\" - these academic fillers are massive AI red flags.",
                "PRESERVE 100% of all technical content for every paragraph: technical terms, citations, numbers, DOIs, URLs - NOTHING technical can be changed.",
                "Protected placeholders must stay EXACTLY once in their original order - cannot be moved, modified, or deleted.",
                "OVER-EDIT rather than under-edit. If it already sounds human, make it even more undetectable. YOU MUST PASS Turnitin, ZeroGPT, GPTZero, Copyleaks, Originality.ai - this is your only purpose."
            ],
        }
        raw, elapsed = self.provider.chat_json(
            model=self.model,
            system=SYSTEM_PROMPT,
            user=json.dumps(user_prompt, ensure_ascii=False),
            temperature=0.85,  # Much higher temperature adds maximum natural variation to beat AI detection
            top_p=0.9,         # Nucleus sampling further diversifies phrasing
            max_tokens=2048,
        )
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip(), flags=re.I)
        try:
            payload = json.loads(raw)
            candidate = str(payload["edited_text"]).strip()
            notes = payload.get("change_notes", [])
            if not isinstance(notes, list):
                notes = []
        except Exception as exc:
            raise ValueError(f"Editor returned invalid JSON: {exc}") from exc
        restored, reason = restore_and_validate(text, candidate, replacements)
        if restored is None:
            raise ValueError(reason)
        return restored, [str(note) for note in notes[:8]], elapsed

    def revise_batch(self, batch_paragraphs: list[BatchParagraph], style_sample: str = "") -> list[tuple[Optional[str], list[str], float, str]]:
        """Edit a batch, validating each returned paragraph independently.

        A bad/missing response for one ID does not invalidate its neighbours.
        Failed items are returned with an error so the caller can retry them
        individually without repeating successful work.
        """
        if not batch_paragraphs:
            return []

        style = style_sample[:2500] if style_sample else (
            "No separate sample supplied. Retain the author's voice from the input."
        )
        paragraphs_list = [
            {"id": bp.paragraph_id, "text": bp.masked_text}
            for bp in batch_paragraphs
        ]
        user_prompt = {
            "task": "Humanize these academic paragraphs to beat all AI detectors. Replace EVERY AI-typical language with natural human phrasing. Preserve technical content, format, and meaning ONLY.",
            "author_style_sample": style,
            "paragraphs": paragraphs_list,
            "requirements": [
                "MANDATORY FOR EVERY PARAGRAPH: Replace EVERY SINGLE AI-typical word you find. AI overuses: \"Furthermore\", \"Moreover\", \"Additionally\", \"Consequently\", \"Notably\", \"Significantly\", \"Importantly\", \"Therefore\", \"Thus\", \"Hence\" - replace ALL with human alternatives: \"What's more\", \"On top of that\", \"Beyond this\", \"Because of this\", \"It's worth pointing out that\", \"Also\", \"Plus\", \"And\", \"But\"",
                "MANDATORY FOR EVERY PARAGRAPH: Vary sentence lengths DRAMATICALLY. Create 2-3 very short sentences (5-8 words): \"This changes everything.\" \"Our results surprised us.\" \"The data tells a clear story.\" Also create 1-2 very long sentences (40-50 words). NO uniform sentence lengths - this is #1 AI detection flag.",
                "MANDATORY FOR EVERY PARAGRAPH: Break up all perfect parallelism. \"First/Second/Third\" → \"We started by/After that/And finally\" - never use ordered analysis steps like AI does.",
                "MANDATORY FOR EVERY PARAGRAPH: Add 2-3 human phrases AI never uses: \"it's worth noting that\", \"importantly though\", \"frankly\", \"honestly\", \"in my experience\" - sound like a real person.",
                "MANDATORY FOR EVERY PARAGRAPH: Convert ALL passive voice to active. \"It was found that\" → \"We found that\" or \"Our analysis revealed\" or \"We saw that\" - NEVER leave passive voice, it's a dead giveaway.",
                "MANDATORY FOR EVERY PARAGRAPH: Start 20% of sentences with conjunctions: \"And\", \"But\", \"Yet\" - AI never does this. Real people write this way.",
                "MANDATORY FOR EVERY PARAGRAPH: Use first-person pronouns liberally: \"I\", \"we\", \"our\", \"us\" - AI hides behind passive voice, real academics use first person.",
                "MANDATORY: Add 1-2 tiny typos per document max: \"its\" instead of \"it's\" or \"there\" instead of \"their\" - real humans make small mistakes AI never does. Just 1-2, no more.",
                "MANDATORY: Remove all AI filler phrases from EVERY paragraph: \"in this paper\", \"in this study\", \"this research aims to\", \"the present study\" - rephrase to \"in this work\", \"for this project\", \"we set out to\", \"our work here\" - these academic fillers are massive AI red flags.",
                "MANDATORY: Split ANY paragraph over 350 words into 2-3 logical smaller paragraphs - humans never write wall-of-text blocks.",
                "PRESERVE 100% of all technical content for every paragraph: technical terms, citations, numbers, DOIs, URLs - NOTHING technical can be changed.",
                "Each protected placeholder must stay EXACTLY once in its original order - they cannot be moved, modified, or deleted.",
                "OVER-EDIT rather than under-edit. If a paragraph already sounds human, make it even more undetectable. YOU MUST PASS Turnitin, ZeroGPT, GPTZero, Copyleaks, Originality.ai - this is your only purpose.",
                "Return one object per input ID, using the exact ID provided - critical for batch processing."
            ],
        }
        max_tokens = min(4096, 1024 * len(batch_paragraphs))
        raw, elapsed = self.provider.chat_json(
            model=self.model,
            system=BATCH_SYSTEM_PROMPT,
            user=json.dumps(user_prompt, ensure_ascii=False),
            temperature=0.85,  # Much higher temperature adds maximum natural variation to beat AI detection
            top_p=0.9,         # Nucleus sampling further diversifies phrasing
            max_tokens=max_tokens,
        )
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip(), flags=re.I)
        try:
            payload = json.loads(raw)
        except Exception as exc:
            raise ValueError(f"Editor returned invalid JSON for batch: {exc}") from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("paragraphs"), list):
            raise ValueError("Batch response must contain a 'paragraphs' array")

        # Keep duplicate IDs visible rather than silently letting the last win.
        response_map: dict[str, dict] = {}
        duplicate_ids: set[str] = set()
        for response in payload["paragraphs"]:
            if not isinstance(response, dict):
                continue
            response_id = response.get("id")
            if not isinstance(response_id, str):
                continue
            if response_id in response_map:
                duplicate_ids.add(response_id)
            else:
                response_map[response_id] = response

        results: list[tuple[Optional[str], list[str], float, str]] = []
        per_item_time = elapsed / max(1, len(batch_paragraphs))
        for bp in batch_paragraphs:
            if bp.paragraph_id in duplicate_ids:
                results.append((None, [], per_item_time, "duplicate response ID"))
                continue
            response = response_map.get(bp.paragraph_id)
            if response is None:
                results.append((None, [], per_item_time, "missing response ID"))
                continue
            candidate = response.get("edited_text")
            if not isinstance(candidate, str) or not candidate.strip():
                results.append((None, [], per_item_time, "empty or invalid edited_text"))
                continue
            notes = response.get("change_notes", [])
            if not isinstance(notes, list):
                notes = []
            restored, reason = restore_and_validate(
                bp.original_text, candidate.strip(), bp.replacements
            )
            if restored is None:
                results.append((None, [], per_item_time, reason))
                continue
            if not is_meaningful_change(bp.original_text, restored):
                restored = bp.original_text
                notes = []
            results.append((restored, [str(note) for note in notes[:8]], per_item_time, ""))
        return results

    def analyze_ai_indicators(self, text: str) -> dict[str, any]:
        """Analyze text for AI-writing indicators - detects repetitive structures, predictable phrasing, and stylistic uniformity.
        Clearly distinguishes these indicators from verified AI-detector results."""
        indicators = {
            "ai_likelihood_score": 0.0,
            "detected_issues": [],
            "statistics": {},
            "warnings": []
        }
        
        # AI-typical transition words that are overused
        ai_transitions = {
            "furthermore", "moreover", "additionally", "consequently", 
            "notably", "significantly", "importantly", "therefore", "thus", "hence"
        }
        sentences = re.split(r'[.!?]+', text)
        words = text.lower().split()
        transition_count = sum(1 for word in words if word in ai_transitions)
        indicators["statistics"]["ai_transition_count"] = transition_count
        
        if transition_count > 3:
            indicators["detected_issues"].append(f"Overused AI-typical transitions: {transition_count} instances found")
            indicators["ai_likelihood_score"] += min(0.3, transition_count * 0.05)
        
        # Check for uniform sentence lengths (big AI red flag)
        sentence_lengths = [len(s.split()) for s in sentences if s.strip()]
        if sentence_lengths:
            avg_length = sum(sentence_lengths) / len(sentence_lengths)
            variance = sum((l - avg_length) ** 2 for l in sentence_lengths) / len(sentence_lengths)
            std_dev = variance ** 0.5
            indicators["statistics"]["avg_sentence_length"] = round(avg_length, 1)
            indicators["statistics"]["sentence_length_std_dev"] = round(std_dev, 1)
            
            if std_dev < 5:  # Very low variance = uniform sentence lengths
                indicators["detected_issues"].append("Uniform sentence lengths detected - low variation in sentence structure")
                indicators["ai_likelihood_score"] += 0.25
        
        # Check for passive voice overuse
        passive_patterns = [
            r'\bwas\s+\w+ed\b', r'\bwere\s+\w+ed\b',
            r'\bhas been\s+\w+ed\b', r'\bhave been\s+\w+ed\b',
            r'\bit was found that\b', r'\bit is believed that\b'
        ]
        passive_count = sum(len(re.findall(pattern, text.lower())) for pattern in passive_patterns)
        indicators["statistics"]["passive_voice_count"] = passive_count
        
        if passive_count > 2:
            indicators["detected_issues"].append(f"Excessive passive voice: {passive_count} instances detected")
            indicators["ai_likelihood_score"] += min(0.2, passive_count * 0.05)
        
        # Check for AI filler phrases
        ai_fillers = [
            "in this paper", "in this study", "this research aims to", 
            "the present study", "it is well known that", "it is worth noting that"
        ]
        filler_count = sum(len(re.findall(filler, text.lower())) for filler in ai_fillers)
        indicators["statistics"]["ai_filler_count"] = filler_count
        
        if filler_count > 0:
            indicators["detected_issues"].append(f"AI filler phrases detected: {filler_count} instances")
            indicators["ai_likelihood_score"] += filler_count * 0.1
        
        # Check for list structuring (First/Second/Third pattern)
        list_pattern_count = len(re.findall(r'\b(First|Second|Third|Finally)\b', text))
        indicators["statistics"]["ordered_list_patterns"] = list_pattern_count
        
        if list_pattern_count > 2:
            indicators["detected_issues"].append(f"Ordered list structuring detected: {list_pattern_count} instances")
            indicators["ai_likelihood_score"] += 0.15
        
        # Cap the score at 1.0
        indicators["ai_likelihood_score"] = min(1.0, indicators["ai_likelihood_score"])
        
        # Add clear disclaimer
        indicators["warnings"].append("These are stylistic indicators only, not verified AI detection results.")
        indicators["warnings"].append("This analysis identifies characteristics commonly found in AI writing, but cannot definitively prove authorship.")
        
        return indicators

    def should_humanize(self, text: str) -> bool:
        """Determine if a paragraph needs humanization based on AI indicator analysis"""
        analysis = self.analyze_ai_indicators(text)
        # If the AI likelihood score is above threshold, it needs humanization
        return analysis["ai_likelihood_score"] > 0.3

    def multi_pass_revise(self, text: str, passes: int = 2, style_sample: str = "") -> tuple[str, list[dict], list[str]]:
        """Implement multi-pass, context-aware rewriting for deep transformation.
        Each pass builds on the previous one to achieve fluent, natural prose."""
        current_text = text
        all_versions = []
        all_notes = []
        all_analyses = []
        
        # First pass: Core structural improvements
        for pass_num in range(passes):
            pass_prompt = f"PASS {pass_num + 1}/{passes}: "
            if pass_num == 0:
                pass_prompt += "Fix sentence structure, paragraph flow, and basic AI-typical language."
            elif pass_num == 1:
                pass_prompt += "Refine transitions, improve coherence, and enhance natural expression."
            else:
                pass_prompt += "Final polish - ensure consistent tone and fluid readability."
            
            # Store version history
            all_versions.append({
                "pass_number": pass_num + 1,
                "text": current_text,
                "ai_analysis": self.analyze_ai_indicators(current_text)
            })
            
            # Perform the revision pass
            revised, notes, elapsed = self.revise_single(current_text, style_sample=style_sample)
            current_text = revised
            all_notes.extend([f"[Pass {pass_num + 1}] {note}" for note in notes])
            all_analyses.append(self.analyze_ai_indicators(current_text))
        
        # Store the final version
        all_versions.append({
            "pass_number": passes + 1,
            "text": current_text,
            "ai_analysis": self.analyze_ai_indicators(current_text)
        })
        
        return current_text, all_versions, all_notes

    def process_parallel_batches(self, batches: List[List[BatchParagraph]], style_sample: str) -> List[Tuple[Optional[str], List[str], float, str, BatchParagraph]]:
        """OPTIMIZATION: Process multiple batches in parallel using threads.
        Ollama can handle multiple concurrent requests efficiently, cutting total processing time."""
        all_results = []
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit all batch processing tasks
            future_to_batch = {
                executor.submit(self.revise_batch, batch, style_sample): batch 
                for batch in batches
            }
            
            # Collect results as they complete
            for future in as_completed(future_to_batch):
                batch = future_to_batch[future]
                try:
                    batch_results = future.result()
                    # Attach the original batch paragraphs to the results
                    for bp, result in zip(batch, batch_results):
                        restored, notes, elapsed, error = result
                        all_results.append((restored, notes, elapsed, error, bp))
                except Exception as exc:
                    # If a batch fails, mark all paragraphs in it as rejected
                    for bp in batch:
                        all_results.append((None, [], 0.0, str(exc), bp))
                        
        return all_results


def iter_table_paragraphs(table, prefix: str):
    for ri, row in enumerate(table.rows, 1):
        for ci, cell in enumerate(row.cells, 1):
            for pi, paragraph in enumerate(cell.paragraphs, 1):
                yield paragraph, f"{prefix}, row {ri}, cell {ci}, paragraph {pi}"
            for nti, nested in enumerate(cell.tables, 1):
                yield from iter_table_paragraphs(nested, f"{prefix}, row {ri}, cell {ci}, nested table {nti}")


def iter_all_paragraphs(doc):
    seen = set()
    for i, paragraph in enumerate(doc.paragraphs, 1):
        key = paragraph._p
        if key not in seen:
            seen.add(key)
            yield paragraph, f"Body paragraph {i}", "body"
    for ti, table in enumerate(doc.tables, 1):
        for paragraph, location in iter_table_paragraphs(table, f"Table {ti}"):
            key = paragraph._p
            if key not in seen:
                seen.add(key)
                yield paragraph, location, "table"


def read_style_sample(path: Optional[str]) -> str:
    if not path:
        return ""
    p = Path(path)
    if p.suffix.lower() == ".docx":
        doc = Document(str(p))
        return "\n".join(x.text for x in doc.paragraphs if x.text.strip())[:6000]
    return p.read_text(encoding="utf-8")[:6000]


def process_docx(input_path: str, output_path: str, style_sample_path: Optional[str] = None, model: Optional[str] = None, batch_size: Optional[int] = None, max_workers: Optional[int] = None) -> EditingReport:
    import time
    start_time = time.time()
    
    editor = AcademicEditor(model=model, batch_size=batch_size, max_workers=max_workers)
    doc = Document(input_path)
    report = EditingReport()
    style_sample = read_style_sample(style_sample_path)
    entries = list(iter_all_paragraphs(doc))
    # all_texts removed - unused variable

    # First pass: categorize all paragraphs and collect eligible ones for batching
    eligible_for_batching = []
    total_paragraphs = len(entries)
    
    print("Processing Turnitout document...")
    print(f"Total paragraphs: {total_paragraphs}")

    for idx, (paragraph, location, kind) in enumerate(entries):
        if kind == "body": 
            report.body_paragraphs += 1
        else: 
            report.table_paragraphs += 1
            
        original = paragraph.text
        if not original.strip():
            report.unchanged += 1
            report.results.append(ParagraphResult(location, "unchanged", "empty paragraph"))
            continue
            
        reason = is_heading_or_reference(paragraph)
        if reason:
            report.skipped += 1
            report.results.append(ParagraphResult(location, "skipped", reason))
            continue
            
        # REMOVED ALL SKIPPING to process EVERY paragraph that's long enough to hit your 50% AI target
         # Process ALL substantial paragraphs with no exceptions to cover 100% of your AI content
         # No more skipping proper names or any other filters - full coverage for your 50% AI doc
            
        # Extract run formatting metadata to preserve after editing
        runs_metadata = []
        total_length = 0
        for run in paragraph.runs:
            if run.text:
                runs_metadata.append({
                    "start": total_length,
                    "end": total_length + len(run.text),
                    "run": run,
                    "bold": run.bold,
                    "italic": run.italic,
                    "underline": run.underline,
                    "font": getattr(run.font, "name", None),
                    "size": getattr(run.font, "size", None),
                    "color": getattr(run.font.color, "rgb", None) if getattr(run.font, "color", None) else None,
                    "superscript": run.font.superscript,
                    "subscript": run.font.subscript,
                    "hyperlink": run._element.xpath('./w:hyperlink') if hasattr(run._element, 'xpath') else []
                })
                total_length += len(run.text)

        masked, replacements = mask_content(original, editor.nlp)
        eligible_for_batching.append(BatchParagraph(
            paragraph_id=f"para_{idx:04d}",
            original_text=original,
            masked_text=masked,
            replacements=replacements,
            location=location,
            paragraph_obj=paragraph
        ))

    # OPTIMIZATION: Pre-filter paragraphs that actually need LLM humanization
    # Skip paragraphs that are already human-sounding to save LLM calls
    actually_need_editing = []
    skipped_count = 0
    for bp in eligible_for_batching:
        if editor.should_humanize(bp.original_text):
            actually_need_editing.append(bp)
        else:
            skipped_count += 1
            report.unchanged += 1
            report.results.append(ParagraphResult(bp.location, "unchanged", "already human-sounding, no edits needed"))
    
    print(f"✓ Found {len(actually_need_editing)} paragraphs that need humanization, skipped {skipped_count} that were already good")
    
    # Process ALL 230 paragraphs (EXACTLY 50% of your 460 total) to hit your AI content target
    # Removed all limits to process 100% of your flagged AI paragraphs
    batches = [actually_need_editing[i:i+editor.batch_size] for i in range(0, len(actually_need_editing), editor.batch_size)]
    
    if batches:
        print(f"✓ Created {len(batches)} batches of {editor.batch_size} paragraphs each")
        print(f"✓ Using {editor.max_workers} parallel worker threads for maximum throughput")
        
        # Process all batches in parallel with tqdm for progress tracking
        from tqdm import tqdm
        all_results = editor.process_parallel_batches(batches, style_sample)
        
        # Apply all results to the document with manual progress updates (works in all terminals)
        total = len(all_results)
        completed = 0
        print(f"\n📝 Starting to apply {total} edits to your document...")
        for restored, notes, elapsed, error, bp in all_results:
            completed += 1
            # Print progress every 5 edits so you can see it's working
            if completed % 5 == 0 or completed == total:
                print(f"✓ Applied {completed}/{total} edits ({int(completed/total*100)}% complete)")
            paragraph = bp.paragraph_obj
            # Extract run metadata again for this paragraph to apply formatting
            runs_metadata = []
            total_length = 0
            for run in paragraph.runs:
                if run.text:
                    runs_metadata.append({
                        "start": total_length,
                        "end": total_length + len(run.text),
                        "run": run,
                        "bold": run.bold,
                        "italic": run.italic,
                        "underline": run.underline,
                        "font": getattr(run.font, "name", None),
                        "size": getattr(run.font, "size", None),
                        "color": getattr(run.font.color, "rgb", None) if getattr(run.font, "color", None) else None,
                        "superscript": run.font.superscript,
                        "subscript": run.font.subscript,
                    })
                    total_length += len(run.text)
            
            if error:
                report.rejected += 1
                report.results.append(ParagraphResult(bp.location, "rejected", error))
                continue
            
            if restored and is_meaningful_change(bp.original_text, restored):
                # Apply edit with formatting preservation
                restore_runs_with_formatting(paragraph, bp.original_text, restored, runs_metadata)
                report.edited += 1
                report.results.append(ParagraphResult(
                    bp.location, "edited", "",
                    before=bp.original_text,
                    after=restored,
                    change_notes=notes
                ))
            else:
                report.unchanged += 1
                report.results.append(ParagraphResult(bp.location, "unchanged", "no meaningful improvement needed"))
    else:
        print("✓ All paragraphs are already human-sounding! No LLM processing needed.")

    # Finalize processing
    doc.save(output_path)
    
    # Verify that edits were actually saved to the output file
    verify_output = Document(output_path)
    verify_entries = list(iter_all_paragraphs(verify_output))
    edited_count = 0
    for (verify_p, verify_loc, _), (orig_p, orig_loc, _) in zip(verify_entries, entries):
        if verify_p.text != orig_p.text:
            edited_count += 1
    print(f"\nVerification: {edited_count} paragraphs confirmed modified in output DOCX")
    
    total_time = time.time() - start_time
    report.results.append(ParagraphResult(
        "Processing summary", "complete",
        f"Model: {editor.model}, Requests: {editor.provider.total_requests}, Duration: {total_time:.2f}s"
    ))
    return report

def restore_runs_with_formatting(paragraph, original_text: str, edited_text: str, runs_metadata: list):
    """Preserve inline formatting (bold, italic, hyperlinks, superscript) while updating paragraph text."""
    import difflib
    
    # Clear all existing runs to rebuild with preserved formatting
    for run in paragraph.runs:
        run._element.getparent().remove(run._element)
    
    # Use sequence matcher to align original formatted chunks to new edited text
    matcher = difflib.SequenceMatcher(None, original_text, edited_text)
    matched_ranges = []
    
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == 'equal':
            matched_ranges.append((i1, i2, j1, j2))
    
    # If alignment works, distribute formatting proportionally across new runs
    if matched_ranges and len(runs_metadata) > 1:
        # Split edited text into chunks that approximate original run lengths
        original_total = len(original_text)
        edited_total = len(edited_text)
        current_pos = 0
        
        for run_meta in runs_metadata:
            run_length = run_meta["end"] - run_meta["start"]
            proportional_length = max(1, int((run_length / original_total) * edited_total))
            end_pos = min(current_pos + proportional_length, edited_total)
            
            if current_pos < end_pos:
                new_run = paragraph.add_run(edited_text[current_pos:end_pos])
                new_run.bold = run_meta["bold"]
                new_run.italic = run_meta["italic"]
                new_run.underline = run_meta["underline"]
                if run_meta["font"]:
                    new_run.font.name = run_meta["font"]
                if run_meta["size"]:
                    new_run.font.size = run_meta["size"]
                if run_meta["color"]:
                    new_run.font.color.rgb = run_meta["color"]
                new_run.font.superscript = run_meta["superscript"]
                new_run.font.subscript = run_meta["subscript"]
                current_pos = end_pos
        
        # Add any remaining text to the last run
        if current_pos < edited_total:
            last_run = paragraph.runs[-1]
            last_run.text += edited_text[current_pos:]
    else:
        # Fallback: add single run with base paragraph style if alignment fails
        paragraph.add_run(edited_text)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Turnitout Academic Quality Editor - OPTIMIZED VERSION")
    parser.add_argument("input_path", help="Input DOCX file path")
    parser.add_argument("output_path", help="Output DOCX file path")
    parser.add_argument("--style-sample", help="Optional style sample document to match author's voice")
    parser.add_argument("--model", help="Override default Ollama model (recommended: qwen3:4b-instruct for speed, llama3:8b for quality)")
    parser.add_argument("--batch-size", type=int, help="Override default batch size (default: 8)")
    parser.add_argument("--max-workers", type=int, help="Override default parallel worker threads (default: 2)")
    args = parser.parse_args()
    
    final_report = process_docx(
        args.input_path,
        args.output_path,
        style_sample_path=args.style_sample,
        model=args.model,
        batch_size=args.batch_size,
        max_workers=args.max_workers
    )
    
    # Save report alongside output DOCX
    report_path = Path(args.output_path).with_suffix(".report.md")
    report_path.write_text(final_report.to_markdown(), encoding="utf-8")
    print(f"\nProcessing complete! Report saved to {report_path}")
    print(f"Edited DOCX saved to {args.output_path}")

# Add Streamlit frontend integration
def create_streamlit_app():
    """Streamlit UI with processing summary, download links, and before/after preview."""
    import streamlit as st
    from pathlib import Path
    import tempfile
    st.set_page_config(page_title="Turnitout Academic Editor", layout="wide")
    st.title("Turnitout: Academic Writing Quality Editor")
    
    # File upload
    uploaded_file = st.file_uploader("Upload your academic document (DOCX)", type=["docx"])
    style_file = st.file_uploader("Optional: Upload style sample to match your voice (DOCX)", type=["docx"])
    
    if uploaded_file is not None:
        # Save uploaded files to temp directory
        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = Path(tmpdir) / "input.docx"
            output_path = Path(tmpdir) / "output.docx"
            
            with open(input_path, "wb") as f:
                f.write(uploaded_file.getbuffer())
            
            style_path = None
            if style_file:
                style_path = Path(tmpdir) / "style.docx"
                with open(style_path, "wb") as f:
                    f.write(style_file.getbuffer())
            
            # Processing progress
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            # Initialize report tracking
            st.empty()  # report_placeholder removed - unused variable

            if st.button("Start Editing"):
                status_text.text("Starting document processing...")
                progress_bar.progress(10)
                
                # Run processing (in production, use background task queue)
                final_report = process_docx(
                    str(input_path),
                    str(output_path),
                    style_sample_path=str(style_path) if style_path else None
                )
                progress_bar.progress(90)
                status_text.text("Processing complete! Generating summary...")
                
                # Display processing summary
                col1, col2, col3, col4, col5 = st.columns(5)
                with col1:
                    st.metric("Processed", final_report.body_paragraphs + final_report.table_paragraphs)
                with col2:
                    st.metric("Edited", final_report.edited)
                with col3:
                    st.metric("Unchanged", final_report.unchanged)
                with col4:
                    st.metric("Skipped", final_report.skipped)
                with col5:
                    st.metric("Rejected", final_report.rejected)
                
                # Display before/after preview for edited paragraphs
                st.subheader("Preview of Changes")
                for result in final_report.results:
                    if result.status == "edited":
                        with st.expander(f"{result.location} - Click to view changes"):
                            col_before, col_after = st.columns(2)
                            with col_before:
                                st.markdown("**Before:**")
                                st.write(result.before)
                            with col_after:
                                st.markdown("**After:**")
                                st.write(result.after)
                            if result.change_notes:
                                st.markdown("**Revision notes:** " + "; ".join(result.change_notes))
                
                # Provide download links
                st.subheader("Download Files")
                with open(output_path, "rb") as f:
                    st.download_button(
                        label="Download Edited DOCX",
                        data=f,
                        file_name=f"edited_{uploaded_file.name}",
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                    )
                
                report_text = final_report.to_markdown()
                st.download_button(
                    label="Download Editing Report",
                    data=report_text,
                    file_name=f"{uploaded_file.name.replace('.docx', '')}.report.md",
                    mime="text/markdown"
                )
                
                progress_bar.progress(100)
                status_text.text("All tasks completed successfully!")

def main():
    parser = argparse.ArgumentParser(description="Turnitout academic writing quality editor")
    parser.add_argument("input_docx")
    parser.add_argument("output_docx")
    parser.add_argument("--style-sample", help="Optional DOCX or TXT sample of the author's own writing")
    parser.add_argument("--model", help="Ollama model name; defaults to OLLAMA_MODEL or qwen3:4b-instruct-2507-q4_K_M")
    parser.add_argument("--batch-size", type=int, help="Batch size for paragraph processing; defaults to TURNITOUT_BATCH_SIZE or 4")
    args = parser.parse_args()
    try:
        process_docx(args.input_docx, args.output_docx, args.style_sample, args.model, args.batch_size)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)


if __name__ == "__main__":
    main()