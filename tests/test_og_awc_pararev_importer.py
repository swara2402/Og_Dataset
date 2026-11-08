import pytest

from scripts.acquire_og_awc_pararev import paper_components


def test_paper_components_group_linked_article_versions_deterministically():
    rows = [
        {"id_source": "version-a", "id_target": "version-b"},
        {"id_source": "version-b", "id_target": "version-c"},
        {"id_source": "version-x", "id_target": "version-y"},
    ]
    first = paper_components(rows)
    second = paper_components(list(reversed(rows)))

    assert first == second
    assert first["version-a"] == first["version-b"] == first["version-c"]
    assert first["version-x"] == first["version-y"]
    assert first["version-a"] != first["version-x"]


def test_paper_components_ignores_incomplete_version_edges():
    rows = [
        {"id_source": "version-a", "id_target": None},
        {"id_source": "", "id_target": "version-b"},
    ]
    assert paper_components(rows) == {}


def test_pararev_acquisition_output_matches_canonical_schema(tmp_path, monkeypatch):
    import json
    import sys

    from scripts.acquire_og_awc_pararev import main
    from scripts.validate_revision_pairs import load_pairs

    raw = tmp_path / "raw.jsonl"
    output = tmp_path / "revision_pairs.jsonl"
    row = {
        "id_source": "article-v1",
        "id_target": "article-v2",
        "id_paragraph": "paragraph-7",
        "parag-1": "  Original scientific paragraph.  ",
        "parag-2": "Revised scientific paragraph.",
        "annot_1": {"label": "upstream annotation"},
        "annot_2": None,
    }
    raw.write_text(json.dumps(row) + "\n", encoding="utf-8")
    monkeypatch.setattr(
        sys, "argv",
        ["acquire_og_awc_pararev.py", "--accept-license",
         "--raw", str(raw), "--output", str(output)],
    )

    assert main() == 0
    pairs = load_pairs(output)
    assert len(pairs) == 1
    pair = pairs[0]
    assert pair["original_text"] == "Original scientific paragraph."
    assert pair["edited_text"] == "Revised scientific paragraph."
    assert pair["edit_types"] == []
    assert pair["meaning_preserved"] is False
    assert pair["review_status"] == "pending_review"
    assert pair["reviewer_id"] is None
    assert pair["source"]["license"] == "CC-BY-NC-SA-4.0"
    assert pair["source"]["text_mining_permitted"] is False
    assert pair["pararev_metadata"]["source_version_id"] == "article-v1"
    assert pair["pararev_metadata"]["target_version_id"] == "article-v2"
    assert pair["pararev_metadata"]["source_annotations"]["annot_1"] == {
        "label": "upstream annotation"
    }


def test_pararev_acquisition_requires_explicit_license_acknowledgement(
    tmp_path, monkeypatch
):
    import sys

    from scripts.acquire_og_awc_pararev import main

    raw = tmp_path / "must-not-download.jsonl"
    output = tmp_path / "revision_pairs.jsonl"
    monkeypatch.setattr(
        sys, "argv",
        ["acquire_og_awc_pararev.py", "--raw", str(raw), "--output", str(output)],
    )

    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 2
    assert not raw.exists()
    assert not output.exists()


def test_validator_rejects_approval_without_text_mining_permission(tmp_path):
    import json

    from scripts.acquire_og_awc_pararev import main
    from scripts.validate_revision_pairs import load_pairs

    raw = tmp_path / "raw.jsonl"
    output = tmp_path / "revision_pairs.jsonl"
    row = {
        "id_source": "article-v1",
        "id_target": "article-v2",
        "id_paragraph": "paragraph-8",
        "parag-1": "Original paragraph.",
        "parag-2": "Revised paragraph.",
    }
    raw.write_text(json.dumps(row) + "\n", encoding="utf-8")
    monkeypatch = pytest.MonkeyPatch()
    try:
        import sys
        monkeypatch.setattr(
            sys, "argv",
            ["acquire_og_awc_pararev.py", "--accept-license",
             "--raw", str(raw), "--output", str(output)],
        )
        assert main() == 0
    finally:
        monkeypatch.undo()

    pair = json.loads(output.read_text(encoding="utf-8").splitlines()[0])
    pair["review_status"] = "human_approved"
    pair["meaning_preserved"] = True
    pair["reviewer_id"] = "reviewer-1"
    output.write_text(json.dumps(pair) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="text-mining permission"):
        load_pairs(output)
