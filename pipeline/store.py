"""Cumulative JSON storage. Nothing is ever deleted; each night adds one edition.

docs/data/editions/index.json      list of editions (date, story count, file)
docs/data/editions/YYYY-MM.json    all editions of that month, keyed by date
state/seen.json                    URLs already published, so a story is not repeated the next day
state/pending_terms.json           new terms proposed by the writer, waiting for your approval
"""
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .group import norm_url

ROOT = Path(__file__).resolve().parent.parent
EDITIONS = ROOT / "docs" / "data" / "editions"
STATE = ROOT / "state"


def read(path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default


def write(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    tmp.replace(path)


def slug(text, n=60):
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s[:n].rstrip("-")


def seen_before(story, edition_date):
    """True if every URL of the story was already published in an earlier edition."""
    seen = read(STATE / "seen.json", {})
    urls = {norm_url(i["url"]) for i in story["items"]}
    earlier = {u for u in urls if seen.get(u) and seen[u] < edition_date}
    if bool(urls) and earlier == urls:
        return True
    # the maker's own post was already published: later coverage of it is not a new story
    from .curate import is_official
    return any(is_official(u) for u in earlier)


def save_edition(edition_date, stories, stats):
    month = edition_date[:7]
    month_file = EDITIONS / f"{month}.json"
    data = read(month_file, {"month": month, "editions": {}})
    for rank, s in enumerate(stories, 1):
        s["rank"] = rank
        s["id"] = f"{edition_date}-{slug(s['title'])}"
        s["date"] = edition_date
    data["editions"][edition_date] = {
        "date": edition_date,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "stories": stories, "stats": stats,
    }
    data["editions"] = dict(sorted(data["editions"].items()))
    write(month_file, data)

    index = read(EDITIONS / "index.json", {"editions": []})
    entry = {"date": edition_date, "file": f"{month}.json", "count": len(stories),
             "spotlight": sum(1 for s in stories if s.get("spotlight")),
             "lead": stories[0]["title"] if stories else ""}
    index["editions"] = [e for e in index["editions"] if e["date"] != edition_date] + [entry]
    index["editions"].sort(key=lambda e: e["date"], reverse=True)
    index["latest"] = index["editions"][0]["date"] if index["editions"] else None
    index["updated"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    write(EDITIONS / "index.json", index)

    # remember published URLs (keep 21 days)
    seen = read(STATE / "seen.json", {})
    for s in stories:
        for src in s["sources"]:
            seen.setdefault(norm_url(src["url"]), edition_date)
    cutoff = (datetime.fromisoformat(edition_date) - timedelta(days=21)).date().isoformat()
    seen = {u: d for u, d in seen.items() if d >= cutoff}
    write(STATE / "seen.json", seen)


def add_pending_terms(edition_date, stories, known_terms):
    # a re-run of the same day replaces that day's proposals instead of adding to them
    pending = [t for t in read(STATE / "pending_terms.json", []) if t.get("first_seen") != edition_date]
    rejected = {t.lower() for t in read(STATE / "rejected_terms.json", [])}
    have = {t["term"].lower() for t in pending} | {t.lower() for t in known_terms} | rejected
    for s in stories:
        for t in s.get("new_terms", []):
            if t["term"].lower() in have:
                continue
            have.add(t["term"].lower())
            pending.append({**t, "first_seen": edition_date, "story": s["id"],
                            "source": s["sources"][0]["url"] if s["sources"] else ""})
    write(STATE / "pending_terms.json", pending)
    return pending
