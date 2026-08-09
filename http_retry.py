"""Shared urllib retry routing for external, idempotent HTTP reads."""

from __future__ import annotations

import ssl
import urllib.error
import urllib.request
from typing import Optional, Tuple


ROUTE_ATTEMPTS: Tuple[Tuple[str, bool], ...] = (
    ("direct", False),
    ("proxy", True),
    ("direct", False),
    ("proxy", True),
)

RETRYABLE_HTTP_STATUSES = frozenset({429, 500, 502, 503, 504})


def _build_opener(use_proxy: bool, context: Optional[ssl.SSLContext]):
    proxy_handler = urllib.request.ProxyHandler() if use_proxy else urllib.request.ProxyHandler({})
    handlers = [proxy_handler]
    if context is not None:
        handlers.append(urllib.request.HTTPSHandler(context=context))
    return urllib.request.build_opener(*handlers)


def urlopen_with_route_retry(request, *, timeout: float, context: Optional[ssl.SSLContext] = None):
    """Open an external GET using direct → proxy → direct → proxy.

    Only transport errors and retryable HTTP statuses are retried. Other 4xx
    responses are returned to the caller as ``HTTPError`` immediately.
    """
    last_error = None
    for index, (route_name, use_proxy) in enumerate(ROUTE_ATTEMPTS, start=1):
        try:
            return _build_opener(use_proxy, context).open(request, timeout=timeout)
        except urllib.error.HTTPError as exc:
            last_error = exc
            if exc.code not in RETRYABLE_HTTP_STATUSES or index == len(ROUTE_ATTEMPTS):
                raise
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as exc:
            last_error = exc
            if index == len(ROUTE_ATTEMPTS):
                raise
        print(
            f"[anima_t8] external request attempt {index}/4 via {route_name} failed: "
            f"{last_error}"
        )

    raise last_error  # pragma: no cover - the loop always returns or raises
