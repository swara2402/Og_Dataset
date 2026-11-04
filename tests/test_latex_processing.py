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
