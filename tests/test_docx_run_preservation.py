from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

from backend.app.export.exporter import _set_paragraph_text


def test_docx_edit_preserves_mixed_run_formatting():
    document = Document()
    paragraph = document.add_paragraph()
    bold_run = paragraph.add_run("Important")
    bold_run.bold = True
    paragraph.add_run(" ordinary wording")

    assert _set_paragraph_text(paragraph, "Important revised wording") is True

    assert paragraph.text == "Important revised wording"
    assert len(paragraph.runs) >= 2
    assert paragraph.runs[0].text == "Important"
    assert paragraph.runs[0].bold is True
    assert "".join(run.text for run in paragraph.runs) == paragraph.text


def test_docx_edit_keeps_paragraph_style_and_run_formatting():
    document = Document()
    paragraph = document.add_paragraph(style="Heading 2")
    run = paragraph.add_run("Original heading")
    run.italic = True

    assert _set_paragraph_text(paragraph, "Revised heading") is True

    assert paragraph.style.name == "Heading 2"
    assert paragraph.text == "Revised heading"
    assert paragraph.runs[0].italic is True


def test_docx_edit_fails_closed_for_hyperlink_xml():
    document = Document()
    paragraph = document.add_paragraph("Keep this ")
    hyperlink = OxmlElement("w:hyperlink")
    hyperlink.set(qn("r:id"), "rId999")
    run = OxmlElement("w:r")
    text = OxmlElement("w:t")
    text.text = "linked text"
    run.append(text)
    hyperlink.append(run)
    paragraph._p.append(hyperlink)
    original_xml = paragraph._p.xml

    assert _set_paragraph_text(paragraph, "Replace all text") is False

    assert paragraph._p.xml == original_xml

def test_docx_edit_fails_closed_for_non_text_content_inside_run():
    document = Document()
    paragraph = document.add_paragraph()
    run = paragraph.add_run("Keep this text")
    drawing = OxmlElement("w:drawing")
    run._r.append(drawing)
    original_xml = paragraph._p.xml

    assert _set_paragraph_text(paragraph, "Replace all text") is False
    assert paragraph._p.xml == original_xml


def test_docx_edit_fails_closed_for_tabs_and_line_breaks_inside_run():
    for tag in ("w:tab", "w:br"):
        document = Document()
        paragraph = document.add_paragraph()
        run = paragraph.add_run("Before")
        run._r.append(OxmlElement(tag))
        run.add_text("After")
        original_xml = paragraph._p.xml

        assert _set_paragraph_text(paragraph, "Replace all text") is False
        assert paragraph._p.xml == original_xml
