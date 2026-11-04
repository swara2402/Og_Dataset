from backend.app.document_processing.parser import DocumentParagraph
from backend.app.humanisation.classifier import ParagraphClassifier


def paragraph(identifier: str, text: str, *, paragraph_type: str = "body", metadata=None):
    return DocumentParagraph(
        id=identifier,
        text=text,
        paragraph_type=paragraph_type,
        location=f"body.{identifier}",
        metadata=metadata or {},
    )


def test_classifier_marks_opening_title_as_heading():
    items = [
        paragraph(
            "title",
            "Orbital Environment Intelligence: A Web-Based Analytical Platform for Monitoring Earth's Tracked Orbital Population",
        ),
        paragraph("abstract", "This paper presents a platform for studying orbital population changes over time."),
    ]

    classified = ParagraphClassifier().classify_all(items)

    assert classified[0].primary_category == "heading"
    assert classified[0].eligible_for_refinement is False
    assert classified[1].eligible_for_refinement is True


def test_classifier_marks_comma_separated_author_names_as_front_matter():
    item = paragraph(
        "authors",
        "Yash Sawant, Yooraj Gole, Yuvraj Gandhi, Nisarg Mulik",
    )

    result = ParagraphClassifier().classify_all([item])[0]

    assert result.primary_category == "front_matter"
    assert result.eligible_for_refinement is False
    assert result.features["structural_signal"] == "author_list"


def test_classifier_respects_docx_title_style_metadata():
    item = paragraph(
        "title",
        "A title with sentence-like punctuation.",
        metadata={"style": "Title"},
    )

    result = ParagraphClassifier().classify_all([item])[0]

    assert result.primary_category == "heading"
    assert result.eligible_for_refinement is False


def test_classifier_does_not_mark_ordinary_prose_as_author_list():
    item = paragraph(
        "body",
        "The researchers evaluated the model using a public benchmark dataset.",
    )

    result = ParagraphClassifier().classify_all([item])[0]

    assert result.eligible_for_refinement is True
    assert result.primary_category != "front_matter"
