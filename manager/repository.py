"""SQLite persistence for manager jobs."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping
from dataclasses import replace
from datetime import datetime
from enum import Enum
from typing import Any

from .models import DownloadEvent, DownloadEventType, DownloadRequest, DownloadResult, Job, JobStatus, utc_now


class JobRepository:
    def __init__(self, connection: sqlite3.Connection):
        self._connection = connection

    def add(self, job: Job) -> Job:
        self._connection.execute(
            '''INSERT INTO jobs (id, url, options_json, status, created_at, updated_at, result_json, error, progress_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            (
                job.id, job.request.url, json.dumps(dict(job.request.options)), job.status.value,
                job.created_at.isoformat(), job.updated_at.isoformat(), self._result_to_json(job.result), job.error,
                self._event_to_json(job.progress),
            ),
        )
        self._connection.commit()
        return job

    def update(self, job: Job) -> Job:
        self._connection.execute(
            '''UPDATE jobs SET status = ?, updated_at = ?, result_json = ?, error = ?, progress_json = ?
               WHERE id = ?''',
            (job.status.value, job.updated_at.isoformat(), self._result_to_json(job.result), job.error,
             self._event_to_json(job.progress), job.id),
        )
        self._connection.commit()
        return job

    def set_status(self, job: Job, status: JobStatus, *, result: DownloadResult | None = None,
                   error: str | None = None, progress: DownloadEvent | None = None) -> Job:
        return self.update(replace(
            job, status=status, updated_at=utc_now(), result=result if result is not None else job.result,
            error=error, progress=progress if progress is not None else job.progress,
        ))

    def get(self, job_id: str) -> Job | None:
        row = self._connection.execute('SELECT * FROM jobs WHERE id = ?', (job_id,)).fetchone()
        return self._job_from_row(row) if row else None

    def list(self) -> list[Job]:
        rows = self._connection.execute('SELECT * FROM jobs ORDER BY created_at DESC, id ASC').fetchall()
        return [self._job_from_row(row) for row in rows]

    @staticmethod
    def _result_to_json(result: DownloadResult | None) -> str | None:
        if result is None:
            return None
        return json.dumps({
            'source_url': result.source_url,
            'output_paths': result.output_paths,
            'title': result.title,
            'metadata': _json_safe(result.metadata),
        })

    @staticmethod
    def _event_to_json(event: DownloadEvent | None) -> str | None:
        if event is None:
            return None
        return json.dumps({
            'type': event.type.value,
            'downloaded_bytes': event.downloaded_bytes,
            'total_bytes': event.total_bytes,
            'percent': event.percent,
            'speed': event.speed,
            'eta': event.eta,
            'output_path': event.output_path,
            'message': event.message,
        })

    @staticmethod
    def _job_from_row(row: sqlite3.Row) -> Job:
        result_data = json.loads(row['result_json']) if row['result_json'] else None
        result = DownloadResult(
            source_url=result_data['source_url'],
            output_paths=tuple(result_data['output_paths']),
            title=result_data['title'],
            metadata=result_data['metadata'],
        ) if result_data else None
        progress_data = json.loads(row['progress_json']) if row['progress_json'] else None
        progress = DownloadEvent(
            type=DownloadEventType(progress_data['type']),
            downloaded_bytes=progress_data.get('downloaded_bytes'),
            total_bytes=progress_data.get('total_bytes'),
            percent=progress_data.get('percent'),
            speed=progress_data.get('speed'),
            eta=progress_data.get('eta'),
            output_path=progress_data.get('output_path'),
            message=progress_data.get('message'),
        ) if progress_data else None
        return Job(
            id=row['id'],
            request=DownloadRequest(url=row['url'], options=json.loads(row['options_json'])),
            status=JobStatus(row['status']),
            created_at=datetime.fromisoformat(row['created_at']),
            updated_at=datetime.fromisoformat(row['updated_at']),
            result=result,
            error=row['error'],
            progress=progress,
        )


def _json_safe(value: Any) -> Any:
    """Convert arbitrary engine metadata into values accepted by JSON."""
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    if isinstance(value, (datetime, Enum)):
        return str(value.value if isinstance(value, Enum) else value.isoformat())
    return str(value)
