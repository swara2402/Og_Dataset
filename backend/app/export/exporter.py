"""Export refined documents while preserving source structure where possible."""
from __future__ import annotations

import io
import re
from difflib import SequenceMatcher
import time
from pathlib import Path
from typing import List

from docx import Document as DocxDocument
from docx.text.paragraph import Paragraph as DocxParagraph

from backend.app.core.jobs import Job, ParagraphState
from backend.app.document_processing.parser import DocxParser

try:
    import fitz  # PyMuPDF
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False

try:
    from reportlab.lib.pagesizes import LETTER
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False


def _safe_stem(filename: str) -> str:
    stem = Path(filename).stem or "document"
    return re.sub(r"[^A-Za-z0-9._-]+", "_", stem)[:80]


def _export_text(state: ParagraphState) -> str:
    if state.review_status == "accepted":
        return state.current_text
    return state.original_text


def _set_paragraph_text(paragraph: DocxParagraph, text: str) -> None:
    """Replace paragraph text while retaining inline formatting where text survives.

    Characters that are inserted or substituted inherit the formatting of the
    nearest preceding source character (or the next character at paragraph
    start). If a rewrite reorders formatting runs, fall back safely rather
    than emitting text in the wrong order.
    """
    runs = paragraph.runs
    if not runs:
        paragraph.add_run(text)
        return

    original = "".join(run.text for run in runs)
    if original == text:
        return

    # Run text containing tabs or line breaks has special OOXML semantics;
    # leave that uncommon case on the conservative legacy path.
    if any("\t" in run.text or "\n" in run.text or "\r" in run.text for run in runs):
        runs[0].text = text
        for run in runs[1:]:
            run.text = ""
        return

    char_runs: list[int] = []
    for index, run in enumerate(runs):
        char_runs.extend([index] * len(run.text))

    matcher = SequenceMatcher(a=original, b=text, autojunk=False)
    assigned: list[int] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            assigned.extend(char_runs[i1:i2])
        elif tag in {"replace", "insert"}:
            if i1 > 0:
                style_index = char_runs[i1 - 1]
            elif i2 > i1:
                style_index = char_runs[i1]
            elif char_runs:
                style_index = char_runs[0]
            else:
                style_index = 0
            assigned.extend([style_index] * (j2 - j1))
        # Deleted source characters intentionally contribute no output.

    if len(assigned) != len(text) or any(
        left > right for left, right in zip(assigned, assigned[1:])
    ):
        runs[0].text = text
        for run in runs[1:]:
            run.text = ""
        return

    buckets = [ [] for _ in runs ]
    for character, run_index in zip(text, assigned):
        buckets[run_index].append(character)
    for run, characters in zip(runs, buckets):
        run.text = "".join(characters)


def _docx_from_states(job: Job) -> bytes:
    """Build a clean DOCX when the original format cannot be edited in place."""
    document = DocxDocument()
    for state in job.paragraphs:
        text = _export_text(state).strip()
        if not text:
            continue
        if state.paragraph_type == "heading":
            document.add_heading(text, level=2)
        else:
            document.add_paragraph(text)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def _docx_bytes(job: Job) -> bytes:
    if job.file_type != "docx" or not job.original_bytes:
        return _docx_from_states(job)
    document = DocxDocument(io.BytesIO(job.original_bytes))
    revised = {state.id: _export_text(state) for state in job.paragraphs}
    extracted = DocxParser.iter_all_elements(document, job.filename)
    for item in extracted:
        new_text = revised.get(item.id)
        if new_text is None or item.original_element is None:
            continue
        if getattr(item, "paragraph_type", "") == "empty":
            continue
        _set_paragraph_text(item.original_element, new_text)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def _plain_text(job: Job) -> str:
    parts: List[str] = []
    for state in job.paragraphs:
        text = _export_text(state).strip()
        if not text:
            continue
        if state.paragraph_type == "heading":
            parts.append(text.upper() if text.isupper() else text)
        else:
            parts.append(text)
    return "\n\n".join(parts) + "\n"


def _markdown_text(job: Job) -> str:
    parts: List[str] = []
    for state in job.paragraphs:
        text = _export_text(state).strip()
        if not text:
            continue
        if state.paragraph_type == "heading":
            if not text.startswith("#"):
                parts.append(f"## {text}")
            else:
                parts.append(text)
        elif state.paragraph_type == "code":
            parts.append(f"```\n{text}\n```")
        elif state.paragraph_type == "reference":
            parts.append(f"- {text}")
        else:
            parts.append(text)
    return "\n\n".join(parts) + "\n"


def _pdf_bytes(job: Job) -> bytes:
    if not REPORTLAB_AVAILABLE:
        raise ValueError("PDF export requires reportlab to be installed.")
    buffer = io.BytesIO()
    style_sheet = getSampleStyleSheet()
    story = []
    for state in job.paragraphs:
        text = _export_text(state).strip()
        if not text:
            continue
        safe = (
            text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )
        if state.paragraph_type == "heading":
            story.append(Paragraph(safe, style_sheet["Heading2"]))
        else:
            story.append(Paragraph(safe, style_sheet["BodyText"]))
        story.append(Spacer(1, 6))
    document = SimpleDocTemplate(
        buffer,
        pagesize=LETTER,
        leftMargin=0.9 * inch,
        rightMargin=0.9 * inch,
        topMargin=0.9 * inch,
        bottomMargin=0.9 * inch,
    )
    document.build(story)
    return buffer.getvalue()


def export_document(job: Job, fmt: str, output_dir: str) -> Path:
    fmt = fmt.lower().lstrip(".")
    stem = _safe_stem(job.filename)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    output = Path(output_dir) / f"{stem}_revised_{timestamp}.{fmt}"
    output.parent.mkdir(parents=True, exist_ok=True)

    if fmt == "docx":
        data = _docx_bytes(job)
    elif fmt in {"txt", "text"}:
        data = _plain_text(job).encode("utf-8")
        output = output.with_suffix(".txt")
    elif fmt in {"md", "markdown"}:
        data = _markdown_text(job).encode("utf-8")
        output = output.with_suffix(".md")
    elif fmt == "pdf":
        data = _pdf_bytes(job)
    else:
        raise ValueError(f"Unsupported export format: {fmt}")

    output.write_bytes(data)
    return output


def export_notes(job: Job, fmt: str) -> List[str]:
    notes: List[str] = [
        "Only accepted changes are included in the export; pending or rejected "
        "suggestions retain their original text."
    ]
    if fmt.lstrip(".").lower() == "docx":
        notes.append(
            "DOCX export preserves paragraphs, headings, tables and paragraph styles. "
            "Inline character formatting beyond the first run, complex hyperlinks and "
            "floating objects may be simplified."
        )
        if not job.original_bytes:
            notes.append("Original DOCX is unavailable; a plain DOCX was generated instead.")
    if fmt.lstrip(".").lower() == "pdf":
        notes.append(
            "PDF export is a simple text-preserving render. Use DOCX for the highest "
            "structural fidelity."
        )
    return notes