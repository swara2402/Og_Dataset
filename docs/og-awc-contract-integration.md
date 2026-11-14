# Og-AWC to Og_Dataset data contract

The companion corpus repository (krishna-swara/Og_Academic_Writing_Corpus) owns
source acquisition, provenance, deduplication, paper-level splits and source
annotations. Og_Dataset owns the application review queue, retrieval eligibility,
document workflow and runtime. The repositories exchange JSONL records; raw
third-party corpus files remain local and are not committed to either repository.

## Import a locally prepared corpus

From the Og_Dataset root, after acquiring, validating and preparing the paper-level
splits in the companion repository, run. Prefer the prepared all.jsonl file so
its train/validation/test assignment is retained:

    python scripts/import_og_awc_records.py \
      --input /path/to/Og_Academic_Writing_Corpus/processed/pararev_splits/all.jsonl \
      --output data/local_corpus/og_awc_import_pending.jsonl \
      --report data/local_corpus/og_awc_import_report.json

The adapter validates each output against the canonical revision-pair schema,
preserves source and paper identifiers, source split, provenance and original
source labels, and rejects source-only records, no-op pairs, duplicates,
unsafe URLs and incomplete provenance. Unknown source labels are preserved
in metadata but are not mapped to unrelated edit categories.

## Mandatory gates

- Missing text_mining_permitted is treated as false.
- Every imported record is pending_review, meaning_preserved=false, and has
  no reviewer ID. The importer cannot approve records.
- The companion corpus does not provide a verified edit rationale; the
  placeholder explicitly requires a human reviewer to assess and add one.
- The 641 annotated ParaRev subset and full ParaRev file overlap. Never count
  them as independent examples; retain lineage and deduplicate.
- Imported records and reports default to data/local_corpus/, which is ignored by Git. Do not move or commit local third-party text into tracked paths.
- Retrieval requires explicit text-mining permission, a compatible license,
  human approval, meaning-preservation review and reviewer attribution.
- A source license declaration does not settle rights in underlying articles.
  Confirm intended non-commercial use and article-level rights before training,
  retrieval or redistribution.

## Training status

This adapter performs no model training. The current product baseline remains
deterministic rules plus local BM25 retrieval. Supervised training is a later
milestone requiring rights-cleared examples, trustworthy task labels,
paper-level train/validation/test splits and human-reviewed quality labels.
