import json
import sys

import pytest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from prepare_corpus import load_manifest, main  # noqa: E402


def test_manifest_rejects_unapproved_licence(tmp_path):
    manifest = tmp_path / "sources.jsonl"
    manifest.write_text(json.dumps({
        "source_id": "P1", "title": "Paper", "url": "https://example.test/paper",
        "license_evidence": "https://example.test/license", "attribution": "Example authors",
        "license": "UNKNOWN", "text_mining_permitted": True,
        "discipline": "computer_science", "sections": ["abstract"],
        "local_text": "paper.txt"
    }) + "\n", encoding="utf-8")
    try:
        load_manifest(manifest)
    except ValueError as exc:
        assert "licence" in str(exc)
    else:
        raise AssertionError("unknown licence must be rejected")


def test_manifest_rejects_path_traversal(tmp_path):
    manifest = tmp_path / "sources.jsonl"
    manifest.write_text(json.dumps({
        "source_id": "P1", "title": "Paper", "url": "https://example.test/paper",
        "license_evidence": "https://example.test/license", "attribution": "Example authors",
        "license": "CC-BY-4.0", "text_mining_permitted": True,
        "discipline": "computer_science", "sections": ["abstract"],
        "local_text": "../paper.txt"
    }) + "\n", encoding="utf-8")
    try:
        load_manifest(manifest)
    except ValueError as exc:
        assert "filename" in str(exc)
    else:
        raise AssertionError("path traversal must be rejected")


def test_corpus_builder_emits_aggregates_not_source_sentences(tmp_path, monkeypatch):
    raw = tmp_path / "raw"
    raw.mkdir()
    secret_sentence = "Our experimental framework evaluates several useful outcomes."
    (raw / "demo.txt").write_text("[SECTION: abstract]\n" + secret_sentence, encoding="utf-8")
    manifest = tmp_path / "sources.jsonl"
    manifest.write_text(json.dumps({
        "source_id": "P1", "title": "Demo", "url": "https://example.test/paper",
        "license_evidence": "https://example.test/license", "attribution": "Example authors",
        "license": "CC-BY-4.0", "text_mining_permitted": True,
        "discipline": "computer_science", "sections": ["abstract"],
        "local_text": "demo.txt"
    }) + "\n", encoding="utf-8")
    output = tmp_path / "observations.json"
    monkeypatch.setattr(sys, "argv", ["prepare_corpus.py", "--manifest", str(manifest),
                                      "--input-dir", str(raw), "--output", str(output)])
    assert main() == 0
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["source_count"] == 1
    assert report["sentence_count"] == 1
    section = report["section_statistics"]["computer_science::abstract"]
    assert section["sentence_opening_patterns"]["pronoun_led"] == 1
    assert "be_auxiliary_markers_per_100_sentences" in section
    assert secret_sentence not in output.read_text(encoding="utf-8")

def _valid_manifest_record(local_text="paper.txt"):
    return {
        "source_id": "P2",
        "title": "Paper",
        "url": "https://example.test/paper",
        "license": "CC-BY-4.0",
        "text_mining_permitted": True,
        "discipline": "computer_science",
        "sections": ["abstract"],
        "local_text": local_text,
        "license_evidence": "https://example.test/license",
        "attribution": "Example authors",
    }


def test_manifest_requires_licence_evidence_for_real_sources(tmp_path):
    manifest = tmp_path / "sources.jsonl"
    record = _valid_manifest_record()
    record.pop("license_evidence")
    record.pop("attribution")
    manifest.write_text(json.dumps(record) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="license_evidence"):
        load_manifest(manifest)


def test_manifest_schema_rejects_duplicate_sections_and_unknown_fields(tmp_path):
    manifest = tmp_path / "sources.jsonl"
    record = _valid_manifest_record()
    record["sections"] = ["abstract", "abstract"]
    record["unexpected"] = "not allowed"
    manifest.write_text(json.dumps(record) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Manifest line 1"):
        load_manifest(manifest)


def test_corpus_builder_rejects_symlinked_source(tmp_path, monkeypatch):
    raw = tmp_path / "raw"
    raw.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("A licensed source extract should remain local.", encoding="utf-8")
    (raw / "paper.txt").symlink_to(outside)
    manifest = tmp_path / "sources.jsonl"
    manifest.write_text(json.dumps(_valid_manifest_record()) + "\n", encoding="utf-8")
    output = tmp_path / "observations.json"
    monkeypatch.setattr(sys, "argv", ["prepare_corpus.py", "--manifest", str(manifest),
                                      "--input-dir", str(raw), "--output", str(output)])
    with pytest.raises(ValueError, match="symbolic link"):
        main()


def test_corpus_builder_enforces_source_size_limit(tmp_path, monkeypatch):
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "paper.txt").write_text("x" * (1024 * 1024 + 1), encoding="utf-8")
    manifest = tmp_path / "sources.jsonl"
    manifest.write_text(json.dumps(_valid_manifest_record()) + "\n", encoding="utf-8")
    output = tmp_path / "observations.json"
    monkeypatch.setattr(sys, "argv", ["prepare_corpus.py", "--manifest", str(manifest),
                                      "--input-dir", str(raw), "--output", str(output),
                                      "--max-source-mb", "1"])
    with pytest.raises(ValueError, match="exceeds the 1 MB limit"):
        main()


def test_manifest_validate_only_does_not_require_local_source_files(tmp_path, monkeypatch):
    manifest = tmp_path / "sources.jsonl"
    manifest.write_text(json.dumps(_valid_manifest_record()) + "\n", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["prepare_corpus.py", "--manifest", str(manifest),
                                      "--validate-only"])
    assert main() == 0
