"""Small local Flask interface for the yt-dlp manager."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from datetime import timedelta
from pathlib import Path
from threading import Event, Lock
from typing import Any
from urllib.parse import urlsplit

from flask import Flask, jsonify, render_template, request
from yt_dlp.cookies import CookieLoadError
from yt_dlp.utils import DownloadCancelled, DownloadError

from .cookies import (
    CookieSourceError, CookieWorkflowStore, cookie_error, cookie_options, is_cookie_load_error, parse_cookie_preference,
)
from .database import initialize_database
from .models import DownloadEvent, DownloadRequest, Job, JobStatus
from .repository import JobRepository
from .yt_dlp_engine import YtDlpInProcessEngine

DEFAULT_DOWNLOAD_DIRECTORY = Path('downloads')
MAX_COOKIE_FILE_BYTES = 5 * 1024 * 1024

def create_app(database_path: str | Path = 'yt-dlp-manager.sqlite3',
               download_directory: str | Path = DEFAULT_DOWNLOAD_DIRECTORY,
               *, engine: YtDlpInProcessEngine | None = None,
               workflow_store: CookieWorkflowStore | None = None) -> Flask:
    app = Flask(__name__)
    database_path = Path(database_path)
    download_directory = Path(download_directory)
    engine = engine or YtDlpInProcessEngine()
    workflow_store = workflow_store or CookieWorkflowStore(timedelta(minutes=15))
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='yt-dlp-manager')
    active_jobs: dict[str, tuple[str, Event]] = {}
    active_jobs_lock = Lock()

    _recover_interrupted_jobs(database_path)

    app.config['MAX_CONTENT_LENGTH'] = MAX_COOKIE_FILE_BYTES

    @app.get('/')
    def index():
        return render_template('index.html')

    @app.post('/api/analyse')
    def analyse():
        url = (request.form.get('url') or '').strip()
        if not _is_valid_url(url):
            return _error('Enter a valid http or https URL.')
        try:
            preference = parse_cookie_preference(request.form.get('cookie_source'), request.form.get('browser'))
            cookie_text = _uploaded_cookie_text() if preference.kind.value == 'file' else None
            media = engine.analyse(url, cookie_options(preference, cookie_text))
            token = workflow_store.create(url, preference, cookie_text, media.formats)
        except CookieSourceError as error:
            return _error(str(error))
        except CookieLoadError as error:
            return _error(cookie_error(preference, error.__context__))
        except DownloadError as error:
            if preference.kind.value != 'none' and is_cookie_load_error(error):
                return _error(cookie_error(preference, error))
            return _error(_analysis_error(error))
        except Exception:
            return _error('Could not analyse this URL. Check that it is supported and available, then try again.')
        return jsonify({
            'media': asdict(media),
            'analysis_token': token,
            'cookie_source': {'kind': preference.kind.value, 'browser': preference.browser},
            'cookie_file_loaded': preference.kind.value == 'file',
        })

    @app.post('/api/jobs')
    def create_job():
        payload = request.get_json(silent=True) or {}
        token = str(payload.get('analysis_token') or '')
        mode, format_id = str(payload.get('mode') or ''), str(payload.get('format_id') or '')
        try:
            workflow = workflow_store.lease(token, str(payload.get('url') or ''))
        except CookieSourceError as error:
            return _error(str(error))
        selected_format = next((item for item in workflow.formats if item.id == format_id and item.mode == mode), None)
        if selected_format is None:
            return _error('Choose an available format from the analysis results.')
        safe_options = {
            'mode': mode,
            'format_id': selected_format.id,
            'format_label': selected_format.label,
            'cookie_source': {'kind': workflow.preference.kind.value, 'browser': workflow.preference.browser},
        }
        connection = initialize_database(database_path)
        try:
            job = Job(request=DownloadRequest(workflow.url, safe_options))
            JobRepository(connection).add(job)
        finally:
            connection.close()
        cancelled = Event()
        with active_jobs_lock:
            active_jobs[job.id] = (token, cancelled)
        executor.submit(_run_job, job.id, token, workflow, selected_format.selector, cancelled)
        return jsonify(_serialize_job(job)), 202

    @app.get('/api/jobs/<job_id>')
    def get_job(job_id: str):
        connection = initialize_database(database_path)
        try:
            job = JobRepository(connection).get(job_id)
        finally:
            connection.close()
        if job is None:
            return _error('Download not found.', 404)
        return jsonify(_serialize_job(job))

    @app.post('/api/jobs/<job_id>/cancel')
    def cancel_job(job_id: str):
        with active_jobs_lock:
            active = active_jobs.get(job_id)
        if active is None:
            return _error('This download can no longer be cancelled.', 409)
        active[1].set()
        return jsonify({'id': job_id, 'status': 'cancelling'})

    def _run_job(job_id: str, token: str, workflow, format_selector: str, cancelled: Event) -> None:
        connection = initialize_database(database_path)
        repository = JobRepository(connection)
        job = repository.get(job_id)
        assert job is not None
        try:
            if cancelled.is_set():
                repository.set_status(job, JobStatus.CANCELLED, error='Download cancelled.')
                return
            job = repository.set_status(job, JobStatus.RUNNING)

            def on_event(event: DownloadEvent) -> None:
                nonlocal job
                job = repository.set_status(job, JobStatus.RUNNING, progress=event)

            engine_options = {
                **cookie_options(workflow.preference, workflow.cookie_text),
                'format': format_selector,
                'noplaylist': True,
                'outtmpl': str(download_directory / '%(title)s [%(id)s].%(ext)s'),
            }
            result = engine.download(DownloadRequest(job.request.url, engine_options), on_event, cancelled.is_set)
            if cancelled.is_set():
                repository.set_status(job, JobStatus.CANCELLED, error='Download cancelled.')
            else:
                repository.set_status(job, JobStatus.SUCCEEDED, result=result)
        except DownloadCancelled:
            repository.set_status(job, JobStatus.CANCELLED, error='Download cancelled.')
        except CookieLoadError as error:
            repository.set_status(job, JobStatus.FAILED, error=cookie_error(workflow.preference, error.__context__))
        except CookieSourceError as error:
            repository.set_status(job, JobStatus.FAILED, error=str(error))
        except DownloadError as error:
            message = cookie_error(workflow.preference, error) if is_cookie_load_error(error) else _download_error(error)
            repository.set_status(job, JobStatus.FAILED, error=message)
        except Exception:
            repository.set_status(job, JobStatus.FAILED, error='Download failed. Check the URL and access settings, then try again.')
        finally:
            connection.close()
            workflow_store.discard(token)
            with active_jobs_lock:
                active_jobs.pop(job_id, None)

    return app


def _uploaded_cookie_text() -> str:
    uploaded = request.files.get('cookie_file')
    if uploaded is None or not uploaded.filename:
        raise CookieSourceError('Choose a Netscape-format cookies.txt file.')
    data = uploaded.read(MAX_COOKIE_FILE_BYTES + 1)
    if len(data) > MAX_COOKIE_FILE_BYTES:
        raise CookieSourceError('cookies.txt must be smaller than 5 MB.')
    try:
        return data.decode('utf-8')
    except UnicodeDecodeError:
        raise CookieSourceError('cookies.txt must be UTF-8 encoded.')


def _serialize_job(job: Job) -> dict[str, Any]:
    return {
        'id': job.id,
        'url': job.request.url,
        'status': job.status.value,
        'created_at': job.created_at.isoformat(),
        'updated_at': job.updated_at.isoformat(),
        'title': job.result.title if job.result else None,
        'output_paths': list(job.result.output_paths) if job.result else [],
        'error': job.error,
        'progress': asdict(job.progress) | {'type': job.progress.type.value} if job.progress else None,
    }


def _recover_interrupted_jobs(database_path: Path) -> None:
    """This small local runner cannot resume work after the process exits."""
    connection = initialize_database(database_path)
    try:
        repository = JobRepository(connection)
        for job in repository.list():
            if job.status not in {JobStatus.QUEUED, JobStatus.RUNNING}:
                continue
            source = job.request.options.get('cookie_source', {})
            message = (
                'Cookie session expired—analyse again and choose cookies.txt.'
                if source.get('kind') == 'file'
                else 'Download interrupted because the local manager was restarted. Start it again to retry.'
            )
            repository.set_status(job, JobStatus.FAILED, error=message)
    finally:
        connection.close()


def _is_valid_url(value: str) -> bool:
    parsed = urlsplit(value)
    return bool(value) and parsed.scheme in {'http', 'https'} and bool(parsed.netloc)


def _error(message: str, status: int = 400):
    return jsonify({'error': message}), status


def _analysis_error(error: DownloadError) -> str:
    """Expose yt-dlp's useful explanation without traceback or cookie data."""
    message = str(error).strip()
    if not message:
        return 'Could not analyse this URL. Check that it is supported and available, then try again.'
    return f'Could not analyse this URL: {message}'


def _download_error(error: DownloadError) -> str:
    """Show an actionable yt-dlp failure without a traceback or credentials."""
    message = str(error).strip()
    if 'ffmpeg is not installed' in message.lower():
        return 'This selection needs ffmpeg to combine video and audio. Install ffmpeg, then try again.'
    return f'Download failed: {message}' if message else 'Download failed. Check the URL and access settings, then try again.'


def run_web(database_path: str | Path, download_directory: str | Path, port: int) -> None:
    """Run the local-only interface on the IPv4 loopback address."""
    create_app(database_path, download_directory).run(host='127.0.0.1', port=port, debug=False)
