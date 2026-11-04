# Local and offline acceptance checklist

This checklist is for a real-machine acceptance run. CI validates code and synthetic
fixtures; it cannot prove that the app works on a particular laptop or that a
third-party document round-trips correctly.

## 1. Install once

Use a supported Python 3.12+ and Node.js 20.19+ (or 22.12+) installation.
With package-registry access available, run from the repository root:

```bash
bash scripts/install_local.sh
```

This creates `.venv`, installs backend dependencies and runs `npm ci`.
Optional spaCy is not required. If you plan to use it, install the optional
dependencies and model before disconnecting from the internet.

## 2. Verify while disconnected

Disable Wi-Fi/Ethernet or otherwise block outbound network access. Then run:

```bash
bash scripts/run_local.sh
```

In a second terminal:

```bash
python3 scripts/check_local.py
```

Expected smoke-check results:
- API health is `healthy` and deterministic rules are loaded.
- Frontend responds on `127.0.0.1:5173`.
- Settings report `local_only=true` and `hosted_llm=false`.
- The smoke checker only contacts loopback URLs.

Open the app at <http://127.0.0.1:5173>. Confirm it still loads and responds
while the machine is disconnected. Stop the launcher with Ctrl+C.

## 3. Document workflow checks

Use copies of representative documents, never the only copy of important work.
For every format, upload, wait for processing, inspect original and proposed
text, accept one safe edit, reject one proposal, restore an earlier version,
restart the app, and confirm the history remains available.

| Format | Acceptance checks | Important limitation |
| --- | --- | --- |
| TXT / Markdown | Paragraph order, headings, citations and accepted/rejected text | Markdown styling is exported as Markdown text |
| DOCX | Headings, tables, paragraph order, headers/footers, bold/italic runs, hyperlinks | Complex XML structures may be preserved unchanged; check export notes for accepted edits that were skipped |
| Text-based PDF | Extracted paragraph order, citations, page text and exported PDF readability | PDF export is regenerated from extracted text; original page layout, columns and typography are not guaranteed to match |
| Scanned PDF | Confirm the default path reports limited/no extractable text; separately test OCR only when optional OCR dependencies are installed and explicitly enabled | OCR is opt-in and may introduce recognition errors |
| LaTeX (.tex) | Preamble, macros, equations, citations and environments remain intact; accepted prose edits splice into the original source | Only mapped prose blocks are editable; compile with the user's local TeX toolchain to verify |

For DOCX, include at least one document with a table, header/footer, formatted
runs and a hyperlink. Verify that unsupported complex XML remains unchanged
rather than being silently flattened. Review any export notes.

For LaTeX, compile the exported source with the same local TeX distribution and
packages as the original document. Compare the PDF output and inspect equations,
references, figures and custom macros.

## 4. Persistence and safety

- Restart both local services and confirm saved jobs, review decisions and
  version history can be reopened.
- Confirm the original upload remains unchanged.
- Confirm rejected and pending suggestions do not appear in exported text.
- Confirm the app does not require a hosted model, external originality search,
  or remote fonts.
- Keep the API bound to loopback for single-user local mode. Do not expose the
  unauthenticated local instance to a network.

## 5. Record the result

Record OS/version, Python and Node versions, document types tested, any export
notes, and pass/fail for each workflow. A format should be marked accepted only
after inspecting the actual exported file in its target application.

CI success is not a substitute for this checklist. In particular, a generated
PDF is not considered layout-preserving merely because it opens successfully.
