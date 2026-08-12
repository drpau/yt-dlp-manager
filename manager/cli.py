"""Command-line interface for the manager foundation."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from dataclasses import asdict
from pathlib import Path
from urllib.parse import urlsplit

from .database import initialize_database
from .models import DownloadRequest, Job
from .repository import JobRepository

DEFAULT_DATABASE_PATH = Path('yt-dlp-manager.sqlite3')


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog='yt-dlp-manager')
    parser.add_argument('--database', type=Path, default=DEFAULT_DATABASE_PATH)
    commands = parser.add_subparsers(dest='command', required=True)
    add_parser = commands.add_parser('add', help='queue a URL')
    add_parser.add_argument('url')
    commands.add_parser('list', help='list jobs')
    show_parser = commands.add_parser('show', help='show a job')
    show_parser.add_argument('job_id')
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    connection = initialize_database(args.database)
    repository = JobRepository(connection)
    try:
        if args.command == 'add':
            if not _is_valid_url(args.url):
                print(f'invalid URL: {args.url}')
                return 2
            job = repository.add(Job(request=DownloadRequest(args.url)))
            print(json.dumps(_serialize_job(job)))
            return 0
        if args.command == 'list':
            print(json.dumps([_serialize_job(job) for job in repository.list()]))
            return 0
        job = repository.get(args.job_id)
        if job is None:
            print(f'job not found: {args.job_id}')
            return 1
        print(json.dumps(_serialize_job(job)))
        return 0
    finally:
        connection.close()


def _serialize_job(job: Job) -> dict[str, object]:
    data = asdict(job)
    data['status'] = job.status.value
    data['created_at'] = job.created_at.isoformat()
    data['updated_at'] = job.updated_at.isoformat()
    return data


def _is_valid_url(value: str) -> bool:
    parsed = urlsplit(value)
    return bool(value.strip()) and parsed.scheme in {'http', 'https'} and bool(parsed.netloc)
