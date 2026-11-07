from backend.app.document_processing.parser import MarkdownParser


def test_backtick_fence_keeps_blank_line_content_inside_protected_code():
    source = (
        "Introductory prose.\n\n"
        "```python\n"
        "def calculate():\n"
        "    return 1\n\n"
        "print(calculate())\n"
        "```\n\n"
        "Later prose remains editable."
    )

    parsed = MarkdownParser.parse_bytes(source.encode("utf-8"), "sample.md")

    code = [item for item in parsed.paragraphs if item.paragraph_type == "code"]
    prose = [item for item in parsed.paragraphs if "prose" in item.text]

    assert len(code) == 1
    assert code[0].text == "def calculate():\n    return 1\n\nprint(calculate())"
    assert code[0].metadata["fence_language"] == "python"
    assert code[0].metadata["closed_fence"] is True
    assert len(prose) == 2
    assert all(item.paragraph_type == "body" for item in prose)


def test_tilde_fence_keeps_blank_lines_and_closing_fence():
    source = (
        "~~~sql\n"
        "SELECT *\n\n"
        "FROM papers;\n"
        "~~~\n\n"
        "Editable explanation."
    )

    parsed = MarkdownParser.parse_bytes(source.encode("utf-8"), "sample.md")

    code = [item for item in parsed.paragraphs if item.paragraph_type == "code"]
    assert len(code) == 1
    assert code[0].text == "SELECT *\n\nFROM papers;"
    assert code[0].metadata["fence_language"] == "sql"
    assert [item.paragraph_type for item in parsed.paragraphs] == ["code", "body"]


def test_unclosed_markdown_fence_fails_closed_to_end_of_file():
    source = "~~~python\nprint('safe')\n\n# not a heading\nstill code"

    parsed = MarkdownParser.parse_bytes(source.encode("utf-8"), "sample.md")

    assert len(parsed.paragraphs) == 1
    assert parsed.paragraphs[0].paragraph_type == "code"
    assert parsed.paragraphs[0].text == "print('safe')\n\n# not a heading\nstill code"
    assert parsed.paragraphs[0].metadata["closed_fence"] is False


def test_four_space_indented_fence_like_line_remains_inside_code_block():
    source = (
        "```python\n"
        "print('before')\n"
        "    ```\n"
        "print('after')\n"
        "```\n"
    )

    parsed = MarkdownParser.parse_bytes(source.encode("utf-8"), "sample.md")

    assert len(parsed.paragraphs) == 1
    assert parsed.paragraphs[0].paragraph_type == "code"
    assert parsed.paragraphs[0].text == "print('before')\n    ```\nprint('after')"
