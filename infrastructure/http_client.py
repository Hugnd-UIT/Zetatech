from __future__ import annotations

import threading
from typing import Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from config import MAX_POOL_SIZE

RETRIES = 3
BACKOFF = 0.5
RETRY_CODES = (429, 500, 502, 503, 504)

_lock = threading.Lock()
_session: Optional[requests.Session] = None
_pool = 0


def _retry() -> Retry:
    return Retry(
        total=RETRIES,
        connect=RETRIES,
        read=RETRIES,
        status=RETRIES,
        backoff_factor=BACKOFF,
        status_forcelist=RETRY_CODES,
        allowed_methods=frozenset({"GET", "HEAD", "OPTIONS"}),
        raise_on_status=False,
    )


def _adapter(size: int) -> HTTPAdapter:
    return HTTPAdapter(
        pool_connections=size,
        pool_maxsize=size,
        max_retries=_retry(),
    )


def _mount(session: requests.Session, size: int) -> None:
    adapter = _adapter(size)
    session.mount("https://", adapter)
    session.mount("http://", adapter)


def get_session(pool_size: int = MAX_POOL_SIZE) -> requests.Session:
    global _session, _pool

    size = min(max(pool_size, 1), MAX_POOL_SIZE)
    with _lock:
        if _session is None:
            _session = requests.Session()
            _mount(_session, size)
            _pool = size
            return _session

        if size > _pool:
            _mount(_session, size)
            _pool = size

        return _session
