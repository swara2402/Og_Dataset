# Turnitout patch notes

## What changed
- Batch responses are validated paragraph-by-paragraph. One missing ID, malformed item, or placeholder failure no longer rejects successful neighbours.
- Only failed batch items are retried individually. If that retry also fails, only that paragraph is marked rejected.
- Duplicate and missing response IDs are detected explicitly.
- Punctuation/whitespace-only rewrites are treated as unchanged, not accepted as edits.
- The author style sample sent with each batch is capped at 2,500 characters to reduce repeated prompt payload.
- Provider timeout handling now covers socket timeouts and malformed JSON responses; empty-response handling is formatted correctly.
- Existing safeguards remain: protected-content restoration/validation, conservative length bounds, and skipping paragraphs with multiple Word runs.

## Install
Put `local_humanizer.py` and `ollama_provider.py` in the same project directory, replacing the old versions. Keep your existing virtual environment and dependencies.

Recommended local model:
```bash
ollama pull qwen3:4b-instruct-2507-q4_K_M
export OLLAMA_MODEL=qwen3:4b-instruct-2507-q4_K_M
python local_humanizer.py input.docx output.docx --batch-size 4
```

Use a real input filename. Do not type the explanatory `#` comment lines from examples into an interactive zsh prompt.

## What to verify
Run on a copy of the original DOCX. Review the generated `.report.md`, especially rejected items and all edited paragraphs. This patch has been syntax-checked and unit-smoke-tested locally, but a full live Ollama run against your document has not been performed here.


## Adaptive editing integration

- Added conservative paragraph-level editing profiles (minimal/moderate/substantial).
- Added an explicit adaptive policy and documentation.
- Replaced forced deep-rewrite/naturalness prompts with issue-led editing instructions.
- Default review passes changed to one in backend, frontend, and `.env.example`.
- Added focused tests for the adaptive profile and prompt construction.
- No AI-detector score targeting or zero-score guarantee is implemented.
