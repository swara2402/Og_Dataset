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


def test_docx_export_notes_identify_accepted_edits_skipped_for_complex_xml():
    from docx.oxml import OxmlElement
    from datetime import datetime, timezone
    from backend.app.core.jobs import Job, ParagraphState
    from backend.app.document_processing.parser import DocumentParser
    from backend.app.export.exporter import export_notes

    document = Document()
    paragraph = document.add_paragraph("A paragraph with a bookmark.")
    bookmark = OxmlElement("w:bookmarkStart")
    bookmark.set("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}id", "7")
    bookmark.set("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}name", "source_anchor")
    paragraph._p.insert(1, bookmark)
    buffer = io.BytesIO()
    document.save(buffer)
    raw = buffer.getvalue()
    parsed = DocumentParser.parse_bytes(raw, "bookmarked.docx")
    item = parsed.paragraphs[0]
    state = ParagraphState(
        id=item.id, index=0, original_text=item.text, paragraph_type="body",
        category="general", section=None, eligible=True, masked_text=item.text,
    )
    state.current_text = "A revised paragraph with a bookmark."
    state.review_status = "accepted"
    job = Job(
        job_id="docx-skip-note-test", filename="bookmarked.docx", file_type="docx",
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        created_at=datetime.now(timezone.utc).isoformat(), style="academic", options={},
        document=parsed, paragraphs=[state], original_bytes=raw,
    )

    notes = export_notes(job, "docx")
    assert any("1 accepted edit(s) were not applied" in note for note in notes)
    assert any(item.id in note and "preserved unchanged" in note for note in notes)
