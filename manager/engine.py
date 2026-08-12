"""Abstraction boundary for download implementations."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol, runtime_checkable

from .models import DownloadEvent, DownloadRequest, DownloadResult

ProgressCallback = Callable[[DownloadEvent], None]


@runtime_checkable
class DownloadEngine(Protocol):
    """Runs one request without exposing a particular downloader implementation."""

    def download(self, request: DownloadRequest, on_event: ProgressCallback | None = None) -> DownloadResult:
        """Download *request* and optionally emit normalized events."""
