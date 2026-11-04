import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from validate_revision_pairs import load_pairs  # noqa: E402


def record(**overrides):
    item = {
        "pair_id": "PAIR-1",
        "discipline": "computer_science",
        "section": "introduction",
        "original_text": "The method have limitations.",
        "edited_text": "The method has limitations.",
        "edit_types": ["grammar"],
        "rationale": "Corrected subject-verb agreement.",
        "protected_claims": ["limitations"],
        "meaning_preserved": True,
        "review_status": "human_approved",
        "reviewer_id": "reviewer-1",
        "source": {
            "kind": "human_revision",
            "reference": "editorial-record-001",
            "license": "CC-BY-4.0",
            "attribution": "Example attribution"
        }
    }
    item.update(overrides)
    return item


def write_records(path, records):
    path.write_text("".join(json.dumps(item) + "\\n" for item in records), encoding="utf-8")


def test_accepts_explicitly_approved_pair(tmp_path):
    path = tmp_path / "pairs.jsonl"
    write_records(path, [record()])
    pairs = load_pairs(path)
    assert len(pairs) == 1
    assert pairs[0]["review_status"] == "human_approved"


def test_rejects_unknown_licence(tmp_path):
    path = tmp_path / "pairs.jsonl"
    item = record()
    item["source"]["license"] = "UNKNOWN"
    write_records(path, [item])
    try:
        load_pairs(path)
    except ValueError as exc:
        assert "licence" in str(exc)
    else:
        raise AssertionError("unknown licence must be rejected")


def test_rejects_approved_pair_without_reviewer(tmp_path):
    path = tmp_path / "pairs.jsonl"
    item = record(reviewer_id=None)
    write_records(path, [item])
    try:
        load_pairs(path)
    except ValueError as exc:
        assert "reviewer_id" in str(exc)
    else:
        raise AssertionError("approved pair without reviewer must be rejected")


def test_rejects_duplicate_normalized_pairs(tmp_path):
    path = tmp_path / "pairs.jsonl"
    first = record()
    second = record(pair_id="PAIR-2", original_text="The   method have limitations.")
    write_records(path, [first, second])
    try:
        load_pairs(path)
    except ValueError as exc:
        assert "duplicate normalized" in str(exc)
    else:
        raise AssertionError("duplicate pair must be rejected")


def test_draft_is_not_promoted_automatically(tmp_path):
    path = tmp_path / "pairs.jsonl"
    item = record(review_status="draft", reviewer_id=None)
    write_records(path, [item])
    assert load_pairs(path)[0]["review_status"] == "draft"
