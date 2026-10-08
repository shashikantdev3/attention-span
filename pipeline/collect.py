"""Step 1: collect candidate items from every source for the time window.

Every item gets the same shape so later steps do not care where it came from:
{id, source, source_name, url, title, text, published, weight, lab, person, topic, original, points}
Items without a publish date are dropped: we cannot prove they are from the last 24 hours.
"""
import calendar
import html
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path

import feedparser

from .http import get

ROOT = Path(__file__).resolve().parent.parent

AI_WORDS = re.compile(
    r"\b(llms?|gpt[-\w.]*|chatgpt|claude|gemini|gemma|anthropic|openai|deepmind|mistral|llama|qwen|deepseek|"
    r"copilot|machine learning|deep learning|neural|transformers?|diffusion|language models?|foundation models?|"
    r"reasoning models?|multimodal|agents?|agentic|mcp|rag|embeddings?|fine-?tun\w*|inference|chatbots?|"
    r"artificial intelligence|genai|generative|hugging ?face|open-?weights?|tokens?|prompt\w*|vibe coding|"
    r"openclaw|cursor|codex|grok|xai|perplexity|nvidia|gpus?|tpus?)\b",
    re.I,
)
AI_CAPS = re.compile(r"\bA\.?I\b")  # case-sensitive "AI", so words like 'said' do not match


def looks_ai(text):
    return bool(AI_WORDS.search(text) or AI_CAPS.search(text))


def clean(text, limit=1500):
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = html.unescape(text)
    return " ".join(text.split())[:limit]


def iso(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def make(src, url, title, text, published, **extra):
    item = {
        "source": src["id"], "source_name": src["name"], "url": url, "title": clean(title, 300),
        "text": clean(text), "published": iso(published), "weight": src.get("weight", 1),
        "lab": src.get("lab"), "person": src.get("person"), "topic": src.get("topic"),
        "original": bool(src.get("original")), "points": 0,
    }
    item.update(extra)
    return item


def from_rss(src, since):
    r = get(src["url"], timeout=src.get("timeout", 25))
    r.raise_for_status()
    feed = feedparser.parse(r.content)
    out = []
    for e in feed.entries:
        t = e.get("published_parsed") or e.get("updated_parsed")
        if not t:
            continue
        published = datetime.fromtimestamp(calendar.timegm(t), tz=timezone.utc)
        if published < since or published > datetime.now(timezone.utc) + timedelta(hours=2):
            continue
        body = ""
        if e.get("content"):
            body = e.content[0].get("value", "")
        body = body or e.get("summary", "")
        title, link = e.get("title", ""), e.get("link", "")
        if not title or not link:
            continue
        if src.get("filter_ai") and not looks_ai(f"{title} {clean(body, 600)}"):
            continue
        out.append(make(src, link, title, body, published))
    return out


def from_hn(src, since):
    ts = int(since.timestamp())
    url = ("https://hn.algolia.com/api/v1/search?tags=story&hitsPerPage=300"
           f"&numericFilters=created_at_i>{ts},points>={src.get('min_points', 40)}")
    hits = get(url).json().get("hits", [])
    out = []
    for h in hits:
        title = h.get("title") or ""
        if not looks_ai(title):
            continue
        hn_link = f"https://news.ycombinator.com/item?id={h['objectID']}"
        published = datetime.fromtimestamp(h["created_at_i"], tz=timezone.utc)
        out.append(make(src, h.get("url") or hn_link, title, h.get("story_text") or "", published,
                        points=h.get("points", 0), discussion=hn_link, comments=h.get("num_comments", 0)))
    return out


def from_hf_papers(src, since):
    data = get("https://huggingface.co/api/daily_papers?limit=100").json()
    out = []
    for d in data:
        paper = d.get("paper", {})
        up = paper.get("upvotes", d.get("upvotes", 0)) or 0
        if up < src.get("min_upvotes", 10):
            continue
        when = d.get("publishedAt") or paper.get("publishedAt")
        if not when:
            continue
        published = datetime.fromisoformat(when.replace("Z", "+00:00"))
        # daily papers are curated a day or two after arXiv posting, so allow a wider window
        if published < since - timedelta(days=2):
            continue
        pid = paper.get("id")
        out.append(make(src, f"https://arxiv.org/abs/{pid}", paper.get("title", d.get("title", "")),
                        paper.get("summary", ""), published, points=up,
                        discussion=f"https://huggingface.co/papers/{pid}", original=True))
    return out


def from_hf_models(src, since):
    data = get("https://huggingface.co/api/models?sort=trendingScore&limit=40").json()
    oldest = datetime.now(timezone.utc) - timedelta(days=src.get("max_age_days", 4))
    out = []
    for m in data:
        created = m.get("createdAt")
        if not created:
            continue
        published = datetime.fromisoformat(created.replace("Z", "+00:00"))
        if published < oldest:
            continue
        mid = m["id"]
        org = mid.split("/")[0]
        out.append(make(src, f"https://huggingface.co/{mid}", mid,
                        f"New model {mid} by {org}. Pipeline: {m.get('pipeline_tag') or 'unknown'}. "
                        f"Likes: {m.get('likes', 0)}. Downloads: {m.get('downloads', 0)}.",
                        published, points=m.get("likes", 0), original=True))
    return out


def from_github(src, since):
    oldest = (datetime.now(timezone.utc) - timedelta(days=src.get("max_age_days", 4))).strftime("%Y-%m-%d")
    seen, out = set(), []
    for topic in ("llm", "ai-agents", "mcp", "generative-ai"):
        q = f"topic:{topic} created:>{oldest} stars:>={src.get('min_stars', 150)}"
        r = get("https://api.github.com/search/repositories", params={"q": q, "sort": "stars", "per_page": 15})
        if r.status_code != 200:
            continue
        for repo in r.json().get("items", []):
            if repo["full_name"] in seen:
                continue
            seen.add(repo["full_name"])
            published = datetime.fromisoformat(repo["created_at"].replace("Z", "+00:00"))
            out.append(make(src, repo["html_url"], f"{repo['full_name']}: {repo.get('description') or ''}",
                            f"{repo.get('description') or ''} Stars: {repo['stargazers_count']}. "
                            f"Language: {repo.get('language')}.", published,
                            points=repo["stargazers_count"], original=True))
    return out


def from_inbox(src, since):
    """state/inbox.txt: one link per line, optionally 'URL | note'. Use it for X posts and anything the feeds miss."""
    path = ROOT / src["path"]
    if not path.exists():
        return []
    out = []
    now = datetime.now(timezone.utc)
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        url, _, note = (p.strip() for p in line.partition("|"))
        out.append(make(src, url, note or url, note, now, original=True, inbox=True))
    return out


HANDLERS = {"rss": from_rss, "hn": from_hn, "hf_papers": from_hf_papers,
            "hf_models": from_hf_models, "github": from_github, "inbox": from_inbox}


def load_sources():
    cfg = json.loads((ROOT / "pipeline" / "sources.json").read_text(encoding="utf-8"))["sources"]
    people = json.loads((ROOT / "docs" / "data" / "people.json").read_text(encoding="utf-8"))
    for p in people:
        for i, f in enumerate(p.get("feeds", [])):
            cfg.append({"id": f"person-{p['id']}-{i}", "name": f"{p['name']} ({f['kind']})", "kind": "rss",
                        "url": f["url"], "weight": 2, "person": p["id"], "original": True})
    return [s for s in cfg if s.get("enabled", True)]


def _run(src, since):
    t0 = time.time()
    try:
        got = HANDLERS[src["kind"]](src, since)
        return got, {"ok": True, "items": len(got), "secs": round(time.time() - t0, 1)}
    except Exception as exc:
        return [], {"ok": False, "error": f"{type(exc).__name__}: {str(exc)[:120]}", "secs": round(time.time() - t0, 1)}


def collect(hours=24, log=print):
    """Fetch all sources in parallel. One failing source never stops the run."""
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    sources = load_sources()
    items, health = [], {}
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(_run, s, since): s for s in sources}
        for fut in as_completed(futures):
            src = futures[fut]
            got, status = fut.result()
            items.extend(got)
            health[src["id"]] = status
            log(f"  {src['id']:28} {'ok  ' if status['ok'] else 'FAIL'} "
                f"{status.get('items', status.get('error'))}  ({status['secs']}s)")
    for i, it in enumerate(items):
        it["id"] = f"i{i}"
    return items, health
