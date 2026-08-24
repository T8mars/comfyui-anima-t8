import urllib.error
import urllib.request
import ssl
from unittest import mock

import pytest

from http_retry import ROUTE_ATTEMPTS, urlopen_with_route_retry


def test_route_order_is_direct_proxy_direct_proxy():
    assert ROUTE_ATTEMPTS == (
        ("direct", False),
        ("proxy", True),
        ("direct", False),
        ("proxy", True),
    )


def test_transport_failures_use_all_routes(monkeypatch):
    used_proxy_maps = []
    response = object()

    class Opener:
        def __init__(self, attempt):
            self.attempt = attempt

        def open(self, request, timeout):
            if self.attempt < 3:
                raise urllib.error.URLError("offline")
            return response

    def fake_proxy_handler(proxies=None):
        used_proxy_maps.append(proxies)
        return ("proxy", proxies)

    openers = iter(Opener(i) for i in range(4))
    monkeypatch.setattr(urllib.request, "ProxyHandler", fake_proxy_handler)
    monkeypatch.setattr(urllib.request, "build_opener", lambda *handlers: next(openers))
    sleep = mock.Mock()
    monkeypatch.setattr("http_retry.time.sleep", sleep)

    assert urlopen_with_route_retry("https://example.com", timeout=3) is response
    assert used_proxy_maps == [{}, None, {}, None]
    assert [call.args[0] for call in sleep.call_args_list] == [1, 5, 10]


def test_retryable_http_status_falls_back(monkeypatch):
    response = object()
    error = urllib.error.HTTPError("https://example.com", 503, "busy", {}, None)
    opener = mock.Mock()
    opener.open.side_effect = [error, response]
    monkeypatch.setattr("http_retry._build_opener", lambda *_: opener)
    sleep = mock.Mock()
    monkeypatch.setattr("http_retry.time.sleep", sleep)

    assert urlopen_with_route_retry("https://example.com", timeout=3) is response
    assert opener.open.call_count == 2
    sleep.assert_called_once_with(1)


def test_http_500_is_not_retried(monkeypatch):
    error = urllib.error.HTTPError("https://example.com", 500, "failed", {}, None)
    opener = mock.Mock()
    opener.open.side_effect = error
    monkeypatch.setattr("http_retry._build_opener", lambda *_: opener)

    with pytest.raises(urllib.error.HTTPError):
        urlopen_with_route_retry("https://example.com", timeout=3)

    assert opener.open.call_count == 1


def test_business_4xx_is_not_retried(monkeypatch):
    error = urllib.error.HTTPError("https://example.com", 400, "bad request", {}, None)
    opener = mock.Mock()
    opener.open.side_effect = error
    monkeypatch.setattr("http_retry._build_opener", lambda *_: opener)

    with pytest.raises(urllib.error.HTTPError) as raised:
        urlopen_with_route_retry("https://example.com", timeout=3)

    assert raised.value.code == 400
    assert opener.open.call_count == 1


def test_tls_eof_while_consuming_body_uses_next_route(monkeypatch):
    first = mock.Mock()
    first.read.side_effect = ssl.SSLEOFError(
        8, "EOF occurred in violation of protocol"
    )
    second = mock.Mock()
    second.read.return_value = b"complete"
    opener = mock.Mock()
    opener.open.side_effect = [first, second]
    monkeypatch.setattr("http_retry._build_opener", lambda *_: opener)
    sleep = mock.Mock()
    monkeypatch.setattr("http_retry.time.sleep", sleep)

    result = urlopen_with_route_retry(
        "https://example.com",
        timeout=3,
        consume=lambda response: response.read(),
    )

    assert result == b"complete"
    assert opener.open.call_count == 2
    sleep.assert_called_once_with(1)
    first.close.assert_called_once()
    second.close.assert_called_once()
