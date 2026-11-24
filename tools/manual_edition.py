"""Write and check an edition by hand, without the model pipeline.

Use it when the stories were researched and written by an editor (or an assistant with web search)
instead of by run_daily.py. It keeps existing stories and their ids, adds new ones, and runs the
checks that every edition must pass before it is committed.

  python tools/manual_edition.py add --date 2026-11-23 --file stories.json
  python tools/manual_edition.py order --date 2026-11-23 --ids id1,id2,...   (new order; others follow)
  python tools/manual_edition.py drop --date 2026-11-23 --ids id1,id2        (also deletes docs/s/<id>.html)
  python tools/manual_edition.py check --date 2026-11-23
  python tools/manual_edition.py list --date 2026-11-23

stories.json is a JSON list of stories with: title, one_liner, summary, eli5, why_it_matters, topic, type,
labs, people, concepts, spotlight, spotlight_reason, sources [{title, url, name, kind}], published (UTC ISO).
Optional: rank (wanted position in the final list), new_terms, buzz.
After add/order/drop, run python tools/bundle_data.py, then check.
"""
import argparse
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from pipeline import store  # noqa: E402
from pipeline.group import norm_url  # noqa: E402

EDITIONS = ROOT / "docs" / "data" / "editions"
FIELDS = ["title", "one_liner", "summary", "eli5", "why_it_matters", "topic", "type", "labs", "people",
          "concepts", "spotlight", "spotlight_reason", "new_terms", "sources", "buzz", "published", "checked",
          "editor_reason", "added_by_editor", "rank", "id", "date"]
TEXT = ["title", "one_liner", "summary", "eli5", "why_it_matters", "spotlight_reason"]
TOPICS = {"industry", "dev-tools", "policy", "models", "research", "agents", "products", "microsoft", "data-bi"}
TYPES = {"event", "product", "model", "paper", "person", "concept"}
KINDS = {"press", "original", "discussion"}
AGGREGATORS = ("techmeme.com", "biztoc.com", "latent.space/p/ainews", "news.smol.ai", "digg.com", "x.com", "twitter.com",
               "fxtwitter.com", "news.google.com", "flipboard.com", "ground.news", "allsides.com", "msn.com",
               "yahoo.com/news/aggregat", "claude.ai/artifact", "claude.site")
DASHES = ("—", "–", " -- ")


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def window(date):
    """An edition closes at 23:45 IST, so it holds publish times from (D-1) 18:15 UTC to D 18:15 UTC."""
    d = datetime.fromisoformat(date).replace(tzinfo=timezone.utc)
    return d - timedelta(hours=5, minutes=45), d + timedelta(hours=18, minutes=15)


def load(date):
    month_file = EDITIONS / f"{date[:7]}.json"
    data = store.read(month_file, {"month": date[:7], "editions": {}})
    ed = data["editions"].get(date) or {"date": date, "generated_at": now(), "stories": [],
                                       "stats": {"items": 0, "stories": 0, "published": 0, "dropped": 0,
                                                 "llm_calls": 0, "models": {}, "fallbacks": [],
                                                 "editor": "written by hand from web research"}}
    return month_file, data, ed


def save(date, month_file, data, ed):
    stories = ed["stories"]
    for rank, s in enumerate(stories, 1):
        s["rank"] = rank
        s["date"] = date
        s.setdefault("id", f"{date}-{store.slug(s['title'])}")
    ed["stories"] = [{k: s[k] for k in FIELDS if k in s} | {k: v for k, v in s.items() if k not in FIELDS}
                     for s in stories]
    ed.setdefault("stats", {})
    ed["stats"]["published"] = ed["stats"]["stories"] = len(stories)
    ed["stats"]["items"] = max(ed["stats"].get("items", 0), len(stories))
    data["editions"][date] = ed
    data["editions"] = dict(sorted(data["editions"].items()))
    store.write(month_file, data)

    index = store.read(EDITIONS / "index.json", {"editions": []})
    entry = {"date": date, "file": month_file.name, "count": len(stories),
             "spotlight": sum(1 for s in stories if s.get("spotlight")),
             "lead": stories[0]["title"] if stories else ""}
    index["editions"] = [e for e in index["editions"] if e["date"] != date] + ([entry] if stories else [])
    index["editions"].sort(key=lambda e: e["date"], reverse=True)
    index["latest"] = index["editions"][0]["date"] if index["editions"] else None
    index["updated"] = now()
    store.write(EDITIONS / "index.json", index)

    seen = store.read(store.STATE / "seen.json", {})
    for s in stories:
        for src in s["sources"]:
            seen.setdefault(norm_url(src["url"]), date)
    store.write(store.STATE / "seen.json", seen)


def cmd_add(a):
    month_file, data, ed = load(a.date)
    new = json.loads(Path(a.file).read_text(encoding="utf-8"))
    have_ids = {s["id"] for s in ed["stories"]}
    stories = list(ed["stories"])
    for s in sorted(new, key=lambda s: s.get("rank") or 999):
        s = dict(s)
        for k in ("verified_note", "edition"):
            s.pop(k, None)
        s.setdefault("new_terms", [])
        s.setdefault("people", [])
        s.setdefault("spotlight", False)
        s.setdefault("spotlight_reason", "")
        s["buzz"] = s.get("buzz") or len({norm_url(x["url"]).split("/")[2] for x in s["sources"]
                                           if x.get("kind") != "discussion"}) or 1
        s.setdefault("checked", {"model": "editor (written by hand from the sources)", "rounds": 1, "hype_flags": []})
        s.setdefault("editor_reason", "Added by the editor from web research.")
        s.setdefault("added_by_editor", now()[:10])
        s["id"] = f"{a.date}-{store.slug(s['title'])}"
        if s["id"] in have_ids:
            print(f"skip, already in the edition: {s['id']}")
            continue
        have_ids.add(s["id"])
        pos = len(stories) if not s.get("rank") else max(0, min(len(stories), s["rank"] - 1))
        s.pop("rank", None)
        stories.insert(pos, s)
    ed["stories"] = stories
    ed["generated_at"] = now()
    save(a.date, month_file, data, ed)
    print(f"edition {a.date}: {len(stories)} stories")


def cmd_order(a):
    month_file, data, ed = load(a.date)
    want = [i.strip() for i in a.ids.split(",") if i.strip()]
    by_id = {s["id"]: s for s in ed["stories"]}
    missing = [i for i in want if i not in by_id]
    if missing:
        sys.exit(f"unknown ids: {missing}")
    ed["stories"] = [by_id[i] for i in want] + [s for s in ed["stories"] if s["id"] not in want]
    save(a.date, month_file, data, ed)
    cmd_list(a)


def cmd_drop(a):
    month_file, data, ed = load(a.date)
    drop = {i.strip() for i in a.ids.split(",") if i.strip()}
    ed["stories"] = [s for s in ed["stories"] if s["id"] not in drop]
    for i in drop:
        page = ROOT / "docs" / "s" / f"{i}.html"
        if page.exists():
            page.unlink()
            print(f"deleted {page.relative_to(ROOT)}")
    save(a.date, month_file, data, ed)
    cmd_list(a)


def cmd_list(a):
    _, _, ed = load(a.date)
    for s in ed["stories"]:
        print(f"{s['rank']:>2} {'*' if s.get('spotlight') else ' '} {s['id']}\n     {s['title']}")


def cmd_check(a):
    _, _, ed = load(a.date)
    errors, warns = [], []
    start, end = window(a.date)
    stories = ed["stories"]
    if not stories:
        errors.append("edition has no stories")
    ids = [s["id"] for s in stories]
    if len(ids) != len(set(ids)):
        errors.append("duplicate story ids")
    # earlier editions (3 days) for repeats
    earlier = []
    for k in range(1, 4):
        d = (datetime.fromisoformat(a.date) - timedelta(days=k)).date().isoformat()
        earlier += [(d, s) for s in load(d)[2]["stories"]]
    old_urls = {norm_url(x["url"]): d for d, s in earlier for x in s["sources"] if x.get("kind") != "discussion"}
    tok = lambda t: {w for w in re.findall(r"[a-z0-9]+", t.lower()) if len(w) > 3}
    for s in stories:
        sid = s["id"]
        for f in ["title", "one_liner", "summary", "eli5", "why_it_matters", "topic", "type", "sources",
                  "published", "rank", "id", "date"]:
            if s.get(f) in (None, "", []):
                errors.append(f"{sid}: missing {f}")
        for f in TEXT + ["new_terms"]:
            txt = json.dumps(s.get(f, ""), ensure_ascii=False)
            if any(d in txt for d in DASHES):
                errors.append(f"{sid}: dash in {f}")
        if s.get("topic") not in TOPICS:
            errors.append(f"{sid}: unknown topic {s.get('topic')}")
        if s.get("type") not in TYPES:
            errors.append(f"{sid}: unknown type {s.get('type')}")
        if not sid.startswith(a.date + "-") or len(sid) > len(a.date) + 61:
            errors.append(f"{sid}: bad id")
        try:
            p = datetime.fromisoformat(s["published"].replace("Z", "+00:00"))
            if not (start <= p < end):
                (errors if not s.get("allow_outside_window") else warns).append(
                    f"{sid}: published {s['published']} outside window {start:%Y-%m-%dT%H:%MZ}..{end:%Y-%m-%dT%H:%MZ}")
        except (KeyError, ValueError, AttributeError):
            errors.append(f"{sid}: bad published time")
        readable = 0
        for x in s.get("sources", []):
            u = x.get("url", "")
            if x.get("kind") not in KINDS:
                errors.append(f"{sid}: bad source kind {x.get('kind')}")
            if any(g in u.lower() for g in AGGREGATORS):
                errors.append(f"{sid}: aggregator or blocked source {u}")
            parts = norm_url(u).split("/", 3)
            if len(parts) < 4 or not parts[3]:
                errors.append(f"{sid}: home page as source {u}")
            if x.get("kind") != "discussion":
                readable += 1
                if norm_url(u) in old_urls and not s.get("follow_up"):
                    warns.append(f"{sid}: source already used on {old_urls[norm_url(u)]}: {u}")
        if readable == 0:
            errors.append(f"{sid}: no readable source")
        elif readable == 1:
            warns.append(f"{sid}: only one readable source")
        for d, o in earlier:
            t1, t2 = tok(s["title"]), tok(o["title"])
            if t1 and t2 and len(t1 & t2) / len(t1 | t2) >= 0.45:
                warns.append(f"{sid}: title close to {d} story {o['id']}")
        if not (ROOT / "docs" / "s" / f"{sid}.html").exists():
            warns.append(f"{sid}: no page docs/s/{sid}.html yet (run tools/bundle_data.py)")
    spots = sum(1 for s in stories if s.get("spotlight"))
    if spots > 2:
        warns.append(f"{spots} spotlights; keep them for genuinely major items")
    if stories and not 6 <= len(stories) <= 20:
        warns.append(f"{len(stories)} stories (aim for 6 to 15)")
    index = store.read(EDITIONS / "index.json", {})
    if a.date not in {e["date"] for e in index.get("editions", [])}:
        errors.append("edition missing from index.json")
    for w in warns:
        print("warn ", w)
    for e in errors:
        print("ERROR", e)
    print(f"check {a.date}: {len(stories)} stories, {len(errors)} errors, {len(warns)} warnings")
    sys.exit(1 if errors else 0)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("add", "order", "drop", "check", "list"):
        p = sub.add_parser(name)
        p.add_argument("--date", required=True)
        if name == "add":
            p.add_argument("--file", required=True)
        if name in ("order", "drop"):
            p.add_argument("--ids", required=True)
    a = ap.parse_args()
    {"add": cmd_add, "order": cmd_order, "drop": cmd_drop, "check": cmd_check, "list": cmd_list}[a.cmd](a)


if __name__ == "__main__":
    main()
