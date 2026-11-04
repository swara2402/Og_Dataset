# Turnitout

A local document editor for academic and technical writing. Its core pipeline is
deterministic and rule-based: it reads the complete document, applies only
small, explainable corrections, and leaves good text unchanged. The editor has no generative-AI provider integration and does not require a model runtime or model API.

The canonical rule manifest and categorized grammar, vocabulary, morphology, and academic-writing rule packs, plus datasets, schemas, profiles, and preservation policies, are maintained in [`knowledge_base/`](./knowledge_base/). The historical
`Og_Dataset` gitlink is not used by runtime processing because this branch does not
contain a usable `.gitmodules` remote mapping. The backend reads the
dataset files at startup and refreshes them for each document job. Dataset
examples still marked `draft` are reference material only; they are not treated
as approved rewrite pairs.

## Features

- Upload DOCX, PDF, TXT, Markdown, and LaTeX (`.tex`) documents.
- Analyze every extracted paragraph in document order; retain headings,
  references, tables, equations, and other protected content unchanged.
- Prefer local word- or phrase-level mechanical corrections. Do not rotate
  synonyms, add filler, or restructure sentences automatically.
- Protect quotations, citations, technical identifiers, URLs, DOIs, equations,
  named entities, numbers, and uncertainty.
- Record each proposal's original and revised text, rule ID, edit scope,
  rationale, review requirement, and review status.
- Accept or reject individual proposals; exports include accepted edits and
  retain original text for pending or rejected suggestions.
- Preserve DOCX paragraph/table structure where supported; provide PDF, text,
  Markdown, and source-preserving LaTeX export.
- Keep analysis and exports local. Public-web originality search is separate
  and opt-in.

The system targets writing quality and meaning preservation. It does not
optimize for AI-detector evasion or promise detector scores.

## Setup

Requirements: Python 3.12+ and Node.js 18+.

```bash
python3 -m pip install -r requirements.txt
# Optional: install spaCy for local linguistic context analysis
# Optional NLP dependencies and model (install only when enabling spaCy):
# python3 -m pip install -r requirements-nlp.txt
# python3 -m spacy download en_core_web_sm
# python3 -m spacy download en_core_web_sm
cd frontend
npm install
npm run build
cd ..
```

## Run

Start the backend from the project root:

```bash
python3 -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

In another terminal:

```bash
cd frontend
npm run dev -- --host 127.0.0.1
```

Open <http://127.0.0.1:5173>. Interactive API documentation is available at
<http://127.0.0.1:8000/docs>.

### Security and deployment

The application supports request authentication and per-user job isolation when
bearer tokens are configured. Configure `OG_API_TOKENS` as a JSON object
mapping stable user IDs to unique, high-entropy secrets:

```bash
export OG_API_TOKENS='{"alice":"REPLACE_WITH_A_LONG_RANDOM_SECRET","bob":"REPLACE_WITH_ANOTHER_LONG_RANDOM_SECRET"}'
export OG_API_AUTH_REQUIRED=true
# Optional: comma-separated user IDs allowed to change global settings and clear cache.
export OG_API_ADMIN_USERS='alice'
```

Send the selected token on every API request:

```http
Authorization: Bearer REPLACE_WITH_A_LONG_RANDOM_SECRET
```

Each uploaded job is tagged with the authenticated user ID. Job listing is
filtered by owner, and attempts to read, change, cancel, review, or export
another user's job return `404`. Existing SQLite records without an owner
are treated as belonging to the legacy `local` account and are not visible
to configured token users. Use separate token secrets for each user; do not
share a single token across people.

Global settings changes and cache clearing are administrator-only when bearer
authentication is enabled. Set `OG_API_ADMIN_USERS` to a comma-separated list
of configured user IDs (for example `alice`). If it is empty, token users
cannot change global settings or clear the shared cache. Trusted local mode
retains its single-user administrator behavior.

Token configuration rejects duplicate user IDs, duplicate bearer secrets, and
more than 500 configured users. User IDs are limited to 128 characters and
tokens must be 32-512 characters. Analysis and originality request bodies
also enforce bounded text and selection sizes to avoid unbounded processing.

The API also applies a sliding-window limit of 120 requests per minute per
authenticated owner and direct client IP by default. Change
`OG_API_RATE_LIMIT_PER_MINUTE` to tune the budget. Excess requests receive
`429` with `Retry-After: 60`. This limiter is in-process: it is useful
for a single local instance, but counters are not shared across workers
or replicas. A multi-worker or public deployment must add a shared gateway
or distributed limiter and configure trusted proxy handling; do not trust
client-supplied forwarding headers as identity.

For backward compatibility, when `OG_API_TOKENS` is empty and
`OG_API_AUTH_REQUIRED` is false, the API runs in unauthenticated
`local` mode. This mode is intended only for a trusted machine with the
backend bound to `127.0.0.1` as shown above. Set
`OG_API_AUTH_REQUIRED=true` in any deployment environment so API requests
fail closed with `503` if tokens are missing. Do not expose the API publicly
without TLS termination, strong unique secrets, a shared rate limiter where
needed, protected database and upload storage, and operational monitoring.

The document editor does not call model APIs. Public-web originality search is a separate network feature and is not part of offline editing. CORS is not an authentication mechanism.

## Corpus-driven writing resources

The project now includes a licence-aware corpus preparation workflow under
`knowledge_base/corpus/`. It is deliberately offline: it does not crawl
repositories or download papers. Add only sources whose individual licences
permit the intended text mining, keep full-text extracts in an untracked local
directory, and use `python scripts/prepare_corpus.py` to build aggregate
section- and discipline-level observations. The output stores statistics,
not source sentences, and never modifies editing rules automatically.

Human-edited examples use the separate
`knowledge_base/schemas/revision_pair.schema.json` contract and live in
`knowledge_base/datasets/revision_pairs.jsonl`. Validate them with
`python scripts/validate_revision_pairs.py`. The validator rejects unknown
licences, duplicate pairs, missing reviewer identity, and approved pairs without
an explicit meaning-preserved decision. Draft and synthetic examples remain
reference material; they are never promoted automatically. CI validates this
file on every push. The terminology inventory lives in `knowledge_base/datasets/terminology.jsonl`, follows `knowledge_base/schemas/terminology.schema.json`, and is checked with `python scripts/validate_terminology.py`. It records discipline-specific definitions, contexts, approved equivalent variants, preferred forms, and substitutions to avoid. Only reviewed entries are loaded at runtime, and context-qualified variant changes are returned as review-required proposals. See
[`knowledge_base/corpus/README.md`](./knowledge_base/corpus/README.md) for
the manifest format, supported licence identifiers, and workflow.

The corpus preparation workflow measures section coverage, sentence-length
distributions, hedge markers, be-auxiliary markers, sentence-opening patterns, and transition
categories. Human-reviewed revision pairs and discipline-specific terminology
have separate provenance-aware schemas and validators. These are descriptive observations—not targets to imitate or
quality scores. The deterministic Python rules remain the only editing
authority; optional offline NLP may later help classify context, but it is
not required.
 
## Tests

```bash
python3 -m pytest -q
python3 scripts/validate_dataset.py
python3 scripts/validate_revision_pairs.py
python3 scripts/validate_terminology.py
python3 scripts/validate_linguistic_patterns.py
python3 scripts/evaluate_preservation.py
```

The synthetic preservation benchmark checks conservative edits against negation, uncertainty, numbers, citations and technical identifiers. It is a regression guard, not proof of semantic equivalence or a substitute for expert human evaluation. The tests use local fixtures and do not call external model services.

## API overview

| Method | Endpoint | Purpose |
| --- | --- | --- |
| GET | `/api/v1/health` | Backend and loaded OG Dataset status |
| POST | `/api/v1/documents/upload` | Upload and process DOCX/PDF/TXT/Markdown |
| GET | `/api/v1/processing/{job_id}/status` | Processing progress |
| GET | `/api/v1/processing/{job_id}/results` | All paragraphs, proposals, and versions |
| POST | `/api/v1/processing/{job_id}/review` | Accept or reject a paragraph change |
| POST | `/api/v1/processing/{job_id}/restore-version` | Restore a recorded paragraph version |
| POST | `/api/v1/processing/{job_id}/cancel` | Cancel processing |
| GET | `/api/v1/analysis/{job_id}/report` | Writing-quality and validation report |
| POST | `/api/v1/export/{job_id}` | Export DOCX, PDF, Markdown, or text |

## Repository audit

The latest source-level architecture and feature audit is documented in [`docs/repository-audit-2026-11-05.md`](./docs/repository-audit-2026-11-05.md). It records verified implementation status, remaining gaps, duplicate data sources, optional provider remnants, test evidence and the remediation order.

## Dataset updates

Edit only `knowledge_base/` for rules, profiles, schemas, examples and policies. Add rules to the appropriate JSON pack and register new packs in `knowledge_base/rules/master_rules.json`.
Run `python3 scripts/validate_dataset.py` before committing dataset changes.
Examples labelled `draft` are never used as approved training or rewriting pairs.

Update the canonical `Og_Dataset/` files from the upstream repository. The
backend loads rules and policy from that directory; `backend/app/rules/`,
`backend/app/datasets/`, and root `rules/` are synchronized compatibility
copies, not independent sources of editing behavior. Invalid or missing
canonical dataset files fail explicitly instead of silently falling back to
another rule set.

## Limitations

- The editor intentionally performs only conservative, deterministic
  corrections. Ambiguous word choices and sentence- or paragraph-level issues
  are surfaced for review instead of guessed.
- PDF extraction and export may lose complex layout, columns, figures, and
  embedded tables. DOCX preserves document structure and paragraph styles but
  can simplify complex inline formatting and floating objects.
- Jobs and review decisions are persisted in a local SQLite database. API-level owner checks prevent one configured token user from accessing another user's job through the application, but all records still share the same database and host filesystem. This is not OS-level tenant isolation or per-user encryption. Protect database, upload and export directories with restrictive filesystem permissions, backups and host access controls before multi-user use.
- Ollama, hosted model gateway code and the legacy LLM-based humanizer have been removed. Optional spaCy analysis is local and never generates replacement text.
- The spaCy provider is opt-in, does not download language models, and can produce conservative morphology-guided subject/finite-verb agreement proposals. These remain proposals requiring user review; spaCy does not generate paragraphs or apply edits automatically.
- Only five synthetic, draft examples are currently provided; there are no
  verified human revision pairs to support broad automatic rewriting.
