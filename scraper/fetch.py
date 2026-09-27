"""Shared HTTP session: browser-like headers, retries and a polite delay between requests."""
import logging
import time

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

log = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
DELAY_SECONDS = 0.8
TIMEOUT_SECONDS = 25

_session = None
_last_request = 0.0


def session():
    global _session
    if _session is None:
        _session = requests.Session()
        _session.headers.update({
            "User-Agent": USER_AGENT,
            "Accept-Language": "en-IN,en;q=0.9",
        })
        retry = Retry(total=2, backoff_factor=2, status_forcelist=(429, 500, 502, 503, 504))
        _session.mount("https://", HTTPAdapter(max_retries=retry))
    return _session


def get_text(url):
    """GET a URL and return the decoded body. Raises on HTTP errors."""
    global _last_request
    wait = DELAY_SECONDS - (time.monotonic() - _last_request)
    if wait > 0:
        time.sleep(wait)
    log.debug("GET %s", url)
    resp = session().get(url, timeout=TIMEOUT_SECONDS)
    _last_request = time.monotonic()
    resp.raise_for_status()
    resp.encoding = resp.encoding if resp.encoding and resp.encoding.lower() != "iso-8859-1" else "utf-8"
    return resp.text
