import io

from docx import Document

from backend.app.document_processing.parser import DocumentParser


def test_docx_nested_tables_are_extracted_and_vertical_merge_is_not_duplicated():
    document = Document()
    table = document.add_table(rows=2, cols=2)

    merged = table.cell(0, 0).merge(table.cell(1, 0))
    merged.text = "Merged cell content"

    nested = merged.add_table(rows=1, cols=1)
    nested.cell(0, 0).text = "Nested table content"
    table.cell(0, 1).text = "Adjacent cell content"
    table.cell(1, 1).text = "Second row content"

    buffer = io.BytesIO()
    document.save(buffer)

    parsed = DocumentParser.parse_bytes(buffer.getvalue(), "nested.docx")
    extracted_text = [item.text for item in parsed.paragraphs]

    assert extracted_text.count("Merged cell content") == 1
    assert extracted_text.count("Nested table content") == 1
    assert "Adjacent cell content" in extracted_text
    assert "Second row content" in extracted_text
