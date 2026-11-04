from pathlib import Path

import pytest

from backend.app.engine.dataset_validation import DatasetValidationError, validate_dataset


def test_canonical_knowledge_base_passes_all_schema_checks():
    root = Path(__file__).resolve().parents[1] / "knowledge_base"
    report = validate_dataset(root)
    assert report["valid"] is True
    assert report["dataset_version"] == "1.2.0"
    assert report["rule_count"] >= 1
    assert report["example_count"] == 5


def test_dataset_validation_rejects_missing_knowledge_base(tmp_path):
    with pytest.raises(DatasetValidationError):
        validate_dataset(tmp_path)


def test_rule_manifest_loads_categorized_packs_from_one_directory():
    root = Path(__file__).resolve().parents[1] / "knowledge_base"
    report = validate_dataset(root)
    assert report["rule_pack_count"] == 4
    assert report["rule_count"] >= 13
