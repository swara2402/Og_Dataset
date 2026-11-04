"""Security-conscious configuration defaults."""

from backend.app.core.config import Settings


def test_offline_core_has_no_public_web_originality_setting():
    assert "enable_web_originality" not in Settings.model_fields


def test_debug_is_disabled_by_default():
    assert Settings(_env_file=None).debug is False
