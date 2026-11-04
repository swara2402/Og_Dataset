"""Protected content masking and restoration for Turnitout.
Handles extraction, masking, and safe restoration of content that must not be altered:
- DOIs, URLs, emails
- Citation markers and bibliographic references
- Equations and formulas
- Numerical values, dates
- Technical terminology and named entities
- Code blocks
"""
from __future__ import annotations
import re
from dataclasses import dataclass
from typing import Optional, List, Tuple, Dict

try:
    import spacy
    from spacy.tokens import Doc
    SPACY_AVAILABLE = True
except ImportError:
    SPACY_AVAILABLE = False

PROTECTED_PATTERNS: dict[str, str] = {
    "email": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
    "url": r"https?://[^\s)\]}>,;]+|www\.[^\s)\]}>,;]+",
    "doi": r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+\b",
    "citation": r"\[\s*\d+(?:\s*[,;–-]\s*\d+)*\s*\]|\([A-Z][A-Za-z .'-]+,\s*\d{4}[a-z]?\)",
    "quoted_text": r"“[^”]*”|‘[^’]*’|\"[^\"\n]*\"",
    "technical_id": r"\b(?:CVE-\d{4}-\d{4,}|CWE-\d+|CVSS(?::\d+(?:\.\d+)?)?|CPE:[^\s,;]+|EPSS)\b",
    "number": r"(?<![A-Za-z])\b\d+(?:[.,]\d+)*(?:\s?%)?\b",
    "equation": r"\$[^$]+\$|\\\([^)]*\\\)|\\\[[^]]*\\\]",
}

PLACEHOLDER_RE = re.compile(r"__TURNITOUT_PROTECTED_\d{4}__")

# Numbers remain readable and are validated directly. Identifiers, citations,
# and quotations are masked so deterministic edits cannot alter their contents.
MASKED_TYPES = {
    "citation", "email", "equation", "quoted_text", "technical_id", "url", "doi"
}


@dataclass
class ProtectedSpan:
    """Represents a protected span in the original text."""
    start: int
    end: int
    value: str
    type: str
    placeholder: str


class ProtectedContentMasker:
    def __init__(self, nlp=None):
        self.nlp = nlp
        self._compile_patterns()

    def _compile_patterns(self):
        """Compile regex patterns for efficient matching."""
        self.compiled_patterns = {
            name: re.compile(pattern, re.I) 
            for name, pattern in PROTECTED_PATTERNS.items()
        }

    def _collect_spacy_entities(self, text: str) -> List[Tuple[int, int, str, str]]:
        """Collect named entities from spaCy if available."""
        spans: List[Tuple[int, int, str, str]] = []
        if not self.nlp or not SPACY_AVAILABLE:
            return spans
        
        doc: Doc = self.nlp(text)
        protected_labels = {
            "PERSON", "ORG", "GPE", "LOC", "FAC", "DATE", "TIME", 
            "MONEY", "PERCENT", "QUANTITY", "CARDINAL", "ORDINAL"
        }
        
        for ent in doc.ents:
            if ent.label_ in protected_labels:
                spans.append((ent.start_char, ent.end_char, ent.text, "entity"))
        
        return spans

    def _collect_regex_spans(self, text: str) -> List[Tuple[int, int, str, str]]:
        """Collect all regex-matched protected spans."""
        spans: List[Tuple[int, int, str, str]] = []
        
        for pattern_name, pattern in self.compiled_patterns.items():
            for match in pattern.finditer(text):
                spans.append((match.start(), match.end(), match.group(0), pattern_name))
        
        return spans

    def _merge_spans(self, text: str, spans: List[Tuple[int, int, str, str]]) -> List[ProtectedSpan]:
        """Merge overlapping spans, retaining the widest original span."""
        if not spans:
            return []
            
        # Sort by start position, then by descending length (so wider spans take precedence)
        spans.sort(key=lambda x: (x[0], -(x[1] - x[0])))
        
        merged: List[Tuple[int, int, str, str]] = []
        for start, end, value, span_type in spans:
            if merged and start < merged[-1][1]:
                # Overlap with previous, keep the wider one
                prev_start, prev_end, prev_value, prev_type = merged[-1]
                if end > prev_end:
                    merged[-1] = (prev_start, end, text[prev_start:end], span_type)
            else:
                merged.append((start, end, value, span_type))
        
        # Convert to ProtectedSpan objects with placeholders
        protected_spans: List[ProtectedSpan] = []
        for idx, (start, end, value, span_type) in enumerate(merged):
            placeholder = f"__TURNITOUT_PROTECTED_{idx:04d}__"
            protected_spans.append(ProtectedSpan(
                start=start,
                end=end,
                value=value,
                type=span_type,
                placeholder=placeholder
            ))
        
        return protected_spans

    def mask(self, text: str) -> Tuple[str, Dict[str, str], List[ProtectedSpan]]:
        """
        Mask all protected content in the text.
        Returns (masked_text, replacements, protected_spans)
        """
        # Collect all spans. Only complex identifiers are masked; readable
        # numbers and citations are preserved by validation instead.
        regex_spans = [
            span for span in self._collect_regex_spans(text) if span[3] in MASKED_TYPES
        ]
        entity_spans = self._collect_spacy_entities(text)
        all_spans = regex_spans + entity_spans
        
        # Merge and create protected spans
        protected_spans = self._merge_spans(text, all_spans)
        
        # Create replacements dictionary
        replacements = {span.placeholder: span.value for span in protected_spans}
        
        # Apply masking to the text (process in reverse to maintain indices)
        masked = text
        for span in reversed(protected_spans):
            masked = masked[:span.start] + span.placeholder + masked[span.end:]
        
        return masked, replacements, protected_spans

    def restore_and_validate(
        self, 
        original_text: str, 
        candidate_text: str, 
        replacements: Dict[str, str]
    ) -> Tuple[Optional[str], str]:
        """
        Restore protected content and validate integrity.
        Returns (restored_text, error_message) - if restoration fails, returns (None, error)
        """
        # Verify all placeholders are present in the correct order
        def get_token_index(token: str) -> int:
            match = re.search(r"_(\d{4})__$", token)
            if not match:
                raise ValueError(f"Invalid placeholder format: {token}")
            return int(match.group(1))
        expected = sorted(replacements.keys(), key=get_token_index)
        found = PLACEHOLDER_RE.findall(candidate_text)
        
        if found != expected:
            return None, "protected placeholders were missing, duplicated, reordered, or altered"
        
        # Restore all protected content
        restored = candidate_text
        for token, value in replacements.items():
            restored = restored.replace(token, value)
        
        # Secondary validation: verify all protected patterns still match
        for pattern_name, pattern in self.compiled_patterns.items():
            original_matches = pattern.findall(original_text, re.I)
            restored_matches = pattern.findall(restored, re.I)
            if original_matches != restored_matches:
                return None, f"{pattern_name} integrity check failed"
        
        # Length validation to prevent excessive changes
        if len(original_text.strip()) > 0:
            ratio = len(restored.strip()) / len(original_text.strip())
            if not (0.60 <= ratio <= 1.50):
                return None, f"edited paragraph length changed outside acceptable range (ratio: {ratio:.2f})"
        
        return restored, ""

    def is_meaningful_change(self, original: str, candidate: str) -> bool:
        """Return False for punctuation/whitespace-only rewrites."""
        if original == candidate:
            return False
        compact_original = re.sub(r"[\W_]+", "", original, flags=re.UNICODE).casefold()
        compact_candidate = re.sub(r"[\W_]+", "", candidate, flags=re.UNICODE).casefold()
        return compact_original != compact_candidate