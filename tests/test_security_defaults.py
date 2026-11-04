"""Security-conscious configuration defaults."""

from backend.app.core.config import Settings


def test_optional_web_originality_and_debug_are_disabled_by_default():
    config = Settings(_env_file=None)

    assert config.enable_web_originality is False
    assert config.debug is False


def test_optional_web_originality_can_be_explicitly_enabled():
    config = Settings(_env_file=None, enable_web_originality=True)

    assert config.enable_web_originality is True
