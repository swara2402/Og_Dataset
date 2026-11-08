"""Validate and curate provenance-aware academic revision pairs.

This tool never generates edits or upgrades review status. Human approval must
already be recorded explicitly in each source JSONL record.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "knowledge_base/schemas/revision_pair.schema.json"
DEFAULT_INPUT = ROOT / "knowledge_base/datasets/revision_pairs.jsonl"
ALLOWED_LICENSES = {"CC-BY-4.0", "CC0-1.0", "CC-BY-SA-4.0", "CC-BY-3.0", "CC-BY-SA-3.0", "CC-BY-NC-SA-4.0"}


def canonical_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().casefold()


def pair_fingerprint(item: dict[str, Any]) -> str:
    payload = "\0".join((canonical_text(item["original_text"]), canonical_text(item["edited_text"])))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def load_pairs(path: Path) -> list[dict[str, Any]]:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    pairs: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    seen_fingerprints: set[str] = set()
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
            location = ".".join(str(part) for part in error.absolute_path) or "record"
            raise ValueError(f"Line {line_number} ({location}): {error.message}")
        pair_id = item["pair_id"]
        if pair_id in seen_ids:
            raise ValueError(f"Line {line_number}: duplicate pair_id {pair_id!r}")
        seen_ids.add(pair_id)
        fingerprint = pair_fingerprint(item)
        if fingerprint in seen_fingerprints:
            raise ValueError(f"Line {line_number}: duplicate normalized original/edited pair")
        seen_fingerprints.add(fingerprint)
        source = item["source"]
        if source["kind"] == "synthetic":
            if source["license"] != "SYNTHETIC":
                raise ValueError(f"Line {line_number}: synthetic records must use SYNTHETIC provenance")
        elif source["license"] not in ALLOWED_LICENSES:
            raise ValueError(f"Line {line_number}: licence is not on the reviewed allowlist")
        if (
            source["kind"] == "public_dataset"
            and item["review_status"] == "human_approved"
            and source.get("text_mining_permitted") is not True
        ):
            raise ValueError(
                f"Line {line_number}: public-dataset pairs cannot be approved without "
                "explicit text-mining permission"
            )
        if item["review_status"] == "human_approved" and item["meaning_preserved"] is not True:
            raise ValueError(f"Line {line_number}: approved pairs must explicitly preserve meaning")
        if item["original_text"].strip() == item["edited_text"].strip() and item["review_status"] == "human_approved":
            raise ValueError(f"Line {line_number}: unchanged pairs cannot be approved as edits")
        pairs.append(item)
    return pairs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--approved-output", type=Path, default=None)
    args = parser.parse_args(argv)
    try:
        pairs = load_pairs(args.input)
    except (OSError, ValueError) as exc:
        print(f"Revision-pair validation failed: {exc}", file=sys.stderr)
        return 1
    approved = [pair for pair in pairs if pair["review_status"] == "human_approved"]
    summary = {
        "records": len(pairs),
        "draft": sum(pair["review_status"] == "draft" for pair in pairs),
        "pending_review": sum(pair["review_status"] == "pending_review" for pair in pairs),
        "human_approved": len(approved),
        "rejected": sum(pair["review_status"] == "rejected" for pair in pairs),
    }
    if args.approved_output is not None:
        args.approved_output.parent.mkdir(parents=True, exist_ok=True)
        args.approved_output.write_text(
            "".join(json.dumps(pair, ensure_ascii=False) + "\n" for pair in approved),
            encoding="utf-8",
        )
        summary["approved_output"] = str(args.approved_output)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
