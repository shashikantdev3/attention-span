"""Importance and discussion signals for story groups, computed in code before the editor sees them.

The editor used to see only how many sources carried a story. A widely discussed essay or memo from an industry
leader (for example Proton's CTO memo in Oct 2026: 240 Hacker News points, a reply post with 99 comments) looked the
same as a minor item, and the prompt told the editor to skip opinion pieces. These signals fix that:

  engagement   Hacker News points (log scale)
  discussion   comment count (log scale), and "heated" when comments are at least half the points
  breadth      independent sources (publisher families count once)
  authority    a major lab's own site, or a company leader (CEO, CTO, founder) in the title or snippet
  shift        language about how AI changes work: memo, manifesto, layoffs, hiring, interviews, "no longer" ...

score() returns 0 to 100. The editor sees the labels; code then adds a high-scoring story the editor left out
(signal_includes) and spotlights picked stories that are both high-scoring and about a shift or a heated debate.
"""
import math
import re
from urllib.parse import urlsplit

SHIFT = re.compile(r"\b(manifestos?|memos?|internal memo|AI mandate|AI-first|layoffs?|laid off|job cuts|hiring|interviews?|jobs|engineers|engineering culture|"
                   r"programming is|is dead|the end of|no longer|future of (?:work|software|coding)|replac\w+|reckoning|"
                   r"open letter|resign\w*|fired|backlash|walkout|software engineers?|developers will|coders?|workforce)\b", re.I)
LEADER = re.compile(r"\b(ceo|cto|cfo|coo|chief [a-z]+ officer|founder|co-founder|cofounder)\b", re.I)
MAJOR = ("openai.com", "anthropic.com", "claude.com", "blog.google", "deepmind.google", "microsoft.com", "github.blog",
         "ai.meta.com", "mistral.ai", "deepseek.com", "qwen.ai", "nvidia.com", "x.ai")

INCLUDE_AT = 60    # an unpicked story at or above this is added by code
SPOTLIGHT_AT = 65  # a picked story at or above this, about a shift or a heated debate, is spotlighted


def _hn(items, key):
    return max((i.get(key) or 0) for i in items if i.get("source") == "hn") if any(i.get("source") == "hn" for i in items) else 0


def measure(story):
    items = story["items"]
    pts, com = _hn(items, "points"), _hn(items, "comments")
    text = " ".join(f"{i['title']} {i.get('text', '')[:400]} {i.get('page_desc', '')}" for i in items)
    sig = {"points": pts, "comments": com, "sources": story.get("buzz", 1),
           "heated": com >= 100 and pts > 0 and com / pts >= 0.8,
           "official": any(urlsplit(i["url"]).netloc.lower().removeprefix("www.").endswith(MAJOR) for i in items),
           "leader": bool(LEADER.search(text)), "shift": bool(SHIFT.search(text)),
           "promo": all(re.match(r"(launch|show) hn", i["title"], re.I) for i in items if i.get("source") == "hn") and pts > 0}
    s = min(45, 18 * math.log10(pts + 1)) + min(20, 10 * math.log10(com + 1)) + min(24, 8 * (sig["sources"] - 1))
    s += 8 * sig["heated"] + 10 * sig["official"] + 6 * sig["leader"] + 10 * sig["shift"]
    sig["score"] = round(min(100, s))
    return sig


def enrich(stories, top=15, log=print):
    """Fetch the page description of the most-discussed links, so the shift and leader checks see more than a title.
    Hacker News link posts carry no text of their own."""
    from .http import get
    busy = sorted(stories, key=lambda s: -_hn(s["items"], "points"))[:top]
    n = 0
    for s in busy:
        for i in s["items"]:
            if i.get("source") != "hn" or i.get("page_desc"):
                continue
            try:
                r = get(i["url"], timeout=10)
                m = re.search(r'<meta[^>]+(?:name|property)="(?:og:)?description"[^>]+content="([^"]{20,600})"', r.text or "", re.I)
                if m:
                    i["page_desc"] = m.group(1); n += 1
            except Exception:  # noqa: BLE001
                pass
    log(f"   signals: read the page description of {n} busy links")


def label(sig):
    parts = []
    if sig["points"]:
        parts.append(f"HN {sig['points']} pts, {sig['comments']} comments")
    if sig["heated"]:
        parts.append("heated debate")
    if sig["official"]:
        parts.append("lab's own post")
    if sig["leader"]:
        parts.append("company leader")
    if sig["shift"]:
        parts.append("industry shift")
    return f"signal {sig['score']}" + (f" ({'; '.join(parts)})" if parts else "")


def annotate(stories):
    for s in stories:
        s["signals"] = measure(s)
    return stories


def signal_includes(stories, picked, limit=3):
    """High-signal stories the editor left out, strongest first."""
    def substance(sig):  # engagement alone is not enough: popular personal blog posts score high too
        return sig["official"] or sig["leader"] or sig["shift"] or sig["sources"] >= 2
    out = [s for s in stories if s["cid"] not in picked and s.get("signals", {}).get("score", 0) >= INCLUDE_AT
           and not s["signals"].get("promo") and substance(s["signals"])]
    return sorted(out, key=lambda s: -s["signals"]["score"])[:limit]


def spotlight_reason(sig):
    why = []
    if sig["shift"]:
        why.append("it speaks to how AI is changing the way software is built")
    if sig["heated"] or sig["comments"] >= 80:
        why.append(f"it drew {sig['comments']} comments on Hacker News")
    if sig["points"] >= 100:
        why.append(f"{sig['points']} points on Hacker News")
    if sig["sources"] >= 3:
        why.append(f"{sig['sources']} independent sources covered it")
    return "Widely discussed: " + ", ".join(why) + "." if why else ""


def auto_spotlight(sig):
    """Rare by design: a high score alone is not enough; it must be about a shift in how AI is built or used,
    or a heated debate around something a company leader said or did."""
    return (sig.get("score", 0) >= SPOTLIGHT_AT and not sig.get("promo")
            and (sig["shift"] or (sig["heated"] and sig["leader"])))
