"""Validate abstract, provenance-aware linguistic pattern records."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
SCHEMA_PATH = ROOT / "knowledge_base/schemas/linguistic_pattern.schema.json"
DEFAULT_INPUT = ROOT / "knowledge_base/datasets/linguistic_patterns.jsonl"
ALLOWED_LICENSES = {"CC-BY-4.0", "CC0-1.0", "CC-BY-SA-4.0", "CC-BY-3.0", "CC-BY-SA-3.0"}


def load_patterns(path: Path) -> list[dict[str, Any]]:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    patterns: list[dict[str, Any]] = []
    ids: set[str] = set()
    keys: set[tuple[str, str, str]] = set()
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Line {line_no}: invalid JSON: {exc.msg}") from exc
        errors = sorted(validator.iter_errors(item), key=lambda error: list(error.absolute_path))
        if errors:
            field = ".".join(str(part) for part in errors[0].absolute_path) or "record"
            raise ValueError(f"Line {line_no} ({field}): {errors[0].message}")
        if item["pattern_id"] in ids:
            raise ValueError(f"Line {line_no}: duplicate pattern_id {item['pattern_id']!r}")
        ids.add(item["pattern_id"])
        source = item["source"]
        if source["kind"] == "synthetic":
            if source["license"] != "SYNTHETIC":
                raise ValueError(f"Line {line_no}: synthetic records must use SYNTHETIC provenance")
        elif source["license"] not in ALLOWED_LICENSES:
            raise ValueError(f"Line {line_no}: licence is not on the reviewed allowlist")
        key = (
            item["discipline"].casefold(),
            item["section"],
            re.sub(r"\s+", " ", item["pattern_name"]).strip().casefold(),
        )
        if key in keys:
            raise ValueError(f"Line {line_no}: duplicate pattern for discipline and section")
        keys.add(key)
        patterns.append(item)
    return patterns


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--reviewed-output", type=Path, default=None)
    args = parser.parse_args(argv)
    try:
        patterns = load_patterns(args.input)
    except (OSError, ValueError) as exc:
        print(f"Linguistic-pattern validation failed: {exc}", file=sys.stderr)
        return 1
    reviewed = [item for item in patterns if item["review_status"] == "reviewed"]
    report = {
        "records": len(patterns),
        "draft": sum(item["review_status"] == "draft" for item in patterns),
        "reviewed": len(reviewed),
        "rejected": sum(item["review_status"] == "rejected" for item in patterns),
    }
    if args.reviewed_output is not None:
        args.reviewed_output.parent.mkdir(parents=True, exist_ok=True)
        args.reviewed_output.write_text(
            "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in reviewed),
            encoding="utf-8",
        )
        report["reviewed_output"] = str(args.reviewed_output)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
