"""Collect X post links that public AI newsletters and digests already link to, then let Claude pick the notable ones.

    python tools/harvest_x.py --since 2026-10-31T18:30Z --until 2026-11-03T13:45Z [--pick 40]

X compliance: this script never requests x.com or twitter.com. It reads newsletter and digest pages
(latent.space AINews, Another Daily AI Newsletter, digg.com/ai, Simon Willison, Techmeme) and takes the
status links those pages publish, with the text around each link. Claude (no web access) then chooses the
notable posts from that list. Every chosen link is checked later through X's official oEmbed endpoint.
Output: state/research/<until-date>-x.json (candidates and picks).
"""
import argparse
import html
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass

EPOCH = 1288834974657
STATUS = re.compile(r"https?://(?:www\.)?(?:x|twitter)\.com/([A-Za-z0-9_]{1,15})/status/(\d{15,25})")
UA = {"User-Agent": "AttentionSpan/1.0 (+https://github.com/shashikantdev3/attention-span)"}
S = requests.Session(); S.headers.update(UA)


def get(url):
    try:
        r = S.get(url, timeout=20)
        return r.text if r.status_code == 200 else ""
    except requests.RequestException:
        return ""


def pages(since, until):
    urls = ["https://digg.com/ai", "https://simonwillison.net/"]
    arch = get("https://www.latent.space/archive")
    urls += ["https://www.latent.space" + p for p in dict.fromkeys(re.findall(r'href="(/p/ainews-[^"/]+/?)"', arch))][:4]
    arch = get("https://www.anothercodingblog.com/archive")
    urls += list(dict.fromkeys(re.findall(r'href="(https://www\.anothercodingblog\.com/p/another-daily-ai-newsletter-[a-z0-9-]+)"', arch)))[:4]
    d = since.date()
    while d <= until.date():
        tm = d.strftime("%y%m%d")
        urls += [f"https://www.techmeme.com/{tm}/p{n}" for n in range(1, 40)]
        d += timedelta(days=1)
    return urls


def text_near(raw, pos, width=260):
    chunk = raw[max(0, pos - 1200): pos + 400]
    chunk = re.sub(r"<[^>]+>", " ", chunk)
    chunk = " ".join(html.unescape(chunk).split())
    return chunk[-width:]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", required=True)
    ap.add_argument("--until", required=True)
    ap.add_argument("--pick", type=int, default=40)
    ap.add_argument("--model", default="claude-sonnet-5-5")
    args = ap.parse_args()
    since = datetime.fromisoformat(args.since.replace("Z", "+00:00"))
    until = datetime.fromisoformat(args.until.replace("Z", "+00:00"))
    lo = (int(since.timestamp() * 1000) - EPOCH) << 22
    hi = (int(until.timestamp() * 1000) - EPOCH) << 22
    have = (ROOT / "docs/data/heads.json").read_text(encoding="utf-8") + (ROOT / "state/heads_skipped.json").read_text(encoding="utf-8")

    t0 = time.time()
    urls = pages(since, until)
    with ThreadPoolExecutor(6) as ex:
        raws = list(ex.map(get, urls))
    cands = {}
    for url, raw in zip(urls, raws):
        for m in STATUS.finditer(raw):
            handle, sid = m.group(1), m.group(2)
            if not (lo <= int(sid) <= hi) or sid in have or handle.lower() in ("techmeme", "share", "intent"):
                continue
            key = f"https://x.com/{handle}/status/{sid}"
            c = cands.setdefault(key, {"url": key, "handle": handle, "seen_on": [], "context": ""})
            if url not in c["seen_on"]:
                c["seen_on"].append(url)
            if len(c["context"]) < 100:
                c["context"] = text_near(raw, m.start())
    cands = sorted(cands.values(), key=lambda c: -len(c["seen_on"]))
    print(f"{len([r for r in raws if r])}/{len(urls)} pages read, {len(cands)} new in-window post links")

    picks = []
    key = os.getenv("ANTHROPIC_API_KEY")
    if cands and key:
        listing = "\n".join(f"{i}. @{c['handle']} (on {len(c['seen_on'])} pages): {c['context'][-220:]}" for i, c in enumerate(cands[:250]))
        prompt = ("These are X posts that AI newsletters and digests linked to, with the text around each link. "
                  f"Pick up to {args.pick} that matter most to people who build with AI: posts from AI labs, their leaders, "
                  "well-known researchers, engineers, teachers and serious analysts; launches, strong takes, useful threads, "
                  "important debates and security incidents. Skip crypto, finance hype, anonymous rumour accounts, "
                  "politics-only posts, memes and news-aggregator accounts. Spread across topics.\n"
                  'Answer with JSON only: {"picks": [{"i": <number>, "about": "one plain sentence on what the post is about, based only on the text given"}]}\n\n'
                  + listing)
        body = {"model": args.model, "max_tokens": 4000, "messages": [{"role": "user", "content": prompt}]}
        try:
            r = requests.post("https://api.anthropic.com/v1/messages", json=body, timeout=240,
                              headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"})
        except requests.RequestException as exc:
            r = None
            print("API call failed:", type(exc).__name__, str(exc)[:200])
        if r is not None and r.status_code == 200:
            data = r.json()
            text = "".join(b.get("text", "") for b in data["content"] if b.get("type") == "text")
            u = data.get("usage", {})
            m = re.search(r"\{.*\}", text, re.S)
            try:
                chosen = json.loads(m.group(0)).get("picks", []) if m else []
            except json.JSONDecodeError:
                chosen = [{"i": int(x)} for x in re.findall(r'"i"\s*:\s*(\d+)', text)]   # a cut-off answer still has its numbers
            for p in chosen:
                if isinstance(p.get("i"), int) and 0 <= p["i"] < len(cands):
                    picks.append({**cands[p["i"]], "about": p.get("about", "")})
            print(f"Claude picked {len(picks)}; {u.get('input_tokens', 0):,} in / {u.get('output_tokens', 0):,} out tokens, "
                  f"about ${u.get('input_tokens', 0) / 1e6 * 2 + u.get('output_tokens', 0) / 1e6 * 10:.2f}")
        elif r is not None:
            print("API error", r.status_code, r.text[:200])
    out = ROOT / "state" / "research" / f"{until:%Y-%m-%d}-x.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"picks": picks, "candidates": cands}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"done in {round(time.time() - t0)}s -> {out}")


if __name__ == "__main__":
    main()
