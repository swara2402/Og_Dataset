from types import SimpleNamespace

import pytest

from backend.app.document_processing.parser import PDFParser


class FakePdfDocument:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


def test_fitz_document_is_closed_after_successful_extraction(monkeypatch):
    document = FakePdfDocument()
    expected = SimpleNamespace(filename="sample.pdf", file_type="pdf")
    monkeypatch.setattr(
        PDFParser,
        "_extract_paragraphs",
        staticmethod(lambda doc, filename, **options: expected),
    )

    result = PDFParser._parse_fitz_document(
        document, "sample.pdf", enable_ocr=True, ocr_language="eng"
    )

    assert result is expected
    assert document.closed is True


def test_fitz_document_is_closed_when_extraction_raises(monkeypatch):
    document = FakePdfDocument()

    def fail_extraction(doc, filename, **options):
        raise RuntimeError("synthetic extraction failure")

    monkeypatch.setattr(PDFParser, "_extract_paragraphs", staticmethod(fail_extraction))

    with pytest.raises(RuntimeError, match="synthetic extraction failure"):
        PDFParser._parse_fitz_document(document, "sample.pdf")

    assert document.closed is True
