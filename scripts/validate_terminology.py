"""Validate provenance-aware academic terminology records."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "knowledge_base/schemas/terminology.schema.json"
DEFAULT_INPUT = ROOT / "knowledge_base/datasets/terminology.jsonl"
ALLOWED_LICENSES = {"CC-BY-4.0", "CC0-1.0", "CC-BY-SA-4.0", "CC-BY-3.0", "CC-BY-SA-3.0"}


def load_entries(path: Path) -> list[dict[str, Any]]:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    entries: list[dict[str, Any]] = []
    ids: set[str] = set()
    terms: set[tuple[str, str]] = set()
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Line {line_number}: invalid JSON: {exc.msg}") from exc
        errors = sorted(validator.iter_errors(item), key=lambda error: list(error.absolute_path))
        if errors:
            error = errors[0]
            field = ".".join(str(part) for part in error.absolute_path) or "record"
            raise ValueError(f"Line {line_number} ({field}): {error.message}")
        if item["term_id"] in ids:
            raise ValueError(f"Line {line_number}: duplicate term_id {item['term_id']!r}")
        ids.add(item["term_id"])
        source = item["source"]
        if source["kind"] == "synthetic":
            if source["license"] != "SYNTHETIC":
                raise ValueError(f"Line {line_number}: synthetic records must use SYNTHETIC provenance")
        elif source["license"] not in ALLOWED_LICENSES:
            raise ValueError(f"Line {line_number}: licence is not on the reviewed allowlist")
        normalized = re.sub(r"\s+", " ", item["term"]).strip().casefold()
        for discipline in item["disciplines"]:
            key = (discipline.casefold(), normalized)
            if key in terms:
                raise ValueError(f"Line {line_number}: duplicate term {item['term']!r} for {discipline}")
            terms.add(key)
        entries.append(item)
    return entries


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--reviewed-output", type=Path, default=None)
    args = parser.parse_args(argv)
    try:
        entries = load_entries(args.input)
    except (OSError, ValueError) as exc:
        print(f"Terminology validation failed: {exc}", file=sys.stderr)
        return 1
    reviewed = [entry for entry in entries if entry["review_status"] == "reviewed"]
    summary = {
        "records": len(entries),
        "draft": sum(entry["review_status"] == "draft" for entry in entries),
        "reviewed": len(reviewed),
        "rejected": sum(entry["review_status"] == "rejected" for entry in entries),
    }
    if args.reviewed_output is not None:
        args.reviewed_output.parent.mkdir(parents=True, exist_ok=True)
        args.reviewed_output.write_text(
            "".join(json.dumps(entry, ensure_ascii=False) + "\n" for entry in reviewed),
            encoding="utf-8",
        )
        summary["reviewed_output"] = str(args.reviewed_output)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
