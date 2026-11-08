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



def test_editing_safe_paragraph_preserves_docx_comments_package_part():
    import zipfile
    from datetime import datetime, timezone
    from xml.etree import ElementTree as ET
    from docx import Document
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from backend.app.core.jobs import Job, ParagraphState
    from backend.app.document_processing.parser import DocumentParser
    from backend.app.export.exporter import _docx_bytes

    document = Document()
    document.add_paragraph("The primary result was recorded .")
    commented = document.add_paragraph("This sentence has an editorial comment.")
    start = OxmlElement("w:commentRangeStart")
    start.set(qn("w:id"), "0")
    end = OxmlElement("w:commentRangeEnd")
    end.set(qn("w:id"), "0")
    reference_run = OxmlElement("w:r")
    reference = OxmlElement("w:commentReference")
    reference.set(qn("w:id"), "0")
    reference_run.append(reference)
    commented._p.insert(1, start)
    commented._p.append(end)
    commented._p.append(reference_run)

    initial = io.BytesIO()
    document.save(initial)
    source = initial.getvalue()
    source_buffer = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(source), "r") as original, zipfile.ZipFile(source_buffer, "w") as patched:
        for item in original.infolist():
            data = original.read(item.filename)
            if item.filename == "word/_rels/document.xml.rels":
                root = ET.fromstring(data)
                ET.SubElement(root, "{http://schemas.openxmlformats.org/package/2006/relationships}Relationship", {
                    "Id": "rIdCommentsTest",
                    "Type": "http://schemas.openxmlformats.org/officeDocument/2006/relationships/comments",
                    "Target": "comments.xml",
                })
                data = ET.tostring(root, encoding="utf-8", xml_declaration=True)
            elif item.filename == "[Content_Types].xml":
                root = ET.fromstring(data)
                ET.SubElement(root, "{http://schemas.openxmlformats.org/package/2006/content-types}Override", {
                    "PartName": "/word/comments.xml",
                    "ContentType": "application/vnd.openxmlformats-officedocument.wordprocessingml.comments+xml",
                })
                data = ET.tostring(root, encoding="utf-8", xml_declaration=True)
            patched.writestr(item, data)
        patched.writestr(
            "word/comments.xml",
            b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            b'<w:comments xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            b'<w:comment w:id="0" w:author="Reviewer"><w:p><w:r><w:t>Check this claim.</w:t></w:r></w:p></w:comment>'
            b'</w:comments>',
        )

    raw = source_buffer.getvalue()
    parsed = DocumentParser.parse_bytes(raw, "comments.docx")
    states = [
        ParagraphState(
            id=item.id, index=index, original_text=item.text,
            paragraph_type=item.paragraph_type, category="general", section=None,
            eligible=True, masked_text=item.text,
        )
        for index, item in enumerate(parsed.paragraphs)
    ]
    edited = next(state for state in states if state.original_text == "The primary result was recorded .")
    edited.current_text = "The primary result was recorded."
    edited.review_status = "accepted"
    job = Job(
        job_id="docx-comments-preservation-test", filename="comments.docx", file_type="docx",
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        created_at=datetime.now(timezone.utc).isoformat(), style="academic", options={},
        document=parsed, paragraphs=states, original_bytes=raw,
    )

    exported_bytes = _docx_bytes(job)
    with zipfile.ZipFile(io.BytesIO(exported_bytes), "r") as exported:
        assert "word/comments.xml" in exported.namelist()
        comments = exported.read("word/comments.xml")
        assert b"Check this claim." in comments
        relationships = ET.fromstring(exported.read("word/_rels/document.xml.rels"))
        assert any(
            relation.attrib.get("Type", "").endswith("/comments")
            and relation.attrib.get("Target") == "comments.xml"
            for relation in relationships
        )
        main_document = exported.read("word/document.xml")
        assert b"commentRangeStart" in main_document
        assert b"commentRangeEnd" in main_document
        assert b"commentReference" in main_document




def test_editing_safe_paragraph_preserves_docx_footnotes_package_part():
    import zipfile
    from datetime import datetime, timezone
    from xml.etree import ElementTree as ET
    from docx import Document
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from backend.app.core.jobs import Job, ParagraphState
    from backend.app.document_processing.parser import DocumentParser
    from backend.app.export.exporter import _docx_bytes

    document = Document()
    document.add_paragraph("The primary result was recorded .")
    footnoted = document.add_paragraph("This statement has a footnote")
    reference_run = OxmlElement("w:r")
    reference = OxmlElement("w:footnoteReference")
    reference.set(qn("w:id"), "1")
    reference_run.append(reference)
    footnoted._p.append(reference_run)

    initial = io.BytesIO()
    document.save(initial)
    source = initial.getvalue()
    source_buffer = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(source), "r") as original, zipfile.ZipFile(source_buffer, "w") as patched:
        for item in original.infolist():
            data = original.read(item.filename)
            if item.filename == "word/_rels/document.xml.rels":
                root = ET.fromstring(data)
                ET.SubElement(root, "{http://schemas.openxmlformats.org/package/2006/relationships}Relationship", {
                    "Id": "rIdFootnotesTest",
                    "Type": "http://schemas.openxmlformats.org/officeDocument/2006/relationships/footnotes",
                    "Target": "footnotes.xml",
                })
                data = ET.tostring(root, encoding="utf-8", xml_declaration=True)
            elif item.filename == "[Content_Types].xml":
                root = ET.fromstring(data)
                ET.SubElement(root, "{http://schemas.openxmlformats.org/package/2006/content-types}Override", {
                    "PartName": "/word/footnotes.xml",
                    "ContentType": "application/vnd.openxmlformats-officedocument.wordprocessingml.footnotes+xml",
                })
                data = ET.tostring(root, encoding="utf-8", xml_declaration=True)
            patched.writestr(item, data)
        patched.writestr(
            "word/footnotes.xml",
            b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            b'<w:footnotes xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            b'<w:footnote w:type="separator" w:id="-1"><w:p><w:r><w:separator/></w:r></w:p></w:footnote>'
            b'<w:footnote w:type="continuationSeparator" w:id="0"><w:p><w:r><w:continuationSeparator/></w:r></w:p></w:footnote>'
            b'<w:footnote w:id="1"><w:p><w:r><w:t>Supporting source note.</w:t></w:r></w:p></w:footnote>'
            b'</w:footnotes>',
        )

    raw = source_buffer.getvalue()
    parsed = DocumentParser.parse_bytes(raw, "footnotes.docx")
    states = [
        ParagraphState(
            id=item.id, index=index, original_text=item.text,
            paragraph_type=item.paragraph_type, category="general", section=None,
            eligible=True, masked_text=item.text,
        )
        for index, item in enumerate(parsed.paragraphs)
    ]
    edited = next(state for state in states if state.original_text == "The primary result was recorded .")
    edited.current_text = "The primary result was recorded."
    edited.review_status = "accepted"
    job = Job(
        job_id="docx-footnotes-preservation-test", filename="footnotes.docx", file_type="docx",
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        created_at=datetime.now(timezone.utc).isoformat(), style="academic", options={},
        document=parsed, paragraphs=states, original_bytes=raw,
    )

    with zipfile.ZipFile(io.BytesIO(_docx_bytes(job)), "r") as exported:
        assert "word/footnotes.xml" in exported.namelist()
        footnotes = exported.read("word/footnotes.xml")
        assert b"Supporting source note." in footnotes
        relationships = ET.fromstring(exported.read("word/_rels/document.xml.rels"))
        assert any(
            relation.attrib.get("Type", "").endswith("/footnotes")
            and relation.attrib.get("Target") == "footnotes.xml"
            for relation in relationships
        )
        assert b"footnoteReference" in exported.read("word/document.xml")



def test_editing_safe_paragraph_preserves_tracked_changes_markup():
    import zipfile
    from docx import Document
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from backend.app.export.exporter import _docx_bytes

    document = Document()
    document.add_paragraph("The primary result was recorded .")
    tracked = document.add_paragraph()
    insertion = OxmlElement("w:ins")
    insertion.set(qn("w:id"), "21")
    insertion.set(qn("w:author"), "Reviewer")
    inserted_run = OxmlElement("w:r")
    inserted_text = OxmlElement("w:t")
    inserted_text.text = " newly inserted wording"
    inserted_run.append(inserted_text)
    insertion.append(inserted_run)
    deletion = OxmlElement("w:del")
    deletion.set(qn("w:id"), "22")
    deletion.set(qn("w:author"), "Reviewer")
    deleted_run = OxmlElement("w:r")
    deleted_text = OxmlElement("w:delText")
    deleted_text.text = "removed wording"
    deleted_run.append(deleted_text)
    deletion.append(deleted_run)
    tracked._p.append(insertion)
    tracked._p.append(deletion)

    job, states = _make_docx_job(document, filename="tracked-changes.docx")
    edited = next(state for state in states if state.original_text == "The primary result was recorded .")
    edited.current_text = "The primary result was recorded."
    edited.review_status = "accepted"

    with zipfile.ZipFile(io.BytesIO(_docx_bytes(job)), "r") as exported:
        xml = exported.read("word/document.xml")
    assert b"<w:ins" in xml
    assert b"<w:del" in xml
    assert b"newly inserted wording" in xml
    assert b"removed wording" in xml
    assert b'w:id="21"' in xml
    assert b'w:id="22"' in xml


def test_editing_safe_paragraph_preserves_docx_content_control():
    import zipfile
    from docx import Document
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from backend.app.export.exporter import _docx_bytes

    document = Document()
    document.add_paragraph("The primary result was recorded .")
    controlled = document.add_paragraph()
    sdt = OxmlElement("w:sdt")
    properties = OxmlElement("w:sdtPr")
    tag = OxmlElement("w:tag")
    tag.set(qn("w:val"), "reviewer-note")
    properties.append(tag)
    content = OxmlElement("w:sdtContent")
    run = OxmlElement("w:r")
    text_node = OxmlElement("w:t")
    text_node.text = "Content controlled by the source document"
    run.append(text_node)
    content.append(run)
    sdt.append(properties)
    sdt.append(content)
    controlled._p.append(sdt)

    job, states = _make_docx_job(document, filename="content-control.docx")
    edited = next(state for state in states if state.original_text == "The primary result was recorded .")
    edited.current_text = "The primary result was recorded."
    edited.review_status = "accepted"

    with zipfile.ZipFile(io.BytesIO(_docx_bytes(job)), "r") as exported:
        xml = exported.read("word/document.xml")
    assert b"<w:sdt>" in xml
    assert b"<w:sdtPr>" in xml
    assert b"<w:tag" in xml
    assert b'reviewer-note' in xml
    assert b"<w:sdtContent>" in xml
    assert b"Content controlled by the source document" in xml
