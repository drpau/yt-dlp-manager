from datetime import datetime, timezone

from manager.database import initialize_database
from manager.models import DownloadRequest, DownloadResult, Job, JobStatus
from manager.repository import JobRepository


def test_repository_persists_queued_job(tmp_path):
    connection = initialize_database(tmp_path / 'jobs.sqlite3')
    repository = JobRepository(connection)
    job = Job(request=DownloadRequest('https://example.com/video', {'format': 'best'}))

    repository.add(job)
    stored = repository.get(job.id)

    assert stored == job
    assert stored.status is JobStatus.QUEUED
    assert repository.list() == [job]


def test_repository_makes_result_metadata_json_safe(tmp_path):
    connection = initialize_database(tmp_path / 'jobs.sqlite3')
    repository = JobRepository(connection)
    job = Job(
        request=DownloadRequest('https://example.com/video'),
        result=DownloadResult(
            source_url='https://example.com/video',
            metadata={'when': datetime(2026, 1, 1, tzinfo=timezone.utc), 'opaque': object()},
        ),
    )

    repository.add(job)

    stored = repository.get(job.id)
    assert stored.result.metadata['when'] == '2026-01-01T00:00:00+00:00'
    assert isinstance(stored.result.metadata['opaque'], str)


def test_repository_lists_same_timestamp_jobs_by_id(tmp_path):
    connection = initialize_database(tmp_path / 'jobs.sqlite3')
    repository = JobRepository(connection)
    timestamp = datetime(2026, 1, 1, tzinfo=timezone.utc)
    repository.add(Job(id='b', request=DownloadRequest('https://example.com/b'), created_at=timestamp, updated_at=timestamp))
    repository.add(Job(id='a', request=DownloadRequest('https://example.com/a'), created_at=timestamp, updated_at=timestamp))

    assert [job.id for job in repository.list()] == ['a', 'b']
