from backend.app.engine.terminology_adapter import TerminologyProposalEngine


def reviewed_entry():
    return {
        "term_id": "TERM-1",
        "term": "confusion matrix",
        "definition": "A table comparing predicted and observed classes.",
        "disciplines": ["computer_science"],
        "contexts": ["classification evaluation"],
        "context_terms": ["classification", "evaluation"],
        "variants": ["confusion-matrix"],
        "preferred_form": "confusion matrix",
        "avoid_substitutions": ["error table"],
        "usage_note": "Use the established technical term.",
        "source": {
            "kind": "expert_curated",
            "reference": "expert-review-001",
            "license": "CC-BY-4.0",
            "attribution": "Curated by reviewer"
        },
        "review_status": "reviewed",
        "reviewer_id": "reviewer-1"
    }


def test_reviewed_context_qualified_term_variant_creates_proposal():
    engine = TerminologyProposalEngine([reviewed_entry()])
    text = "The confusion-matrix summarizes classification evaluation [12]."
    proposals = engine.analyze("p1", text, academic_domain="computer_science")
    assert len(proposals) == 1
    assert proposals[0].suggested_text == "The confusion matrix summarizes classification evaluation [12]."
    assert proposals[0].requires_review is True
    assert proposals[0].validation["checks"]["citations"] is True


def test_unreviewed_or_wrong_discipline_term_is_ignored():
    draft = reviewed_entry()
    draft["review_status"] = "draft"
    wrong_domain = reviewed_entry()
    engine = TerminologyProposalEngine([draft, wrong_domain])
    text = "The confusion-matrix summarizes classification evaluation."
    assert engine.analyze("p1", text, academic_domain="psychology") == []
