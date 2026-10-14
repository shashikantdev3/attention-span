"""Attention Heads: what the people in seed/heads.py posted about AI this week.

Free sources only, no keys:
  - Bluesky public API (public.api.bsky.app): each person's own posts, no replies, no reposts.
  - state/heads_inbox.txt: X or Bluesky post links you paste, one per line ("URL | optional note").
    Add them with: python tools/add_posts.py  (paste anything, for example a WhatsApp chat, it finds the links)
    X posts are read only through X's official embed service (publish.twitter.com/oembed). Nothing is scraped,
    nobody logs in, and the site shows X posts through X's own embedded-post widget.
    A line is moved to state/heads_inbox_done.txt once it has been handled.
  - Once a week every X post is checked again through oEmbed; a deleted post is removed from the site.

Each new post gets a short "What it means" note from the free LLM chain. The note may only explain
what the post itself says; code checks that every number in the note appears in the post.
Posts are kept forever in docs/data/heads.json. The site shows the last 7 days.

Run on its own:  python run_daily.py --heads-only
"""
import html
import json
import time
from html.parser import HTMLParser
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import llm
from .collect import looks_ai
from .curate import NUM, tidy
from .http import get

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "docs" / "data"
OUT = DATA / "heads.json"
INBOX = ROOT / "state" / "heads_inbox.txt"
INBOX_DONE = ROOT / "state" / "heads_inbox_done.txt"
REFRESH = ROOT / "state" / "x_refresh.json"
SKIPPED = ROOT / "state" / "heads_skipped.json"
BSKY = "https://public.api.bsky.app/xrpc/"
OEMBED = "https://publish.twitter.com/oembed"

DATA_WORDS = re.compile(r"\b(power ?bi|fabric|dax|semantic models?|lakehouse|analytics|data (?:science|engineering)|"
                        r"sql|copilot|data agents?)\b", re.I)
X_URL = re.compile(r"https?://(?:www\.|mobile\.)?(?:x|twitter)\.com/([A-Za-z0-9_]{1,15})/status(?:es)?/(\d+)")
BSKY_URL = re.compile(r"https?://bsky\.app/profile/([^/\s]+)/post/([A-Za-z0-9]+)")
MONTHS = {m: i for i, m in enumerate(["January", "February", "March", "April", "May", "June", "July", "August",
                                      "September", "October", "November", "December"], 1)}
WINDOW_DAYS = 7
MAX_NEW = 60          # most new posts sent to the AI per night
BATCH = 10


def roster():
    sys.path.insert(0, str(ROOT / "seed"))
    from heads import GROUPS, HEADS
    return GROUPS, HEADS


def relevant(text):
    return looks_ai(text) or bool(DATA_WORDS.search(text))


def _iso(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_time(s):
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return None


# ---------- Bluesky ----------

def _bsky_context(post):
    """Text of a linked page card or a quoted post, so the note knows what the post points at."""
    embed = post.get("embed") or {}
    kind = embed.get("$type", "")
    if "recordWithMedia" in kind:
        embed = embed.get("record") or {}
        kind = embed.get("$type", "app.bsky.embed.record#view")
    if "external" in kind:
        ext = embed.get("external") or {}
        return {"kind": "link", "url": ext.get("uri", ""), "title": ext.get("title", ""),
                "text": (ext.get("description") or "")[:400]}
    if "record" in kind:
        rec = embed.get("record") or {}
        rec = rec.get("record", rec) if "value" not in rec else rec
        author = (rec.get("author") or {}).get("handle", "")
        text = ((rec.get("value") or {}).get("text") or "")[:400]
        if text:
            return {"kind": "quote", "url": "", "title": f"Quoted post by @{author}", "text": text}
    return None


def _bsky_links(rec):
    """Bluesky shortens long links in the text ('example.com/a/b...'); the full address is in the facets."""
    raw = (rec.get("text") or "").encode("utf-8")
    out = []
    for f in rec.get("facets") or []:
        idx = f.get("index") or {}
        for feat in f.get("features") or []:
            if feat.get("$type", "").endswith("#link") and feat.get("uri", "").startswith(("http://", "https://")):
                try:
                    shown = raw[idx["byteStart"]:idx["byteEnd"]].decode("utf-8")
                except (KeyError, UnicodeDecodeError):
                    continue
                if shown:
                    out.append({"text": shown, "url": feat["uri"]})
    return out


def bsky_post(head, post):
    rec = post.get("record") or {}
    handle = post["author"]["handle"]
    rkey = post["uri"].rsplit("/", 1)[-1]
    created = _parse_time(rec.get("createdAt", ""))
    indexed = _parse_time(post.get("indexedAt", "")) or created
    if not created:
        return None
    when = min(created, indexed)  # an imported, back-dated post must not look new
    return {"id": f"bsky-{handle}-{rkey}", "person": head["id"], "platform": "bluesky",
            "url": f"https://bsky.app/profile/{handle}/post/{rkey}", "posted_at": _iso(when),
            "text": (rec.get("text") or "").strip(), "links": _bsky_links(rec), "context": _bsky_context(post),
            "likes": post.get("likeCount", 0), "reposts": post.get("repostCount", 0), "via": "feed"}


def bsky_feed(head, since):
    r = get(BSKY + "app.bsky.feed.getAuthorFeed", timeout=20,
            params={"actor": head["bsky"], "limit": 50, "filter": "posts_no_replies"})
    r.raise_for_status()
    out = []
    for item in r.json().get("feed", []):
        if item.get("reason"):                      # a repost of someone else
            continue
        post = item["post"]
        if post["author"]["handle"].lower() != head["bsky"].lower():
            continue
        p = bsky_post(head, post)
        if p and _parse_time(p["posted_at"]) >= since:
            out.append(p)
    return out


# ---------- inbox (X and Bluesky links you paste) ----------

class _EmbedCleaner(HTMLParser):
    """Keeps only X's blockquote with its p, a and br tags; drops scripts, styles and unknown attributes."""
    KEEP = {"blockquote": ("class", "lang", "dir", "data-dnt"), "p": ("lang", "dir"), "a": ("href",), "br": ()}

    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.out, self.depth, self.skip = [], 0, 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.skip += 1
            return
        if self.skip or tag not in self.KEEP or (tag != "blockquote" and not self.depth):
            return
        if tag == "blockquote":
            self.depth += 1
        kept = []
        for k, v in attrs:
            if k not in self.KEEP[tag] or v is None:
                continue
            if k == "href" and not v.startswith("https://"):
                continue
            kept.append(f' {k}="{html.escape(v, quote=True)}"')
        self.out.append(f"<{tag}{''.join(kept)}>" if tag != "br" else "<br>")

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.skip = max(0, self.skip - 1)
            return
        if self.skip or tag not in self.KEEP or tag == "br" or not self.depth:
            return
        self.out.append(f"</{tag}>")
        if tag == "blockquote":
            self.depth -= 1

    def handle_data(self, data):
        if self.depth and not self.skip:
            self.out.append(html.escape(data, quote=False))

    def handle_entityref(self, name):
        if self.depth and not self.skip:
            self.out.append(f"&{name};")

    def handle_charref(self, name):
        if self.depth and not self.skip:
            self.out.append(f"&#{name};")


def clean_embed(raw):
    c = _EmbedCleaner()
    c.feed(raw or "")
    out = "".join(c.out).strip()
    return out if out.startswith("<blockquote") and 'class="twitter-tweet"' in out else ""


def x_post(url, handle_hint):
    r = get(OEMBED, timeout=20, params={"url": url, "omit_script": 1, "dnt": "true", "hide_thread": "true"})
    if r.status_code != 200:
        raise ValueError(f"X embed returned {r.status_code} (deleted, private or wrong link?)")
    j = r.json()
    raw = j.get("html", "")
    m = re.search(r"<p[^>]*>(.*?)</p>", raw, re.S)
    body = m.group(1) if m else ""
    body = re.sub(r"<br\s*/?>", "\n", body)
    body = re.sub(r"<a [^>]*>(pic\.twitter\.com/\w+)</a>", "", body)
    body = re.sub(r"<a [^>]*>([^<]*)</a>", r"\1", body)
    text = html.unescape(re.sub(r"<[^>]+>", "", body)).strip()
    dates = re.findall(r">(\w+) (\d{1,2}), (\d{4})</a>", raw)
    if not dates or dates[-1][0] not in MONTHS:
        raise ValueError("could not read the post date from the X embed")
    mon, day, year = dates[-1]
    author = (j.get("author_url") or "").rstrip("/").rsplit("/", 1)[-1] or handle_hint
    status = X_URL.search(url).group(2)
    # X post ids carry their own creation time (milliseconds since 4 Nov 2010), which is exact;
    # the date printed in the embed is only a day and is in US time
    exact = datetime.fromtimestamp(((int(status) >> 22) + 1288834974657) / 1000, tz=timezone.utc)
    printed = datetime(int(year), MONTHS[mon], int(day), 12, tzinfo=timezone.utc)
    posted, date_only = (exact, False) if abs((exact - printed).days) <= 2 else (printed, True)
    return author, {"id": f"x-{status}", "platform": "x", "url": f"https://x.com/{author}/status/{status}",
                    "posted_at": _iso(posted), "date_only": date_only, "text": text, "context": None,
                    "embed_html": clean_embed(raw), "via": "inbox"}


def bsky_link(url):
    m = BSKY_URL.search(url)
    actor, rkey = m.group(1), m.group(2)
    did = actor
    if not actor.startswith("did:"):
        r = get(BSKY + "com.atproto.identity.resolveHandle", params={"handle": actor}, timeout=20)
        r.raise_for_status()
        did = r.json()["did"]
    r = get(BSKY + "app.bsky.feed.getPosts", params={"uris": f"at://{did}/app.bsky.feed.post/{rkey}"}, timeout=20)
    r.raise_for_status()
    posts = r.json().get("posts", [])
    if not posts:
        raise ValueError("Bluesky post not found")
    return posts[0]


def status_id(url):
    m = X_URL.search(url)
    if m:
        return f"x-{m.group(2)}"
    m = BSKY_URL.search(url)
    return f"bsky-{m.group(1)}-{m.group(2)}" if m else None


def read_inbox(heads, log, known=()):
    """Returns (posts, finished_lines). Finished lines are moved out of the inbox after the run."""
    finished = []
    if not INBOX.exists():
        INBOX.write_text("# Paste X or Bluesky post links here, one per line:  URL | optional note\n"
                         "# Only posts by the people in seed/heads.py are used. Lines starting with # are ignored.\n",
                         encoding="utf-8")
        return [], finished
    by_x = {h["x"].lower(): h for h in heads if h.get("x")}
    by_bsky = {h["bsky"].lower(): h for h in heads if h.get("bsky")}
    out = []
    for line in INBOX.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        url, _, note = (part.strip() for part in line.partition("|"))
        if status_id(url) in known:
            finished.append(line)          # already on the site
            continue
        try:
            if X_URL.search(url):
                author, p = x_post(url, X_URL.search(url).group(1))
                head = by_x.get(author.lower())
            elif BSKY_URL.search(url):
                post = bsky_link(url)
                head = by_bsky.get(post["author"]["handle"].lower())
                p = bsky_post(head, post) if head else None
                if p:
                    p["via"] = "inbox"
            else:
                log(f"   inbox: not an X or Bluesky post link, skipped: {url[:80]}")
                finished.append(f"{line}  # skipped: not a post link")
                continue
        except ValueError as exc:          # deleted, private or unreadable: no point retrying
            log(f"   inbox: could not read {url[:80]} ({str(exc)[:80]})")
            finished.append(f"{line}  # skipped: {str(exc)[:60]}")
            continue
        except Exception as exc:           # network trouble: keep the line and try again tomorrow
            log(f"   inbox: could not read {url[:80]} ({str(exc)[:80]})")
            continue
        if not head or not p:
            log(f"   inbox: {url[:80]} is not by one of the tracked accounts, skipped")
            finished.append(f"{line}  # skipped: not a tracked account")
            continue
        p["person"] = head["id"]
        if note:
            p["note"] = note[:200]
        p["_line"] = line
        out.append(p)
    return out, finished


def move_done(lines, log):
    """Take handled lines out of the inbox and append them, dated, to state/heads_inbox_done.txt."""
    if not lines or not INBOX.exists():
        return
    handled = {l.split("  # skipped")[0].strip() for l in lines}
    keep = [l for l in INBOX.read_text(encoding="utf-8").splitlines() if l.strip() not in handled]
    INBOX.write_text("\n".join(keep).rstrip() + "\n", encoding="utf-8")
    stamp = datetime.now(timezone.utc).date().isoformat()
    with INBOX_DONE.open("a", encoding="utf-8") as f:
        for l in lines:
            f.write(f"{stamp}  {l}\n")
    log(f"   inbox: {len(lines)} handled lines moved to state/heads_inbox_done.txt")


def refresh_x(log=print, every_days=7, force=False, dry_run=False):
    """Check X posts again through oEmbed; a post its author deleted (or made private) is removed from the site."""
    state = _load(REFRESH, {})
    now = datetime.now(timezone.utc)
    last = state.get("last_run")
    if not force and last and _parse_time(last) and (now - _parse_time(last)).days < every_days:
        return {"skipped": True, "last_run": last}
    store = _load(OUT, None)
    if not store:
        return {"checked": 0, "removed": 0}
    checked = removed = 0
    for p in store.get("posts", []):
        if p.get("platform") != "x" or p.get("removed"):
            continue
        time.sleep(1)
        try:
            r = get(OEMBED, timeout=20, params={"url": p["url"], "omit_script": 1, "dnt": "true"})
        except Exception as exc:
            log(f"   x refresh: stopped, network problem ({type(exc).__name__})")
            break
        if r.status_code == 429:
            log("   x refresh: X asked us to slow down; stopping until next time")
            break
        checked += 1
        if r.status_code in (403, 404):
            removed += 1
            log(f"   x refresh: {p['url']} is gone, removing it")
            if not dry_run:
                for k in ("text", "links", "embed_html", "meaning", "context", "note", "concepts", "story"):
                    p.pop(k, None)
                p["removed"] = now.date().isoformat()
    if not dry_run:
        OUT.write_text(json.dumps(store, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        REFRESH.write_text(json.dumps({"last_run": _iso(now), "checked": checked, "removed": removed}), encoding="utf-8")
    log(f"   x refresh: {checked} X posts checked, {removed} removed")
    return {"checked": checked, "removed": removed}


# ---------- "What it means" ----------

SYSTEM = """You explain posts by well-known AI people to a smart reader who is not an AI expert.

For each POST decide and write:
- keep: true if the post says something substantive about AI, machine learning, AI products, AI policy, or data and BI
  (Power BI, Fabric, analytics). false for greetings, personal life, jokes with no point, job ads, event logistics,
  or a bare link with nothing said about it.
- meaning: one or two plain sentences, at most 45 words. Say what the post claims, shares or announces, and why a
  person who builds with AI might care.
  Use ONLY the POST text and its LINK or QUOTE context. Do not add facts, names, numbers, dates or events that are not there.
  An opinion, prediction or claim stays attributed to the author ("Marcus argues...", "Altman says...").
  If the post is unclear, explain only what is clear. Never use em dashes.
- concepts: up to 3 ids from CONCEPTS that the post is clearly about, else [].
- story: the id of a STORY only if the post is clearly about that exact news, else null.

Reply as JSON: {"posts": [{"id": "...", "keep": true, "meaning": "...", "concepts": [], "story": null}]}"""


CHECK = """You check short notes that explain social media posts by AI people.
A note FAILS if it:
- states a fact, name, number, cause or consequence that the POST and its LINK or QUOTE do not say;
- presents the author's opinion, claim or prediction as settled fact instead of attributing it to the author;
- misreads what the post says.
Judge only against the text given. Wording and simplification are fine.
Reply as JSON: {"problems": [{"id": "...", "issue": "one short sentence"}]} listing only the notes that fail."""


def _post_block(p, names):
    parts = [f"id: {p['id']}", f"author: {names[p['person']]}", f"date: {p['posted_at'][:10]}", f"POST: {p['text']}"]
    ctx = p.get("context")
    if ctx:
        parts.append(f"{'LINK' if ctx['kind'] == 'link' else 'QUOTE'}: {ctx.get('title', '')} {ctx.get('text', '')}".strip())
    if p.get("note"):
        parts.append(f"EDITOR NOTE (context only, not a fact to repeat): {p['note']}")
    return "\n".join(parts)


def _source_text(p):
    ctx = p.get("context") or {}
    return f"{p['text']} {ctx.get('title', '')} {ctx.get('text', '')}".replace(",", "")


def _bad_numbers(meaning, p):
    hay = _source_text(p)
    return [n for n in (x.replace(",", "").rstrip(".") for x in NUM.findall(meaning)) if n and n not in hay]


def explain(posts, names, concept_ids, stories, log):
    """Return {post_id: result}. Posts the AI could not handle are left out and tried again next night."""
    concepts_txt = ", ".join(concept_ids)
    stories_txt = "\n".join(f"{s['id']}: {s['title']}" for s in stories) or "(none)"
    results = {}
    for i in range(0, len(posts), BATCH):
        chunk = posts[i:i + BATCH]
        user = (f"CONCEPTS: {concepts_txt}\n\nSTORIES this week:\n{stories_txt}\n\n" +
                "\n\n".join(_post_block(p, names) for p in chunk))
        try:
            res, model = llm.ask_json(SYSTEM, user, max_tokens=2200, tag="heads")
        except RuntimeError as exc:
            log(f"   heads: AI notes failed for {len(chunk)} posts ({str(exc)[:100]})")
            continue
        for r in res.get("posts") or []:
            if isinstance(r, dict) and r.get("id"):
                r["model"] = model
                results[r["id"]] = r
    # check every note: code for numbers, a different model family for anything the post does not say
    by_id = {p["id"]: p for p in posts}
    todo = [pid for pid, r in results.items() if pid in by_id and r.get("keep") and r.get("meaning")]
    problems = {}
    for pid in todo:
        bad = _bad_numbers(results[pid]["meaning"], by_id[pid])
        if bad:
            problems[pid] = f"uses numbers that are not in the post: {', '.join(bad)}"
    for i in range(0, len(todo), BATCH):
        chunk = todo[i:i + BATCH]
        user = "\n\n".join(_post_block(by_id[pid], names) + f"\nNOTE: {results[pid]['meaning']}" for pid in chunk)
        try:
            res, checker = llm.ask_json(CHECK, user, max_tokens=1200, tag="checker")
        except RuntimeError as exc:
            log(f"   heads: checker unavailable ({str(exc)[:80]}); notes kept with the number check only")
            continue
        for pr in res.get("problems") or []:
            if isinstance(pr, dict) and pr.get("id") in chunk and pr.get("issue"):
                problems.setdefault(pr["id"], str(pr["issue"])[:300])
        for pid in chunk:
            results[pid]["checked"] = checker
    for pid, issue in problems.items():
        p = by_id[pid]
        user = (_post_block(p, names) + f"\n\nYour earlier note: {results[pid]['meaning']}\nA checker found this problem: "
                f"{issue}\nWrite the note again so it only says what the post says.\n\nCONCEPTS: " + concepts_txt)
        try:
            res, model = llm.ask_json(SYSTEM, user, max_tokens=800, tag="heads")
            new = next((r for r in res.get("posts") or [] if isinstance(r, dict) and r.get("id") == pid), None)
        except RuntimeError:
            new = None
        if new and new.get("meaning") and not _bad_numbers(new["meaning"], p):
            new["model"], new["checked"] = model, results[pid].get("checked")
            new["concepts"] = new.get("concepts") or results[pid].get("concepts")
            new["story"] = new.get("story") or results[pid].get("story")
            results[pid] = new
            log(f"   heads: note for {pid} rewritten ({issue[:70]})")
        else:
            results[pid]["meaning"] = ""   # publish the quote without a note rather than a wrong note
            log(f"   heads: note for {pid} dropped ({issue[:70]})")
    return results


# ---------- store ----------

def _load(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def recent_stories(days=WINDOW_DAYS):
    index = _load(DATA / "editions" / "index.json", {"editions": []})
    out, months = [], {}
    for e in index.get("editions", [])[:days]:
        if e["file"] not in months:
            months[e["file"]] = _load(DATA / "editions" / e["file"], {"editions": {}})
        ed = months[e["file"]].get("editions", {}).get(e["date"], {})
        out += [{"id": s["id"], "title": s["title"]} for s in ed.get("stories", [])]
    return out


def update(log=print, days=WINDOW_DAYS):
    groups, heads = roster()
    names = {h["id"]: h["name"] for h in heads}
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=days)
    store = _load(OUT, {"posts": []})
    known = {p["id"]: p for p in store.get("posts", [])}
    skipped = _load(SKIPPED, {})
    skipped = {k: v for k, v in skipped.items() if v >= (now - timedelta(days=21)).date().isoformat()}

    # 1. collect
    found, health = [], {}
    with_bsky = [h for h in heads if h.get("bsky")]

    def one(h):
        try:
            return h, bsky_feed(h, since), None
        except Exception as exc:
            return h, [], f"{type(exc).__name__}: {str(exc)[:60]}"

    with ThreadPoolExecutor(max_workers=8) as pool:
        for h, posts, err in pool.map(one, with_bsky):
            health[h["id"]] = err or len(posts)
            found += posts
    failed = [k for k, v in health.items() if isinstance(v, str)]
    log(f"   Bluesky: {len(found)} posts in {days} days from {len(with_bsky) - len(failed)} of {len(with_bsky)} accounts"
        + (f" ({len(failed)} failed: {', '.join(failed)})" if failed else ""))
    inbox, finished = read_inbox(heads, log, known)
    log(f"   inbox: {len(inbox)} new post links read")

    # 2. pick the new ones worth a note
    new, seen_ids = [], set()
    for p in inbox + found:
        if p["id"] in known or p["id"] in skipped or p["id"] in seen_ids:
            continue
        seen_ids.add(p["id"])
        ctx = p.get("context") or {}
        if p["via"] == "feed":
            if not relevant(f"{p['text']} {ctx.get('title', '')} {ctx.get('text', '')}"):
                skipped[p["id"]] = p["posted_at"][:10]
                continue
            if len(p["text"]) < 25 and not ctx:
                skipped[p["id"]] = p["posted_at"][:10]
                continue
        new.append(p)
    new = sorted(new, key=lambda p: (p["via"] == "inbox", p["posted_at"]), reverse=True)[:MAX_NEW]  # your links first
    log(f"   {len(new)} new posts to explain")

    # 3. explain
    concepts = _load(DATA / "concepts.json", [])
    concept_ids = [c["id"] for c in concepts]
    stories = recent_stories(days)
    story_ids = {s["id"] for s in stories}
    results = explain(new, names, concept_ids, stories, log) if new else {}

    added = 0
    for p in new:
        r = results.get(p["id"])
        if not r:
            continue                      # AI unavailable: try again next night
        if not r.get("keep") and p["via"] != "inbox":
            skipped[p["id"]] = p["posted_at"][:10]
            continue
        p["meaning"] = tidy(r.get("meaning") or "")
        p["concepts"] = [c for c in (r.get("concepts") or []) if c in concept_ids][:3]
        p["story"] = r.get("story") if r.get("story") in story_ids else None
        p["model"] = r.get("model")
        p["checked"] = r.get("checked")
        p["added"] = now.date().isoformat()
        line = p.pop("_line", None)
        if line:
            finished.append(line)
        known[p["id"]] = p
        added += 1

    # likes, reposts and link data can change; refresh them for posts still in the window
    for p in found:
        if p["id"] in known:
            for k in ("likes", "reposts", "links", "context"):
                known[p["id"]][k] = p.get(k)

    for p in known.values():
        p.pop("_line", None)
    posts = sorted(known.values(), key=lambda p: p["posted_at"], reverse=True)
    out = {"updated_at": _iso(now), "window_days": days, "groups": groups, "people": heads, "posts": posts}
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    SKIPPED.parent.mkdir(parents=True, exist_ok=True)
    SKIPPED.write_text(json.dumps(skipped, indent=0, sort_keys=True), encoding="utf-8")
    move_done(finished, log)
    week = [p for p in posts if _parse_time(p["posted_at"]) >= since and not p.get("removed")]
    log(f"   {added} posts added; {len(week)} in the last {days} days; {len(posts)} kept in total")
    return {"added": added, "week": len(week), "total": len(posts), "bsky_failed": failed}
