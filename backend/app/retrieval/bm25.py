from __future__ import annotations
import math, re
from collections import Counter
from dataclasses import dataclass
from typing import Sequence

# Unicode-aware letters/digits, excluding underscores, with internal apostrophes/hyphens.
_TOKEN_RE = re.compile(r"[^\W_]+(?:['’-][^\W_]+)*", re.UNICODE)

def tokenize(text: str) -> list[str]:
    return [t.casefold().replace("’", "'") for t in _TOKEN_RE.findall(text)]

@dataclass(frozen=True)
class SearchHit:
    index: int
    score: float

class BM25Index:
    """Dependency-free BM25 scorer. Apply metadata filters before indexing."""
    def __init__(self, documents: Sequence[str], *, k1: float = 1.5, b: float = 0.75):
        if k1 <= 0 or not 0 <= b <= 1: raise ValueError("invalid BM25 parameters")
        self.k1, self.b = k1, b
        self.tokens = [tokenize(d) for d in documents]
        self.lengths = [len(x) for x in self.tokens]
        self.avgdl = sum(self.lengths) / len(self.lengths) if self.lengths else 0.0
        self.tf = [Counter(x) for x in self.tokens]
        df = Counter()
        for row in self.tf: df.update(row.keys())
        n = len(self.tokens)
        self.idf = {term: math.log(1 + (n-freq+0.5)/(freq+0.5)) for term, freq in df.items()}
    def search(self, query: str, *, limit: int = 8) -> list[SearchHit]:
        if limit < 1: raise ValueError("limit must be positive")
        terms = list(dict.fromkeys(tokenize(query)))
        hits = []
        for i, frequencies in enumerate(self.tf):
            score = 0.0
            for term in terms:
                f = frequencies.get(term, 0)
                if f:
                    norm = f + self.k1*(1-self.b+self.b*self.lengths[i]/(self.avgdl or 1))
                    score += self.idf.get(term, 0)*f*(self.k1+1)/norm
            if score > 0: hits.append(SearchHit(i, score))
        return sorted(hits, key=lambda h: (-h.score, h.index))[:limit]
