import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from validate_linguistic_patterns import load_patterns  # noqa: E402


def pattern(**overrides):
    item = {
        "pattern_id": "PAT-1",
        "discipline": "computer_science",
        "section": "introduction",
        "pattern_name": "problem-gap-aim",
        "structural_template": "[PROBLEM_CONTEXT] -> [RESEARCH_GAP] -> [STUDY_AIM]",
        "functional_role": "Introduce the problem, identify a bounded gap, and state the study aim.",
        "usage_context": "Use only when all three rhetorical moves are supported by the paper.",
        "avoid_when": ["The research gap is not established by cited evidence."],
        "source": {
            "kind": "expert_curated",
            "reference": "rhetorical-review-001",
            "license": "CC-BY-4.0",
            "attribution": "Curated by reviewer"
        },
        "review_status": "reviewed",
        "reviewer_id": "reviewer-1"
    }
    item.update(overrides)
    return item


def write(path, items):
    path.write_text("".join(json.dumps(item) + "\n" for item in items), encoding="utf-8")


def test_accepts_reviewed_abstract_pattern(tmp_path):
    path = tmp_path / "patterns.jsonl"
    write(path, [pattern()])
    assert load_patterns(path)[0]["pattern_name"] == "problem-gap-aim"


def test_rejects_duplicate_discipline_section_pattern(tmp_path):
    path = tmp_path / "patterns.jsonl"
    write(path, [pattern(), pattern(pattern_id="PAT-2", pattern_name="Problem   Gap Aim")])
    try:
        load_patterns(path)
    except ValueError as exc:
        assert "duplicate pattern" in str(exc)
    else:
        raise AssertionError("duplicate pattern must be rejected")


def test_rejects_unknown_source_licence(tmp_path):
    path = tmp_path / "patterns.jsonl"
    item = pattern()
    item["source"]["license"] = "UNKNOWN"
    write(path, [item])
    try:
        load_patterns(path)
    except ValueError as exc:
        assert "licence" in str(exc)
    else:
        raise AssertionError("unknown licence must be rejected")
