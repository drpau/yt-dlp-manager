"""Ephemeral cookie-source handling for the local web manager."""

from __future__ import annotations

import io
import secrets
import threading
from dataclasses import dataclass
from datetime import timedelta

from .models import CookieSourceKind, CookieSourcePreference
from .models import MediaFormat

SUPPORTED_BROWSERS = ('chrome', 'edge', 'firefox', 'brave')
CHROMIUM_COOKIE_UNAVAILABLE_MESSAGE = (
    "This browser's cookie database is currently unavailable. Close the browser completely and try again, "
    'or use a cookies.txt file.'
)


class CookieSourceError(ValueError):
    """A safe error that can be shown in the local UI."""


def parse_cookie_preference(kind: str | None, browser: str | None = None) -> CookieSourcePreference:
    try:
        source_kind = CookieSourceKind(kind or CookieSourceKind.NONE)
    except ValueError:
        raise CookieSourceError('Choose a valid cookie source.')
    browser_name = (browser or '').lower()
    if source_kind is CookieSourceKind.BROWSER:
        if browser_name not in SUPPORTED_BROWSERS:
            raise CookieSourceError('Choose Chrome, Edge, Firefox, or Brave.')
        return CookieSourcePreference(source_kind, browser_name)
    return CookieSourcePreference(source_kind)


def cookie_options(preference: CookieSourcePreference, cookie_text: str | None = None) -> dict[str, object]:
    """Create one-use yt-dlp options without materialising cookie data on disk."""
    if preference.kind is CookieSourceKind.BROWSER:
        return {'cookiesfrombrowser': (preference.browser,)}
    if preference.kind is CookieSourceKind.FILE:
        if cookie_text is None:
            raise CookieSourceError('Cookie session expired. Analyse the URL and choose cookies.txt again.')
        return {'cookiefile': io.StringIO(cookie_text)}
    return {}


def cookie_error(preference: CookieSourcePreference, cause: BaseException | None = None) -> str:
    """Turn known browser-loader failures into safe, actionable UI guidance."""
    cause_text = str(cause or '').lower()
    if preference.kind is CookieSourceKind.BROWSER:
        if 'could not copy chrome cookie database' in cause_text:
            return CHROMIUM_COOKIE_UNAVAILABLE_MESSAGE
        if 'failed to decrypt with dpapi' in cause_text:
            return (
                f'{preference.browser.title()} cookies could not be decrypted by this yt-dlp build. '
                'Use a Netscape-format cookies.txt export for this browser profile.'
            )
        if 'could not find' in cause_text and 'cookies database' in cause_text:
            return (
                f'No {preference.browser.title()} cookie profile was found. Sign in to that browser profile, '
                'or use a Netscape-format cookies.txt export.'
            )
        return (
            f"Couldn't read cookies from {preference.browser.title()}. Close the browser completely and try again, "
            'or use a Netscape-format cookies.txt export.'
        )
    if preference.kind is CookieSourceKind.FILE:
        return "Couldn't read this cookies.txt file. Choose a Netscape-format cookies.txt export."
    return 'Could not load the selected cookie source.'


def is_cookie_load_error(error: BaseException) -> bool:
    """Recognise yt-dlp cookie failures that are reported as DownloadError."""
    message = str(error).lower()
    return any(marker in message for marker in (
        'could not copy chrome cookie database',
        'failed to decrypt with dpapi',
        'cookies database',
        'permission denied',
        'failed to load cookies',
    ))


@dataclass
class CookieWorkflow:
    url: str
    preference: CookieSourcePreference
    cookie_text: str | None
    formats: tuple[MediaFormat, ...]
    timer: threading.Timer


class CookieWorkflowStore:
    """Memory-only workflow state; cookie data is never serialised or written to disk."""

    def __init__(self, ttl: timedelta = timedelta(minutes=15)):
        self._ttl = ttl
        self._lock = threading.Lock()
        self._workflows: dict[str, CookieWorkflow] = {}

    def create(self, url: str, preference: CookieSourcePreference, cookie_text: str | None = None,
               formats: tuple[MediaFormat, ...] = ()) -> str:
        if preference.kind is CookieSourceKind.FILE and cookie_text is None:
            raise CookieSourceError('Choose a Netscape-format cookies.txt file.')
        token = secrets.token_urlsafe(24)
        timer = threading.Timer(self._ttl.total_seconds(), self.discard, args=(token,))
        timer.daemon = True
        workflow = CookieWorkflow(url=url, preference=preference, cookie_text=cookie_text, formats=formats, timer=timer)
        with self._lock:
            self._workflows[token] = workflow
        timer.start()
        return token

    def get(self, token: str, url: str) -> CookieWorkflow:
        with self._lock:
            workflow = self._workflows.get(token)
        if workflow is None or workflow.url != url:
            raise CookieSourceError('Analysis session expired. Analyse the URL again.')
        return workflow

    def lease(self, token: str, url: str) -> CookieWorkflow:
        workflow = self.get(token, url)
        workflow.timer.cancel()
        return workflow

    def discard(self, token: str) -> None:
        with self._lock:
            workflow = self._workflows.pop(token, None)
        if workflow:
            workflow.timer.cancel()
            workflow.cookie_text = None
