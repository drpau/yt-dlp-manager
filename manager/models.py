"""Domain types shared by manager persistence and download engines."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import uuid4


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class JobStatus(StrEnum):
    QUEUED = 'queued'
    RUNNING = 'running'
    SUCCEEDED = 'succeeded'
    FAILED = 'failed'
    CANCELLED = 'cancelled'


class CookieSourceKind(StrEnum):
    NONE = 'none'
    BROWSER = 'browser'
    FILE = 'file'


class DownloadEventType(StrEnum):
    PROGRESS = 'progress'
    COMPLETED = 'completed'
    ERROR = 'error'


@dataclass(frozen=True)
class DownloadRequest:
    url: str
    options: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CookieSourcePreference:
    """Non-sensitive cookie source selection safe to retain with a job."""

    kind: CookieSourceKind = CookieSourceKind.NONE
    browser: str | None = None


@dataclass(frozen=True)
class DownloadResult:
    source_url: str
    output_paths: tuple[str, ...] = ()
    title: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DownloadEvent:
    """A download-engine-neutral event suitable for future worker consumers."""

    type: DownloadEventType
    downloaded_bytes: int | None = None
    total_bytes: int | None = None
    percent: float | None = None
    speed: float | None = None
    eta: float | None = None
    output_path: str | None = None
    message: str | None = None


@dataclass(frozen=True)
class MediaInfo:
    title: str
    thumbnail: str | None = None
    duration: float | None = None
    uploader: str | None = None
    source: str | None = None
    formats: tuple[MediaFormat, ...] = ()


@dataclass(frozen=True)
class MediaFormat:
    """A safe, user-selectable yt-dlp format exposed by analysis."""

    id: str
    label: str
    mode: str
    selector: str


@dataclass(frozen=True)
class Job:
    request: DownloadRequest
    id: str = field(default_factory=lambda: str(uuid4()))
    status: JobStatus = JobStatus.QUEUED
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)
    result: DownloadResult | None = None
    error: str | None = None
    progress: DownloadEvent | None = None
