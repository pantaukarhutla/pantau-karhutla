"""HTTP for every upstream source: one client setup and one retrying GET."""

from __future__ import annotations

import logging
import os
import time

import httpx

log = logging.getLogger(__name__)

# Sent to every data provider. A contact URL helps them reach the operator;
# set HAZE_CONTACT_URL to the project's public address (no personal accounts).
_CONTACT = os.environ.get("HAZE_CONTACT_URL")
USER_AGENT = f"pantau-karhutla/0.1 (+{_CONTACT})" if _CONTACT else "pantau-karhutla/0.1"


class GiveUp(RuntimeError):
    """Every attempt of a request failed."""


def client(timeout: float = 60.0, connect: float = 20.0) -> httpx.Client:
    """Client with our User-Agent that follows redirects; `timeout` in seconds
    (connecting gets at most `connect` s)."""
    return httpx.Client(
        timeout=httpx.Timeout(timeout, connect=min(timeout, connect)),
        headers={"User-Agent": USER_AGENT},
        follow_redirects=True,
    )


def get(
    c: httpx.Client,
    url: str,
    params: dict | None = None,
    attempts: int = 4,
    pause_s: float = 2.0,
    label: str | None = None,
) -> httpx.Response:
    """GET, retrying transport errors, HTTP 429 and 5xx after pause_s, 2 x pause_s,
    4 x pause_s, ... Any other response is returned as is. `label` replaces the
    URL in logs and errors (for URLs that carry a key)."""
    label = label or url
    for i in range(attempts):
        try:
            r = c.get(url, params=params)
            if r.status_code < 500 and r.status_code != 429:
                return r
            log.warning("HTTP %s from %s", r.status_code, label)
        except httpx.TransportError as exc:
            log.warning("transport error %s from %s", exc, label)
        time.sleep(pause_s * 2**i)
    raise GiveUp(f"giving up on {label}")
