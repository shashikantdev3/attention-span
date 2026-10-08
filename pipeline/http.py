"""One shared HTTP helper: polite user agent, timeouts and a small retry."""
import time

import requests

UA = "AttentionSpan/1.0 (+https://github.com/shashikantdev3/attention-span; daily AI digest)"
_session = requests.Session()
_session.headers.update({"User-Agent": UA, "Accept-Language": "en"})


def get(url, timeout=20, retries=1, **kwargs):
    last = None
    for attempt in range(retries + 1):
        try:
            r = _session.get(url, timeout=timeout, **kwargs)
            if r.status_code in (429, 502, 503, 504) and attempt < retries:
                time.sleep(2 * (attempt + 1))
                continue
            return r
        except requests.RequestException as exc:
            last = exc
            if attempt < retries:
                time.sleep(2 * (attempt + 1))
    raise last


def post(url, timeout=60, **kwargs):
    return _session.post(url, timeout=timeout, **kwargs)
