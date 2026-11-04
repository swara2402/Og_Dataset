from backend.app.core.jobs import Job
from backend.app.document_processing.parser import ParsedDocument
from backend.app.export.exporter import export_document


def _job(job_id: str) -> Job:
    filename = "shared-name.txt"
    document = ParsedDocument(filename=filename, file_type="txt")
    return Job(
        job_id=job_id,
        filename=filename,
        file_type="txt",
        content_type="text/plain",
        created_at="2026-01-01T00:00:00+00:00",
        style="academic",
        options={},
        document=document,
        paragraphs=[],
    )


def test_same_named_documents_get_distinct_export_paths(tmp_path):
    first = export_document(_job("user-a-job-id"), "txt", str(tmp_path))
    second = export_document(_job("user-b-job-id"), "txt", str(tmp_path))

    assert first != second
    assert first.exists()
    assert second.exists()
    assert first.read_text(encoding="utf-8") == second.read_text(encoding="utf-8")
