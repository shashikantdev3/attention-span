"""Fetch an article and keep its readable text, so the AI summarises the real source."""
import html
import re

from .http import get

DROP = re.compile(r"<(script|style|noscript|svg|nav|footer|header|aside|form|iframe)[^>]*>.*?</\1>", re.S | re.I)


def article_text(url, limit=6000):
    try:
        r = get(url, timeout=20, retries=0)
    except Exception:
        return ""
    if r.status_code != 200 or "html" not in r.headers.get("content-type", ""):
        return ""
    page = r.text
    m = re.search(r"<article[^>]*>(.*?)</article>", page, re.S | re.I)
    body = m.group(1) if m else page
    body = DROP.sub(" ", body)
    paras = re.findall(r"<(?:p|h1|h2|h3|li)[^>]*>(.*?)</(?:p|h1|h2|h3|li)>", body, re.S | re.I)
    text = " ".join(re.sub(r"<[^>]+>", " ", p) for p in paras)
    text = " ".join(html.unescape(text).split())
    return text[:limit]
