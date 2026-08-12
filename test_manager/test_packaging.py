from pathlib import Path


def test_manager_package_is_included_in_wheel_and_sdist():
    pyproject = Path(__file__).parents[1] / 'pyproject.toml'
    contents = pyproject.read_text(encoding='utf-8')

    assert '    "/manager",' in contents
    assert 'packages = ["yt_dlp", "manager"]' in contents
