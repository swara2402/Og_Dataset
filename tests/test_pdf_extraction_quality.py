from backend.app.document_processing.parser import PDFParser


def test_pdf_quality_metadata_flags_image_only_and_sparse_pages():
    metadata = PDFParser._quality_metadata(
        ["A sufficiently long page of extracted text. " * 3, "", "Short"],
        "pymupdf",
    )

    assert metadata["page_count"] == 3
    assert metadata["extractor"] == "pymupdf"
    assert metadata["pages_with_no_text"] == [2]
    assert metadata["pages_with_little_text"] == [3]
    assert metadata["text_characters"] > 40
    assert any("may be scanned images" in warning for warning in metadata["extraction_warnings"])
    assert any("extraction loss" in warning for warning in metadata["extraction_warnings"])


def test_pdf_quality_metadata_does_not_warn_for_normal_text_pages():
    metadata = PDFParser._quality_metadata(
        ["This page contains enough selectable text for a normal extraction."],
        "pypdf",
    )

    assert metadata["pages_with_no_text"] == []
    assert metadata["pages_with_little_text"] == []
    assert metadata["extraction_warnings"] == []
