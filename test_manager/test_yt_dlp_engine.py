from manager.engine import DownloadEngine
from manager.models import DownloadEventType, DownloadRequest
from manager.yt_dlp_engine import YtDlpInProcessEngine


class FakeYoutubeDL:
    options = None

    def __init__(self, options):
        self.options = options
        FakeYoutubeDL.options = options

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def extract_info(self, url, download):
        assert download is True
        self.options['progress_hooks'][0]({
            'status': 'downloading', 'downloaded_bytes': 25, 'total_bytes': 100,
            'speed': 10, 'eta': 8, 'filename': 'output.mp4',
        })
        return {'id': 'video-id', 'title': 'Example'}

    def prepare_filename(self, info):
        return 'output.mp4'


def test_in_process_engine_adapts_yt_dlp_and_normalizes_progress(monkeypatch):
    monkeypatch.setattr('manager.yt_dlp_engine.YoutubeDL', FakeYoutubeDL)
    engine = YtDlpInProcessEngine()
    events = []

    result = engine.download(DownloadRequest('https://example.com/video'), events.append)

    assert isinstance(engine, DownloadEngine)
    assert result.title == 'Example'
    assert result.output_paths == ('output.mp4',)
    assert events[0].type is DownloadEventType.PROGRESS
    assert events[0].percent == 25
    assert events[-1].type is DownloadEventType.COMPLETED
