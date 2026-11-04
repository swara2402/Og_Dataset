import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from validate_terminology import load_entries  # noqa: E402


def entry(**overrides):
    item = {
        "term_id": "TERM-1",
        "term": "confusion matrix",
        "definition": "A table comparing predicted and observed classes.",
        "disciplines": ["computer_science"],
        "contexts": ["classification evaluation"],
        "context_terms": ["classification", "evaluation"],
        "variants": ["confusion-matrix"],
        "preferred_form": "confusion matrix",
        "avoid_substitutions": ["error table"],
        "usage_note": "Use the established technical term.",
        "source": {
            "kind": "expert_curated",
            "reference": "expert-review-001",
            "license": "CC-BY-4.0",
            "attribution": "Curated by reviewer"
        },
        "review_status": "reviewed",
        "reviewer_id": "reviewer-1"
    }
    item.update(overrides)
    return item


def write_entries(path, entries):
    path.write_text("".join(json.dumps(item) + "\n" for item in entries), encoding="utf-8")


def test_accepts_reviewed_term(tmp_path):
    path = tmp_path / "terms.jsonl"
    write_entries(path, [entry()])
    assert load_entries(path)[0]["term"] == "confusion matrix"


def test_rejects_unknown_licence(tmp_path):
    path = tmp_path / "terms.jsonl"
    item = entry()
    item["source"]["license"] = "UNKNOWN"
    write_entries(path, [item])
    try:
        load_entries(path)
    except ValueError as exc:
        assert "licence" in str(exc)
    else:
        raise AssertionError("unknown licence must be rejected")


def test_rejects_duplicate_term_in_same_discipline(tmp_path):
    path = tmp_path / "terms.jsonl"
    first = entry()
    second = entry(term_id="TERM-2", term="Confusion   matrix")
    write_entries(path, [first, second])
    try:
        load_entries(path)
    except ValueError as exc:
        assert "duplicate term" in str(exc)
    else:
        raise AssertionError("duplicate discipline term must be rejected")


def test_draft_terms_are_not_promoted(tmp_path):
    path = tmp_path / "terms.jsonl"
    item = entry(review_status="draft", reviewer_id=None)
    write_entries(path, [item])
    assert load_entries(path)[0]["review_status"] == "draft"
