import io
import json
import time

from yt_dlp.utils import DownloadError

from manager.cookies import CHROMIUM_COOKIE_UNAVAILABLE_MESSAGE
from manager.database import initialize_database
from manager.models import DownloadRequest, Job, MediaFormat
from manager.repository import JobRepository
from manager.models import DownloadEvent, DownloadEventType, DownloadResult, MediaInfo
from manager.web import create_app


class FakeEngine:
    def __init__(self):
        self.analysis_options = None
        self.download_options = None

    def analyse(self, url, options):
        self.analysis_options = options
        return MediaInfo(
            'Example video', 'https://example.com/thumb.jpg', 120, 'Example channel', 'Youtube', (
                MediaFormat('video:18', '360p - MP4', 'video', '18'),
                MediaFormat('audio:140', 'Audio - M4A - 130 kbps', 'audio', '140'),
            ),
        )

    def download(self, request, on_event, cancel_check):
        self.download_options = request.options
        on_event(DownloadEvent(DownloadEventType.PROGRESS, downloaded_bytes=50, total_bytes=100, percent=50))
        return DownloadResult(request.url, ('download.mp4',), 'Example video')


def _analyse(client, *, cookie_source='none', browser=None, cookie_data=None):
    data = {'url': 'https://example.com/video', 'cookie_source': cookie_source}
    if browser:
        data['browser'] = browser
    if cookie_data is not None:
        data['cookie_file'] = (io.BytesIO(cookie_data.encode()), 'cookies.txt')
    return client.post('/api/analyse', data=data, content_type='multipart/form-data')


def _wait_for_terminal(client, job_id):
    for _ in range(50):
        job = client.get(f'/api/jobs/{job_id}').get_json()
        if job['status'] in {'succeeded', 'failed', 'cancelled'}:
            return job
        time.sleep(.02)
    raise AssertionError('job did not finish')


def test_file_cookie_is_used_for_analyse_and_download_without_persistence(tmp_path):
    engine = FakeEngine()
    app = create_app(tmp_path / 'jobs.sqlite3', tmp_path / 'downloads', engine=engine)
    client = app.test_client()

    analysed = _analyse(client, cookie_source='file', cookie_data='# Netscape HTTP Cookie File\n.example.com\tTRUE\t/\tFALSE\t0\tSID\tsecret')
    assert analysed.status_code == 200
    token = analysed.get_json()['analysis_token']
    assert engine.analysis_options['cookiefile'].getvalue().endswith('SID\tsecret')

    created = client.post('/api/jobs', json={
        'analysis_token': token, 'url': 'https://example.com/video', 'mode': 'video', 'format_id': 'video:18',
    })
    job = _wait_for_terminal(client, created.get_json()['id'])
    assert job['status'] == 'succeeded'
    assert engine.download_options['cookiefile'].getvalue().endswith('SID\tsecret')
    database_text = (tmp_path / 'jobs.sqlite3').read_bytes()
    assert b'secret' not in database_text
    stored_options = json.loads(client.get(f"/api/jobs/{job['id']}").get_data(as_text=True))
    assert stored_options['error'] is None


def test_browser_selection_is_reused_for_analyse_and_download(tmp_path):
    engine = FakeEngine()
    client = create_app(tmp_path / 'jobs.sqlite3', tmp_path / 'downloads', engine=engine).test_client()

    analysed = _analyse(client, cookie_source='browser', browser='edge')
    token = analysed.get_json()['analysis_token']
    created = client.post('/api/jobs', json={
        'analysis_token': token, 'url': 'https://example.com/video', 'mode': 'audio', 'format_id': 'audio:140',
    })
    job = _wait_for_terminal(client, created.get_json()['id'])

    assert job['status'] == 'succeeded'
    assert engine.analysis_options['cookiesfrombrowser'] == ('edge',)
    assert engine.download_options['cookiesfrombrowser'] == ('edge',)


def test_analyse_returns_media_specific_formats_and_rejects_unknown_format(tmp_path):
    client = create_app(tmp_path / 'jobs.sqlite3', tmp_path / 'downloads', engine=FakeEngine()).test_client()

    analysed = _analyse(client).get_json()
    assert [item['id'] for item in analysed['media']['formats']] == ['video:18', 'audio:140']
    response = client.post('/api/jobs', json={
        'analysis_token': analysed['analysis_token'], 'url': 'https://example.com/video',
        'mode': 'video', 'format_id': 'video:not-analysed',
    })

    assert response.status_code == 400
    assert 'available format' in response.get_json()['error']


def test_file_cookie_is_selected_once_and_required_only_for_analyse(tmp_path):
    client = create_app(tmp_path / 'jobs.sqlite3', tmp_path / 'downloads', engine=FakeEngine()).test_client()

    response = _analyse(client, cookie_source='file')

    assert response.status_code == 400
    assert 'Choose a Netscape-format' in response.get_json()['error']


def test_analyse_returns_the_safe_ytdlp_error_message(tmp_path):
    class FailingEngine(FakeEngine):
        def analyse(self, url, options):
            raise DownloadError('Sign in to confirm you are not a bot')

    client = create_app(tmp_path / 'jobs.sqlite3', tmp_path / 'downloads', engine=FailingEngine()).test_client()

    response = _analyse(client)

    assert response.status_code == 400
    assert response.get_json()['error'] == 'Could not analyse this URL: Sign in to confirm you are not a bot'


def test_analyse_recognises_ytdlp_cookie_errors_reported_as_download_errors(tmp_path):
    class FailingEngine(FakeEngine):
        def analyse(self, url, options):
            raise DownloadError('Could not copy Chrome cookie database')

    client = create_app(tmp_path / 'jobs.sqlite3', tmp_path / 'downloads', engine=FailingEngine()).test_client()

    response = _analyse(client, cookie_source='browser', browser='edge')

    assert response.status_code == 400
    assert response.get_json()['error'] == CHROMIUM_COOKIE_UNAVAILABLE_MESSAGE


def test_restart_fails_pending_file_cookie_job_without_cookie_data(tmp_path):
    database = tmp_path / 'jobs.sqlite3'
    connection = initialize_database(database)
    try:
        job_id = JobRepository(connection).add(Job(request=DownloadRequest('https://example.com/video', {
            'cookie_source': {'kind': 'file'},
        }))).id
    finally:
        connection.close()

    app = create_app(database, tmp_path / 'downloads', engine=FakeEngine())
    client = app.test_client()
    job = client.get('/api/jobs/' + job_id).get_json()

    assert job['status'] == 'failed'
    assert 'Cookie session expired' in job['error']
