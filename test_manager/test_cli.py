import json
from pathlib import Path

import pytest

from manager.cli import main


def test_cli_add_list_and_show_job(tmp_path, capsys):
    database = tmp_path / 'jobs.sqlite3'

    assert main(['--database', str(database), 'add', 'https://example.com/video']) == 0
    added = json.loads(capsys.readouterr().out)
    assert added['status'] == 'queued'

    assert main(['--database', str(database), 'list']) == 0
    jobs = json.loads(capsys.readouterr().out)
    assert [job['id'] for job in jobs] == [added['id']]

    assert main(['--database', str(database), 'show', added['id']]) == 0
    assert json.loads(capsys.readouterr().out)['request']['url'] == 'https://example.com/video'


def test_cli_returns_error_for_unknown_job(tmp_path, capsys):
    assert main(['--database', str(tmp_path / 'jobs.sqlite3'), 'show', 'missing']) == 1
    assert capsys.readouterr().out == 'job not found: missing\n'


def test_cli_rejects_blank_or_malformed_url(tmp_path, capsys):
    database = tmp_path / 'jobs.sqlite3'

    assert main(['--database', str(database), 'add', ' ']) == 2
    assert capsys.readouterr().out == 'invalid URL:  \n'
    assert main(['--database', str(database), 'add', 'not-a-url']) == 2
    assert capsys.readouterr().out == 'invalid URL: not-a-url\n'


def test_cli_creates_database_parent_directory(tmp_path, capsys):
    database = tmp_path / 'nested' / 'manager.sqlite3'

    assert main(['--database', str(database), 'add', 'https://example.com/video']) == 0
    capsys.readouterr()
    assert database.is_file()


def test_web_command_has_no_host_option_and_uses_the_fixed_loopback_runner(tmp_path, monkeypatch):
    called_with = None

    def fake_run_web(database, download_directory, port):
        nonlocal called_with
        called_with = (database, download_directory, port)

    monkeypatch.setattr('manager.web.run_web', fake_run_web)

    database = tmp_path / 'jobs.sqlite3'
    assert main(['--database', str(database), 'web', '--port', '9000']) == 0
    assert called_with == (database, Path('downloads'), 9000)
    with pytest.raises(SystemExit) as error:
        main(['web', '--host', '0.0.0.0'])
    assert error.value.code == 2
