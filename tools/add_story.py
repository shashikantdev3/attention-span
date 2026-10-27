"""Add a story the nightly run missed to an existing edition.

    python tools/add_story.py URL [URL ...] --date 2026-10-10 [--rank 2]

The first URL should be the original (the maker's own post); any others are coverage of the same news.
The story goes through the same writer and fact-checker as the nightly run, so it is only added if every
claim is in the sources. It is marked as added by the editor, and the edition keeps its original time.
Nothing is committed: review, then publish with git as usual.
"""
import argparse
import json
import re
import sys
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass

from pipeline import store  # noqa: E402
from pipeline.curate import is_official, write_story  # noqa: E402
from pipeline.extract import article_text  # noqa: E402
from pipeline.http import get  # noqa: E402

DATA = ROOT / "docs" / "data"


def meta_tag(html, prop):
    m = re.search(rf'<meta[^>]+(?:property|name)="{re.escape(prop)}"[^>]+content="([^"]*)"', html) or \
        re.search(rf'<meta[^>]+content="([^"]*)"[^>]+(?:property|name)="{re.escape(prop)}"', html)
    return unescape(m.group(1)).strip() if m else ""


def feed_for(url):
    """The source in pipeline/sources.json on the same site, if any (gives its name and lab)."""
    host = urlsplit(url).netloc.lower().removeprefix("www.")
    for src in json.loads((ROOT / "pipeline" / "sources.json").read_text(encoding="utf-8"))["sources"]:
        if src.get("url") and urlsplit(src["url"]).netloc.lower().removeprefix("www.") == host:
            return src
    return {}


def item_for(url, n):
    r = get(url, timeout=25)
    r.raise_for_status()
    html = r.text
    title = meta_tag(html, "og:title") or unescape(re.search(r"<title>(.*?)</title>", html, re.S).group(1)).strip()
    published = meta_tag(html, "article:published_time")
    if published:
        published = datetime.fromisoformat(re.sub(r"([+-]\d\d)(\d\d)$", r"\1:\2", published.replace("Z", "+00:00"))).astimezone(timezone.utc)  # "+0000" too
        published = published.strftime("%Y-%m-%dT%H:%M:%SZ")
    src = feed_for(url)
    original = is_official(url) or bool(src.get("original"))
    return {"source": src.get("id", "editor"), "source_name": src.get("name") or meta_tag(html, "og:site_name")
            or urlsplit(url).netloc, "url": url, "title": title,
            "text": meta_tag(html, "og:description") or article_text(url)[:600],
            "published": published or None, "weight": src.get("weight", 2), "lab": src.get("lab"),
            "person": None, "topic": None, "original": original, "points": 0, "id": f"e{n}"}


def main():
    ap = argparse.ArgumentParser(description="Add a missed story to an edition")
    ap.add_argument("urls", nargs="+")
    ap.add_argument("--date", required=True, help="edition date, for example 2026-10-10")
    ap.add_argument("--rank", type=int, default=None, help="position in the edition (default: last)")
    ap.add_argument("--topic", default=None)
    args = ap.parse_args()

    month_file = DATA / "editions" / f"{args.date[:7]}.json"
    month = store.read(month_file, None)
    if not month or args.date not in month["editions"]:
        sys.exit(f"There is no edition for {args.date}.")
    ed = month["editions"][args.date]
    known = {s["url"] for st in ed["stories"] for s in st["sources"]}
    if any(u in known for u in args.urls):
        sys.exit("That link is already in this edition.")

    items = [item_for(u, n) for n, u in enumerate(args.urls)]
    for it in items:
        it["published"] = it["published"] or ed["generated_at"]
        print(f"  {it['source_name']}: {it['title'][:90]} ({it['published']})")
    story = {"cid": "editor", "items": items, "sources": sorted({i["source"] for i in items}), "buzz": len(items)}

    meta = json.loads((DATA / "meta.json").read_text(encoding="utf-8"))
    concepts = json.loads((DATA / "concepts.json").read_text(encoding="utf-8"))
    people = json.loads((DATA / "people.json").read_text(encoding="utf-8"))
    fields, rep = write_story(story, meta, [c["id"] for c in concepts], people, args.topic, print)
    if not fields:
        sys.exit(f"Not added: the fact-check failed twice: {rep['rounds'][-1]['problems'][:3]}")

    fields["editor_reason"] = "Added by the editor after the nightly run missed it."
    fields["added_by_editor"] = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    fields["id"] = f"{args.date}-{store.slug(fields['title'])}"
    fields["date"] = args.date
    stories = ed["stories"]
    pos = len(stories) if not args.rank else max(0, min(len(stories), args.rank - 1))
    stories.insert(pos, fields)
    for rank, s in enumerate(stories, 1):
        s["rank"] = rank
    ed.setdefault("stats", {})["published"] = len(stories)
    store.write(month_file, month)

    index = store.read(DATA / "editions" / "index.json", {"editions": []})
    for e in index["editions"]:
        if e["date"] == args.date:
            e.update(count=len(stories), lead=stories[0]["title"],
                     spotlight=sum(1 for s in stories if s.get("spotlight")))
    store.write(DATA / "editions" / "index.json", index)

    seen = store.read(ROOT / "state" / "seen.json", {})
    for src in fields["sources"]:
        seen.setdefault(store.norm_url(src["url"]), args.date)
    store.write(ROOT / "state" / "seen.json", seen)
    store.add_pending_terms(args.date, stories, [c["term"] for c in concepts])

    sys.path.insert(0, str(ROOT / "tools"))
    from bundle_data import bundle
    bundle()
    print(f"\nAdded at rank {pos + 1} of {len(stories)} in {args.date}: {fields['title']}")
    print(f"  {fields['one_liner']}")
    print("Review it, then publish with git.")


if __name__ == "__main__":
    main()
