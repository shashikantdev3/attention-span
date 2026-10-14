"""Plain HTML pages for search engines and link previews, plus sitemap.xml, robots.txt and feed.xml.

The site itself is one JavaScript page, which search engines and LinkedIn previews read poorly.
This writes a readable static page for every story, edition, week and concept, each linking into the app:

    docs/s/<story id>.html      docs/e/<date>.html      docs/w/<year-Wnn>.html      docs/c/<concept id>.html
    docs/sitemap.xml            docs/robots.txt         docs/feed.xml (RSS, latest 50 stories)

Runs automatically from tools/bundle_data.py (so after every nightly run and seed build).
Set SITE_URL in .env if the site moves; the default is the GitHub Pages address.
"""
import html
import json
import os
from datetime import date, datetime, timedelta, timezone
from email.utils import format_datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
DATA = DOCS / "data"
SITE = os.getenv("SITE_URL", "https://shashikantdev3.github.io/attention-span/").rstrip("/") + "/"
NAME = "Attention Span"
TAGLINE = "Today's AI news, traced back to its roots."
OG_IMAGE = "assets/og.png"

e = lambda s: html.escape(str(s or ""), quote=True)  # noqa: E731


def read(p, default=None):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def long_date(d):
    return datetime.fromisoformat(d).strftime("%A, %-d %B %Y") if os.name != "nt" else \
        datetime.fromisoformat(d).strftime("%A, %#d %B %Y")


def short_date(d):
    return datetime.fromisoformat(d).strftime("%-d %b %Y") if os.name != "nt" else \
        datetime.fromisoformat(d).strftime("%#d %b %Y")


def iso_week(d):
    y, w, _ = date.fromisoformat(d).isocalendar()
    return f"{y}-W{w:02d}"


def week_bounds(wid):
    y, w = wid.split("-W")
    start = date.fromisocalendar(int(y), int(w), 1)
    return start, start + timedelta(days=6)


def page(path, title, description, body, app_link, kind="article", ld=None, image=OG_IMAGE):
    """Write one static page. `path` is relative to docs/, for example 's/x.html'."""
    depth = path.count("/")
    up = "../" * depth
    url = SITE + path
    ld_json = f'<script type="application/ld+json">{json.dumps(ld, ensure_ascii=False)}</script>' if ld else ""
    doc = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(title)} | {NAME}</title>
<meta name="description" content="{e(description)}">
<link rel="canonical" href="{e(url)}">
<meta property="og:type" content="{kind}">
<meta property="og:site_name" content="{NAME}">
<meta property="og:title" content="{e(title)}">
<meta property="og:description" content="{e(description)}">
<meta property="og:url" content="{e(url)}">
<meta property="og:image" content="{e(SITE + image)}">
<meta name="twitter:card" content="summary_large_image">
<meta name="theme-color" content="#EDF0EA">
<link rel="alternate" type="application/rss+xml" title="{NAME}" href="{up}feed.xml">
<script>try{{var t=localStorage.getItem("as-theme");if(!t)t=matchMedia("(prefers-color-scheme: dark)").matches?"night":"day";if(t==="night")document.documentElement.setAttribute("data-theme","night")}}catch(e){{}}</script>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=Newsreader:ital,opsz,wght@0,6..72,400;0,6..72,500;0,6..72,600;0,6..72,700;1,6..72,400&family=Bodoni+Moda:opsz,wght@6..96,700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="{up}assets/style.css">
{ld_json}
</head>
<body class="static">
<header class="masthead static-head"><div class="wrap">
  <a class="brand" href="{up}index.html"><span class="static-name">{NAME}</span></a>
  <span class="tagline">{e(TAGLINE)}</span>
</div></header>
<main id="main"><div class="wrap static-body">
{body}
<p class="static-app"><a href="{up}index.html{app_link}">Open this in Attention Span</a>, where every story links to its history,
concepts and the people behind it.</p>
</div></main>
<footer class="site"><div class="wrap">
  <span>{NAME} is built by <a href="https://github.com/shashikantdev3">Shashikant</a>. Every entry links its source.</span>
  <span>Data under <a href="https://creativecommons.org/licenses/by-nc/4.0/" rel="license">CC BY-NC 4.0</a>. Code under MIT.</span>
</div></footer>
</body>
</html>
"""
    out = DOCS / path
    out.parent.mkdir(parents=True, exist_ok=True)
    if not out.exists() or out.read_text(encoding="utf-8") != doc:
        out.write_text(doc, encoding="utf-8")
    return url


def build():
    meta = read(DATA / "meta.json", {})
    labs = {l["id"]: l["name"] for l in meta.get("labs", [])}
    layers = {l["id"]: l["name"] for l in meta.get("layers", [])}
    topics = {t["id"]: t["name"] for t in meta.get("topics", [])}
    concepts = read(DATA / "concepts.json", [])
    cby = {c["id"]: c for c in concepts}
    timeline = {t["id"]: t for t in read(DATA / "timeline.json", [])}
    index = read(DATA / "editions" / "index.json", {"editions": []})
    editions, months = {}, {}
    for ed in index.get("editions", []):
        if ed["file"] not in months:
            months[ed["file"]] = read(DATA / "editions" / ed["file"], {"editions": {}})
        if ed["date"] in months[ed["file"]].get("editions", {}):
            editions[ed["date"]] = months[ed["file"]]["editions"][ed["date"]]
    stories = [s for d in sorted(editions, reverse=True) for s in editions[d]["stories"]]
    urls = [(SITE, index.get("updated", "")[:10] or date.today().isoformat())]
    news_by_concept = {}
    for s in stories:
        for c in s.get("concepts", []):
            news_by_concept.setdefault(c, []).append(s)

    def concept_chips(ids, up="../"):
        return "".join(f'<a class="chip concept" href="{up}c/{e(c)}.html">{e(cby[c]["term"])}</a>'
                       for c in ids if c in cby)

    # stories
    for s in stories:
        src = "".join(f'<li><a href="{e(x["url"])}" rel="noopener">{e(x["name"])}: {e(x["title"])}</a> '
                      f'<span class="kind">{e(x["kind"])}</span></li>' for x in s.get("sources", []))
        tags = "".join(f'<span class="chip">{e(labs.get(l, l))}</span>' for l in s.get("labs", [])) + concept_chips(s.get("concepts", []))
        body = f"""<article class="static-story">
<p class="static-kicker"><a href="../e/{e(s['date'])}.html">{e(long_date(s['date']))}</a>, {e(topics.get(s.get('topic'), s.get('topic', '')))},
{s.get('buzz', 1)} source{'s' if s.get('buzz', 1) != 1 else ''}</p>
<h1>{e(s['title'])}</h1>
<p class="one-liner">{e(s['one_liner'])}</p>
<p>{e(s['summary'])}</p>
{f'<div class="eli5"><h4>Like I am 5</h4><p>{e(s["eli5"])}</p></div>' if s.get('eli5') else ''}
{f'<div class="why"><h4>Why it matters</h4><p>{e(s["why_it_matters"])}</p></div>' if s.get('why_it_matters') else ''}
<div class="sources"><h4>Sources, original first</h4><ol>{src}</ol></div>
{f'<div class="tags">{tags}</div>' if tags else ''}
<p class="asof">Written from the sources above and checked by a second AI model; every number was matched against the sources.</p>
</article>"""
        ld = {"@context": "https://schema.org", "@type": "NewsArticle", "headline": s["title"][:110],
              "description": s["one_liner"], "datePublished": s.get("published") or s["date"], "dateModified": s["date"],
              "author": {"@type": "Organization", "name": NAME, "url": SITE},
              "publisher": {"@type": "Organization", "name": NAME, "url": SITE},
              "mainEntityOfPage": SITE + f"s/{s['id']}.html", "image": SITE + OG_IMAGE,
              "isBasedOn": [x["url"] for x in s.get("sources", []) if x.get("kind") != "discussion"]}
        urls.append((page(f"s/{s['id']}.html", s["title"], s["one_liner"], body, f"#/today/{s['date']}/{s['id']}",
                          ld=ld), s["date"]))

    # editions
    for d, ed in editions.items():
        items = "".join(f'<li><a href="../s/{e(s["id"])}.html">{e(s["title"])}</a><p>{e(s["one_liner"])}</p></li>'
                        for s in ed["stories"])
        body = f"""<h1>AI news for {e(long_date(d))}</h1>
<p class="one-liner">{len(ed['stories'])} stories, each written from its sources and fact-checked.</p>
<ol class="static-list">{items}</ol>
<p><a href="../w/{iso_week(d)}.html">The rest of this week</a></p>"""
        lead = ed["stories"][0]["title"] if ed["stories"] else ""
        urls.append((page(f"e/{d}.html", f"AI news, {short_date(d)}: {lead}", f"{len(ed['stories'])} AI stories for {long_date(d)}, "
                          f"led by: {lead}.", body, f"#/today/{d}", kind="website"), d))

    # weeks
    weeks = {}
    for d in editions:
        weeks.setdefault(iso_week(d), []).append(d)
    for wid, dates in weeks.items():
        start, end = week_bounds(wid)
        ws = [s for d in sorted(dates) for s in editions[d]["stories"]]
        score = lambda s: (s.get("buzz") or 1) * 2 + (3 if s.get("rank") == 1 else 0) + (2 if s.get("spotlight") else 0) \
            - (s.get("rank") or 10) * 0.1  # noqa: E731
        top = sorted(ws, key=score, reverse=True)[:7]
        rng = f"{start.day} {start.strftime('%B') if start.month != end.month else ''} to {end.day} {end.strftime('%B %Y')}".replace("  ", " ")
        items = "".join(f'<li><a href="../s/{e(s["id"])}.html">{e(s["title"])}</a><p>{e(s["one_liner"])}</p></li>' for s in top)
        days = "".join(f'<li><a href="../e/{d}.html">{e(long_date(d))}</a></li>' for d in sorted(dates, reverse=True))
        body = f"""<h1>The week in AI: {e(rng)}</h1>
<p class="one-liner">The stories that mattered most, from {len(dates)} daily edition{'s' if len(dates) != 1 else ''} and {len(ws)} stories.</p>
<ol class="static-list">{items}</ol>
<h2>Every edition this week</h2><ul>{days}</ul>"""
        urls.append((page(f"w/{wid}.html", f"The week in AI, {rng}", f"The {len(top)} AI stories that mattered most, {rng}.",
                          body, f"#/week/{wid}", kind="website"), max(dates)))

    # concepts
    for c in concepts:
        rel = lambda ids: ", ".join(f'<a href="{e(x)}.html">{e(cby[x]["term"])}</a>' for x in ids if x in cby) or "none in this glossary yet"  # noqa: E731
        hist = "".join(f'<li>{e(timeline[t]["date"])}: {e(timeline[t]["title"])}. {e(timeline[t]["one_liner"])}</li>'
                       for t in c.get("entries", []) if t in timeline)
        news = "".join(f'<li><a href="../s/{e(s["id"])}.html">{e(s["title"])}</a> ({e(short_date(s["date"]))})</li>'
                       for s in news_by_concept.get(c["id"], [])[:10])
        body = f"""<article class="static-story">
<p class="static-kicker">Concept, {e(layers.get(c['layer'], c['layer']))}</p>
<h1>What is {e(c['term'])}?</h1>
{f'<p class="asof">Also called {e(", ".join(c["aka"]))}</p>' if c.get('aka') else ''}
<p class="one-liner">{e(c['definition'])}</p>
<div class="eli5"><h4>Like I am 5</h4><p>{e(c['eli5'])}</p></div>
<p><b>Evolved from:</b> {rel(c.get('evolved_from', []))}</p>
<p><b>Led to:</b> {rel(c.get('led_to', []))}</p>
{f'<h2>In history</h2><ul>{hist}</ul>' if hist else ''}
{f'<h2>In the news</h2><ul>{news}</ul>' if news else ''}
</article>"""
        ld = {"@context": "https://schema.org", "@type": "DefinedTerm", "name": c["term"], "description": c["definition"],
              "url": SITE + f"c/{c['id']}.html",
              "inDefinedTermSet": {"@type": "DefinedTermSet", "name": f"{NAME} AI glossary", "url": SITE + "#/concepts"}}
        urls.append((page(f"c/{c['id']}.html", f"What is {c['term']}? Plain definition and lineage", c["definition"][:300],
                          body, f"#/concepts/{c['id']}", ld=ld), index.get("updated", "")[:10] or date.today().isoformat()))

    # sitemap, robots, feed
    sm = "".join(f"<url><loc>{e(u)}</loc><lastmod>{d}</lastmod></url>" for u, d in urls)
    (DOCS / "sitemap.xml").write_text('<?xml version="1.0" encoding="UTF-8"?>\n'
                                      f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{sm}</urlset>\n',
                                      encoding="utf-8")
    (DOCS / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {SITE}sitemap.xml\n", encoding="utf-8")

    def rfc822(s):
        try:
            dt = datetime.fromisoformat((s.get("published") or s["date"] + "T18:00:00Z").replace("Z", "+00:00"))
        except ValueError:
            dt = datetime.fromisoformat(s["date"] + "T18:00:00+00:00")
        return format_datetime(dt.astimezone(timezone.utc))

    items = "".join(f"""<item><title>{e(s['title'])}</title><link>{e(SITE)}s/{e(s['id'])}.html</link>
<guid isPermaLink="true">{e(SITE)}s/{e(s['id'])}.html</guid><pubDate>{rfc822(s)}</pubDate>
<description>{e(s['one_liner'] + ' ' + s['summary'])}</description></item>""" for s in stories[:50])
    (DOCS / "feed.xml").write_text(f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom"><channel>
<title>{NAME}</title><link>{e(SITE)}</link><description>{e(TAGLINE)}</description><language>en</language>
<atom:link href="{e(SITE)}feed.xml" rel="self" type="application/rss+xml"/>
{items}
</channel></rss>
""", encoding="utf-8")
    return len(urls)


if __name__ == "__main__":
    print(f"wrote {build()} pages into the sitemap")
