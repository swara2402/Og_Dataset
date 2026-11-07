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
    ],
)
def test_latex_export_rejects_changes_to_tex_commands_or_special_tokens(original, revised):
    with pytest.raises(ValueError, match="changes commands or special syntax"):
        _latex_text(make_job(original, original, revised))


def test_latex_export_rejects_overlapping_source_offsets():
    source = "First block. Second block."
    first = SimpleNamespace(
        metadata={"source_start": 0, "source_end": 13},
        paragraph_type="body",
    )
    second = SimpleNamespace(
        metadata={"source_start": 10, "source_end": len(source)},
        paragraph_type="body",
    )
    states = [
        SimpleNamespace(review_status="accepted", current_text="First paragraph.", original_text="First block.", paragraph_type="body"),
        SimpleNamespace(review_status="accepted", current_text="Second paragraph.", original_text="Second block.", paragraph_type="body"),
    ]
    document = SimpleNamespace(paragraphs=[first, second])
    job = SimpleNamespace(file_type="tex", original_bytes=source.encode(), document=document, paragraphs=states)
    with pytest.raises(ValueError, match="offsets overlap"):
        _latex_text(job)
