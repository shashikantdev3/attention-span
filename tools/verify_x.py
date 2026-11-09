"""Check X post links through X's official oEmbed endpoint (publish.twitter.com). No login, no scraping.

    python tools/verify_x.py OUT.json URL [URL ...]
"""
import html
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

EPOCH = 1288834974657


def verify(urls, gap=1.05):
    out = []
    for u in urls:
        m = re.search(r"(?:x|twitter)\.com/([^/]+)/status/(\d+)", u)
        if not m:
            out.append({"url": u, "fail": "not a status link"})
            continue
        handle, sid = m.groups()
        q = "https://publish.twitter.com/oembed?" + urllib.parse.urlencode(
            {"url": f"https://x.com/{handle}/status/{sid}", "omit_script": 1, "dnt": "true", "hide_thread": "true"})
        try:
            d = json.load(urllib.request.urlopen(q, timeout=20))
            text = html.unescape(re.sub(r"\s+", " ", re.sub("<[^>]+>", " ", d["html"]))).strip()
            when = datetime.fromtimestamp(((int(sid) >> 22) + EPOCH) / 1000, tz=timezone.utc)
            out.append({"url": f"https://x.com/{handle}/status/{sid}", "author": d["author_url"].rsplit("/", 1)[-1],
                        "posted_at": when.strftime("%Y-%m-%dT%H:%M:%SZ"), "text": text[:400]})
        except Exception as exc:  # noqa: BLE001  deleted, protected or not found
            out.append({"url": u, "fail": str(exc)[:120]})
        time.sleep(gap)
    return out


if __name__ == "__main__":
    res = verify(sys.argv[2:])
    with open(sys.argv[1], "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=0)
    print(len(res), "done", sum("fail" in r for r in res), "failed")
