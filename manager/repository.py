"""SQLite persistence for manager jobs."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping
from datetime import datetime
from enum import Enum
from typing import Any

from .models import DownloadRequest, DownloadResult, Job, JobStatus


class JobRepository:
    def __init__(self, connection: sqlite3.Connection):
        self._connection = connection

    def add(self, job: Job) -> Job:
        self._connection.execute(
            '''INSERT INTO jobs (id, url, options_json, status, created_at, updated_at, result_json, error)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
            (
                job.id, job.request.url, json.dumps(dict(job.request.options)), job.status.value,
                job.created_at.isoformat(), job.updated_at.isoformat(), self._result_to_json(job.result), job.error,
            ),
        )
        self._connection.commit()
        return job

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
    def _job_from_row(row: sqlite3.Row) -> Job:
        result_data = json.loads(row['result_json']) if row['result_json'] else None
        result = DownloadResult(
            source_url=result_data['source_url'],
            output_paths=tuple(result_data['output_paths']),
            title=result_data['title'],
            metadata=result_data['metadata'],
        ) if result_data else None
        return Job(
            id=row['id'],
            request=DownloadRequest(url=row['url'], options=json.loads(row['options_json'])),
            status=JobStatus(row['status']),
            created_at=datetime.fromisoformat(row['created_at']),
            updated_at=datetime.fromisoformat(row['updated_at']),
            result=result,
            error=row['error'],
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
