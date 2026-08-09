import urllib.error
import urllib.request
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

    assert urlopen_with_route_retry("https://example.com", timeout=3) is response
    assert used_proxy_maps == [{}, None, {}, None]


def test_retryable_http_status_falls_back(monkeypatch):
    response = object()
    error = urllib.error.HTTPError("https://example.com", 503, "busy", {}, None)
    opener = mock.Mock()
    opener.open.side_effect = [error, response]
    monkeypatch.setattr("http_retry._build_opener", lambda *_: opener)

    assert urlopen_with_route_retry("https://example.com", timeout=3) is response
    assert opener.open.call_count == 2


def test_business_4xx_is_not_retried(monkeypatch):
    error = urllib.error.HTTPError("https://example.com", 400, "bad request", {}, None)
    opener = mock.Mock()
    opener.open.side_effect = error
    monkeypatch.setattr("http_retry._build_opener", lambda *_: opener)

    with pytest.raises(urllib.error.HTTPError) as raised:
        urlopen_with_route_retry("https://example.com", timeout=3)

    assert raised.value.code == 400
    assert opener.open.call_count == 1
