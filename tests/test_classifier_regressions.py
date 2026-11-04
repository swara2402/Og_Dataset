"""Regression tests for paragraph classification tokenization and section context."""

from backend.app.humanisation.classifier import ParagraphClassifier
from backend.app.document_processing.parser import DocumentParagraph


def paragraph(identifier: str, text: str, kind: str = "body") -> DocumentParagraph:
    return DocumentParagraph(
        id=identifier,
        text=text,
        paragraph_type=kind,
        location=f"body.{identifier}",
    )


def test_technical_terms_match_when_followed_by_punctuation():
    result = ParagraphClassifier().classify(
        paragraph(
            "technical",
            "The model, architecture, and vector representation support inference.",
        )
    )
    assert result.primary_category == "technical_explanation"


def test_multiword_literature_indicators_are_counted_as_phrases():
    result = ParagraphClassifier().classify(
        paragraph(
            "literature",
            "According to prior studies, this approach was examined across several reports.",
        )
    )
    assert result.primary_category == "literature_review"


def test_methodology_markers_match_as_complete_phrases():
    result = ParagraphClassifier().classify(
        paragraph(
            "method",
            "We used a stratified sampling procedure for data collection.",
        )
    )
    assert result.primary_category == "methodology"


def test_introduction_heading_resets_references_section_context():
    classifier = ParagraphClassifier()
    references = classifier.classify(paragraph("refs", "References", kind="heading"))
    assert references.primary_category == "heading"

    introduction = classifier.classify(
        paragraph("intro", "Introduction", kind="heading")
    )
    assert introduction.primary_category == "heading"
    assert introduction.features["detected_section"] == "introduction"

    body = classifier.classify(
        paragraph("intro-body", "This paper examines the effects of the proposed system.")
    )
    assert body.primary_category != "references"
    assert body.eligible_for_refinement is True
