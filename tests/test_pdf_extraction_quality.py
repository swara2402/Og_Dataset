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


class _FakePDFPage:
    def get_text(self, kind):
        return "" if kind == "text" else []


class _FakePDFDocument:
    def __iter__(self):
        return iter([_FakePDFPage()])


def test_pdf_ocr_is_opt_in_and_records_ocr_page(monkeypatch):
    def fake_ocr(page, *, language, dpi):
        assert language == "eng"
        assert dpi == 240
        return "This scanned page now contains readable OCR text."

    monkeypatch.setattr(PDFParser, "_ocr_page", staticmethod(fake_ocr))
    parsed = PDFParser._extract_paragraphs(
        _FakePDFDocument(), "scan.pdf", enable_ocr=True, ocr_language="eng", ocr_dpi=240
    )

    assert len(parsed.paragraphs) == 1
    assert parsed.paragraphs[0].text == "This scanned page now contains readable OCR text."
    assert parsed.paragraphs[0].metadata["ocr"] is True
    assert parsed.metadata["ocr_enabled"] is True
    assert parsed.metadata["ocr_pages"] == [1]
    assert parsed.metadata["ocr_warning"] is None


def test_pdf_ocr_unavailable_preserves_extraction_and_reports_warning(monkeypatch):
    def unavailable(page, *, language, dpi):
        raise ImportError("OCR dependencies are not installed")

    monkeypatch.setattr(PDFParser, "_ocr_page", staticmethod(unavailable))
    parsed = PDFParser._extract_paragraphs(
        _FakePDFDocument(), "scan.pdf", enable_ocr=True
    )

    assert parsed.paragraphs == []
    assert parsed.metadata["ocr_pages"] == []
    assert parsed.metadata["ocr_unavailable_pages"] == [1]
    assert "OCR dependencies are not installed" in parsed.metadata["ocr_warning"]


def test_pdf_ocr_is_not_attempted_when_disabled(monkeypatch):
    def should_not_run(*args, **kwargs):
        raise AssertionError("OCR must remain disabled by default")

    monkeypatch.setattr(PDFParser, "_ocr_page", staticmethod(should_not_run))
    parsed = PDFParser._extract_paragraphs(_FakePDFDocument(), "scan.pdf")

    assert parsed.metadata["ocr_enabled"] is False
    assert parsed.metadata["ocr_pages"] == []
