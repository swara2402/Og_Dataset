from types import SimpleNamespace

import pytest

from backend.app.export.exporter import _latex_text


def make_job(source: str, original: str, revised: str):
    item = SimpleNamespace(
        metadata={"source_start": 0, "source_end": len(source)},
        paragraph_type="body",
    )
    state = SimpleNamespace(
        review_status="accepted",
        current_text=revised,
        original_text=original,
        paragraph_type="body",
    )
    return SimpleNamespace(
        file_type="tex",
        original_bytes=source.encode("utf-8"),
        document=SimpleNamespace(paragraphs=[item]),
        paragraphs=[state],
    )


def test_latex_export_allows_prose_change_without_tex_syntax_change():
    source = "The result is clear."
    job = make_job(source, source, "The result is convincing.")
    assert _latex_text(job) == "The result is convincing."


@pytest.mark.parametrize(
    "original,revised",
    [
        ("The result is clear.", "The result is 50% significant."),
        (r"Use \emph{careful wording}.", r"Use \textbf{careful wording}."),
        ("A & B are compared.", "A and B are compared."),
        ("A simple result.", "A simple result #1."),
        (r"Prior work supports this claim \cite{smith2020}.", r"Prior work supports this claim \cite{jones2021}."),
        (r"See Section \ref{sec:methods}.", r"See Section \ref{sec:results}."),
    ],
)
def test_latex_export_rejects_changes_to_tex_commands_or_special_tokens(original, revised):
    with pytest.raises(ValueError, match="changes commands, references or special syntax"):
        _latex_text(make_job(original, original, revised))


def test_latex_export_rejects_overlapping_source_offsets():
    source = "abcdefghi"
    first = SimpleNamespace(
        metadata={"source_start": 0, "source_end": 6},
        paragraph_type="body",
    )
    second = SimpleNamespace(
        metadata={"source_start": 3, "source_end": len(source)},
        paragraph_type="body",
    )
    states = [
        SimpleNamespace(review_status="accepted", current_text="abcxyz", original_text="abcdef", paragraph_type="body"),
        SimpleNamespace(review_status="accepted", current_text="defxyz", original_text="defghi", paragraph_type="body"),
    ]
    document = SimpleNamespace(paragraphs=[first, second])
    job = SimpleNamespace(file_type="tex", original_bytes=source.encode(), document=document, paragraphs=states)
    with pytest.raises(ValueError, match="offsets overlap"):
        _latex_text(job)

@pytest.mark.parametrize(
    "original,revised",
    [
        (r"Keep this figure \\begin{figure} stable.", r"Keep this figure \\begin{table} stable."),
        (r"See the image \\includegraphics{figures/result.png}.", r"See the image \\includegraphics{figures/other.png}."),
        (r"Use the \\usepackage{amsmath} package.", r"Use the \\usepackage{graphicx} package."),
    ],
)
def test_latex_export_rejects_changes_to_environment_and_resource_arguments(original, revised):
    with pytest.raises(ValueError, match="changes commands, references or special syntax"):
        _latex_text(make_job(original, original, revised))
