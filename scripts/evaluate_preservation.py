"""Run the synthetic meaning-preservation regression set."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CASES = ROOT / "knowledge_base/datasets/preservation_evaluation.jsonl"
SCHEMA_PATH = ROOT / "knowledge_base/schemas/preservation_case.schema.json"


def evaluate(path: Path) -> dict:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    from backend.app.protected_content.masker import ProtectedContentMasker
    from backend.app.validation.validator import validate_rewrite

    masker = ProtectedContentMasker()
    outcomes = []
    seen = set()
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        case = json.loads(line)
        errors = sorted(validator.iter_errors(case), key=lambda error: list(error.absolute_path))
        if errors:
            raise ValueError(f"Line {line_no}: {errors[0].message}")
        if case["case_id"] in seen:
            raise ValueError(f"Duplicate evaluation case ID: {case['case_id']}")
        seen.add(case["case_id"])
        masked_original, _original_replacements, spans = masker.mask(case["original_text"])
        masked_candidate, _candidate_replacements, _candidate_spans = masker.mask(case["candidate_text"])
        protected = [{"type": span.type, "value": span.value} for span in spans]
        report = validate_rewrite(
            case["original_text"], case["candidate_text"],
            masked_original, masked_candidate, protected,
        )
        outcomes.append({
            "case_id": case["case_id"],
            "expected_valid": case["expected_valid"],
            "actual_valid": report["valid"],
            "passed": report["valid"] is case["expected_valid"],
            "issues": report["issues"],
        })
    failed = [item for item in outcomes if not item["passed"]]
    return {
        "cases": len(outcomes),
        "passed": len(outcomes) - len(failed),
        "failed": len(failed),
        "outcomes": outcomes,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    args = parser.parse_args(argv)
    try:
        report = evaluate(args.cases)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"Preservation evaluation failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2))
    return 0 if report["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
