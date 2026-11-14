from types import SimpleNamespace

from backend.app.document_processing.parser import MarkdownParser
from backend.app.export.exporter import _markdown_text


def _export_parsed_markdown(source: str) -> str:
    parsed = MarkdownParser.parse_bytes(source.encode("utf-8"), "sample.md")
    states = [
        SimpleNamespace(
            review_status="unchanged",
            current_text=item.text,
            original_text=item.text,
            paragraph_type=item.paragraph_type,
        )
        for item in parsed.paragraphs
    ]
    return _markdown_text(SimpleNamespace(paragraphs=states, document=parsed))


def test_markdown_export_preserves_fence_language_and_code_content():
    source = "Intro.\n\n```python\nprint('hello')\n\nprint('world')\n```\n"
    exported = _export_parsed_markdown(source)

    assert "```python\n" in exported
    reparsed = MarkdownParser.parse_bytes(exported.encode("utf-8"), "roundtrip.md")
    code = [item for item in reparsed.paragraphs if item.paragraph_type == "code"]
    assert len(code) == 1
    assert code[0].metadata["fence_language"] == "python"
    assert code[0].text == "print('hello')\n\nprint('world')"


def test_markdown_export_uses_longer_fence_when_code_contains_triple_backticks():
    source = (
        "````python\n"
        "message = \"\"\"example\"\"\"\n"
        "```\n"
        "print(message)\n"
        "````\n"
    )
    exported = _export_parsed_markdown(source)

    assert "````python\n" in exported
    reparsed = MarkdownParser.parse_bytes(exported.encode("utf-8"), "roundtrip.md")
    code = [item for item in reparsed.paragraphs if item.paragraph_type == "code"]
    assert len(code) == 1
    assert code[0].text == "message = \"\"\"example\"\"\"\n```\nprint(message)"


def test_markdown_export_preserves_tilde_fence_language():
    source = "~~~sql\nSELECT * FROM papers;\n~~~\n"
    exported = _export_parsed_markdown(source)

    assert "~~~sql\n" in exported
    reparsed = MarkdownParser.parse_bytes(exported.encode("utf-8"), "roundtrip.md")
    assert reparsed.paragraphs[0].metadata["fence_language"] == "sql"
    assert reparsed.paragraphs[0].text == "SELECT * FROM papers;"



def test_markdown_export_preserves_trailing_blank_lines_inside_code():
    source = "```python\nprint('x')\n\n```\n"
    exported = _export_parsed_markdown(source)
    reparsed = MarkdownParser.parse_bytes(exported.encode("utf-8"), "roundtrip.md")

    assert reparsed.paragraphs[0].text == "print('x')\n"


def test_markdown_export_keeps_empty_code_fence():
    source = "```text\n```\n"
    exported = _export_parsed_markdown(source)
    reparsed = MarkdownParser.parse_bytes(exported.encode("utf-8"), "roundtrip.md")

    assert len(reparsed.paragraphs) == 1
    assert reparsed.paragraphs[0].paragraph_type == "code"
    assert reparsed.paragraphs[0].text == ""
