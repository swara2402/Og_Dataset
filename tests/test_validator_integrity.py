from backend.app.validation.validator import validate_rewrite


def _validate(original: str, revised: str):
    return validate_rewrite(
        original_text=original,
        revised_text=revised,
        masked_original=original,
        masked_revised=revised,
        protected_items=[],
    )


def test_validator_rejects_reordered_numbers_even_when_none_are_lost():
    original = "The first group had 12 cases and the second had 24 cases."
    revised = "The first group had 24 cases and the second had 12 cases."
    result = _validate(original, revised)

    assert result["valid"] is False
    assert result["critical"] is True
    assert result["checks"]["numbers"] is False
    assert "Numbers were reordered." in result["issues"]


def test_validator_rejects_reordered_citations_even_when_both_remain():
    original = "Prior work supports this result [1], while another study differs [2]."
    revised = "Prior work supports this result [2], while another study differs [1]."
    result = _validate(original, revised)

    assert result["valid"] is False
    assert result["critical"] is True
    assert result["checks"]["citations"] is False
    assert "Citations/links were reordered." in result["issues"]


def test_validator_accepts_unchanged_evidence_order():
    original = "The first group had 12 cases [1], and the second had 24 cases [2]."
    result = _validate(original, original)

    assert result["checks"]["numbers"] is True
    assert result["checks"]["citations"] is True
