# Deterministic academic editing architecture

## Canonical data layout

The only runtime dataset source is `knowledge_base/`.

- `rules/master_rules.json` is the rule-pack manifest.
- `rules/grammar.json`, `rules/vocabulary.json`, `rules/morphology.json`, and `rules/academic_writing.json` hold categorized rule records.
- `rules/adaptive_editing_policy.json` controls conservative edit scope.
- `datasets/examples.jsonl` contains synthetic draft examples only.
- `datasets/revision_pairs.jsonl` contains provenance-aware human revision pairs; only explicitly human-approved records are eligible for approved-only export.
- `datasets/terminology.jsonl` contains discipline-qualified terms and reviewed equivalent variants.
- `datasets/linguistic_patterns.jsonl` contains abstract rhetorical patterns by discipline and section.
- `schemas/` defines each dataset contract.
- `corpus/` stores source manifests and aggregate observations, not copyrighted full papers.

The backend reloads the canonical knowledge base for each document job. Missing or malformed data is reported as an error; the application does not silently fall back to duplicate directories.

## Editing behavior

The default engine is deterministic Python. It applies only implemented, conservative local corrections such as safe repeated function-word removal and punctuation/spacing cleanup. It does not treat descriptive JSON guidance as an implemented transformation. It does not automatically rewrite full sentences or paragraphs, rotate synonyms, add filler, or change accurate technical vocabulary.

Uncertain repetition and structural issues are flagged for author review. Good writing is returned unchanged.

Optional spaCy is local and disabled by default. When explicitly enabled for paragraph analysis, it provides POS, dependency and morphology observations and can return narrow subject/finite-verb agreement proposals. Those proposals require user review and are never automatically applied. No model is downloaded at runtime.

Reviewed terminology entries can produce context-qualified preferred-term proposals when the discipline and required context terms match. Draft entries are excluded. The adapter only uses explicitly recorded equivalent variants; it does not invent synonyms.

## Preservation and document handling

The pipeline protects quotations, citations, references, equations, numbers, technical identifiers and other sensitive spans before editing. It validates placeholders, numeric/citation preservation, negation and uncertainty, and a lexical-overlap heuristic before recording a proposal. The lexical heuristic is not a semantic model and cannot prove meaning preservation.

DOCX import/export preserves supported paragraph and run formatting, with complex XML features deliberately skipped when safe rewriting cannot be guaranteed. PDF handling is text-oriented and may not retain layout. LaTeX protection is conservative. Review decisions and paragraph versions are persisted in local SQLite; users can restore a previously recorded version.

## Data curation

Published papers may inform aggregate corpus observations only after the individual work's licence and text-mining permissions are checked. Full-text extracts stay in a local untracked directory unless redistribution is explicitly permitted. Corpus preparation is offline and stores aggregate statistics rather than source sentences.

Revision pairs, terminology and linguistic patterns require source provenance, licence metadata, deduplication and explicit human review. Draft data is never silently promoted. The current curated datasets are intentionally empty: no unverified research-paper content or invented expert approvals have been added.

## Validation commands

Run from the repository root:

```bash
python scripts/validate_dataset.py
python scripts/validate_revision_pairs.py
python scripts/validate_terminology.py
python scripts/validate_linguistic_patterns.py
python scripts/evaluate_preservation.py
python -m pytest -q
```

The preservation evaluation set is synthetic regression coverage, not an expert benchmark or a guarantee of semantic equivalence. Human evaluation and real licensed corpus curation remain necessary before broad academic rewriting can be considered reliable.
