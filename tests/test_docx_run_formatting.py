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


def _make_docx_job(document, filename="structure.docx"):
    from datetime import datetime, timezone
    from backend.app.core.jobs import Job, ParagraphState
    from backend.app.document_processing.parser import DocumentParser

    buffer = io.BytesIO()
    document.save(buffer)
    raw = buffer.getvalue()
    parsed = DocumentParser.parse_bytes(raw, filename)
    states = [
        ParagraphState(
            id=item.id, index=index, original_text=item.text,
            paragraph_type=item.paragraph_type, category="general", section=None,
            eligible=True, masked_text=item.text,
        )
        for index, item in enumerate(parsed.paragraphs)
    ]
    job = Job(
        job_id="docx-structure-test", filename=filename, file_type="docx",
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        created_at=datetime.now(timezone.utc).isoformat(), style="academic", options={},
        document=parsed, paragraphs=states, original_bytes=raw,
    )
    return job, states


def test_table_cell_edits_are_exported_and_header_footer_are_preserved():
    from docx import Document
    from backend.app.export.exporter import _docx_bytes

    document = Document()
    document.sections[0].header.paragraphs[0].text = "Original running header"
    document.sections[0].footer.paragraphs[0].text = "Original page footer"
    table = document.add_table(rows=1, cols=1)
    table.cell(0, 0).text = "The table result was recorded ."
    job, states = _make_docx_job(document)

    table_state = next(state for state in states if state.paragraph_type == "table")
    table_state.current_text = "The table result was recorded."
    table_state.review_status = "accepted"

    exported = Document(io.BytesIO(_docx_bytes(job)))
    assert exported.tables[0].cell(0, 0).text == "The table result was recorded."
    assert exported.sections[0].header.paragraphs[0].text == "Original running header"
    assert exported.sections[0].footer.paragraphs[0].text == "Original page footer"


def test_hyperlink_paragraph_is_preserved_and_reported_as_not_rewritten():
    from datetime import datetime, timezone
    from docx import Document
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.opc.constants import RELATIONSHIP_TYPE as RT
    from backend.app.core.jobs import Job, ParagraphState
    from backend.app.document_processing.parser import DocumentParser
    from backend.app.export.exporter import _docx_bytes, export_notes

    document = Document()
    paragraph = document.add_paragraph()
    paragraph.add_run("Read ")
    relationship_id = paragraph.part.relate_to("https://example.org/source", RT.HYPERLINK, is_external=True)
    hyperlink = OxmlElement("w:hyperlink")
    hyperlink.set(qn("r:id"), relationship_id)
    run = OxmlElement("w:r")
    text_node = OxmlElement("w:t")
    text_node.text = "the source"
    run.append(text_node)
    hyperlink.append(run)
    paragraph._p.append(hyperlink)
    paragraph.add_run(" carefully.")
    buffer = io.BytesIO()
    document.save(buffer)
    raw = buffer.getvalue()
    parsed = DocumentParser.parse_bytes(raw, "hyperlink.docx")
    item = parsed.paragraphs[0]
    state = ParagraphState(
        id=item.id, index=0, original_text=item.text, paragraph_type="body",
        category="general", section=None, eligible=True, masked_text=item.text,
    )
    state.current_text = "Read this source carefully."
    state.review_status = "accepted"
    job = Job(
        job_id="docx-hyperlink-test", filename="hyperlink.docx", file_type="docx",
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        created_at=datetime.now(timezone.utc).isoformat(), style="academic", options={},
        document=parsed, paragraphs=[state], original_bytes=raw,
    )

    exported = Document(io.BytesIO(_docx_bytes(job)))
    xml = exported.paragraphs[0]._p.xml
    assert "the source" in xml
    assert exported.part.rels[relationship_id].target_ref == "https://example.org/source"
    assert exported.paragraphs[0].text == item.text
    assert any("1 accepted edit(s) were not applied" in note for note in export_notes(job, "docx"))


def test_nested_table_accepted_edit_is_applied_without_flattening_docx():
    from docx import Document
    from backend.app.export.exporter import _docx_bytes

    document = Document()
    outer = document.add_table(rows=1, cols=1)
    nested = outer.cell(0, 0).add_table(rows=1, cols=1)
    nested.cell(0, 0).text = "The nested result was recorded ."

    job, states = _make_docx_job(document, filename="nested-edit.docx")
    nested_state = next(
        state for state in states
        if state.paragraph_type == "table"
        and state.original_text == "The nested result was recorded ."
    )
    nested_state.current_text = "The nested result was recorded."
    nested_state.review_status = "accepted"

    exported = Document(io.BytesIO(_docx_bytes(job)))
    exported_nested = exported.tables[0].cell(0, 0).tables[0]
    assert exported_nested.cell(0, 0).text == "The nested result was recorded."



def test_editing_text_preserves_embedded_docx_image_and_relationship():
    import base64
    from docx import Document
    from backend.app.export.exporter import _docx_bytes

    # Tiny valid PNG fixture; no external image file or network dependency.
    png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/pZ8AAAAASUVORK5CYII="
    )
    document = Document()
    document.add_paragraph("The experimental result was recorded .")
    image_paragraph = document.add_paragraph()
    image_paragraph.add_run().add_picture(io.BytesIO(png))

    job, states = _make_docx_job(document, filename="image-preservation.docx")
    text_state = next(
        state for state in states
        if state.original_text == "The experimental result was recorded ."
    )
    text_state.current_text = "The experimental result was recorded."
    text_state.review_status = "accepted"

    exported = Document(io.BytesIO(_docx_bytes(job)))
    assert len(exported.inline_shapes) == 1

    image_relationship_id = (
        exported.inline_shapes[0]._inline.graphic.graphicData.pic
        .blipFill.blip.embed
    )
    image_part = exported.part.related_parts[image_relationship_id]
    assert image_part.blob == png
