from backend.app.protected_content.masker import ProtectedContentMasker


def test_literal_placeholder_text_is_preserved_without_colliding_with_internal_tokens():
    original = (
        "The document contains __TURNITOUT_PROTECTED_0000__ as an example "
        "and a contact address author@example.org."
    )
    masker = ProtectedContentMasker()
    masked, replacements, spans = masker.mask(original)
    assert any(span.type == "literal_placeholder" for span in spans)
    restored, error = masker.restore_and_validate(original, masked, replacements)
    assert error == ""
    assert restored == original


def test_multiple_literal_placeholders_keep_their_exact_order_and_text():
    original = (
        "__TURNITOUT_PROTECTED_0000__ appears before "
        "__TURNITOUT_PROTECTED_0001__ and https://example.org/path."
    )
    masker = ProtectedContentMasker()
    masked, replacements, _ = masker.mask(original)
    restored, error = masker.restore_and_validate(original, masked, replacements)
    assert error == ""
    assert restored == original
