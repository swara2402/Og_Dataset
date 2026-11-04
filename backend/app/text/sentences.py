"""Conservative deterministic sentence segmentation for academic prose."""
from __future__ import annotations

import re

# These abbreviations commonly occur inside sentences. They are intentionally
# conservative: ambiguous cases are kept together rather than split incorrectly.
_ABBREVIATIONS = {
    "dr", "prof", "mr", "mrs", "ms", "fig", "eq", "ref", "refs", "vol",
    "no", "inc", "approx", "dept", "e.g", "i.e", "etc", "vs", "al",
}
_BOUNDARY_RE = re.compile(r"(?<=[.!?])\s+")
_TRAILING_CLOSERS = '")\'”’]}'
_TOKEN_RE = re.compile(r"([A-Za-z]+(?:\.[A-Za-z]+)*)$")


def split_sentences(text: str) -> list[str]:
    """Split at likely sentence boundaries without breaking decimals/initials.

    The function does not rewrite text. Unknown or ambiguous abbreviations are
    preserved as part of the current sentence to avoid false segmentation.
    """
    value = text.strip()
    if not value:
        return []

    parts: list[str] = []
    start = 0
    for match in _BOUNDARY_RE.finditer(value):
        punctuation_index = match.start() - 1
        while punctuation_index >= start and value[punctuation_index] in _TRAILING_CLOSERS:
            punctuation_index -= 1
        punctuation = value[punctuation_index] if punctuation_index >= start else ""
        if punctuation not in ".!?":
            continue
        if punctuation == ".":
            # Decimal and version-like numeric tokens are not sentence ends.
            before = value[punctuation_index - 1] if punctuation_index else ""
            after = value[punctuation_index + 1] if punctuation_index + 1 < len(value) else ""
            if before.isdigit() and after.isdigit():
                continue
            prefix = value[start:punctuation_index].rstrip()
            token_match = _TOKEN_RE.search(prefix)
            if token_match:
                token = token_match.group(1)
                dotted_initialism = "." in token and all(
                    len(piece) == 1 for piece in token.split(".")
                )
                if token.casefold() in _ABBREVIATIONS:
                    continue
                if len(token) == 1 and token.isupper():
                    continue
                if dotted_initialism:
                    continue
        sentence = value[start:match.start()].strip()
        if sentence:
            parts.append(sentence)
        start = match.end()

    tail = value[start:].strip()
    if tail:
        parts.append(tail)
    return parts
