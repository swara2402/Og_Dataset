from types import SimpleNamespace

import pytest

pytest.importorskip("reportlab")

from backend.app.export.exporter import _pdf_bytes


def test_pdf_export_reports_unsupported_unicode_without_low_level_error():
    state = SimpleNamespace(
        review_status="unchanged",
        current_text="中文研究数据分析。",
        original_text="Η ανάλυση εξετάζει δεδομένα.",
        paragraph_type="body",
    )
    job = SimpleNamespace(paragraphs=[state])

    with pytest.raises(ValueError, match="cannot encode one or more characters"):
        _pdf_bytes(job)
