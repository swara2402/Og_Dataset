"""Validate dataset files before an engine loads them."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, SchemaError


class DatasetValidationError(ValueError):
    pass


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DatasetValidationError(f"Cannot read valid JSON from {path}: {exc}") from exc


def validate_dataset(root: str | Path) -> dict[str, Any]:
    """Validate rules, policy and JSONL examples; returns a compact report."""
    root = Path(root)
    rules_doc = _load_json(root / "rules" / "master_rules.json")
    policy = _load_json(root / "rules" / "adaptive_editing_policy.json")
    schema = _load_json(root / "schemas" / "example.schema.json")
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as exc:
        raise DatasetValidationError(f"Invalid example JSON Schema: {exc.message}") from exc

    rules = rules_doc.get("rules") if isinstance(rules_doc, dict) else None
    if not isinstance(rules, list) or not rules:
        raise DatasetValidationError("master_rules.json must contain a non-empty rules array")
    ids = [rule.get("id") for rule in rules if isinstance(rule, dict)]
    if len(ids) != len(rules) or any(not isinstance(item, str) or not item for item in ids):
        raise DatasetValidationError("Every rule must be an object with a non-empty id")
    if len(ids) != len(set(ids)):
        raise DatasetValidationError("Rule IDs must be unique")
    if not isinstance(policy, dict) or not isinstance(policy.get("edit_scope_priority"), list):
        raise DatasetValidationError("Editing policy is missing edit_scope_priority")

    examples_path = root / "datasets" / "examples.jsonl"
    validator = Draft202012Validator(schema)
    seen: set[str] = set()
    count = 0
    with examples_path.open(encoding="utf-8") as stream:
        for line_no, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError as exc:
                raise DatasetValidationError(f"Invalid JSONL at line {line_no}: {exc.msg}") from exc
            errors = sorted(validator.iter_errors(item), key=lambda err: list(err.absolute_path))
            if errors:
                raise DatasetValidationError(f"Example line {line_no}: {errors[0].message}")
            identifier = item["example_id"]
            if identifier in seen:
                raise DatasetValidationError(f"Duplicate example_id: {identifier}")
            seen.add(identifier)
            count += 1

    return {"valid": True, "dataset_version": str(rules_doc.get("version", "unknown")),
            "rule_count": len(rules), "example_count": count}
