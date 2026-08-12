from datetime import timedelta

import pytest

from manager.cookies import (
    CHROMIUM_COOKIE_UNAVAILABLE_MESSAGE, CookieSourceError, CookieWorkflowStore, cookie_error, cookie_options,
    is_cookie_load_error, parse_cookie_preference,
)


@pytest.mark.parametrize('browser', ['chrome', 'edge', 'firefox', 'brave'])
def test_browser_cookie_options_are_passed_directly(browser):
    preference = parse_cookie_preference('browser', browser)

    assert cookie_options(preference) == {'cookiesfrombrowser': (browser,)}


def test_file_cookie_options_use_an_in_memory_text_stream():
    stream = cookie_options(parse_cookie_preference('file'), '# Netscape HTTP Cookie File\n')['cookiefile']

    assert stream.read() == '# Netscape HTTP Cookie File\n'
    assert not isinstance(stream, str)


def test_file_workflow_expires_without_durable_state():
    store = CookieWorkflowStore(timedelta(milliseconds=1))
    token = store.create('https://example.com/video', parse_cookie_preference('file'), 'secret-cookie')
    store.discard(token)

    with pytest.raises(CookieSourceError, match='expired'):
        store.get(token, 'https://example.com/video')


def test_chromium_cookie_database_lock_has_the_friendly_fallback_message():
    edge = parse_cookie_preference('browser', 'edge')
    error = RuntimeError('Could not copy Chrome cookie database')

    assert is_cookie_load_error(error)
    assert cookie_error(edge, error) == CHROMIUM_COOKIE_UNAVAILABLE_MESSAGE


def test_permission_denied_is_recognised_as_a_cookie_load_error():
    assert is_cookie_load_error(RuntimeError('Permission denied: Cookies'))
