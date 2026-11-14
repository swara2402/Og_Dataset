# ParaRev integration (local-only)

Og_Dataset can acquire the full ParaRev revision-pair corpus from the companion
[Og Academic Writing Corpus](https://github.com/krishna-swara/Og_Academic_Writing_Corpus)
project's pinned upstream source revision. This is an opt-in local acquisition;
no corpus text is committed to this repository.

## Acquire and validate

Use Python 3.12+ with the repository dependencies installed:

```bash
python scripts/acquire_og_awc_pararev.py --accept-license
python scripts/validate_revision_pairs.py --input data/local_corpus/revision_pairs.jsonl
```

The source declares **CC BY-NC-SA 4.0**. Run the acquisition only for non-commercial
use when you can comply with attribution and share-alike requirements. This
dataset-level declaration does not settle rights in every underlying paper.
All downloaded and normalized text is ignored by Git under `data/local_corpus/`.
Do not publish, redistribute, or use commercially without a separate rights review.

## Safety and data semantics

- The importer preserves real original/revised paragraph pairs and source IDs.
- Paper-version links are grouped into stable paper-level IDs to avoid split leakage.
- The 641-row annotated ParaRev subset is contained in the full corpus; do not count
  it as independent data. ParaRev is derived from CASIMIR; do not double-count CASIMIR.
- Missing discipline and section labels are represented as `unspecified` and `other`.
- No edit labels or rationale are invented. The importer records that the source
  does not supply a verified rationale and leaves `edit_types` empty.
- Every pair is `pending_review`, `meaning_preserved=false`, with no reviewer. Text-mining permission is explicitly set to false because the dataset licence does not resolve underlying paper rights.
  The importer never approves records or applies edits to a user's document.
- Retrieval remains limited to its separately configured licence allowlist and
  human-approved, meaning-preserved records. ParaRev is not silently enabled as
  a production retrieval source.

## Source and attribution

- Dataset: https://huggingface.co/datasets/taln-ls2n/pararev
- Pinned revision: `e61dc8a43ae067513208e75f79b49f9928dcbec3`
- Declared licence: https://creativecommons.org/licenses/by-nc-sa/4.0/
- Attribution: Jourdan et al., *ParaRev: Building a dataset for Scientific
  Paragraph Revision annotated with revision instruction* (WRAICOGS 2025).
