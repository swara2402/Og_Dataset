# OG Dataset integration

`Og_Dataset/` is the canonical runtime source for the master rules, editing
policy, JSONL examples, schema, and exploratory academic reference profile.
The backend reads these files at startup and reloads them for every document
job. Missing or malformed source data is reported as an error; the application
does not silently use a stale fallback.

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
python3 Og_Dataset/scripts/validate_dataset.py Og_Dataset/datasets/examples.jsonl
python3 -m pytest -q
```
