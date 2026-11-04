from backend.app.core.jobs import Job, ParagraphState, SQLiteJobStore
from backend.app.document_processing.parser import ParsedDocument, DocumentParagraph


def _job():
    paragraph = DocumentParagraph(
        id="p1", text="A short paragraph for persistence.",
        paragraph_type="body", location="body.0", metadata={},
    )
    state = ParagraphState(
        id="p1", index=0, original_text=paragraph.text,
        paragraph_type="body", category="general", section=None, eligible=True,
    )
    return Job(
        job_id="job-persist-1", filename="sample.txt", file_type="txt",
        content_type="text/plain", created_at="2026-11-05T12:00:00+00:00",
        style="academic", options={}, document=ParsedDocument(
            filename="sample.txt", file_type="txt", paragraphs=[paragraph],
        ), paragraphs=[state], original_bytes=b"A short paragraph for persistence.",
        status="completed", progress={"percent": 100},
    )


def test_sqlite_job_store_round_trips_job_and_versions(tmp_path):
    path = tmp_path / "jobs.sqlite3"
    first = SQLiteJobStore(db_path=str(path))
    job = _job()
    job.paragraphs[0].add_version(
        text="A revised paragraph for persistence.",
        masked_text="A revised paragraph for persistence.",
        pass_number=1,
        source="rule-based",
    )
    first.create(job)

    restarted = SQLiteJobStore(db_path=str(path))
    restored = restarted.get(job.job_id)

    assert restored is not None
    assert restored.status == "completed"
    assert restored.paragraphs[0].current_text == "A revised paragraph for persistence."
    assert len(restored.paragraphs[0].versions) == 2
    assert restored.original_bytes == job.original_bytes
    assert restarted.list()[0].job_id == job.job_id


def test_sqlite_job_store_marks_interrupted_jobs_for_recovery(tmp_path):
    path = tmp_path / "jobs.sqlite3"
    store = SQLiteJobStore(db_path=str(path))
    job = _job()
    job.status = "processing"
    store.create(job)

    restarted = SQLiteJobStore(db_path=str(path))
    restored = restarted.get(job.job_id)

    assert restored is not None
    assert restored.status == "failed"
    assert "interrupted" in (restored.error or "").lower()
    assert restored.paragraphs[0].original_text == job.paragraphs[0].original_text


def test_sqlite_job_store_prunes_persistent_history_across_restarts(tmp_path):
    path = tmp_path / "jobs.sqlite3"
    store = SQLiteJobStore(max_jobs=2, db_path=str(path))
    for index in range(3):
        job = _job()
        job.job_id = f"job-prune-{index}"
        job.created_at = f"2026-11-05T12:00:0{index}+00:00"
        store.create(job)

    restarted = SQLiteJobStore(max_jobs=2, db_path=str(path))

    assert len(restarted.list()) == 2
    assert restarted.get("job-prune-0") is None
    assert restarted.get("job-prune-1") is not None
    assert restarted.get("job-prune-2") is not None


def test_sqlite_job_store_recovers_interrupted_jobs_even_when_loaded_lazily(tmp_path):
    path = tmp_path / "jobs.sqlite3"
    store = SQLiteJobStore(max_jobs=1, db_path=str(path))
    for index in range(2):
        job = _job()
        job.job_id = f"job-recovery-{index}"
        job.created_at = f"2026-11-05T12:00:0{index}+00:00"
        job.status = "processing"
        store.create(job)

    restarted = SQLiteJobStore(max_jobs=1, db_path=str(path))
    restored = restarted.get("job-recovery-0")

    assert restored is not None
    assert restored.status == "failed"
    assert "interrupted" in (restored.error or "").lower()
