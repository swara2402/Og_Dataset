from backend.app.protected_content.masker import ProtectedContentMasker


def test_restore_validation_checks_protected_content_at_character_zero():
    masker = ProtectedContentMasker()
    original = "https://example.com/paper DOI 10.1234/example"
    masked, replacements, spans = masker.mask(original)
    assert spans

    token = spans[0].placeholder
    tampered = dict(replacements)
    tampered[token] = "https://attacker.invalid/changed"

    restored, error = masker.restore_and_validate(original, masked, tampered)

    assert restored is None
    assert "integrity check failed" in error
