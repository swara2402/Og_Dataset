"""Originality and source-similarity analysis.

This is genuine text matching against sources returned by a search provider, but
it is NOT a check of the entire internet. Only the sentences the user chooses to
search are sent to the provider. Results are presented as similarity evidence,
not as an accusation of plagiarism.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from difflib import SequenceMatcher
from typing import Any, Dict, List, Tuple

from backend.app.originality.providers import SourceProvider
from backend.app.validation.validator import CITATION_RE, split_sentences

QUOTE_RE = re.compile(r'"[^"]{20,}"|“[^”]{20,}”|‘[^’]{20,}’')
YEAR_RE = re.compile(r"\b(?:19|20)\d{2}[a-z]?\b")


@dataclass
class Match:
    id: str
    query_sentence: str
    sentence_index: int
    matched_text: str
    source_title: str
    source_url: str
    provider: str
    similarity: float
    direct_quotation: bool
    citation_found: bool
    classification: str

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["similarity"] = round(self.similarity, 1)
        return data


def _normalise(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", text.lower())).strip()


def similarity(a: str, b: str) -> float:
    a_norm = _normalise(a)
    b_norm = _normalise(b)
    if not a_norm or not b_norm:
        return 0.0
    sequence = SequenceMatcher(None, a_norm, b_norm).ratio()
    a_tokens = set(a_norm.split())
    b_tokens = set(b_norm.split())
    jaccard = len(a_tokens & b_tokens) / max(1, len(a_tokens | b_tokens))
    return round(sequence * 0.65 + jaccard * 0.35, 4)


def best_match(target: str, candidate_text: str) -> Tuple[float, str]:
    """Return the best sentence-level similarity inside candidate_text."""
    if not candidate_text:
        return 0.0, ""
    best_score = similarity(target, candidate_text)
    best_text = candidate_text[:600]
    for sentence in split_sentences(candidate_text):
        if len(sentence) < 25:
            continue
        score = similarity(target, sentence)
        if score > best_score:
            best_score = score
            best_text = sentence
    return best_score, best_text


def _select_queries(text: str, max_queries: int) -> List[Tuple[int, str]]:
    queries: List[Tuple[int, str]] = []
    seen = set()
    for index, sentence in enumerate(split_sentences(text)):
        clean = sentence.strip()
        if len(clean) < 45 or len(clean) > 500:
            continue
        if CITATION_RE.search(clean) and len(re.findall(r"[A-Za-z]+", clean)) < 12:
            continue
        key = _normalise(clean)[:120]
        if key in seen:
            continue
        seen.add(key)
        queries.append((index, clean))
        if len(queries) >= max_queries:
            break
    return queries


def _is_direct_quotation(text: str, sentence: str) -> bool:
    for quoted in QUOTE_RE.findall(text):
        if similarity(quoted.strip("\"“”‘’"), sentence) > 0.72:
            return True
    return False


def _has_nearby_citation(text: str, sentence: str) -> bool:
    position = text.find(sentence)
    if position == -1:
        return bool(CITATION_RE.search(text))
    window = text[max(0, position - 180) : position + len(sentence) + 180]
    return bool(CITATION_RE.search(window) or YEAR_RE.search(window))


def _search_query(sentence: str) -> str:
    words = re.findall(r"[A-Za-z0-9'%.-]+", sentence)
    phrase = " ".join(words[:20])
    return f'"{phrase}"' if len(phrase) >= 24 else phrase


async def check_originality(
    text: str,
    provider: SourceProvider,
    max_queries: int = 6,
    pages_per_query: int = 2,
    fetch_pages: bool = True,
    similarity_threshold: float = 52.0,
) -> Dict[str, Any]:
    queries = _select_queries(text, max_queries)
    matches: List[Match] = []
    searched: List[Dict[str, Any]] = []
    seen_urls: set[str] = set()
    match_counter = 0

    for sentence_index, sentence in queries:
        query = _search_query(sentence)
        searched.append({"sentence_index": sentence_index, "query": query})
        try:
            results = await provider.search(query, max_results=max(2, pages_per_query + 1))
        except Exception as exc:
            searched[-1]["error"] = str(exc)
            continue
        if not results:
            # Try without exact quotes as a fallback.
            try:
                results = await provider.search(" ".join(query.strip('"').split()[:12]), max_results=3)
            except Exception:
                results = []

        for result in results[: max(1, pages_per_query + 1)]:
            score, matched_text = best_match(sentence, result.snippet)
            if fetch_pages and result.url and len(seen_urls) < pages_per_query * max_queries:
                seen_urls.add(result.url)
                page_text = await provider.fetch_text(result.url)
                page_score, page_match = best_match(sentence, page_text)
                if page_score > score:
                    score = page_score
                    matched_text = page_match
            if score * 100 < similarity_threshold:
                continue
            direct_quote = _is_direct_quotation(text, sentence)
            citation_found = _has_nearby_citation(text, sentence)
            if direct_quote and not citation_found:
                classification = "uncited_quotation"
            elif direct_quote:
                classification = "quoted_with_citation"
            elif citation_found:
                classification = "cited_similarity"
            else:
                classification = "unexplained_similarity"
            match_counter += 1
            matches.append(
                Match(
                    id=f"match_{match_counter}",
                    query_sentence=sentence,
                    sentence_index=sentence_index,
                    matched_text=matched_text,
                    source_title=result.title or result.url,
                    source_url=result.url,
                    provider=result.provider,
                    similarity=score * 100,
                    direct_quotation=direct_quote,
                    citation_found=citation_found,
                    classification=classification,
                )
            )

    # Keep the strongest match per source/query pair.
    deduped: Dict[Tuple[str, str], Match] = {}
    for match in matches:
        key = (match.query_sentence, match.source_url)
        if key not in deduped or match.similarity > deduped[key].similarity:
            deduped[key] = match
    matches = sorted(deduped.values(), key=lambda item: item.similarity, reverse=True)

    total_chars = max(1, len(text))
    matched_chars = sum(len(match.matched_text) for match in matches)
    unique_percentage = max(0.0, 100.0 - (matched_chars / total_chars * 100))
    sources = {match.source_url for match in matches}
    unexplained = [match for match in matches if match.classification in {"unexplained_similarity", "uncited_quotation"}]

    if not queries:
        summary = "No sufficiently long sentences were available for a source check."
    elif not matches:
        summary = (
            f"{len(queries)} sentence(s) were searched with no strong matches above "
            f"{similarity_threshold:.0f}% similarity. This does not prove originality."
        )
    else:
        summary = (
            f"{len(matches)} potential match(es) found across {len(sources)} source(s). "
            f"{len(unexplained)} need manual review for citation or attribution."
        )

    return {
        "provider": provider.name,
        "scope": "open_web_search_sample",
        "disclosure": (
            "Only the queries listed in `searched_queries` were sent to the search provider. "
            "The full document was not uploaded. This check samples selected sentences and "
            "does not cover the entire internet, paywalled databases, or private repositories."
        ),
        "summary": summary,
        "searched_queries": searched,
        "sentences_searched": len(queries),
        "matches": [match.to_dict() for match in matches],
        "statistics": {
            "matched_sources": len(sources),
            "potential_matches": len(matches),
            "needs_manual_review": len(unexplained),
            "uncited_quotations": sum(1 for match in matches if match.classification == "uncited_quotation"),
            "unique_content_percentage": round(unique_percentage, 1),
            "matched_text_percentage": round(100 - unique_percentage, 1),
            "similarity_threshold": similarity_threshold,
        },
        "limitations": [
            "Search engines return a limited sample of indexed public pages.",
            "Paywalled journals, books and private repositories are not searched.",
            "Text similarity can occur for common phrasing and is not proof of plagiarism.",
            "Always verify matches manually and cite sources where appropriate.",
        ],
    }