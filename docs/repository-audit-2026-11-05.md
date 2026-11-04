# Repository source audit — 2026-11-05

Audited repository: `swara2402/Og_Dataset`  
Audited branch: `main`  
Audited commit: `c14aeeb95be7e5152bef08bac8474ae013a08b6a`

This is a source-code and CI audit, not a claim of real-device or expert linguistic validation. Findings below are based on tracked source, configuration, tests, and the successful CI run for the audited commit.

## Executive result

**The repository is a functional deterministic document-editing prototype, not yet the complete offline academic writing platform described in the roadmap.** The upload/process/review/export pipeline and baseline validation are present. The no-Ollama requirement is not met: Ollama code is still imported and reachable through an explicit API option and visible frontend controls. The rule/data layout also contains divergent duplicate copies.

## Phase status

| Phase | Status | Evidence / remaining work |
| --- | --- | --- |
| 1. Repository audit | Complete (source-level) | Tracked backend, frontend, rules, providers, document formats, dependencies, tests and CI inspected. Manual UI/device testing remains separate. |
| 2. Architecture consolidation | Incomplete | Runtime loads `knowledge_base/`, but compatibility copies remain in `backend/app/rules/`, `backend/app/datasets/` and root `rules/`; rule/policy copies are not byte-identical. Ollama remains wired into the API/UI. |
| 3. Linguistic engine | Partial | Deterministic local corrections, duplicate-word/spacing checks, protected-content masking and proposal validation exist. Broad grammar coverage, morphology, context-sensitive vocabulary, voice conversion, clause/paragraph restructuring and coherence rules are not implemented to roadmap depth. |
| 4. Learning datasets | Early foundation | Five synthetic draft examples only; no verified human revision pairs or real licensed paper corpus. Corpus manifest/aggregate script and revision-pair schema were added, but the manifest is only a synthetic placeholder and the aggregate report is empty. No terminology or discipline-specific linguistic-pattern dataset yet. |
| 5. Offline NLP | Partial | Optional spaCy provider exists and returns POS/tag/lemma/dependency/entity observations. It does not currently guide deterministic transformations. No semantic-similarity model is integrated. |
| 6. Document editing | Partial / usable baseline | DOCX, PDF text extraction, TXT, Markdown and LaTeX parsing paths exist; DOCX/PDF/TXT/MD/TEX export paths exist. DOCX attempts to preserve run formatting and skips unsafe complex XML edits. PDF layout fidelity is limited. LaTeX protection exists but requires broader regression coverage. Paragraph accept/reject and version display exist; a user-facing restore/undo action is not exposed as a dedicated API/UI operation. |
| 7. Validation and testing | Partial | Automated tests cover auth, job workflow, dataset validation, protected content, DOCX formatting, PDF extraction, LaTeX, SQLite and proposal contracts. Current CI: 90 passed, 1 skipped, 1 warning; frontend lint/build pass. No broad expert writing evaluation, benchmark corpus, performance/load benchmark or measured meaning-preservation study. |
| 8. Final product | Partial | React/Vite UI, local API, SQLite job snapshots, history view, review controls and exports exist. Offline-first local use is supported for core editing. Product polish, restore/undo, stronger history UX, packaging/install experience and full offline acceptance tests remain. |

## Confirmed architecture findings

### Runtime and rule sources

- `backend/app/humanisation/adaptive_editing.py` resolves the runtime dataset root to `knowledge_base/` by default (overridable with `OG_DATASET_DIR`).
- The canonical runtime tree is therefore `knowledge_base/rules/`, `knowledge_base/datasets/`, `knowledge_base/schemas/`, `knowledge_base/profiles/` and related knowledge-base resources.
- Duplicate compatibility trees still exist at `backend/app/rules/`, `backend/app/datasets/` and root `rules/`.
- The master-rules copies in `backend/app/rules/` and root `rules/` have the same blob SHA, but `knowledge_base/rules/master_rules.json` differs. The adaptive-policy copies also differ. This contradicts the README's statement that all compatibility copies are synchronized and creates a source-of-truth risk.
- Runtime validation checks the canonical knowledge base; it does not establish that the compatibility copies match it.

### AI/provider cleanup

- Ollama is still a live optional feature, not merely dead files:
  - `backend/app/api/router.py` imports `LocalOllamaAdapter`, `OllamaSuggestionEngine` and `OllamaProvider`.
  - `POST /api/v1/analysis/paragraph` accepts `include_local_llm` and can invoke Ollama when enabled.
  - `GET /api/v1/engines/status` exposes Ollama configuration.
  - `backend/app/core/config.py` still defines Ollama settings.
  - `frontend/src/pages/DocumentWorkspace.tsx`, `frontend/src/pages/Settings.tsx` and `frontend/src/contexts/APIContext.tsx` still expose Ollama state and controls.
  - Legacy files include `backend/app/providers/ollama_adapter.py`, `backend/app/providers/ollama_suggestion_engine.py`, root `ollama_provider.py`, `ollama_provider.py`-related compatibility modules, `hosted_gateway.py`, `Dockerfile.gateway` and `docker-compose.hosted.yml`.
- Core `requirements.txt` does not declare a hosted generative-AI SDK. The explicit Ollama implementation uses the repository's own HTTP client wrapper. The hosted gateway is an Ollama gateway, not a required core editing service.
- Optional spaCy is isolated in `requirements-nlp.txt`; core requirements do not install spaCy.
- Public-web originality search was present as an opt-in network feature in the audited snapshot; it has since been removed from the offline core.
- `quality_analysis/ai_indicators.py` computes stylistic heuristics, not an AI detector or AI percentage. It should be described as optional writing-style diagnostics, not a writing-quality objective or editing target.

### Linguistic engine

- The active editing engine is deterministic and conservative. It includes local corrections and explicit JSON rule loading.
- The current rule set contains 12 rules, but the existence of a rule record does not mean every linguistic feature in the roadmap is implemented or applied.
- `ContextualSynonymSelector` supports constrained candidate selection, but there is no demonstrated broad, curated academic terminology inventory or morphology dataset.
- The current validator checks protected placeholders, numbers, citations, modality markers, length and lexical overlap. These checks are useful guardrails, not proof that semantic meaning is preserved. The lexical similarity calculation is not a semantic model.
- The proposal pipeline returns reviewable proposals and detects conflicting outputs. The default rule adapter abstains when protected-content restoration or validation fails.

### Document and history workflow

- Upload preflights size, extension and parser availability, classifies paragraphs, masks protected spans and creates a job.
- Job and paragraph versions are persisted in SQLite snapshots; owner-scoped job access is present.
- Accept/reject and proposal-review endpoints exist. The UI exposes original/revised/compare/version tabs.
- There is no dedicated undo/restore-version endpoint or corresponding UI action in the inspected route list. Version history is viewable, but not a complete editing-history control surface.
- DOCX formatting preservation is best-effort. Complex XML children (for example hyperlinks, fields, drawings and bookmarks) are deliberately skipped rather than rewritten unsafely. Export notes must be checked by users.
- PDF extraction/export is text-oriented and may not preserve page layout, columns, figures or embedded tables. OCR is optional and disabled by default.

## Dependency and test review

- Core Python dependencies include FastAPI, Pydantic, httpx, python-docx, pypdf, ReportLab, Markdown, BeautifulSoup, jsonschema and multipart support.
- Optional dependencies are separated for spaCy and OCR.
- Frontend is React + TypeScript + Vite with ESLint; CI runs lint and production build.
- Audited CI run: `41903546868`, commit `c14aeeb`, completed successfully.
- Backend result: `90 passed, 1 skipped, 1 warning`. The warning is Starlette's deprecation notice for using httpx with its TestClient.
- Frontend lint and production build passed.
- The test suite is useful regression coverage, but does not currently constitute expert evaluation of academic prose or a statistically meaningful meaning-preservation benchmark.

## Priority remediation order

1. Remove Ollama from API, settings, UI, tests, root compatibility files and hosted-gateway deployment artifacts. Keep the deterministic engine and optional spaCy only.
2. Keep public-web originality search excluded from the offline product path; verify no external network clients remain in the core.
3. Make `knowledge_base/` the only tracked runtime dataset source; remove duplicate rule/example copies or generate compatibility copies mechanically with drift checks.
4. Expand canonical schemas and validation to cover terminology, discipline/section tags, linguistic patterns, source provenance, revision-pair eligibility and licence metadata.
5. Implement deterministic grammar/punctuation, morphology-aware and context-aware rules incrementally with minimal-change defaults and abstention when ambiguous.
6. Integrate spaCy observations into rule selection through explicit, testable features; do not let NLP generate replacement text.
7. Add a human-reviewed revision-pair curation workflow and licensed corpus intake. Keep raw full-text papers out of the repository unless redistribution rights expressly permit it.
8. Add restore/undo controls, stronger export fidelity reporting and persistent document-history UX.
9. Build a reviewed evaluation set and run meaning-preservation, grammar, readability, performance and human-review benchmarks.
10. Add offline acceptance tests that fail if runtime attempts outbound network access.

## Audit limitations

- No live browser session or physical-device test was performed.
- No expert linguist/editor review was performed.
- No external paper collection was downloaded or licence-reviewed as part of this audit.
- CI verifies the automated checks only; it does not certify academic quality or production readiness.


## Follow-up implementation update

Ollama was removed from the API request contract, runtime provider imports, settings model, workspace controls and settings display. The deterministic rule engine and optional local spaCy context provider remain. Provider-file and hosted-gateway artifact deletion is in progress; this follow-up does not change the earlier audit findings at its recorded commit.


## Follow-up implementation — model-provider removal and canonical dataset consolidation

Changes landed on `main` after the audit snapshot:

- Removed Ollama request fields and runtime construction from the paragraph-analysis API.
- Removed Ollama configuration fields from application settings and removed the related environment variables.
- Removed Ollama UI controls, status reporting, and TypeScript request/status types.
- Deleted the Ollama provider, adapter, suggestion engine, hosted gateway, gateway Docker files, and the legacy standalone LLM humanizer and its legacy tests/notes.
- Deleted duplicate rule/example directories at `backend/app/rules/`, `backend/app/datasets/`, and root `rules/`. The runtime canonical dataset is now `knowledge_base/`.
- Added architecture regression tests for the single canonical dataset location, absence of Ollama configuration/provider files, and the paragraph-analysis request contract.
- Retained optional spaCy context analysis. It is local, does not generate text, and is not required for core deterministic processing.
- Removed the public-web originality API route, provider imports and provider modules, runtime settings, frontend client method, and related configuration tests. The core no longer exposes a public search operation.

The follow-up code changes are in commits after the original audit snapshot. CI must pass on the final current `main` SHA before this follow-up is considered verified.


## Further learning-data and offline NLP work

- Added a strict JSONL validator and approved-only export for revision pairs. It checks schema, licence allowlist, reviewer identity, explicit meaning-preservation approval, duplicate IDs and normalized duplicate text pairs. It never changes draft status.
- Added a provenance-aware terminology schema and validator with discipline-specific uniqueness, preferred forms, and substitutions to avoid. The inventory is currently empty; no terms have been falsely marked as expert-reviewed.
- Added both validators to CI.
- Extended optional spaCy use beyond passive observation: when explicitly enabled for paragraph analysis, it can identify narrowly defined subject/finite-verb agreement candidates using POS, dependency and morphological number features. The adapter creates deterministic, review-required proposals and validates protected content, citations, numbers and modality before returning them. It does not generate text or auto-apply corrections.
- The agreement adapter is intentionally conservative: it skips ambiguous/coordinated/pronominal subjects and unsupported verb forms. Broader grammar, clause restructuring, voice conversion and paragraph coherence remain incomplete and need their own testable rule families.


## Document history update

- Added `POST /api/v1/processing/{job_id}/restore-version` to restore a previously persisted paragraph version after processing has completed.
- Restore copies the stored text, masked text, validation and rule metadata back into the active paragraph state, recalculates document statistics, and persists the job.
- Added a restore action beside each version in the Document Workspace history panel.
- Added API tests for restoring the original version, persistence after reload, and 404 for an unknown version.
- Restore is an explicit user action. It does not delete version history or mutate the original uploaded bytes.


## Context-qualified terminology proposals

- Added `variants` and `context_terms` to the terminology schema. A reviewed entry must explicitly identify approved equivalent surface forms and context terms; it cannot rely on a free-form synonym list.
- Runtime loads only entries whose `review_status` is `reviewed`; draft entries are excluded.
- Added a deterministic proposal adapter that requires a matching discipline and all context terms before proposing a preferred form for a recorded variant.
- The adapter protects citations and other masked spans, validates the candidate with the shared preservation checks, and returns a review-required proposal. It does not auto-apply terminology edits.
- The canonical terminology inventory remains empty until real terms have appropriate provenance and expert review.


## Corpus observations and preservation regression set

- Corpus observations now include heuristic sentence-opening categories by discipline and section, in addition to sentence-length, hedge, be-auxiliary and transition counts.
- The former passive-voice marker label was corrected: counting forms of `be` is not a syntactic passive-voice classifier. The output now calls these be-auxiliary markers and documents their limitations.
- Added a synthetic preservation regression set covering safe mechanical edits and negative controls for uncertainty, negation, numbers, citations and technical identifiers.
- The benchmark uses the shared preservation validator and is included in CI. It is a regression guard, not proof of semantic equivalence or expert linguistic quality.
- The first CI attempt exposed that the standalone benchmark script did not add the repository root to `sys.path`; that runner issue was fixed in the follow-up commit. Final verification is pending on the current main SHA.


## Discipline- and section-specific linguistic pattern dataset

- Added a schema and JSONL validator for abstract linguistic patterns with discipline, document section, structural template, rhetorical function, usage context, caution conditions, source licence, attribution and review status.
- Duplicate pattern names within the same discipline/section are rejected.
- The dataset starts empty. No published-paper sentences or unverified patterns have been inserted.
- The validator is included in CI. Reviewed abstract patterns may inform guidance, but they are not used to auto-generate or rewrite user prose.


## Current verified snapshot

Repository main at the time of this update: `b40741db6bca74782efe53f984c10cb508a94a6d`.

- **Phase 1 — Source audit:** complete at source-code level.
- **Phase 2 — Consolidation:** the Ollama/hosted model gateway and legacy LLM humanizer are removed; the duplicate rule directories are deleted; `knowledge_base/` is the single canonical dataset location with a manifest and four categorized rule packs.
- **Phase 3 — Linguistic engine:** still partial. The deterministic core applies conservative mechanical corrections; optional spaCy and reviewed terminology adapters can produce narrowly scoped review-only proposals. Broad grammar, syntax, voice, clause and paragraph transformations remain incomplete.
- **Phase 4 — Learning data:** schema, provenance, deduplication and CI validation foundations exist for revision pairs, terminology and rhetorical patterns. These datasets are empty. The corpus manifest is a synthetic placeholder and no licensed paper collection or human-reviewed revision corpus has been curated.
- **Phase 5 — Offline NLP:** partial. Optional local spaCy morphology supports a narrow agreement proposal; no semantic embedding model is integrated.
- **Phase 6 — Document editing:** working baseline with DOCX/PDF/TXT/Markdown/LaTeX paths, protected-content checks, accept/reject, version history and explicit version restore. Formatting fidelity is best-effort for complex DOCX/PDF layouts.
- **Phase 7 — Testing:** automated regression and synthetic preservation benchmark pass. No independent expert linguistic evaluation or representative academic benchmark has been completed.
- **Phase 8 — Product:** local web UI, SQLite persistence and exports exist. Packaging, complete offline acceptance, broad UI/device testing and production hardening remain.

Final CI for the snapshot above: run `41908148484` completed successfully. Backend: **117 passed, 1 skipped, 1 warning**. Frontend lint and production build passed. The remaining warning is the existing Starlette TestClient/httpx deprecation notice.

This is not a claim of complete platform readiness. Real corpus curation, expert-reviewed data, broader deterministic linguistic rules and human evaluation are still required.


## Offline boundary follow-up

The optional public-web originality feature has now been removed from the core application rather than merely disabled by default. The API route and DuckDuckGo provider modules are deleted, its settings are removed, the frontend API client no longer exposes a search action, and the privacy copy now describes local-only processing. A configuration regression test asserts that the web-search setting is absent. The offline guarantee still needs a broader static scan and test coverage for all outbound network-capable code paths before it can be treated as formally verified.


## Offline boundary and morphology follow-up (latest verified code snapshot)

- Removed the public-web originality route, DuckDuckGo provider modules, related runtime settings, frontend client method, analysis-page tab/action, and obsolete route tests.
- Added architecture regression tests that assert the route/provider are absent and scan backend application imports for outbound HTTP client dependencies.
- The offline privacy copy now states that document analysis, editing, history and exports remain local.
- Expanded optional spaCy morphology tests for plural and singular agreement, common irregular forms (`be`, `have`, `do`), pronoun abstention, coordinated-subject abstention and ambiguous morphology.
- Strengthened preservation validation: negation and uncertainty markers are compared with their local lexical context, not only by token counts. A regression test covers a changed predicate with the same uncertainty marker.
- Latest verified code snapshot: `5ee1ec0fff572b165b839b6c630cdd740eec2710`.
- CI run `41909806855`: **121 passed, 1 skipped, 1 warning**; frontend lint and production build passed.
- This verifies the tested source snapshot, not a guarantee that every dependency or every future code path is incapable of network access. The AST guard covers backend application imports, and the removed originality feature has no API/UI entry point.


### Follow-up verification after offline cleanup

- Removed the legacy per-job originality field from SQLite snapshot serialization and API workflow reset logic; old snapshots remain readable because unknown legacy keys are ignored during reconstruction.
- Removed obsolete originality UI state from the Analysis page and replaced the Settings disclosure with a local-only notice.
- Updated API metadata so it no longer advertises originality checking.
- Current verified code snapshot: `6d432966e05b1363381193200be1bb5534ce3664`.
- CI run `41910037558`: **121 passed, 1 skipped, 1 warning**; frontend lint and production build passed.


## Conservative punctuation correction follow-up

The punctuation rule previously inserted a space after every period immediately followed by a letter. That could split abbreviations such as `e.g.` and `i.e.`. It now inserts a sentence-boundary space only before a capitalised next token, preserving lowercase abbreviation components and decimal values. Added regression coverage for `e.g.`, `i.e.`, and decimal notation.

Latest verified code snapshot: `d02b18489d57f3bedecf7291605585c0953f1177`.
CI run `41910285189`: **122 passed, 1 skipped, 1 warning**; frontend lint and production build passed.


## Corpus ingestion hardening

- Added a JSON Schema contract for each corpus source manifest record and made CI validate the manifest without reading source files.
- Non-synthetic sources now require an allowed licence, explicit text-mining permission, a source URL, a separate licence-evidence URL and attribution.
- Local source ingestion rejects symlinks and enforces a configurable per-file size limit (50 MB default, 1–500 MB allowed).
- Added tests for malformed metadata, missing licence evidence, path traversal, symlinks, size limits and validation-only mode.
- Latest verified code snapshot: `8bbafcf92ced41571cbf6d58ede3253df42a012d`.
- CI run `41911369124`: **129 passed, 1 skipped, 1 warning**; frontend lint and production build passed.
