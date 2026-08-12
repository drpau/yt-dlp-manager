"""In-process implementation of the manager download engine."""

from __future__ import annotations

from typing import Any

from yt_dlp import YoutubeDL

from .engine import ProgressCallback
from .models import DownloadEvent, DownloadEventType, DownloadRequest, DownloadResult


class YtDlpInProcessEngine:
    """Adapter that keeps yt-dlp details behind the DownloadEngine boundary."""

    def download(self, request: DownloadRequest, on_event: ProgressCallback | None = None) -> DownloadResult:
        options = dict(request.options)
        hooks = list(options.pop('progress_hooks', ()))
        if on_event:
            hooks.append(lambda data: on_event(self._normalize_progress(data)))
        if hooks:
            options['progress_hooks'] = hooks

        with YoutubeDL(options) as downloader:
            info = downloader.extract_info(request.url, download=True)
            output_paths = self._output_paths(downloader, info)
        result = DownloadResult(
            source_url=request.url,
            output_paths=output_paths,
            title=info.get('title'),
            metadata=info,
        )
        if on_event:
            on_event(DownloadEvent(DownloadEventType.COMPLETED, output_path=output_paths[0] if output_paths else None))
        return result

    @staticmethod
    def _output_paths(downloader: YoutubeDL, info: dict[str, Any]) -> tuple[str, ...]:
        if info.get('_type') == 'playlist':
            return tuple(
                downloader.prepare_filename(entry)
                for entry in info.get('entries', ())
                if entry is not None
            )
        return (downloader.prepare_filename(info),)

    @staticmethod
    def _normalize_progress(data: dict[str, Any]) -> DownloadEvent:
        status = data.get('status')
        if status == 'error':
            return DownloadEvent(DownloadEventType.ERROR, message=str(data.get('error') or 'yt-dlp download failed'))
        downloaded = data.get('downloaded_bytes')
        total = data.get('total_bytes') or data.get('total_bytes_estimate')
        percent = (downloaded / total * 100) if downloaded is not None and total else None
        return DownloadEvent(
            DownloadEventType.PROGRESS,
            downloaded_bytes=downloaded,
            total_bytes=total,
            percent=percent,
            speed=data.get('speed'),
            eta=data.get('eta'),
            output_path=data.get('filename'),
        )
