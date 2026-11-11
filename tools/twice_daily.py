"""Twice-daily run (06:30 and 18:30 IST, see tools/schedule_twice_daily.ps1).

What one run does, for everything published since the previous run:
  1. collects the feeds and builds or extends the edition of each day (the day ends at 23:45 IST)
  2. asks Claude with web search for important stories the feeds missed, and adds them through the
     normal writer and fact-checker (tools/add_story.py)
  3. finds X posts through public newsletters and Techmeme (tools/harvest_x.py), checks each one through
     X's official oEmbed endpoint, and adds posts by people on the roster to the Context Window
  4. scans the changes against your private blocklist (BLOCKLIST_FILE in .env) before anything is published
  5. writes the git commands to state/tmp/publish/PUBLISH.txt and shows a Windows notification

It never commits or pushes. Claude (ANTHROPIC_API_KEY) is used first for picking, writing and notes.
    python tools/twice_daily.py            the full run
    python tools/twice_daily.py --plan     only print the window and the edition days, change nothing
"""
import argparse
import json
import math
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass

DATA = ROOT / "docs" / "data"
TMP = ROOT / "state" / "tmp"
OUT = TMP / "publish"                        # git-ignored: the report may quote blocklist hits
STATE_F = ROOT / "state" / "schedule_state.json"
SHIFT = timedelta(hours=5, minutes=45)       # an item belongs to the IST day of (its time + 15 minutes)
MAX_HOURS = 100
PY = sys.executable

# Claude first; Gemini and Groq stay as fallbacks. Any LLM_CHAIN_* line in .env still wins.
for k, v in {"LLM_CHAIN_EDITOR": "anthropic:claude-sonnet-5-5,gemini:gemini-3.5-flash,gemini:gemini-3.5-flash-lite",
             "LLM_CHAIN_WRITER": "anthropic:claude-sonnet-5-5,gemini:gemini-3.5-flash-lite,groq:openai/gpt-oss-120b",
             "LLM_CHAIN_HEADS": "anthropic:claude-haiku-5-5,gemini:gemini-3.5-flash-lite,groq:openai/gpt-oss-120b",
             "LLM_CHAIN_DEDUPE": "anthropic:claude-haiku-5-5,gemini:gemini-3.5-flash-lite,groq:openai/gpt-oss-120b"}.items():
    os.environ.setdefault(k, v)
os.environ.setdefault("PYTHONUTF8", "1")
PRICE = {"claude-sonnet-5-5": (2.0, 10.0), "claude-haiku-5-5": (1.0, 5.0), "claude-opus-5-5": (5.0, 25.0)}

LOG = []


def log(msg=""):
    line = f"{datetime.now():%H:%M:%S}  {msg}"
    print(line, flush=True)
    LOG.append(line)


def read(path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def write(path, obj):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(obj, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def ts(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)


def day_of(dt):
    return (dt + SHIFT).date().isoformat()


def iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def run(args, env=None, timeout=1800):
    """Run a step as a child process; return (exit code, output)."""
    e = dict(os.environ, **(env or {}))
    try:
        p = subprocess.run([PY, *args], cwd=ROOT, env=e, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=timeout)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except subprocess.TimeoutExpired:
        return 124, f"timed out after {timeout}s"


def spend_from(text):
    """Dollar cost from the lines the steps print."""
    usd = sum(float(x) for x in re.findall(r"about \$(\d+\.\d+)", text))
    for model, tin, tout in re.findall(r"paid model anthropic:([\w.-]+): ([\d,]+) tokens in, ([\d,]+) out", text):
        pin, pout = PRICE.get(model, (2.0, 10.0))
        usd += int(tin.replace(",", "")) / 1e6 * pin + int(tout.replace(",", "")) / 1e6 * pout
    return usd


def editions():
    idx = read(DATA / "editions" / "index.json", {"editions": []})
    return {e["date"]: e for e in idx["editions"]}


def month(day):
    return read(DATA / "editions" / f"{day[:7]}.json", {"editions": {}})


def window(now):
    st = read(STATE_F, {})
    if st.get("until"):
        since = ts(st["until"]) - timedelta(minutes=30)
    else:
        ed = editions()
        last = max(ed) if ed else (now - timedelta(days=1)).date().isoformat()
        since = datetime.fromisoformat(f"{last}T18:15:00+00:00")       # the end of the latest edition's day
    return max(since, now - timedelta(hours=MAX_HOURS)), now


# ---------------------------------------------------------------- 1. editions

def build_day(day, items, health):
    """Build the day's edition, or extend it when it already exists (keeping what is there)."""
    exists = day in editions()
    old = month(day)["editions"].get(day, {}).get("stories", []) if exists else []
    write(TMP / "last_items.json", {"at": iso(datetime.now(timezone.utc)), "items": items, "health": health})
    env = {"SEEN_INCLUDE_SAME_DAY": "1"} if exists else {}
    code, out = run(["run_daily.py", "--resume", "--date", day, "--no-heads", "--max", "8" if exists else "12"], env)
    added = [l.strip() for l in out.splitlines() if l.strip().startswith("ok ")]
    if code != 0:
        log(f"   {day}: run stopped ({out.strip().splitlines()[-1][:150] if out.strip() else code})")
        if exists:                     # never lose the stories that were already there
            restore(day, old, [])
        return out, 0
    new = month(day)["editions"].get(day, {}).get("stories", [])
    prev = [d for d in sorted(editions()) if d < day][-4:]
    restore(day, old, new, prev)
    log(f"   {day}: {'extended' if exists else 'new edition'}, {len(added)} stories written")
    return out, len(added)


# a story built from a headline alone (the writer says so in the summary) is not a story
NO_TEXT = re.compile(r"title is the only text|only (?:a |the )?(?:headline|title)s? (?:is|are|was|were) (?:given|provided)|"
                     r"sources? (?:give|gives|provide|provides) only (?:a |the )?headlines?|only text provided", re.I)


def rerank(stories):
    """One model call orders an extended edition by importance. The lead stays first unless a new story is clearly
    bigger; spotlighted stories stay at the top. Any bad answer keeps the order as it was."""
    from pipeline import llm
    rows = "\n".join(f"{i}. {s['title']} ({len(s['sources'])} sources)" for i, s in enumerate(stories))
    system = ("You order the stories of a daily AI news edition for people who build with AI, most important first: "
              "frontier model launches, major lab announcements, big deals, security incidents and policy that changes "
              "what builders can do come before minor product updates, opinion posts and small releases. "
              "Keep story 0 first unless another is clearly bigger news. "
              'Answer JSON: {"order": [every story number exactly once]}')
    try:
        res, _ = llm.ask_json(system, rows, max_tokens=400, tag="dedupe")
        order = [int(i) for i in res.get("order", [])]
    except Exception as exc:  # noqa: BLE001
        log(f"   reorder skipped: {type(exc).__name__}")
        return stories
    if sorted(order) != list(range(len(stories))):
        log("   reorder skipped: the answer did not list every story once")
        return stories
    out = [stories[i] for i in order]
    return [s for s in out if s.get("spotlight")] + [s for s in out if not s.get("spotlight")]


def restore(day, old, new, prev=()):
    """Old stories keep their places; new ones that repeat a story from today or the two days before are dropped."""
    F = DATA / "editions" / f"{day[:7]}.json"
    m = month(day)
    old_urls = {s["url"] for st in old for s in st["sources"]}
    old_ids = {s["id"] for s in old}
    fresh = []
    for s in new:
        if s["id"] in old_ids or ({x["url"] for x in s["sources"]} & old_urls):
            continue
        if NO_TEXT.search(s.get("summary", "")):
            log(f"   dropped a headline-only story: {s['title'][:80]}")
            continue
        if any(same_story(s["title"], o["title"]) for o in old) or is_dup(s["title"], prev):
            log(f"   dropped a repeat: {s['title'][:80]}")
            continue
        fresh.append(s)
    reps = llm_repeats([s["title"] for s in fresh], [o["title"] for o in old] + titles_of(prev))
    for i in sorted(reps, reverse=True):
        log(f"   dropped a repeat: {fresh[i]['title'][:70]} (same news as: {reps[i][:50]})")
        del fresh[i]
    lead_new = [s for s in fresh if s.get("spotlight")]
    rest_new = [s for s in fresh if not s.get("spotlight")]
    k = 0                                   # new spotlights go right after the existing spotlighted stories,
    while k < len(old) and old[k].get("spotlight"):   # so a later run never takes the lead from the earlier one
        k += 1
    stories = old[:k] + lead_new + old[k:] + rest_new
    n_spot = 0
    for r, s in enumerate(stories, 1):
        s["rank"] = r
        if s.get("spotlight"):
            n_spot += 1
            if n_spot > 2:
                s["spotlight"], s["spotlight_reason"] = False, ""
    if old and fresh:
        stories = rerank(stories)
    ed = m["editions"].setdefault(day, {"date": day, "stats": {}})
    ed["stories"] = stories
    ed["generated_at"] = iso(datetime.now(timezone.utc))
    write(F, m)
    I = DATA / "editions" / "index.json"
    idx = read(I, {"editions": []})
    for e in idx["editions"]:
        if e["date"] == day:
            e.update(count=len(stories), lead=stories[0]["title"] if stories else "",
                     spotlight=sum(1 for s in stories if s.get("spotlight")))
    write(I, idx)


# ---------------------------------------------------------------- 2. missed stories

WORD = re.compile(r"[a-z0-9$.]{4,}")
MONEY = re.compile(r"\$\s?(\d+(?:\.\d+)?)\s*(trillion|billion|million|t|b|m)\b", re.I)
NAME = re.compile(r"\b[A-Z][A-Za-z0-9]{2,}")
SKIP = {"Report", "Reports", "Reportedly", "Says", "The", "New", "How", "Why", "What", "With", "After", "From", "Study"}


def money(t):
    return {f"${float(n):g}{u[0].lower()}" for n, u in MONEY.findall(t)} | set(re.findall(r"\$\d[\d,.]*", t))


def words(t):
    return set(WORD.findall(re.sub(r"'s?\b", "", t.lower())))


def same_story(a, b):
    """Two headlines about the same news: many shared words, or the same amount of money and the same company."""
    w, v = words(a), words(b)
    if len(w & v) >= 5 or (len(w & v) >= 3 and len(w & v) / len(w | v) >= 0.35):
        return True
    names = (set(NAME.findall(a)) & set(NAME.findall(b))) - SKIP
    return bool(money(a) & money(b) and names)


def titles_of(days):
    return [s["title"] for d in days for s in month(d)["editions"].get(d, {}).get("stories", [])]


def llm_repeats(new_titles, old_titles):
    """One cheap call: which new headlines report the same news as an earlier one? Returns {new index: old title}.
    Word overlap misses rewordings ("board opens probe" vs "board investigates"), so a model reads them."""
    if not new_titles or not old_titles:
        return {}
    from pipeline import llm
    system = ("You check a daily news site for repeated stories. A new headline is a repeat if it reports the same "
              "event, launch, deal or announcement as an earlier headline, even if worded differently or with a small "
              "extra detail. A genuinely new development (a later decision, a different product, new numbers from a "
              'different event) is not a repeat. Answer JSON: {"repeats": {"<new number>": <earlier number>}}; '
              "leave out new headlines that are not repeats.")
    user = ("Earlier headlines:\n" + "\n".join(f"{i}. {x}" for i, x in enumerate(old_titles))
            + "\n\nNew headlines:\n" + "\n".join(f"{i}. {x}" for i, x in enumerate(new_titles)))
    try:
        res, _ = llm.ask_json(system, user, max_tokens=600, tag="dedupe")
    except Exception as exc:  # noqa: BLE001  the word check still ran; never stop the run for this
        log(f"   repeat check skipped: {type(exc).__name__}")
        return {}
    out = {}
    for k, v in (res.get("repeats") or {}).items():
        try:
            k, v = int(k), int(v)
        except (TypeError, ValueError):
            continue
        # guard against a mixed-up number ("Claude Sheets" matched to an AlphaProof story on 10 Nov):
        # the two headlines must share a word that is not a company name
        if 0 <= k < len(new_titles) and 0 <= v < len(old_titles) and topic_words(new_titles[k]) & topic_words(old_titles[v]):
            out[k] = old_titles[v]
    return out


COMMON = {"anthropic", "openai", "google", "nvidia", "meta", "microsoft", "apple", "amazon", "claude", "chatgpt", "report",
          "reports", "reportedly", "says", "with", "from", "after", "launches", "releases", "about", "into", "over", "their",
          "the", "and", "for", "new", "its", "says", "that", "this", "will", "than", "more", "per"}


def topic_words(t):
    return {w for w in re.findall(r"[a-z0-9][a-z0-9.$-]{2,}", t.lower().replace("'s", "")) if w not in COMMON}


def is_dup(title, days):
    for d in days:
        for s in month(d)["editions"].get(d, {}).get("stories", []):
            if same_story(title, s["title"]):
                return s["title"]
    return None


# aggregators and pages that refuse plain requests or sit behind paywalls: never a story's source
BLOCKED = re.compile(r"techmeme\.com|killtheai|theneuron\.ai|bloomberg\.com|wsj\.com|ft\.com|reuters\.com|nytimes\.com|"
                     r"theinformation\.com|x\.com|twitter\.com|news\.google|ycombinator\.com|substack\.com|"
                     r"recap|digest|roundup|aitools|ai-news-(?:today|\w+-\d)|top-\d+-ai-news|anothercodingblog|newsletter|"
                     r"latent\.space/p/ainews", re.I)


def article_url(u):
    """A home or section page (cnbc.com/ai-artificial-intelligence/, finance.yahoo.com/technology/ai/) is not a source:
    an article path has a digit, an .html ending, or a slug of at least four words."""
    path = urlsplit(u).path.strip("/")
    last = path.rsplit("/", 1)[-1]
    return bool(path) and (bool(re.search(r"\d", path)) or last.endswith((".html", ".htm")) or last.count("-") >= 3)


def missed_stories(since, until, touched, max_add):
    from pipeline.store import norm_url
    code, out = run(["tools/research.py", "--since", iso(since), "--until", iso(until), "--focus", "news",
                     "--searches", os.getenv("RESEARCH_SEARCHES", "6")], timeout=900)
    log("   " + (out.strip().splitlines()[-1][:160] if out.strip() else f"research exit {code}"))
    res = read(ROOT / "state" / "research" / f"{until:%Y-%m-%d}-news.json", {})
    seen = read(ROOT / "state" / "seen.json", {})
    have = sorted(editions())
    added, tried, notes, queue = [], 0, [], []
    for st in res.get("stories", []):
        url = (st.get("url") or "").strip()
        if not url.startswith("http") or norm_url(url) in seen:
            continue
        if re.search(r"\b(roundup|round-up|recap|digest|weekly|this week in|top \d+)\b", st.get("headline", ""), re.I):
            notes.append(f"skipped (a roundup, not one story): {st.get('headline', '')[:80]}")
            continue
        d = st.get("date") or touched[-1]
        if d not in have:
            d = touched[0] if d < touched[0] else touched[-1]
        prev = [x for x in have if x <= d][-5:]
        dup = is_dup(st.get("headline", ""), prev)
        if dup:
            notes.append(f"skipped (already covered as \"{dup[:60]}\"): {st.get('headline', '')[:80]}")
            continue
        urls = [u for u in [url] + list(st.get("also") or []) if u.startswith("http") and not BLOCKED.search(u)
                and article_url(u)][:2]
        if not urls:
            notes.append(f"skipped (only aggregator or paywalled links): {st.get('headline', '')[:80]}")
            continue
        queue.append((st, d, urls))
    reps = llm_repeats([st.get("headline", "") for st, _, _ in queue], titles_of(have[-6:]))
    for i, (st, d, urls) in enumerate(queue):
        if len(added) >= max_add or tried >= max_add + 3:
            break
        if i in reps:
            notes.append(f"skipped (same news as \"{reps[i][:60]}\"): {st.get('headline', '')[:80]}")
            continue
        h = st.get("headline", "")
        earlier = [a.split(": ", 1)[-1] for a in added]
        if earlier and (any(same_story(h, e) for e in earlier) or llm_repeats([h], earlier)):
            notes.append(f"skipped (same news as a story added in this run): {h[:80]}")
            continue
        tried += 1
        code, o = run(["tools/add_story.py", *urls, "--date", d], timeout=600)
        out += "\n" + o
        m = re.search(r"Added at rank \d+ of \d+ in ([\d-]+): (.+)", o)
        if m:
            added.append(f"{m.group(1)}: {m.group(2)}")
        else:
            last = o.strip().splitlines()[-1][:140] if o.strip() else str(code)
            notes.append(f"not added ({last}): {st.get('headline', '')[:80]}")
    for a in added:
        log(f"   added: {a}")
    return out, added, notes


# ---------------------------------------------------------------- 3. Context Window

def context_window(since, until):
    from pipeline import heads
    from verify_x import verify
    code, out = run(["tools/harvest_x.py", "--since", iso(since), "--until", iso(until)], timeout=900)
    log("   " + " | ".join(l.strip() for l in out.splitlines() if "picked" in l or "pages read" in l)[:200])
    picks = read(ROOT / "state" / "research" / f"{until:%Y-%m-%d}-x.json", {}).get("picks", [])[:int(os.getenv("X_MAX", "30"))]
    if not picks:
        return out, 0, []
    checked = verify([p["url"] for p in picks])
    _, roster = heads.roster()
    on_roster = {(h.get("x") or "").lower() for h in roster if h.get("x")}
    mine, other = [], []
    for c in checked:
        if "fail" in c:
            continue
        (mine if c["author"].lower() in on_roster else other).append(c)
    if mine:
        with open(ROOT / "state" / "heads_inbox.txt", "a", encoding="utf-8") as f:
            for c in mine:
                f.write(c["url"] + "\n")
        before = len(read(DATA / "heads.json", {"posts": []}).get("posts", []))
        lines = []
        heads.update(log=lambda m: lines.append(str(m)))
        out += "\n" + "\n".join(lines)
        after = len(read(DATA / "heads.json", {"posts": []}).get("posts", []))
        log(f"   {len(mine)} roster posts sent to the Context Window ({after - before} new); "
            f"{len(other)} by people not on the roster are listed for you")
    return out, len(mine), other


# ---------------------------------------------------------------- 4. privacy scan

def git(*args):
    p = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return p.stdout


def privacy_scan():
    f = os.getenv("BLOCKLIST_FILE")
    if not f or not Path(f).exists():
        return None, "NOT RUN: set BLOCKLIST_FILE in .env to your private blocklist file."
    terms = [t.strip() for t in Path(f).read_text(encoding="utf-8").splitlines() if t.strip() and not t.startswith("#")]
    try:
        status = git("status", "--porcelain", "--untracked-files=all")
    except FileNotFoundError:
        return None, "NOT RUN: git was not found on this computer."
    text = git("diff", "-U0")
    added = "\n".join(l[1:] for l in text.splitlines() if l.startswith("+") and not l.startswith("+++"))
    for line in status.splitlines():
        if line.startswith("??"):
            p = ROOT / line[3:].strip().strip('"')
            if p.is_file() and p.stat().st_size < 20_000_000:
                added += "\n" + p.read_text(encoding="utf-8", errors="ignore")
    hits = []
    for t in terms:
        for m in re.finditer(r"(?<![A-Za-z])" + re.escape(t) + r"(?![A-Za-z])", added, re.I):
            hits.append(f"'{t}' near: ...{added[max(0, m.start() - 60): m.end() + 60]}...".replace("\n", " "))
            break
    return hits, ("CLEAN" if not hits else f"STOP: {len(hits)} blocked term(s) found, do not push")


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", action="store_true")
    ap.add_argument("--skip-research", action="store_true")
    ap.add_argument("--skip-x", action="store_true")
    args = ap.parse_args()
    t0 = time.time()
    now = datetime.now(timezone.utc)
    since, until = window(now)
    log(f"Window {iso(since)} to {iso(until)} ({(until - since).total_seconds() / 3600:.1f} hours)")
    if args.plan:
        d, days = since, []
        while day_of(d) <= day_of(until):
            days.append(day_of(d)); d += timedelta(days=1)
        log(f"Edition days: {', '.join(days)}; existing: {[x for x in days if x in editions()]}")
        return

    from pipeline.collect import collect
    alltext, problems = "", []
    log("1. Collecting")
    items, health = collect(hours=math.ceil((until - since).total_seconds() / 3600) + 1, log=lambda m: None)
    items = [i for i in items if i.get("published") and since <= ts(i["published"]) < until]
    by_day = {}
    for i in items:
        by_day.setdefault(day_of(ts(i["published"])), []).append(i)
    log(f"   {len(items)} items: " + ", ".join(f"{d} ({len(v)})" for d, v in sorted(by_day.items())))
    touched, written = [], 0
    for d in sorted(by_day):
        if len(by_day[d]) < 3 and d not in editions():
            log(f"   {d}: only {len(by_day[d])} items, left for the next run")
            continue
        try:
            out, n = build_day(d, by_day[d], health)
            alltext += out
            written += n
            if d in editions():
                touched.append(d)
        except Exception as exc:  # noqa: BLE001
            problems.append(f"edition {d}: {type(exc).__name__}: {exc}")
            log(f"   {d}: failed: {exc}")

    added, notes = [], []
    if touched and not args.skip_research:
        log("2. Missed stories (Claude with web search)")
        try:
            out, added, notes = missed_stories(since, until, touched, int(os.getenv("RESEARCH_MAX_ADD", "4")))
            alltext += out
        except Exception as exc:  # noqa: BLE001
            problems.append(f"missed stories: {type(exc).__name__}: {exc}")

    n_posts, others = 0, []
    if not args.skip_x:
        log("3. Context Window")
        try:
            out, n_posts, others = context_window(since, until)
            alltext += out
        except Exception as exc:  # noqa: BLE001
            problems.append(f"Context Window: {type(exc).__name__}: {exc}")

    from bundle_data import bundle
    bundle()
    for d in touched:                  # pages of stories dropped as repeats are not linked from anywhere: remove them
        ids = {s["id"] for s in month(d)["editions"].get(d, {}).get("stories", [])}
        for page in (ROOT / "docs" / "s").glob(f"{d}-*.html"):
            if page.stem not in ids:
                page.unlink()
                log(f"   removed unused page {page.name}")
    write(STATE_F, {"until": iso(until), "finished": iso(datetime.now(timezone.utc))})

    log("4. Privacy scan")
    hits, verdict = privacy_scan()
    log(f"   {verdict}")
    spend = spend_from(alltext)

    ed = editions()
    leads = [ed[d]["lead"] for d in touched if d in ed and ed[d].get("lead")]
    lead = re.sub(r"[\"`$]", "", leads[-1]).replace("'", "\u2019") if leads else ""
    if len(lead) > 90:
        lead = lead[:90].rsplit(" ", 1)[0]       # cut at a word, not mid-word
    days = ", ".join(touched) if touched else "no edition changes"
    msg = f"Editions {days}" + (f" (lead story: {lead})" if lead else "") + f"; Context Window: {n_posts} posts"
    cmds = (f"cd \"{ROOT}\"\ngit add README.md docs pipeline seed state tools\ngit commit -m '{msg}'\ngit push\n")

    OUT.mkdir(parents=True, exist_ok=True)
    report = [f"# Attention Span twice-daily run, {datetime.now():%d %b %Y %H:%M}", "",
              f"Privacy scan: {verdict}"] + [f"- {h}" for h in (hits or [])] + ["",
              "## Publish (run in PowerShell or Git Bash)" if hits == [] else "## Publish: DO NOT run until the scan is clean",
              "```", cmds.strip(), "```", "",
              f"Stories written: {written} across {days}. Missed stories added: {len(added)}. "
              f"Context Window posts sent: {n_posts}. Claude API spend this run: about ${spend:.2f}. "
              f"Time: {round((time.time() - t0) / 60)} min.", ""]
    report += ["## Missed stories added"] + [f"- {a}" for a in added] + [""] if added else []
    report += ["## Missed stories not added"] + [f"- {n}" for n in notes] + [""] if notes else []
    report += ["## X posts by people not on the roster (add them to seed/heads.py if you want them)"] + \
              [f"- {o['url']} : {o['text'][:160]}" for o in others] + [""] if others else []
    report += ["## Problems"] + [f"- {p}" for p in problems] + [""] if problems else []
    report += ["## Log", "```"] + LOG + ["```"]
    (OUT / "PUBLISH.md").write_text("\n".join(report), encoding="utf-8")
    (OUT / "last_run_full.log").write_text(alltext, encoding="utf-8")    # every step's own output, for fixing problems
    with open(OUT / "history.log", "a", encoding="utf-8") as f:
        f.write(f"{iso(now)}  {verdict}  {msg}  ${spend:.2f}\n")
    log(f"Report: {OUT / 'PUBLISH.md'}")

    if os.name == "nt":
        text = (f"{written + len(added)} stories, {n_posts} posts. Scan: {verdict.split(':')[0]}. "
                "Git commands are in state\\tmp\\publish\\PUBLISH.md")
        subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                        str(ROOT / "tools" / "notify.ps1"), "-Title", "Attention Span updated", "-Text", text])
        if os.getenv("OPEN_REPORT", "1") == "1":
            subprocess.Popen(["notepad.exe", str(OUT / "PUBLISH.md")])


if __name__ == "__main__":
    main()
