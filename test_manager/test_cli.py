import json

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
