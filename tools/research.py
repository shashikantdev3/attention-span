"""Find the AI news stories and X posts the feeds missed, using Claude with web search (Anthropic API).

    python tools/research.py --since 2026-10-31T18:30Z --until 2026-11-03T13:45Z --focus news
    python tools/research.py --since ... --until ... --focus labs      (X posts from labs and leaders)
    python tools/research.py --since ... --until ... --focus people    (X posts from researchers, teachers, investors)

X compliance: x.com and twitter.com are blocked domains for the search, so Claude never reads X itself.
Posts are only taken from public coverage (newsletters, news sites, digests) that link to them, and every
status URL is later checked through X's official oEmbed endpoint before it is shown on the site.
Each call is capped (--searches, default 8) and the token use and cost are printed. Results go to
state/research/<until-date>-<focus>.json. Nothing is published by this script.
"""
import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass

EPOCH = 1288834974657
STATUS = re.compile(r"https?://(?:x|twitter)\.com/([A-Za-z0-9_]{1,15})/status/(\d{15,25})")

FOCUS = {
    "news": ("the most important AI news stories (launches, models, research, funding, policy, security, markets, chips). "
             "For each give a readable, non-paywalled source URL, preferably the maker's own announcement or a free outlet "
             "(not Bloomberg, WSJ, FT, Reuters or NYT), and its publish date. Up to 25 stories."),
    "labs": ("the most notable AI posts on X (Twitter) by AI labs and companies (OpenAI, Anthropic, Google DeepMind, Meta, "
             "xAI, Mistral, DeepSeek, Qwen, Moonshot, MiniMax, NVIDIA, Hugging Face, Microsoft, GitHub, Cursor, Cohere, "
             "Apple) and their leaders. Up to 25 posts."),
    "people": ("the most notable, discussed AI posts on X (Twitter) by well-known researchers, engineers, teachers, "
               "investors and analysts worldwide (for example Karpathy, LeCun, Andrew Ng, Jim Fan, Simon Willison, "
               "Ethan Mollick, Nathan Lambert, swyx, Francois Chollet), including strong takes and useful threads. "
               "Skip crypto, anonymous rumour accounts, politics-only posts and memes. Up to 25 posts."),
}

PRICE = {"claude-sonnet-5-5": (2.0, 10.0), "claude-haiku-5-5": (1.0, 5.0), "claude-opus-5-5": (5.0, 25.0)}


def snowflake_time(i):
    return datetime.fromtimestamp(((int(i) >> 22) + EPOCH) / 1000, tz=timezone.utc)


def ask(model, prompt, searches, key):
    body = {"model": model, "max_tokens": 8000,
            "tools": [{"type": "web_search_20250305", "name": "web_search", "max_uses": searches,
                       "blocked_domains": ["x.com", "twitter.com", "nitter.net", "xcancel.com"]}],
            "messages": [{"role": "user", "content": prompt}]}
    headers = {"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"}
    usage = {"input_tokens": 0, "output_tokens": 0, "searches": 0}
    text = ""
    for _ in range(4):  # a server-tool turn can pause; send it back to continue
        r = requests.post("https://api.anthropic.com/v1/messages", json=body, headers=headers, timeout=170)
        if r.status_code != 200:
            sys.exit(f"API error {r.status_code}: {r.text[:300]}")
        data = r.json()
        u = data.get("usage") or {}
        usage["input_tokens"] += int(u.get("input_tokens") or 0) + int(u.get("cache_read_input_tokens") or 0)
        usage["output_tokens"] += int(u.get("output_tokens") or 0)
        usage["searches"] += int((u.get("server_tool_use") or {}).get("web_search_requests") or 0)
        text += "".join(b.get("text", "") for b in data["content"] if b.get("type") == "text")
        if data.get("stop_reason") != "pause_turn":
            break
        body["messages"] = body["messages"] + [{"role": "assistant", "content": data["content"]}]
    return text, usage


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", required=True)
    ap.add_argument("--until", required=True)
    ap.add_argument("--focus", choices=FOCUS, default="news")
    ap.add_argument("--searches", type=int, default=8)
    ap.add_argument("--model", default="claude-sonnet-5-5")
    args = ap.parse_args()
    key = os.getenv("ANTHROPIC_API_KEY") or sys.exit("ANTHROPIC_API_KEY missing in .env")
    since = datetime.fromisoformat(args.since.replace("Z", "+00:00"))
    until = datetime.fromisoformat(args.until.replace("Z", "+00:00"))

    posts = args.focus != "news"
    prompt = (f"You help edit a daily AI news site for AI builders. Find {FOCUS[args.focus]} "
              f"Window: {since:%d %b %Y %H:%M} UTC to {until:%d %b %Y %H:%M} UTC.\n"
              "Search news sites, newsletters and digests (latent.space AINews, anothercodingblog.com, theneuron.ai, "
              "The Decoder, TechCrunch, The Verge, Simon Willison's blog, aiweekly.co, digg.com/ai, Hacker News, "
              "GitHub digest issues).\n")
    if posts:
        prompt += ("Only report a post if a page you read shows its full status URL (https://x.com/<handle>/status/<digits>). "
                   "Never construct or guess a status ID. Note if a claim was later corrected or disputed.\n"
                   'Answer with JSON only: {"posts": [{"url": "...", "author": "Name (@handle)", "about": "one plain sentence", '
                   '"found_on": "page URL"}]}')
    else:
        prompt += ('Answer with JSON only: {"stories": [{"headline": "...", "url": "...", "also": ["other readable URLs"], '
                   '"date": "YYYY-MM-DD", "why": "one plain sentence"}]}')

    t0 = time.time()
    text, usage = ask(args.model, prompt, args.searches, key)
    m = re.search(r"\{.*\}", text, re.S)
    try:
        result = json.loads(m.group(0)) if m else {}
    except json.JSONDecodeError:
        result = {"raw": text}
    if posts:
        kept, dropped = [], []
        for p in result.get("posts", []):
            s = STATUS.search(p.get("url", ""))
            if not s:
                dropped.append((p.get("url"), "not a status URL")); continue
            when = snowflake_time(s.group(2))
            if not (since <= when <= until):
                dropped.append((p.get("url"), f"outside window ({when:%d %b %H:%M})")); continue
            p["url"] = f"https://x.com/{s.group(1)}/status/{s.group(2)}"
            p["posted_at"] = when.strftime("%Y-%m-%dT%H:%M:%SZ")
            kept.append(p)
        result = {"posts": kept, "dropped": dropped}
    pin, pout = PRICE.get(args.model, (2.0, 10.0))
    cost = usage["input_tokens"] / 1e6 * pin + usage["output_tokens"] / 1e6 * pout + usage["searches"] * 0.01
    result["meta"] = {"focus": args.focus, "since": args.since, "until": args.until, "model": args.model,
                      "usage": usage, "cost_usd": round(cost, 3), "seconds": round(time.time() - t0)}
    out = ROOT / "state" / "research" / f"{until:%Y-%m-%d}-{args.focus}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    n = len(result.get("posts", result.get("stories", [])))
    print(f"{args.focus}: {n} kept, {len(result.get('dropped', []))} dropped; {usage['searches']} searches, "
          f"{usage['input_tokens']:,} in / {usage['output_tokens']:,} out tokens, about ${cost:.2f}, {result['meta']['seconds']}s -> {out}")


if __name__ == "__main__":
    main()
