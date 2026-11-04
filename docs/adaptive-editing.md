# OG Dataset integration

The tracked runtime source is the root `rules/` directory, the examples at
`backend/app/datasets/examples.jsonl`, and the schema at
`backend/app/schemas/example.schema.json`. The backend reloads these files for
each document job. An optional external dataset checkout may be selected with
`OG_DATASET_DIR`; required files are validated at load time. The historical
nested `Og_Dataset` gitlink is not used by the web pipeline.

## Editing behavior

The engine applies a single deterministic pass to the complete extracted
document. It prioritizes word-level corrections, then local phrase corrections.
It does not automatically restructure sentences or paragraphs. The current
rules support obvious local mechanical corrections; uncertain repetitions,
long sentences, and other structural concerns are flagged for author review.

Good writing is returned unchanged. The engine does not insert words, remove
hedges, replace accurate technical words, rotate synonyms, add transitions, or
edit text merely to make it look different. The contextual synonym selector
accepts only explicit alternatives with compatible part-of-speech and
context-term constraints, and abstains when candidates tie or context is
insufficient. Draft dataset examples are not used as automatic rewrite pairs.

## Document coverage and safeguards

Every extracted paragraph remains in the result and export in source order.
Body paragraphs are eligible for minimal rule-based corrections; headings,
references, tables, code, equations, quotations, citations, technical IDs, and
other protected spans remain unchanged. No per-paragraph size limit silently
skips content.

Numbers, citations, quotations, protected placeholders, and negation/uncertainty
are validated before a proposal is recorded. Failed validation leaves the
source text in place and returns a review flag. For each proposal, the result
includes original and revised text, applied rule IDs, edit scope, a concise
rationale, a change summary, validation, and review status. Users can accept or
reject each proposal before export.

## Data status

The five current examples are synthetic and marked `draft`. The reference
writing profile summarizes the AgriSense, ScamShield, and SkyTrace papers; it
is genre guidance, not a set of verified human revision pairs. Neither source
is treated as evidence of detector behavior or used to optimize detector
scores.

Run the dataset validator and backend regression suite:

```bash
python3 -m pytest -q
```
