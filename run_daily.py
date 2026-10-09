"""Attention Span nightly run. One command:

    python run_daily.py

What it does:
  1. collects the last 24 hours from every source in pipeline/sources.json (plus people's feeds and state/inbox.txt)
  2. removes duplicates and groups items into stories
  3. an AI editor picks the stories that matter
  4. each story is written from its fetched source text, then fact-checked by a separate AI call and by code
  5. the edition is appended to docs/data/editions/ (cumulative JSON) and a report goes to state/reports/

It never commits or pushes. Review the report, then commit yourself.

Options:
  --hours 36         look back further (for example after a missed night)
  --max 12           most stories to publish
  --date 2026-10-08  edition date (default: today in EDITION_UTC_OFFSET, default +05:30)
  --dry-run          do everything but do not write the edition
  --resume           continue an interrupted run with the same items (no quota spent twice)
"""
import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass

from pipeline import llm, store  # noqa: E402
from pipeline.collect import collect  # noqa: E402
from pipeline.curate import apply_merges, editor, must_include, write_story  # noqa: E402
from pipeline.group import group  # noqa: E402

DATA = ROOT / "docs" / "data"


def edition_today():
    """The edition date in local time. A run before 06:00 belongs to the day that just ended,
    so a nightly run that slips past midnight is still filed under the right day."""
    off = os.getenv("EDITION_UTC_OFFSET", "+05:30")
    sign = -1 if off.startswith("-") else 1
    h, m = off.lstrip("+-").split(":")
    local = datetime.now(timezone.utc) + sign * timedelta(hours=int(h), minutes=int(m))
    if local.hour < 6:
        local -= timedelta(days=1)
    return local.date().isoformat()


def hours_since_last_edition(default=24, cap=72):
    """Look back to the previous edition, so a missed night is caught up (at most 3 days)."""
    try:
        index = json.loads((DATA / "editions" / "index.json").read_text(encoding="utf-8"))
        last = index["editions"][0]
        month = json.loads((DATA / "editions" / last["file"]).read_text(encoding="utf-8"))
        made = datetime.fromisoformat(month["editions"][last["date"]]["generated_at"].replace("Z", "+00:00"))
        gap = (datetime.now(timezone.utc) - made).total_seconds() / 3600 + 1
        return int(min(cap, max(default, round(gap))))
    except (FileNotFoundError, KeyError, IndexError, ValueError):
        return default


def main():
    ap = argparse.ArgumentParser(description="Attention Span nightly run")
    ap.add_argument("--hours", type=int, default=None,
                    help="how far back to look; default: since the last edition, at least 24 and at most 72")
    ap.add_argument("--max", type=int, default=12)
    ap.add_argument("--date", default=None)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--resume", action="store_true",
                    help="reuse the items collected by the last run (after an interruption); cached AI answers are reused too")
    args = ap.parse_args()

    if not (os.getenv("GEMINI_API_KEY") or os.getenv("GROQ_API_KEY")):
        sys.exit("No API keys found. Put GEMINI_API_KEY and GROQ_API_KEY in the .env file.")

    t0 = time.time()
    if args.hours is None:
        args.hours = hours_since_last_edition()
    day = args.date or edition_today()
    lines = [f"# Attention Span run for {day}", ""]

    def log(msg):
        print(msg, flush=True)
        lines.append(msg)

    meta = json.loads((DATA / "meta.json").read_text(encoding="utf-8"))
    concepts = json.loads((DATA / "concepts.json").read_text(encoding="utf-8"))
    people = json.loads((DATA / "people.json").read_text(encoding="utf-8"))
    concept_ids = [c["id"] for c in concepts]

    last = ROOT / "state" / "tmp" / "last_items.json"
    if args.resume and last.exists():
        saved = json.loads(last.read_text(encoding="utf-8"))
        items, health = saved["items"], saved["health"]
        log(f"1. Resuming with {len(items)} items collected at {saved['at']}")
    else:
        log(f"1. Collecting the last {args.hours} hours")
        items, health = collect(hours=args.hours, log=log)
        last.parent.mkdir(parents=True, exist_ok=True)
        last.write_text(json.dumps({"at": datetime.now(timezone.utc).isoformat(), "items": items, "health": health}),
                        encoding="utf-8")
    failed = [k for k, v in health.items() if not v["ok"]]
    log(f"   {len(items)} items from {len(health) - len(failed)} sources ({len(failed)} failed: {', '.join(failed) or 'none'})")
    if not items:
        sys.exit("Nothing collected. Check your internet connection.")

    log("2. Grouping into stories")
    stories = group(items)
    fresh = [s for s in stories if not store.seen_before(s, day)]
    log(f"   {len(stories)} stories, {len(stories) - len(fresh)} already published on an earlier day")

    log("3. Editor picks")
    candidates = fresh[:45]
    picks = editor(candidates, meta, args.max, log)
    by_cid = apply_merges(candidates, picks.get("merge"), log)
    spotlight = {}
    for sp in (picks.get("spotlight") or [])[:2]:
        if isinstance(sp, dict) and sp.get("cid"):
            spotlight[sp["cid"]] = sp.get("reason", "")

    pick_list = [p for p in picks.get("picks", []) if p.get("cid") in by_cid]
    merged_away = {c for g in (picks.get("merge") or []) for c in g[1:]}
    picked = {p["cid"] for p in pick_list} | merged_away
    for extra in must_include([by_cid[c] for c in by_cid], picked):
        pick_list.insert(1, {"cid": extra["cid"], "topic": None,
                             "reason": "Included automatically: a major lab's own announcement with a strong signal."})
        log(f"    safety net added {extra['cid']}: {extra['items'][0]['title'][:70]}")

    log("4. Writing and fact-checking")
    published, dropped, reports = [], [], []
    for p in pick_list[: args.max]:
        story = by_cid.get(p.get("cid"))
        if not story:
            continue
        try:
            fields, rep = write_story(story, meta, concept_ids, people, p.get("topic"), log)
        except RuntimeError as exc:
            log(f"    skipped {p.get('cid')}: {exc}")
            dropped.append({"cid": p.get("cid"), "reason": str(exc)[:200]})
            continue
        reports.append(rep)
        if fields:
            fields["editor_reason"] = p.get("reason", "")
            if p.get("cid") in spotlight:
                fields["spotlight"] = True
                fields["spotlight_reason"] = spotlight[p["cid"]].replace("\u2014", ",")
            published.append(fields)
            flag = "  [spotlight]" if fields["spotlight"] else ""
            log(f"    ok  {fields['title']}  ({fields['buzz']} sources){flag}")
        else:
            dropped.append({"cid": story["cid"], "title": story["items"][0]["title"],
                            "reason": rep["rounds"][-1]["problems"][:3]})

    stats = {"items": len(items), "stories": len(stories), "sources_ok": len(health) - len(failed),
             "sources_failed": failed, "published": len(published), "dropped": len(dropped),
             "llm_calls": llm.STATS["calls"], "cache_hits": llm.STATS["cache_hits"],
             "models": llm.STATS["by_model"], "fallbacks": llm.STATS["fallbacks"][-6:],
             "seconds": round(time.time() - t0)}

    log("5. Saving")
    if args.dry_run:
        log("   dry run: edition not written")
    elif published:
        store.save_edition(day, published, stats)
        pending = store.add_pending_terms(day, published, [c["term"] for c in concepts])
        sys.path.insert(0, str(ROOT / "tools"))
        from bundle_data import bundle
        bundle()
        log(f"   edition {day}: {len(published)} stories written to docs/data/editions/")
        log(f"   {len(pending)} new terms waiting for review (python tools/review_terms.py)")
    else:
        log("   nothing passed the checks, so no edition was written")

    log("")
    log("## Dropped stories")
    for d in dropped:
        log(f"- {d}")
    log("")
    log(f"## Stats\n{json.dumps(stats, indent=1)}")
    rep_dir = ROOT / "state" / "reports"
    rep_dir.mkdir(parents=True, exist_ok=True)
    (rep_dir / f"{day}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nDone in {stats['seconds']}s. Report: state/reports/{day}.md")
    if published and not args.dry_run:
        print("\nTo publish, review the report, then run:\n"
              f'  git add docs/data state/seen.json state/pending_terms.json\n  git commit -m "Edition {day}"\n  git push')


if __name__ == "__main__":
    main()
