"""Fact-check every timeline entry and person against its sources.

- arXiv links: the entry date must equal the arXiv v1 submission date (via the arXiv API),
  and the paper title is recorded for review.
- DOI links: the year (and month when given) must match Crossref's publication date.
- Other links: must load (HTTP 2xx/3xx); when the entry has a full date, that date must
  appear on the page for the entry to count as date-verified.
- A source marked kind="paper" that was posted after the launch is supporting evidence only.
- x.com links cannot be fetched without the paid API, so they are marked 'unverifiable'.

Writes state/verification.json (read by seed/build_seed.py) and a readable report at
state/reports/seed_check.md. Run: python tools/verify_seed.py
"""
import json
import re
import sys
import time
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "seed"))
sys.path.insert(0, str(ROOT))

from timeline import TIMELINE  # noqa: E402
from people import PEOPLE  # noqa: E402
from pipeline.http import get  # noqa: E402

STATE = ROOT / "state"
ATOM = "{http://www.w3.org/2005/Atom}"
UNVERIFIABLE_HOSTS = ("x.com", "twitter.com")


def arxiv_meta(arxiv_id):
    r = get(f"https://export.arxiv.org/api/query?id_list={arxiv_id}", timeout=30)
    root = ET.fromstring(r.content)
    entry = root.find(f"{ATOM}entry")
    if entry is None:
        return None
    published = entry.findtext(f"{ATOM}published", "")[:10]
    title = " ".join(entry.findtext(f"{ATOM}title", "").split())
    return {"date": published, "title": title}


def crossref_meta(doi):
    r = get(f"https://api.crossref.org/works/{doi}", timeout=30)
    if r.status_code != 200:
        return None
    msg = r.json()["message"]
    dates = []
    for key in ("published-online", "published-print", "issued"):
        dp = msg.get(key, {}).get("date-parts")
        if dp and dp[0] and dp[0][0]:
            dates.append(dp[0])
    title = " ".join((msg.get("title") or [""])[0].split())
    return {"dates": dates, "title": title}


def page_title(html):
    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
    return " ".join(m.group(1).split())[:160] if m else ""


MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August",
          "September", "October", "November", "December"]


def date_variants(d):
    """Ways a page might print a YYYY-MM-DD date."""
    y, m, day = int(d[:4]), int(d[5:7]), int(d[8:10])
    full, short = MONTHS[m - 1], MONTHS[m - 1][:3]
    return [d, f"{y}/{m:02d}/{day:02d}", f"{full} {day}, {y}", f"{short} {day}, {y}", f"{short}. {day}, {y}",
            f"{day} {full} {y}", f"{day} {short} {y}", f"{full} {day:02d}, {y}", f"{short} {day:02d}, {y}"]


def check_url(url):
    """Returns (ok, http_status, page_title, html)."""
    try:
        r = get(url, timeout=30)
        ok = 200 <= r.status_code < 400
        is_html = "html" in r.headers.get("content-type", "")
        return ok, r.status_code, (page_title(r.text) if ok and is_html else ""), (r.text if ok and is_html else "")
    except Exception as exc:  # network errors count as failures
        return False, f"error: {type(exc).__name__}", "", ""


# Per-source results, worst first. An entry's status is decided from these.
#   failed: link broken, id unknown, or the date contradicts the launch source
#   date-verified: the date was matched against arXiv, Crossref or the page itself
#   link-ok: the link works but the date could not be matched automatically
#   unverifiable: host cannot be fetched for free (X)
def check_entry(e):
    notes, results = [], []
    want = e["date"]
    for src in e["sources"]:
        url, kind = src["url"], src.get("kind", "primary")
        if any(h in url for h in UNVERIFIABLE_HOSTS):
            notes.append(f"unverifiable host (X has no free API): {url}")
            results.append("unverifiable")
            continue
        m = re.search(r"arxiv\.org/abs/([\w.]+)", url)
        d = re.search(r"doi\.org/(.+)$", url)
        if m:
            meta = arxiv_meta(m.group(1))
            time.sleep(3)  # arXiv asks for at most one request every 3 seconds
            if not meta:
                notes.append(f"arXiv id not found: {m.group(1)}")
                results.append("failed")
                continue
            notes.append(f"arXiv: {meta['title']} (v1 {meta['date']})")
            if meta["date"].startswith(want) or (len(want) == 10 and want == meta["date"]):
                results.append("date-verified")
            elif kind == "paper":
                notes.append(f"paper posted {meta['date']}, after the {want} launch: supporting source")
                results.append("link-ok")
            else:
                notes.append(f"DATE MISMATCH: entry {want}, arXiv v1 {meta['date']}")
                results.append("failed")
        elif d:
            meta = crossref_meta(d.group(1))
            time.sleep(1)
            if not meta:
                notes.append(f"DOI not found in Crossref: {d.group(1)}")
                results.append("failed")
                continue
            notes.append(f"Crossref: {meta['title']} {meta['dates']}")
            want_parts = [int(x) for x in want.split("-")]
            if any(dt[:min(len(dt), len(want_parts))] == want_parts[:min(len(dt), len(want_parts))] for dt in meta["dates"]):
                results.append("date-verified")
            elif any(dt[0] == want_parts[0] for dt in meta["dates"]):
                notes.append(f"year matches, month or day differs: entry {want}")
                results.append("warning")
            else:
                notes.append(f"YEAR MISMATCH: entry {want}, Crossref {meta['dates']}")
                results.append("failed")
        else:
            ok, code, title, html = check_url(url)
            if not ok:
                notes.append(f"LINK FAILED ({code}): {url}")
                results.append("failed")
                continue
            notes.append(f"page loads ({code}): {title}")
            if len(want) == 10 and any(v in html for v in date_variants(want)):
                notes.append(f"date {want} found on page")
                results.append("date-verified")
            else:
                results.append("link-ok")
    if "failed" in results:
        status = "failed"
    elif "date-verified" in results:
        status = "verified"
    elif "warning" in results:
        status = "warning"
    elif "link-ok" in results:
        status = "link-ok"
    else:
        status = "unverifiable"
    return status, notes


def main():
    only = set(sys.argv[1:])
    path = STATE / "verification.json"
    results = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    today = date.today().isoformat()
    for e in TIMELINE:
        if only and e["id"] not in only:
            continue
        status, notes = check_entry(e)
        results[e["id"]] = {"status": status, "checked_on": today, "notes": notes}
        print(f"[{status:12}] {e['id']}")
    people = {}
    for p in PEOPLE:
        if only and p["id"] not in only:
            continue
        ok, code, title, _ = check_url(p["role_source"]["url"])
        people[p["id"]] = {"role_source_ok": ok, "code": code, "title": title}
        print(f"[{'verified' if ok else 'failed':12}] person {p['id']} role source")
    results["_people"] = {**results.get("_people", {}), **people}
    STATE.mkdir(exist_ok=True)
    path.write_text(json.dumps(results, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")

    lines = [f"# Seed check, {today}\n"]
    for e in TIMELINE:
        r = results.get(e["id"])
        if not r:
            continue
        lines.append(f"## [{r['status']}] {e['date']} {e['title']}")
        lines += [f"- {n}" for n in r["notes"]]
        lines.append("")
    (STATE / "reports").mkdir(parents=True, exist_ok=True)
    (STATE / "reports" / "seed_check.md").write_text("\n".join(lines), encoding="utf-8")
    counts = {}
    for k, r in results.items():
        if not k.startswith("_"):
            counts[r["status"]] = counts.get(r["status"], 0) + 1
    print("summary:", counts)


if __name__ == "__main__":
    main()
