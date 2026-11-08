"""Acquire ParaRev locally and map genuine revision pairs to Og_Dataset review records.

Third-party text is written only under ignored data/local_corpus/. Records remain
pending_review and are never made eligible for retrieval automatically.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SOURCE_URL = "https://huggingface.co/datasets/taln-ls2n/pararev"
REVISION = "e61dc8a43ae067513208e75f79b49f9928dcbec3"
FILENAME = "pararev_full_without_annotation.jsonl"
EXPECTED_SHA256 = "bd5a078c2b544c9a53c0c2b3f22fe8d2c089d156682def9abd094b0f6b13f1ac"
MAX_RAW_BYTES = 256 * 1024 * 1024
DOWNLOAD_URL = f"{SOURCE_URL}/resolve/{REVISION}/{FILENAME}?download=true"
LICENSE = "CC-BY-NC-SA-4.0"
LICENSE_URL = "https://creativecommons.org/licenses/by-nc-sa/4.0/"
ATTRIBUTION = (
    "Jourdan et al., ParaRev: Building a dataset for Scientific Paragraph "
    "Revision annotated with revision instruction (WRAICOGS 2025)."
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def read_rows(path: Path):
    with path.open(encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL at line {line_no}: {exc.msg}") from exc
            if not isinstance(row, dict):
                raise ValueError(f"Expected JSON object at line {line_no}")
            yield line_no, row


def _source_field(row: dict[str, Any], canonical: str, legacy: str) -> Any:
    if canonical in row and legacy in row and row[canonical] != row[legacy]:
        raise ValueError(f"Conflicting upstream fields: {canonical} and {legacy}")
    return row[canonical] if canonical in row else row.get(legacy)


def paper_components(rows: list[dict[str, Any]]) -> dict[str, str]:
    parent: dict[str, str] = {}

    def find(value: str) -> str:
        parent.setdefault(value, value)
        if parent[value] != value:
            parent[value] = find(parent[value])
        return parent[value]

    for row in rows:
        left, right = row.get("id_source"), row.get("id_target")
        if isinstance(left, str) and left.strip() and isinstance(right, str) and right.strip():
            a, b = find(left.strip()), find(right.strip())
            if a != b:
                first, second = sorted((a, b))
                parent[second] = first

    groups: dict[str, list[str]] = {}
    for version in list(parent):
        groups.setdefault(find(version), []).append(version)
    result: dict[str, str] = {}
    for versions in groups.values():
        digest = hashlib.sha256("\\0".join(sorted(versions)).encode()).hexdigest()[:20]
        for version in versions:
            result[version] = "pararev-paper-" + digest
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--accept-license", action="store_true",
        help="acknowledge CC BY-NC-SA 4.0 non-commercial, attribution and share-alike conditions")
    parser.add_argument("--raw", type=Path, default=Path("data/local_corpus/raw/pararev_full.jsonl"))
    parser.add_argument("--output", type=Path, default=Path("data/local_corpus/revision_pairs.jsonl"))
    args = parser.parse_args()
    if not args.accept_license:
        parser.error("ParaRev declares CC BY-NC-SA 4.0; pass --accept-license only after reviewing and accepting its conditions.")

    args.raw.parent.mkdir(parents=True, exist_ok=True)
    if not args.raw.exists():
        request = urllib.request.Request(DOWNLOAD_URL, headers={"User-Agent": "Og-Dataset-local-corpus/1.0"})
        partial = args.raw.with_suffix(args.raw.suffix + ".part")
        try:
            with urllib.request.urlopen(request, timeout=240) as response, partial.open("wb") as target:
                content_length = response.headers.get("Content-Length")
                if content_length and int(content_length) > MAX_RAW_BYTES:
                    raise ValueError("ParaRev download exceeds the configured 256 MiB safety limit")
                downloaded = 0
                while chunk := response.read(1024 * 1024):
                    downloaded += len(chunk)
                    if downloaded > MAX_RAW_BYTES:
                        raise ValueError("ParaRev download exceeds the configured 256 MiB safety limit")
                    target.write(chunk)
            partial.replace(args.raw)
        finally:
            partial.unlink(missing_ok=True)

    digest = sha256_file(args.raw)
    if digest != EXPECTED_SHA256:
        raise ValueError(
            "ParaRev source checksum mismatch; refusing to process an unverified file "
            f"(expected {EXPECTED_SHA256}, received {digest})"
        )

    if args.raw.resolve() == args.output.resolve():
        raise ValueError("Raw ParaRev input and normalized output must be different files")

    # Collect only article-version links for deterministic paper-level grouping.
    rows_for_links: list[dict[str, Any]] = []
    for _, row in read_rows(args.raw):
        rows_for_links.append({"id_source": row.get("id_source"), "id_target": row.get("id_target")})
    version_to_paper = paper_components(rows_for_links)
    acquired = datetime.now(timezone.utc).date().isoformat()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    written = excluded = 0
    try:
        with temporary.open("w", encoding="utf-8", newline="") as out:
            for line_no, row in read_rows(args.raw):
                # The Hugging Face viewer exposes the canonical fields as
                # parag_1/parag_2. Accept the historical hyphenated spelling
                # as a compatibility alias, but reject conflicting duplicates.
                original = _source_field(row, "parag_1", "parag-1")
                revised = _source_field(row, "parag_2", "parag-2")
                source_version, target_version = row.get("id_source"), row.get("id_target")
                paragraph_id = row.get("id_paragraph")
                required = (original, revised, source_version, target_version, paragraph_id)
                if not all(isinstance(v, str) and v.strip() for v in required):
                    excluded += 1
                    continue
                original, revised = original.strip(), revised.strip()
                key = f"{paragraph_id.strip()}:{source_version.strip()}:{target_version.strip()}"
                pair_id = "pararev-" + hashlib.sha256(key.encode()).hexdigest()[:24]
                record = {
                    "pair_id": pair_id,
                    "discipline": "unspecified",
                    "section": "other",
                    "original_text": original,
                    "edited_text": revised,
                    "edit_types": [],
                    "rationale": "The upstream record supplies a revision pair but no verified edit rationale; none has been inferred.",
                    "protected_claims": [],
                    "meaning_preserved": False,
                    "review_status": "pending_review",
                    "reviewer_id": None,
                    "source": {
                        "kind": "public_dataset",
                        "reference": f"ParaRev record {paragraph_id.strip()} (source row {line_no})",
                        "license": LICENSE,
                        "attribution": ATTRIBUTION,
                        "url": SOURCE_URL,
                        "license_evidence": LICENSE_URL,
                        "text_mining_permitted": False
                    },
                    "pararev_metadata": {
                        "paper_id": version_to_paper.get(source_version.strip(), "unassigned"),
                        "source_version_id": source_version.strip(),
                        "target_version_id": target_version.strip(),
                        "paragraph_id": paragraph_id.strip(),
                        "source_revision": REVISION,
                        "source_filename": FILENAME,
                        "source_row_number": line_no,
                        "source_annotations": {
                            "annot_1": row.get("annot_1"),
                            "annot_2": row.get("annot_2")
                        },
                        "overlap_group": "pararev_full_includes_641_annotated_subset"
                    }
                }
                out.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
                written += 1
        temporary.replace(args.output)
    finally:
        temporary.unlink(missing_ok=True)

    manifest = {
        "source": "ParaRev full",
        "source_revision": REVISION,
        "source_file": FILENAME,
        "license": LICENSE,
        "attribution": ATTRIBUTION,
        "acquisition_date": acquired,
        "raw_sha256": digest,
        "records_written": written,
        "records_excluded": excluded,
        "normalized_output": str(args.output),
        "publication_status": "local_only_pending_underlying_article_rights_review",
        "review_status": "all_records_pending_review",
        "warning": "The 641 annotated subset is contained in this full dataset. Do not count it twice or combine with CASIMIR as independent data. Dataset-level terms do not resolve every underlying paper right; text mining remains disabled until rights are checked."
    }
    args.output.with_suffix(".manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
