import io

from docx import Document

from backend.app.export.exporter import _set_paragraph_text


def test_accepted_edit_preserves_supported_run_character_formatting():
    document = Document()
    paragraph = document.add_paragraph()
    first = paragraph.add_run("The ")
    first.bold = True
    second = paragraph.add_run("the model")
    second.italic = True
    paragraph.add_run(" was evaluated.")

    assert _set_paragraph_text(paragraph, "The model was evaluated.") is True

    assert paragraph.text == "The model was evaluated."
    assert paragraph.runs[0].bold is True
    assert paragraph.runs[1].italic is True
    assert paragraph.runs[2].bold is not True
    assert paragraph.runs[2].italic is not True

    buffer = io.BytesIO()
    document.save(buffer)
    buffer.seek(0)
    restored = Document(buffer)
    assert restored.paragraphs[0].text == "The model was evaluated."
    assert restored.paragraphs[0].runs[0].bold is True
    assert restored.paragraphs[0].runs[1].italic is True
