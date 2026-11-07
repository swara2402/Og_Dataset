"""Export refined documents while preserving source structure where possible."""
from __future__ import annotations

import io
import re
import time
from copy import deepcopy
from difflib import SequenceMatcher

from docx.oxml.ns import qn
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


def _set_paragraph_text(paragraph: DocxParagraph, text: str) -> bool:
    """Apply an accepted text edit while retaining safe paragraph/run formatting.

    Unusual XML children (hyperlinks, fields, drawings, bookmarks, etc.) are
    deliberately left untouched rather than risk corrupting document content.
    """
    original = paragraph.text
    if original == text:
        return True

    children = list(paragraph._p.iterchildren())
    allowed_tags = {qn("w:pPr"), qn("w:r")}
    if any(child.tag not in allowed_tags for child in children):
        return False

    runs = list(paragraph.runs)
    if not runs:
        paragraph.add_run(text)
        return True

    run_text = "".join(run.text for run in runs)
    if run_text != original:
        return False

    char_run_indexes: list[int] = []
    for index, run in enumerate(runs):
        char_run_indexes.extend([index] * len(run.text))

    matcher = SequenceMatcher(a=original, b=text, autojunk=False)
    styled_chars: list[tuple[str, int]] = []
    for operation, old_start, old_end, new_start, new_end in matcher.get_opcodes():
        if operation == "equal":
            for offset, char in enumerate(text[new_start:new_end]):
                styled_chars.append((char, char_run_indexes[old_start + offset]))
        elif operation in {"replace", "insert"}:
            if old_start < len(char_run_indexes):
                source_index = char_run_indexes[old_start]
            elif char_run_indexes:
                source_index = char_run_indexes[-1]
            else:
                source_index = 0
            styled_chars.extend((char, source_index) for char in text[new_start:new_end])

    segments: list[tuple[str, int]] = []
    for char, run_index in styled_chars:
        if segments and segments[-1][1] == run_index:
            segments[-1] = (segments[-1][0] + char, run_index)
        else:
            segments.append((char, run_index))

    formatting = [
        deepcopy(run._r.rPr) if run._r.rPr is not None else None
        for run in runs
    ]
    paragraph.clear()
    for segment, source_index in segments:
        new_run = paragraph.add_run(segment)
        source_format = formatting[source_index]
        if source_format is not None:
            new_run._r.insert(0, deepcopy(source_format))
    return True

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


def _docx_unapplied_edits(job: Job) -> list[str]:
    """Return accepted DOCX edits that cannot safely be applied to the source XML."""
    if job.file_type != "docx" or not job.original_bytes:
        return []
    document = DocxDocument(io.BytesIO(job.original_bytes))
    revised = {state.id: state for state in job.paragraphs}
    found: set[str] = set()
    skipped: list[str] = []
    for item in DocxParser.iter_all_elements(document, job.filename):
        state = revised.get(item.id)
        if state is None or state.review_status != "accepted" or state.current_text == state.original_text:
            continue
        found.add(state.id)
        children = list(item.original_element._p.iterchildren())
        if any(child.tag not in {qn("w:pPr"), qn("w:r")} for child in children):
            skipped.append(state.id)
            continue
        if "".join(run.text for run in item.original_element.runs) != item.original_element.text:
            skipped.append(state.id)
    skipped.extend(
        state.id for state in job.paragraphs
        if state.review_status == "accepted"
        and state.current_text != state.original_text
        and state.id not in found
    )
    return skipped


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
        if not _set_paragraph_text(item.original_element, new_text):
            # Preserve complex XML exactly rather than flattening unsupported content.
            continue
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


def _latex_structure_signature(value: str) -> tuple[str, ...]:
    """Return TeX commands and unescaped structural/special tokens in order."""
    pattern = r"\\(?:[A-Za-z@]+|.)|(?<!\\)[\x7b\x7d]|(?<!\\)[%$&#_^~]"
    return tuple(re.findall(pattern, value))


def _latex_reference_signature(value: str) -> tuple[str, ...]:
    """Keep citation keys, labels, references and resource paths byte-for-byte."""
    pattern = (
        r"\\(?:cite[a-zA-Z]*|ref|eqref|pageref|label|autoref|cref|Cref|"
        r"nameref|hyperref|url|bibliography|addbibresource|begin|end|"
        r"includegraphics|input|include|documentclass|usepackage|"
        r"bibliographystyle|lstinputlisting)\*?"
        r"(?:\[[^\]]*\])*\s*\{[^{}]*\}"
    )
    return tuple(re.findall(pattern, value))

def _latex_text(job: Job) -> str:
    """Splice accepted prose edits into the original TeX source by exact offsets."""
    if job.file_type != "tex" or not job.original_bytes:
        raise ValueError("LaTeX export requires the original .tex source file.")
    source = job.original_bytes.decode("utf-8")
    if len(job.document.paragraphs) != len(job.paragraphs):
        raise ValueError("LaTeX paragraph mapping is incomplete; source was not modified.")

    edits: list[tuple[int, int, str]] = []
    for item, state in zip(job.document.paragraphs, job.paragraphs):
        if state.review_status != "accepted" or state.current_text == state.original_text:
            continue
        start = item.metadata.get("source_start")
        end = item.metadata.get("source_end")
        if not isinstance(start, int) or not isinstance(end, int) or not (0 <= start <= end <= len(source)):
            raise ValueError("LaTeX source offsets are invalid; source was not modified.")
        if source[start:end] != state.original_text:
            raise ValueError("LaTeX source no longer matches parsed paragraph offsets.")
        if state.paragraph_type != "body":
            raise ValueError("Only prose blocks can be exported as LaTeX edits.")
        if (
            _latex_structure_signature(state.original_text) != _latex_structure_signature(state.current_text)
            or _latex_reference_signature(state.original_text) != _latex_reference_signature(state.current_text)
        ):
            raise ValueError(
                "LaTeX edit changes commands, references or special syntax; source was not modified."
            )
        edits.append((start, end, state.current_text))

    ordered_edits = sorted(edits)
    if any(current[0] < previous[1] for previous, current in zip(ordered_edits, ordered_edits[1:])):
        raise ValueError("LaTeX edit offsets overlap; source was not modified.")

    for start, end, replacement in reversed(ordered_edits):
        source = source[:start] + replacement + source[end:]
    return source


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
    # Include the opaque job ID so concurrent users exporting same-named files
    # cannot overwrite one another in the shared export directory.
    job_suffix = re.sub(r"[^A-Za-z0-9_-]+", "_", job.job_id)[:64] or "job"
    output = Path(output_dir) / f"{stem}_revised_{timestamp}_{job_suffix}.{fmt}"
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
    elif fmt == "tex":
        data = _latex_text(job).encode("utf-8")
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
            "DOCX export preserves paragraph styles and supported run-level formatting. "
            "Paragraphs containing hyperlinks, fields, drawings, bookmarks or other "
            "complex inline XML are preserved unchanged rather than rewritten."
        )
        if not job.original_bytes:
            notes.append("Original DOCX is unavailable; a plain DOCX was generated instead.")
        else:
            skipped = _docx_unapplied_edits(job)
            if skipped:
                preview = ", ".join(skipped[:12])
                remainder = f" (+{len(skipped) - 12} more)" if len(skipped) > 12 else ""
                notes.append(
                    f"WARNING: {len(skipped)} accepted edit(s) were not applied because their "
                    f"paragraph XML contains unsupported inline content: {preview}{remainder}. "
                    "Those source paragraphs were preserved unchanged; review them manually."
                )
    if fmt.lstrip(".").lower() == "tex":
        notes.append(
            "LaTeX export splices accepted prose edits into the original source by exact offsets. "
            "Commands, citations, math, code environments, headings and bibliography blocks are preserved."
        )
    if fmt.lstrip(".").lower() == "pdf":
        notes.append(
            "PDF export is a simple text-preserving render. Use DOCX for the highest "
            "structural fidelity."
        )
    return notes