# Turnitout

A local document editor for academic and technical writing. Its core pipeline is
deterministic and rule-based: it reads the complete document, applies only
small, explainable corrections, and leaves good text unchanged. The editor does
not require Ollama, an external LLM, or a model API.

The canonical rules, adaptive policy, examples, schemas, profiles, and preservation
policies are maintained in [`knowledge_base/`](./knowledge_base/). The historical
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

The document API is currently designed for a trusted, local-only workflow and
has no user authentication or per-user document isolation. Keep the backend
bound to `127.0.0.1` as shown above; do not expose port `8000` directly to the
internet or place it behind a public reverse proxy without adding application
authentication, authorization, rate limits, and private job ownership. The
separate `hosted_gateway.py` protects access to an Ollama model gateway only;
it does **not** authenticate the document API. CORS is not an authentication
mechanism. The example configuration disables public-web originality searches
and debug mode by default; enable optional network features deliberately.

## Tests

```bash
python3 -m pytest -q
python3 scripts/validate_dataset.py
```

The tests use local fixtures and do not call Ollama or the public web.

## API overview

| Method | Endpoint | Purpose |
| --- | --- | --- |
| GET | `/api/v1/health` | Backend and loaded OG Dataset status |
| POST | `/api/v1/documents/upload` | Upload and process DOCX/PDF/TXT/Markdown |
| GET | `/api/v1/processing/{job_id}/status` | Processing progress |
| GET | `/api/v1/processing/{job_id}/results` | All paragraphs, proposals, and versions |
| POST | `/api/v1/processing/{job_id}/review` | Accept or reject a paragraph change |
| POST | `/api/v1/processing/{job_id}/cancel` | Cancel processing |
| GET | `/api/v1/analysis/{job_id}/report` | Writing-quality and validation report |
| POST | `/api/v1/originality/check` | Explicit opt-in public-web search |
| POST | `/api/v1/export/{job_id}` | Export DOCX, PDF, Markdown, or text |

## Dataset updates

Edit only `knowledge_base/` for rules, profiles, schemas, examples and policies.
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
- Jobs and review decisions are persisted in a local SQLite database. The database and uploaded originals remain on the host filesystem; configure protected storage and backups before using valuable documents. This is single-user local persistence, not multi-user isolation.
- The Ollama adapter is opt-in, requires a locally running Ollama service and an explicitly configured model, and is never called by default.
- The spaCy provider is opt-in, does not download language models, and provides context observations rather than rewriting text.
- Only five synthetic, draft examples are currently provided; there are no
  verified human revision pairs to support broad automatic rewriting.
