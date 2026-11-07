"""Evaluate local academic-example retrieval against human-labelled relevance judgements.

Judgements are deliberately external to the corpus: this tool never creates labels,
approves examples, or changes documents.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from backend.app.retrieval.corpus import RevisionCorpus


def evaluate_queries(
    corpus: RevisionCorpus,
    judgments: list[dict[str, Any]],
    ks: list[int],
) -> dict[str, Any]:
    if not ks or any(k < 1 for k in ks):
        raise ValueError("k values must be positive integers")
    if not judgments:
        raise ValueError("at least one human-labelled query is required")

    eligible_ids = {pair["pair_id"] for pair in corpus.pairs}
    rows = []
    for line_no, item in enumerate(judgments, 1):
        query = item.get("query")
        relevant = item.get("relevant_pair_ids")
        if not isinstance(query, str) or len(query.strip()) < 2:
            raise ValueError(f"judgement line {line_no}: query must contain at least two characters")
        if not isinstance(relevant, list) or not relevant or any(not isinstance(x, str) for x in relevant):
            raise ValueError(f"judgement line {line_no}: relevant_pair_ids must be a non-empty string list")
        if len(set(relevant)) != len(relevant):
            raise ValueError(f"judgement line {line_no}: duplicate relevant pair ID")
        unknown = sorted(set(relevant) - eligible_ids)
        if unknown:
            raise ValueError(f"judgement line {line_no}: IDs are not in the eligible corpus: {unknown}")
        filters = item.get("filters") or {}
        if not isinstance(filters, dict) or set(filters) - {"discipline", "section", "edit_type"}:
            raise ValueError(f"judgement line {line_no}: unsupported filters")
        ranked = corpus.search(query, **filters, limit=max(ks))
        ranked_ids = [hit["pair_id"] for hit in ranked]
        relevant_set = set(relevant)
        metrics = {}
        first_rank = next((i for i, pair_id in enumerate(ranked_ids, 1) if pair_id in relevant_set), None)
        for k in ks:
            top = ranked_ids[:k]
            found = len(set(top) & relevant_set)
            metrics[str(k)] = {
                "precision": found / k,
                "recall": found / len(relevant_set),
                "reciprocal_rank": 1 / first_rank if first_rank and first_rank <= k else 0.0,
            }
        rows.append({"query": query, "metrics_at_k": metrics})

    aggregate = {}
    for k in ks:
        key = str(k)
        aggregate[key] = {
            metric: sum(row["metrics_at_k"][key][metric] for row in rows) / len(rows)
            for metric in ("precision", "recall", "reciprocal_rank")
        }
    return {
        "retrieval": "local-bm25",
        "queries_evaluated": len(rows),
        "k_values": ks,
        "macro_average": aggregate,
        "per_query": rows,
        "labels_source": "externally supplied human relevance judgements",
        "corpus_size": len(corpus.pairs),
    }


def load_judgements(path: Path) -> list[dict[str, Any]]:
    rows = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSON on judgement line {line_no}") from exc
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--judgements", type=Path, required=True, help="JSONL human relevance labels")
    parser.add_argument("--k", type=int, action="append", default=None, help="cutoff; repeat, e.g. --k 1 --k 5")
    parser.add_argument("--output", type=Path, help="optional JSON report path")
    args = parser.parse_args()
    report = evaluate_queries(RevisionCorpus.load(), load_judgements(args.judgements), args.k or [1, 3, 5])
    rendered = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
