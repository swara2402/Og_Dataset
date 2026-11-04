from datetime import datetime, timezone

from backend.app.core.jobs import Job, ParagraphState
from backend.app.document_processing.parser import DocumentParser
from backend.app.export.exporter import export_document


def test_latex_ingestion_and_export_preserve_commands_math_and_source_layout(tmp_path):
    source = (
        "\\documentclass{article}\n"
        "\\begin{document}\n\n"
        "\\section{Introduction}\n\n"
        "The the model was evaluated \\cite{smith2023}.\n\n"
        "\\begin{equation}\nE = mc^2\n\\end{equation}\n\n"
        "\\end{document}\n"
    )
    raw = source.encode("utf-8")
    parsed = DocumentParser.parse_bytes(raw, "paper.tex")
    assert parsed.file_type == "tex"
    body = next(item for item in parsed.paragraphs if item.paragraph_type == "body")
    equation = next(item for item in parsed.paragraphs if item.paragraph_type == "equation")
    assert "\\cite{smith2023}" in body.text
    assert "E = mc^2" in equation.text

    states = [
        ParagraphState(
            id=item.id,
            index=index,
            original_text=item.text,
            paragraph_type=item.paragraph_type,
            category=item.paragraph_type,
            section=None,
            eligible=item.paragraph_type == "body",
            masked_text=item.text,
        )
        for index, item in enumerate(parsed.paragraphs)
    ]
    body_state = next(state for state in states if state.id == body.id)
    body_state.current_text = body_state.original_text.replace("The the ", "The ")
    body_state.review_status = "accepted"
    job = Job(
        job_id="latex-export-test",
        filename="paper.tex",
        file_type="tex",
        content_type="application/x-tex",
        created_at=datetime.now(timezone.utc).isoformat(),
        style="academic",
        options={},
        document=parsed,
        paragraphs=states,
        original_bytes=raw,
    )

    output = export_document(job, "tex", str(tmp_path))
    revised = output.read_text(encoding="utf-8")
    assert "\\documentclass{article}" in revised
    assert "\\section{Introduction}" in revised
    assert "The model was evaluated \\cite{smith2023}." in revised
    assert "\\begin{equation}\nE = mc^2\n\\end{equation}" in revised
    assert "\\end{document}" in revised
    assert "The the model" not in revised


def test_latex_parser_preserves_utf8_bom_and_exact_source_offsets():
    source = "\ufeff\\documentclass{article}\n\\begin{document}\n\nCafé naïve text.\n\n\\end{document}\n"
    parsed = DocumentParser.parse_bytes(source.encode("utf-8"), "unicode.tex")
    body = next(item for item in parsed.paragraphs if item.paragraph_type == "body")
    start = body.metadata["source_start"]
    end = body.metadata["source_end"]
    assert source[start:end] == body.text
    assert body.text == "Café naïve text."
    assert parsed.metadata["source_length"] == len(source)


def test_latex_parser_protects_inline_math_links_and_comments():
    source = (
        "\\documentclass{article}\n"
        "\\begin{document}\n\n"
        "The value is $x^2 + y^2$ in this model.\n\n"
        "The linked source is \\href{https://example.com}{available here}.\n\n"
        "% Keep this author note unchanged.\n\n"
        "\\begin{align}\na &= b + c \\\\\nd &= e + f\n\\end{align}\n\n"
        "\\end{document}\n"
    )
    parsed = DocumentParser.parse_bytes(source.encode("utf-8"), "protected.tex")
    assert next(item for item in parsed.paragraphs if "$x^2" in item.text).paragraph_type == "equation"
    assert next(item for item in parsed.paragraphs if "\\href" in item.text).paragraph_type == "code"
    assert next(item for item in parsed.paragraphs if item.text.startswith("%")).paragraph_type == "code"
    assert next(item for item in parsed.paragraphs if "\\begin{align}" in item.text).paragraph_type == "equation"


def test_latex_export_refuses_invalid_or_non_body_source_edits(tmp_path):
    source = "\\documentclass{article}\n\\begin{document}\n\n\\section{Title}\n\nBody text.\n\n\\end{document}\n"
    parsed = DocumentParser.parse_bytes(source.encode("utf-8"), "guard.tex")
    states = [
        ParagraphState(
            id=item.id,
            index=index,
            original_text=item.text,
            paragraph_type=item.paragraph_type,
            category=item.paragraph_type,
            section=None,
            eligible=item.paragraph_type == "body",
            masked_text=item.text,
        )
        for index, item in enumerate(parsed.paragraphs)
    ]
    heading_state = next(state for state in states if state.paragraph_type == "heading")
    heading_state.current_text = "Changed heading"
    heading_state.review_status = "accepted"
    job = Job(
        job_id="latex-guard-test",
        filename="guard.tex",
        file_type="tex",
        content_type="application/x-tex",
        created_at=datetime.now(timezone.utc).isoformat(),
        style="academic",
        options={},
        document=parsed,
        paragraphs=states,
        original_bytes=source.encode("utf-8"),
    )
    import pytest
    with pytest.raises(ValueError, match="Only prose blocks"):
        export_document(job, "tex", str(tmp_path))



def test_latex_parser_protects_layout_graphics_and_inline_code_environments():
    source = (
        "\\documentclass{article}\n"
        "\\begin{document}\n\n"
        "A normal paragraph remains editable.\n\n"
        "\\begin{figure}\n\\includegraphics{plot.pdf}\n\n"
        "\\caption{A result}\n\\end{figure}\n\n"
        "\\begin{tabular}{cc}\na & b\nc & d\n\\end{tabular}\n\n"
        "Inline source: \\verb|x = y| should remain protected.\n\n"
        "\\end{document}\n"
    )
    parsed = DocumentParser.parse_bytes(source.encode("utf-8"), "layout.tex")
    normal = next(item for item in parsed.paragraphs if "normal paragraph" in item.text)
    figure_blocks = [
        item for item in parsed.paragraphs
        if item.text.startswith("\\begin{figure}") or "\\caption{A result}" in item.text
    ]
    table = next(item for item in parsed.paragraphs if "\\begin{tabular}" in item.text)
    inline = next(item for item in parsed.paragraphs if "\\verb" in item.text)

    assert normal.paragraph_type == "body"
    assert figure_blocks and all(item.paragraph_type == "code" for item in figure_blocks)
    assert table.paragraph_type == "code"
    assert inline.paragraph_type == "code"
