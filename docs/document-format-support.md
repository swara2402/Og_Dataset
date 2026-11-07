# Document format support and fidelity

This project uses deterministic local parsing and export. “Supported” means the format can be ingested and exported; it does not mean every layout feature round-trips losslessly.

## Current behavior

| Format | Import | Export | Fidelity and safety behavior |
|---|---|---|---|
| DOCX | Yes | Yes | The original DOCX package is reopened for export. Paragraph styles and supported run formatting are retained. Body paragraphs and table-cell paragraphs are extracted in document order. Paragraphs with complex inline XML (for example hyperlinks, fields, drawings or bookmarks) are left unchanged when a rewrite would be unsafe; export notes identify skipped accepted edits. Headers, footers and other unparsed package parts remain in the original package. |
| PDF | Yes | Yes | Import extracts readable text and paragraph order. It does not preserve complex columns, page layout, embedded tables or image-only content without optional local OCR. Export creates a new, simple text-based PDF; it is not a visual reconstruction of the source PDF. The built-in PDF fonts do not cover every Unicode script; unsupported characters produce a clear export error rather than a malformed file. Use DOCX or TXT when the selected PDF font cannot encode the document's characters. |
| LaTeX (.tex) | Yes | Yes | Import retains exact source offsets. Export splices only accepted body-paragraph edits into the original source. Edits that change TeX commands, braces, or unescaped special syntax are rejected, as are invalid or overlapping offsets. Structural blocks, equations, code and bibliography content are not eligible for prose rewriting. |
| TXT | Yes | Yes | UTF-8 text is imported and exported as paragraphs separated by blank lines. Original whitespace layout is not guaranteed to round-trip. |
| Markdown | Yes | Yes | Markdown is imported as text blocks and exported with basic heading, code-block and reference formatting. Fenced code blocks and contiguous four-space/tab-indented code blocks (including internal blank lines) are protected from prose edits. This is a conservative subset, not a complete CommonMark parser; arbitrary Markdown extensions and exact source formatting are not guaranteed to round-trip. |

## Review and preservation rules

- Only accepted edits are included in exports. Pending and rejected suggestions retain original text.
- The original source file is retained with the local job so format-aware exports can preserve source structure.
- If an export cannot safely apply an accepted edit, it must preserve the source content and report the skipped edit rather than silently flatten or damage it.
- PDF extraction warnings are surfaced because extracted text may omit layout and image-only content.
- LaTeX export fails closed when offsets or syntax checks do not match the original source.
- OCR and spaCy are optional local features. Neither is downloaded or enabled implicitly.

## Remaining acceptance work

Automated tests and CI are necessary but not sufficient for release. Before calling document fidelity complete, run a manual fixture set containing:
- DOCX with headings, mixed run formatting, tables, hyperlinks, fields, headers and footers.
- Born-digital and scanned PDFs, including columns, tables and equations.
- LaTeX with citations, inline math, escaped special characters, macros and protected environments.
- TXT and Markdown with Unicode, blank lines, lists, code fences and long paragraphs.

For each fixture, compare extracted text, inspect the exported file in its target application, and verify that skipped or rejected edits are clearly reported. Keep the original fixture unchanged for byte-level comparison where applicable.
