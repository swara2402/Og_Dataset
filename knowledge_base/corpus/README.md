# Corpus-driven academic writing resources

This directory stores **derived, aggregate writing observations**, not a mirror of copyrighted papers.

## Source workflow

1. Obtain papers through an official repository or publisher-supported route.
2. Check the licence for each individual work. Public access is not a reuse licence.
3. Add one JSONL record per source to `sources.jsonl`, recording the exact licence, URL/identifier, discipline, sections available, and whether text mining is permitted.
4. Put locally obtained plain-text extracts under an untracked working directory (for example `data/corpus_raw/`). Never commit full papers unless their licence expressly permits redistribution.
5. Run `python scripts/prepare_corpus.py --manifest knowledge_base/corpus/sources.jsonl --input-dir data/corpus_raw --output knowledge_base/corpus/observations.json`.
6. Review the aggregate report before using it to inform rules. Corpus observations are descriptive, not instructions to rewrite a sentence.

The script fails closed for missing/unknown licences and sources not explicitly marked as permitting text mining. It does not download papers, copy source sentences into the output, train a model, or automatically change editing rules.

## Source manifest format

Each line is a JSON object:

```json
{
  "source_id": "PAPER-0001",
  "title": "Paper title",
  "url": "https://example.org/paper",
  "license": "CC-BY-4.0",
  "text_mining_permitted": true,
  "discipline": "computer_science",
  "sections": ["abstract", "introduction", "methods", "results", "discussion"],
  "local_text": "PAPER-0001.txt"
}
```

Use the licence identifier and retain attribution requirements. The allowlist is intentionally conservative; update it only after checking the licence terms. A repository-wide statement does not override an article-specific licence.

## What is measured

The report aggregates sentence counts, sentence-length distributions, section coverage, hedge-marker frequency, be-auxiliary marker frequency and heuristic sentence-opening patterns, and transition-category frequency. These are coarse corpus statistics, not quality scores. They must not be used to force a particular style, inflate complexity, or replace discipline-specific human review.

## Revision pairs

Human-edited pairs belong in a separate dataset and require documented source rights, an edit rationale, protected meaning/claims, and explicit human approval. Synthetic examples must remain labelled synthetic. Unreviewed pairs are never promoted into approved examples automatically.


## Manifest validation and local ingestion limits

Each JSONL source record is checked against `knowledge_base/schemas/corpus_source.schema.json`. The manifest requires a unique source ID, title, URL field (which may be null for synthetic fixtures), licence, explicit `text_mining_permitted: true`, discipline, supported section labels and a plain `.txt` filename. Real sources must include a non-empty source URL, licence-evidence URL and attribution; synthetic fixtures may omit those fields. The script rejects unapproved licences, duplicate IDs, duplicate/unsupported sections, path traversal, symlinked source files and files larger than 50 MB by default.

Validate the manifest without reading source files:

```bash
python scripts/prepare_corpus.py --validate-only
```

The corpus remains empty until real source permissions and attribution have been checked. A manifest flag is an auditable declaration, not independent proof that a licence permits text mining.
