from backend.app.document_processing.parser import LatexParser


def test_latex_protected_environment_remains_protected_across_blank_lines():
    source = (
        "\\begin{lstlisting}\n"
        "print('do not edit')\n\n"
        "second code paragraph\n"
        "\\end{lstlisting}\n\n"
        "This is ordinary prose."
    )

    parsed = LatexParser.parse_bytes(source.encode("utf-8"), "sample.tex")

    protected = [item for item in parsed.paragraphs if "lstlisting" in item.text or "code paragraph" in item.text]
    prose = [item for item in parsed.paragraphs if "ordinary prose" in item.text]

    assert protected
    assert all(item.paragraph_type == "code" for item in protected)
    assert len(prose) == 1
    assert prose[0].paragraph_type == "body"


def test_latex_nested_protected_environments_do_not_leak_protection():
    source = (
        "\\begin{figure}\n"
        "Figure content\n\n"
        "\\begin{tabular}{c}A\\\\B\\end{tabular}\n"
        "\\end{figure}\n\n"
        "A later paragraph should remain editable."
    )

    parsed = LatexParser.parse_bytes(source.encode("utf-8"), "nested.tex")

    figure_blocks = [item for item in parsed.paragraphs if "figure" in item.text or "tabular" in item.text or "Figure content" in item.text]
    later = [item for item in parsed.paragraphs if "later paragraph" in item.text]

    assert figure_blocks
    assert all(item.paragraph_type == "code" for item in figure_blocks)
    assert len(later) == 1
    assert later[0].paragraph_type == "body"


def test_latex_unclosed_protected_environment_fails_closed_for_following_blocks():
    source = (
        "\\begin{verbatim}\n"
        "literal source\n\n"
        "still literal without closing environment"
    )

    parsed = LatexParser.parse_bytes(source.encode("utf-8"), "unclosed.tex")

    assert parsed.paragraphs
    assert all(item.paragraph_type == "code" for item in parsed.paragraphs)
