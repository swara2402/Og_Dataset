from backend.app.document_processing.parser import PDFParser


class FakePdfPage:
    def __init__(self, text="", blocks=None):
        self.text = text
        self.blocks = blocks or []
        self.text_calls = 0

    def get_text(self, mode):
        if mode == "text":
            self.text_calls += 1
            return self.text
        if mode == "blocks":
            return self.blocks
        raise AssertionError(f"Unexpected extraction mode: {mode}")


class FakePdfDocument:
    def __init__(self, *pages):
        self.pages = pages

    def __iter__(self):
        return iter(self.pages)


def test_ocr_replaces_sparse_page_text_and_uses_cached_original_text(monkeypatch):
    page = FakePdfPage(text="", blocks=[])
    document = FakePdfDocument(page)
    monkeypatch.setattr(
        PDFParser, "_ocr_page",
        staticmethod(lambda page, *, language, dpi: "INTRODUCTION\n\nRecognized academic text."),
    )

    parsed = PDFParser._extract_paragraphs(
        document, "scan.pdf", enable_ocr=True, ocr_language="eng", ocr_dpi=240
    )

    assert [paragraph.text for paragraph in parsed.paragraphs] == [
        "INTRODUCTION", "Recognized academic text."
    ]
    assert all(paragraph.metadata["ocr"] is True for paragraph in parsed.paragraphs)
    assert parsed.metadata["ocr_pages"] == [1]
    assert parsed.metadata["ocr_unavailable_pages"] == []
    assert page.text_calls == 1


def test_unavailable_ocr_keeps_selectable_page_blocks_and_reports_warning(monkeypatch):
    page = FakePdfPage(
        text="short",
        blocks=[(0, 0, 10, 10, "Selectable fallback text", 0, 0)],
    )
    document = FakePdfDocument(page)

    def unavailable(page, *, language, dpi):
        raise ImportError("optional OCR dependencies are missing")

    monkeypatch.setattr(PDFParser, "_ocr_page", staticmethod(unavailable))

    parsed = PDFParser._extract_paragraphs(
        document, "mixed.pdf", enable_ocr=True
    )

    assert [paragraph.text for paragraph in parsed.paragraphs] == [
        "Selectable fallback text"
    ]
    assert parsed.paragraphs[0].metadata["page"] == 1
    assert parsed.metadata["ocr_pages"] == []
    assert parsed.metadata["ocr_unavailable_pages"] == [1]
    assert "optional OCR dependencies are missing" in parsed.metadata["ocr_warning"]
    assert page.text_calls == 1

def test_pypdf_fallback_reports_empty_and_sparse_pages_as_ocr_unavailable(monkeypatch):
    import backend.app.document_processing.parser as parser_module

    class Page:
        def __init__(self, text):
            self.text = text

        def extract_text(self):
            return self.text

    class Reader:
        def __init__(self, _stream):
            self.pages = [Page(""), Page("short"), Page("This page has enough selectable text to skip OCR.")]

    monkeypatch.setattr(parser_module, "PYMUPDF_AVAILABLE", False)
    monkeypatch.setattr(parser_module, "PYPDF_AVAILABLE", True)
    monkeypatch.setattr(parser_module, "PypdfReader", Reader)

    parsed = PDFParser.parse_bytes(b"fake-pdf", "fallback.pdf", enable_ocr=True)

    assert parsed.metadata["ocr_unavailable_pages"] == [1, 2]
    assert parsed.metadata["ocr_warning"] is not None
    assert parsed.metadata["ocr_pages"] == []


def test_pypdf_fallback_does_not_warn_when_no_pages_need_ocr(monkeypatch):
    import backend.app.document_processing.parser as parser_module

    class Page:
        def extract_text(self):
            return "This page has enough selectable text to skip OCR."

    class Reader:
        def __init__(self, _stream):
            self.pages = [Page()]

    monkeypatch.setattr(parser_module, "PYMUPDF_AVAILABLE", False)
    monkeypatch.setattr(parser_module, "PYPDF_AVAILABLE", True)
    monkeypatch.setattr(parser_module, "PypdfReader", Reader)

    parsed = PDFParser.parse_bytes(b"fake-pdf", "text.pdf", enable_ocr=True)

    assert parsed.metadata["ocr_unavailable_pages"] == []
    assert parsed.metadata["ocr_warning"] is None
