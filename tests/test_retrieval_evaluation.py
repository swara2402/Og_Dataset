import pytest

from backend.app.retrieval.corpus import RevisionCorpus
from scripts.evaluate_retrieval import evaluate_queries


def approved(pair_id, text):
    return {
        "pair_id": pair_id,
        "discipline": "computer science",
        "section": "methods",
        "original_text": text,
        "edited_text": text + " revised",
        "edit_types": ["clarity"],
        "rationale": "clarity",
        "meaning_preserved": True,
        "review_status": "human_approved",
        "reviewer_id": "reviewer-1",
        "source": {
            "kind": "human_revision",
            "reference": pair_id,
            "license": "CC0-1.0",
            "attribution": "reviewer",
        },
    }


def test_evaluation_reports_precision_recall_and_reciprocal_rank():
    corpus = RevisionCorpus([
        approved("p1", "neural network classification"),
        approved("p2", "qualitative interview analysis"),
    ])
    report = evaluate_queries(
        corpus,
        [{"query": "neural network", "relevant_pair_ids": ["p1"]}],
        [1, 2],
    )
    assert report["queries_evaluated"] == 1
    assert report["macro_average"]["1"]["precision"] == 1.0
    assert report["macro_average"]["1"]["recall"] == 1.0
    assert report["macro_average"]["1"]["reciprocal_rank"] == 1.0
    assert report["macro_average"]["2"]["precision"] == 0.5


def test_evaluation_rejects_labels_for_ineligible_or_unknown_examples():
    corpus = RevisionCorpus([approved("p1", "neural network")])
    with pytest.raises(ValueError, match="not in the eligible corpus"):
        evaluate_queries(corpus, [{"query": "neural", "relevant_pair_ids": ["pending"]}], [1])


def test_evaluation_requires_human_labels():
    with pytest.raises(ValueError, match="at least one"):
        evaluate_queries(RevisionCorpus([]), [], [1])


def test_evaluation_rejects_invalid_k():
    with pytest.raises(ValueError, match="positive"):
        evaluate_queries(RevisionCorpus([]), [{"query": "neural", "relevant_pair_ids": ["p1"]}], [0])
