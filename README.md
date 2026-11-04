# Turnitout

A local document editor for academic and technical writing. Its core pipeline is
deterministic and rule-based: it reads the complete document, applies only
small, explainable corrections, and leaves good text unchanged. The editor does
not require Ollama, an external LLM, or a model API.

The runtime dataset is stored in tracked repository files: rules in
`rules/`, examples in `backend/app/datasets/examples.jsonl`, and the example
schema in `backend/app/schemas/`. The backend reloads these files for each
document job. The historical nested `Og_Dataset` gitlink is not a runtime
dependency. Examples marked `draft` are validation fixtures only; they are
never treated as approved rewrite pairs. An external dataset checkout can be
selected explicitly with `OG_DATASET_DIR`.

## Features

- Upload DOCX, PDF, TXT, and Markdown documents.
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
  and Markdown export.
- Keep analysis and exports local. Public-web originality search is separate
  and opt-in.

The system targets writing quality and meaning preservation. It does not
optimize for AI-detector evasion or promise detector scores.

## Setup

Requirements: Python 3.12+ and Node.js 18+.

```bash
python3 -m pip install -r requirements.txt
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

## Tests

```bash
python3 -m pytest -q
python3 -m pytest -q
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

Update the tracked runtime files together: `rules/master_rules.json`,
`rules/adaptive_editing_policy.json`, `backend/app/datasets/examples.jsonl`,
and `backend/app/schemas/example.schema.json`. Keep the duplicate rules under
`backend/app/rules/` synchronized for compatibility. If a separate dataset
checkout is supplied through `OG_DATASET_DIR`, it must contain matching
`rules/`, `datasets/`, and `schemas/` files. Missing required files fail
explicitly. A reference-writing profile is optional and is not inferred from
detector results.

## Limitations

- The editor intentionally performs only conservative, deterministic
  corrections. Ambiguous word choices and sentence- or paragraph-level issues
  are surfaced for review instead of guessed.
- PDF extraction and export may lose complex layout, columns, figures, and
  embedded tables. DOCX preserves document structure and paragraph styles but
  can simplify complex inline formatting and floating objects.
- Jobs are held in memory and disappear when the backend restarts.
- Only five synthetic, draft examples are currently provided; there are no
  verified human revision pairs to support broad automatic rewriting.
