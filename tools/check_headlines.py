"""Headline honesty check: scores every headline with a decision model (Microsoft-Decision-1 through OpenRouter).

A decision model does not write text. You give it some content (the "state") and a few typed questions,
and it answers each one with a probability or a choice in a single short call. This script asks three
questions about every headline in an edition:

    supported   (yes/no)  Is every claim in our headline backed by our fact-checked summary?
    strength    (choice)  Compared with the original publisher's headline, is ours the same, stronger or weaker?
    hype        (score)   From 0 (plain and factual) to 4 (clickbait).

    python tools/check_headlines.py                                   latest edition
    python tools/check_headlines.py --date 2026-10-13                 one edition
    python tools/check_headlines.py --all                             every edition so far
    python tools/check_headlines.py --headline "..." --text "..."     any headline against any text
    python tools/check_headlines.py --model typesafe/jev-1.13         another decision model

Needs OPENROUTER_API_KEY in .env (prepaid credits; one check costs a fraction of a cent).
Writes state/reports/headline_honesty_<date>.md and adds every answer to state/reports/headline_honesty.json.
Answers are cached in state/cache/decisions/, so running it twice does not pay twice.
The summary is the reference because full source texts are not stored; the summary itself passed the
fact-checker against the source when the edition was written.
"""
import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
EDITIONS = ROOT / "docs" / "data" / "editions"
REPORTS = ROOT / "state" / "reports"
CACHE = ROOT / "state" / "cache" / "decisions"
RESULTS = REPORTS / "headline_honesty.json"
URL = "https://openrouter.ai/api/alpha/decisions"
DEFAULT_MODEL = "microsoft/microsoft-decision-1"

QUESTIONS = {
    "supported": {
        "type": "noul",
        "instructions": "Read our_headline and the summary. Is every claim in our_headline supported by the summary?",
        "criteria": {
            "true": "Every fact, number, name and claim in our_headline appears in or follows directly from the summary.",
            "false": "our_headline states something the summary does not support, or presents an allegation or "
                     "a report as a confirmed fact.",
        },
    },
    "strength": {
        "type": "choice",
        "instructions": "Compare our_headline with the original_headlines written by the publishers. "
                        "How strong is our wording?",
        "criteria": {
            "same": "Same certainty and intensity as the original headlines.",
            "stronger": "More certain, alarming or sweeping than the original headlines.",
            "weaker": "More cautious or less specific than the original headlines.",
        },
    },
    "hype": {
        "type": "score",
        "instructions": "How much hype or clickbait is in our_headline?",
        "criteria": [
            "Plain and factual: says who did what.",
            "Mostly plain, one loaded word.",
            "Some hype: vague superlatives or a teaser.",
            "Strong hype: exaggeration or emotional framing.",
            "Clickbait: withholds the point or overstates it to get a click.",
        ],
    },
}


def load_env():
    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env")
    except ImportError:
        pass
    key = os.getenv("OPENROUTER_API_KEY")
    if not key:
        sys.exit("OPENROUTER_API_KEY is not in .env")
    return key


def ask(key, model, state):
    body = {"model": model, "state": state, "questions": QUESTIONS,
            "provider": {"data_collection": "deny"}, "session_id": "attention-span-headline-honesty"}
    h = hashlib.sha256(json.dumps([model, state, QUESTIONS], sort_keys=True).encode("utf-8")).hexdigest()[:24]
    cached = CACHE / f"{h}.json"
    if cached.exists():
        return json.loads(cached.read_text(encoding="utf-8")), True
    r = requests.post(URL, json=body, timeout=60,
                      headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    if r.status_code == 402:
        sys.exit("OpenRouter says the credits are used up (HTTP 402). Nothing else was charged.")
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code}: {r.text[:200]}")
    data = r.json()
    CACHE.mkdir(parents=True, exist_ok=True)
    cached.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return data, False


def verdict(a):
    """Turn the three answers into one plain flag."""
    supported = a["supported"]["noul"]
    strength = a["strength"]["choice"]
    strong_p = a["strength"]["probabilities"].get("stronger", 0)
    hype = a["hype"]["score"]          # expected value on the 0 to 4 scale of the criteria list
    reasons = []
    if supported < 0.5:
        reasons.append("claim not in the summary")
    if strength == "stronger" and strong_p >= 0.75:
        reasons.append("stronger than the original")
    if hype >= 2.5:
        reasons.append("hype")
    return ("check" if reasons else "ok"), reasons


def stories_for(dates):
    out = []
    for f in sorted(EDITIONS.glob("20*.json")):
        month = json.loads(f.read_text(encoding="utf-8"))
        for day, ed in month.get("editions", {}).items():
            if dates is None or day in dates:
                out += ed.get("stories", [])
    return out


def latest_date():
    idx = json.loads((EDITIONS / "index.json").read_text(encoding="utf-8"))
    return idx["editions"][0]["date"]


def main():
    ap = argparse.ArgumentParser(description="Check our headlines with a decision model")
    ap.add_argument("--date", help="edition date, YYYY-MM-DD (default: the latest)")
    ap.add_argument("--all", action="store_true", help="every edition so far")
    ap.add_argument("--headline", help="check this headline instead of an edition")
    ap.add_argument("--text", help="the text the headline should be faithful to (with --headline)")
    ap.add_argument("--original", default="", help="the publisher's own headline (with --headline)")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    args = ap.parse_args()
    key = load_env()

    if args.headline:
        if not args.text:
            sys.exit("--headline needs --text")
        state = {"our_headline": args.headline, "summary": args.text,
                 "original_headlines": [args.original] if args.original else []}
        data, _ = ask(key, args.model, state)
        a = data["answers"]
        flag, reasons = verdict(a)
        print(f"supported  {a['supported']['noul']:.2f}  (1.00 = fully supported)")
        print(f"strength   {a['strength']['choice']}  {json.dumps({k: round(v, 2) for k, v in a['strength']['probabilities'].items()})}")
        print(f"hype       {a['hype']['score']:.1f}  (0 plain to 4 clickbait)")
        print(f"verdict    {flag}{': ' + ', '.join(reasons) if reasons else ''}")
        print(f"model      {data.get('model')}   cost ${(data.get('usage') or {}).get('cost', 0):.6f}")
        return

    label = "all" if args.all else (args.date or latest_date())
    stories = stories_for(None if args.all else {label})
    if not stories:
        sys.exit(f"No stories found for {label}")

    results = json.loads(RESULTS.read_text(encoding="utf-8")) if RESULTS.exists() else {}
    rows, cost, paid, flagged = [], 0.0, 0, 0
    print(f"Checking {len(stories)} headlines with {args.model}")
    for s in stories:
        # a repo or model id ("LiquidAI/d1-3B") is not a headline to compare wording with
        originals = [src["title"] for src in s.get("sources", [])
                     if src.get("title") and len(src["title"].split()) >= 3][:4]
        state = {"our_headline": s["title"], "summary": s.get("summary", ""), "original_headlines": originals}
        try:
            data, was_cached = ask(key, args.model, state)
        except Exception as exc:
            print(f"  skip  {s['title'][:70]}  ({str(exc)[:80]})")
            continue
        a = data["answers"]
        flag, reasons = verdict(a)
        if not was_cached:
            paid += 1
            cost += float((data.get("usage") or {}).get("cost") or 0)
        flagged += flag == "check"
        row = {"id": s["id"], "date": s.get("date"), "headline": s["title"],
               "original_headlines": state["original_headlines"],
               "supported": round(a["supported"]["noul"], 3), "strength": a["strength"]["choice"],
               "strength_probabilities": {k: round(v, 3) for k, v in a["strength"]["probabilities"].items()},
               "hype": round(a["hype"]["score"], 2), "verdict": flag, "reasons": reasons,
               "model": data.get("model"), "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        rows.append(row)
        results[f"{s['id']}|{args.model}"] = row
        mark = "CHECK" if flag == "check" else "ok   "
        print(f"  {mark} {row['supported']:.2f}  {row['strength']:<8} hype {row['hype']:.1f}  {s['title'][:70]}")

    REPORTS.mkdir(parents=True, exist_ok=True)
    RESULTS.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    lines = [f"# Headline honesty, {label}", "",
             f"Model: {args.model}. {len(rows)} headlines, {flagged} to look at. "
             f"{paid} paid calls, ${cost:.5f}.", "",
             "Supported is the probability that every claim in the headline is backed by the summary. "
             "Strength compares our wording with the publishers' headlines. Hype runs from 0 (plain) to 4 (clickbait). "
             "A flag means a person should read the story again, not that the headline is wrong.", "",
             "| Verdict | Supported | Strength | Hype | Our headline | Publisher's headline |",
             "|---|---|---|---|---|---|"]
    for r in sorted(rows, key=lambda r: (r["verdict"] != "check", r["supported"])):
        orig = (r["original_headlines"] or [""])[0].replace("|", "/")
        why = f"check: {', '.join(r['reasons'])}" if r["reasons"] else "ok"
        lines.append(f"| {why} | {r['supported']:.2f} | {r['strength']} | {r['hype']:.1f} | "
                     f"{r['headline'].replace('|', '/')} | {orig} |")
    out = REPORTS / f"headline_honesty_{label}.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\n{len(rows)} checked, {flagged} to look at, {paid} paid calls, ${cost:.5f}")
    print(f"Report: {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
