"""Import companion Og-AWC JSONL records into Og_Dataset's review queue.

This adapter is not an approval or training step. Every imported record remains
pending_review and meaning_preserved=false. Missing explicit text-mining
permission is treated as false.
"""
from __future__ import annotations
import argparse, hashlib, json, re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "knowledge_base" / "schemas" / "revision_pair.schema.json"
EDIT_TYPE_MAP = {"grammar": "grammar", "clarity": "clarity", "cohesion": "coherence", "terminology": "terminology"}
SECTIONS = {"abstract", "introduction", "literature_review", "methods", "results", "discussion", "conclusion", "other"}

def _https(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is missing")
    parsed = urlparse(value.strip())
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        raise ValueError(f"{field} must be a safe HTTPS URL")
    return value.strip()

def _safe_id(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]", "_", value)[:100]
    if not cleaned:
        raise ValueError("record_id cannot be converted to a safe identifier")
    return cleaned

def convert_record(record: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(record, dict):
        raise ValueError("record must be a JSON object")
    required = {"record_id", "source_id", "paper_id", "record_type", "original_text", "revised_text", "split", "provenance"}
    missing = sorted(required - record.keys())
    if missing:
        raise ValueError("missing fields: " + ", ".join(missing))
    if record["record_type"] not in {"revision_pair", "human_reviewed_edit"}:
        raise ValueError("only genuine revision-pair records can be imported")
    for field in ("record_id", "source_id", "paper_id", "original_text", "revised_text"):
        if not isinstance(record[field], str) or not record[field].strip():
            raise ValueError(f"{field} must be a non-empty string")
    if record["original_text"].strip() == record["revised_text"].strip():
        raise ValueError("no-op revision pair")
    if record["split"] not in {"train", "validation", "test", "unassigned"}:
        raise ValueError("unsupported source split")
    provenance = record["provenance"]
    if not isinstance(provenance, dict):
        raise ValueError("provenance must be an object")
    source_url = _https(provenance.get("source_url"), "provenance.source_url")
    license_evidence = _https(provenance.get("license_evidence") or provenance.get("license_url"), "provenance.license_evidence")
    license_id, attribution = provenance.get("license_id"), provenance.get("attribution")
    if not isinstance(license_id, str) or not license_id.strip():
        raise ValueError("provenance.license_id is missing")
    if not isinstance(attribution, str) or not attribution.strip():
        raise ValueError("provenance.attribution is missing")
    permission = provenance.get("text_mining_permitted", False)
    if not isinstance(permission, bool):
        raise ValueError("text_mining_permitted must be an explicit boolean when supplied")
    raw_labels = record.get("edit_labels", [])
    if not isinstance(raw_labels, list) or any(not isinstance(x, str) for x in raw_labels):
        raise ValueError("edit_labels must be a list of strings")
    edit_types = sorted({EDIT_TYPE_MAP[x] for x in raw_labels if x in EDIT_TYPE_MAP})
    section = record.get("section", "other")
    if section not in SECTIONS:
        section = "other"
    discipline = record.get("discipline", "unspecified")
    if not isinstance(discipline, str) or not discipline.strip():
        discipline = "unspecified"
    source_record_id = provenance.get("source_record_id")
    reference = source_record_id if isinstance(source_record_id, str) and source_record_id.strip() else record["record_id"]
    normalized_original = re.sub(r"\s+", " ", record["original_text"]).strip().casefold()
    normalized_revised = re.sub(r"\s+", " ", record["revised_text"]).strip().casefold()
    digest = hashlib.sha256((normalized_original + "\0" + normalized_revised + "\0" + record["record_type"]).encode()).hexdigest()
    acquisition_date = provenance.get("acquisition_date")
    result = {
        "pair_id": "ogawc_" + _safe_id(record["record_id"]),
        "discipline": discipline, "section": section,
        "original_text": record["original_text"].strip(), "edited_text": record["revised_text"].strip(),
        "edit_types": edit_types,
        "rationale": "The companion corpus does not provide a verified edit rationale; a human reviewer must assess the change and supply one before approval.",
        "meaning_preserved": False, "review_status": "pending_review", "reviewer_id": None,
        "source": {"kind": "public_dataset", "reference": reference, "license": license_id.strip(),
                   "attribution": attribution.strip(), "url": source_url, "license_evidence": license_evidence,
                   "text_mining_permitted": permission},
        "og_awc_metadata": {
            "record_id": record["record_id"], "source_id": record["source_id"], "paper_id": record["paper_id"],
            "record_type": record["record_type"], "source_split": record["split"],
            "source_record_id": source_record_id if isinstance(source_record_id, str) else None,
            "source_notes": str(provenance.get("notes", "")), "source_edit_labels": raw_labels,
        },
    }
    if isinstance(acquisition_date, str) and acquisition_date.strip():
        result["og_awc_metadata"]["acquisition_date"] = acquisition_date
    if record["source_id"] == "pararev":
        mapping = {
            "paper_id": record.get("paper_id"), "source_version_id": provenance.get("source_article_version_id"),
            "target_version_id": provenance.get("source_target_id"), "paragraph_id": provenance.get("source_record_id"),
            "source_revision": provenance.get("source_version"), "source_filename": provenance.get("source_file"),
            "source_row_number": provenance.get("source_row_number"), "source_annotations": provenance.get("source_annotations"),
        }
        result["pararev_metadata"] = {k: v for k, v in mapping.items() if v is not None}
    return result

def import_records(input_path: Path, output_path: Path, report_path: Path) -> dict[str, Any]:
    validator = Draft202012Validator(json.loads(SCHEMA_PATH.read_text(encoding="utf-8")), format_checker=FormatChecker())
    imported, rejected, ids, digests = [], [], set(), set()
    total = 0
    with input_path.open(encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, 1):
            if not line.strip():
                continue
            total += 1
            try:
                raw_record = json.loads(line)
                item = convert_record(raw_record)
                normalized_original = re.sub(r"\\s+", " ", raw_record["original_text"]).strip().casefold()
                normalized_revised = re.sub(r"\\s+", " ", raw_record["revised_text"]).strip().casefold()
                digest = hashlib.sha256((normalized_original + "\\0" + normalized_revised + "\\0" + raw_record["record_type"]).encode()).hexdigest()
                errors = list(validator.iter_errors(item))
                if errors:
                    raise ValueError(errors[0].message)
                if item["pair_id"] in ids:
                    raise ValueError("duplicate record_id")
                if digest in digests:
                    raise ValueError("duplicate normalized paper/text pair")
                ids.add(item["pair_id"]); digests.add(digest); imported.append(item)
            except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
                rejected.append({"line": line_no, "reason": str(exc)})
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="\n") as handle:
        for item in imported:
            handle.write(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n")
    report = {"input_records": total, "imported_pending_review": len(imported), "rejected": len(rejected),
              "approved": 0, "retrieval_eligible": sum(x["source"]["text_mining_permitted"] for x in imported),
              "note": "No record is approved. Missing text-mining permission defaults to false.", "rejections": rejected}
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=ROOT / "knowledge_base/datasets/og_awc_import_pending.jsonl")
    parser.add_argument("--report", type=Path, default=ROOT / "reports/og_awc_import_report.json")
    args = parser.parse_args()
    report = import_records(args.input, args.output, args.report)
    print(json.dumps({k: v for k, v in report.items() if k != "rejections"}, indent=2))
    return 0 if report["rejected"] == 0 else 2

if __name__ == "__main__":
    raise SystemExit(main())
