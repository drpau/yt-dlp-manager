from pathlib import Path

from manager.web import run_web


def test_run_web_binds_only_to_ipv4_loopback(monkeypatch, tmp_path):
    calls = []

    class App:
        def run(self, **kwargs):
            calls.append(kwargs)

    monkeypatch.setattr('manager.web.create_app', lambda database, downloads: App())

    run_web(tmp_path / 'jobs.sqlite3', Path('downloads'), 9000)

    assert calls == [{'host': '127.0.0.1', 'port': 9000, 'debug': False}]
