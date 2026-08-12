"""In-process implementation of the manager download engine."""

from __future__ import annotations

from typing import Any

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadCancelled

from .engine import CancelCheck, ProgressCallback
from .models import DownloadEvent, DownloadEventType, DownloadRequest, DownloadResult, MediaFormat, MediaInfo


class YtDlpInProcessEngine:
    """Adapter that keeps yt-dlp details behind the DownloadEngine boundary."""

    def analyse(self, url: str, options: dict[str, Any] | None = None) -> MediaInfo:
        """Extract only the compact media information needed by the web UI."""
        analysis_options = dict(options or {})
        analysis_options.update({'quiet': True, 'no_warnings': True, 'noplaylist': True})
        with YoutubeDL(analysis_options) as downloader:
            info = downloader.extract_info(url, download=False)
        return MediaInfo(
            title=info.get('title') or 'Untitled media',
            thumbnail=info.get('thumbnail'),
            duration=info.get('duration'),
            uploader=info.get('uploader') or info.get('channel') or info.get('creator'),
            source=info.get('extractor_key') or info.get('extractor'),
            formats=self._media_formats(info),
        )

    @staticmethod
    def _media_formats(info: dict[str, Any]) -> tuple[MediaFormat, ...]:
        formats: list[MediaFormat] = []
        for item in info.get('formats') or ():
            format_id = item.get('format_id')
            vcodec, acodec = item.get('vcodec'), item.get('acodec')
            if not format_id or (vcodec == 'none' and acodec == 'none'):
                continue
            ext = (item.get('ext') or 'media').upper()
            if vcodec and vcodec != 'none' and item.get('height'):
                height = f"{item['height']}p"
                codec = (vcodec.split('.')[0] or 'video').upper()
                has_audio = acodec and acodec != 'none'
                formats.append(MediaFormat(
                    id=f'video:{format_id}',
                    label=f'{height} · {ext} · {codec}' + ('' if has_audio else ' + best audio'),
                    mode='video',
                    selector=format_id if has_audio else f'{format_id}+bestaudio/best',
                ))
            elif acodec and acodec != 'none' and (not vcodec or vcodec == 'none'):
                bitrate = item.get('abr')
                detail = f' · {round(bitrate)} kbps' if bitrate else ''
                formats.append(MediaFormat(
                    id=f'audio:{format_id}', label=f'Audio · {ext}{detail}', mode='audio', selector=format_id,
                ))
        return tuple(sorted(formats, key=lambda item: (item.mode, item.label), reverse=True))

    def download(self, request: DownloadRequest, on_event: ProgressCallback | None = None,
                 cancel_check: CancelCheck | None = None) -> DownloadResult:
        options = dict(request.options)
        hooks = list(options.pop('progress_hooks', ()))
        if on_event:
            hooks.append(lambda data: self._handle_progress(data, on_event, cancel_check))
        if hooks:
            options['progress_hooks'] = hooks

        with YoutubeDL(options) as downloader:
            info = downloader.extract_info(request.url, download=True)
            output_paths = self._output_paths(downloader, info)
        result = DownloadResult(
            source_url=request.url,
            output_paths=output_paths,
            title=info.get('title'),
            metadata=self._safe_metadata(info),
        )
        if on_event:
            on_event(DownloadEvent(DownloadEventType.COMPLETED, output_path=output_paths[0] if output_paths else None))
        return result

    @classmethod
    def _handle_progress(cls, data: dict[str, Any], on_event: ProgressCallback,
                         cancel_check: CancelCheck | None) -> None:
        if cancel_check and cancel_check():
            raise DownloadCancelled('Download cancelled')
        on_event(cls._normalize_progress(data))

    @staticmethod
    def _safe_metadata(info: dict[str, Any]) -> dict[str, Any]:
        """Persist only display metadata, never arbitrary extractor state or request headers."""
        return {
            key: info[key]
            for key in ('id', 'title', 'uploader', 'channel', 'duration', 'thumbnail', 'extractor', 'webpage_url')
            if info.get(key) is not None
        }

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
