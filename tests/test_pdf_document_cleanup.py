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


def test_parse_bytes_routes_through_cleanup_and_preserves_ocr_options(monkeypatch):
    from backend.app.document_processing import parser as parser_module

    document = FakePdfDocument()
    expected = SimpleNamespace(filename="sample.pdf", file_type="pdf")
    monkeypatch.setattr(
        parser_module, "PYMUPDF_AVAILABLE", True
    )
    monkeypatch.setattr(
        parser_module, "fitz", SimpleNamespace(
            open=lambda **kwargs: document
        )
    )
    received = {}

    def extract(doc, filename, **options):
        received.update(options)
        return expected

    monkeypatch.setattr(PDFParser, "_extract_paragraphs", staticmethod(extract))

    result = PDFParser.parse_bytes(
        b"%PDF-fake", "sample.pdf",
        enable_ocr=True, ocr_language="eng", ocr_dpi=240,
    )

    assert result is expected
    assert document.closed is True
    assert received == {
        "enable_ocr": True, "ocr_language": "eng", "ocr_dpi": 240,
    }


def test_parse_file_routes_through_cleanup(monkeypatch, tmp_path):
    from backend.app.document_processing import parser as parser_module

    document = FakePdfDocument()
    expected = SimpleNamespace(filename="sample.pdf", file_type="pdf")
    monkeypatch.setattr(parser_module, "PYMUPDF_AVAILABLE", True)
    monkeypatch.setattr(
        parser_module, "fitz", SimpleNamespace(
            open=lambda path: document
        )
    )
    monkeypatch.setattr(
        PDFParser, "_extract_paragraphs",
        staticmethod(lambda doc, filename, **options: expected),
    )

    path = tmp_path / "sample.pdf"
    path.write_bytes(b"%PDF-fake")

    result = PDFParser.parse(path, "sample.pdf")

    assert result is expected
    assert document.closed is True
