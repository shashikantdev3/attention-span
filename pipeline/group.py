"""Step 2: remove duplicates and group items about the same event into stories.

Pure Python TF-IDF over titles and the start of each item's text, so nothing heavy
needs installing. Buzz = how many distinct sources carry the story.
"""
import math
import re
from collections import Counter
from urllib.parse import urlsplit, urlunsplit

STOP = set("""a an the and or of to in on for with by from at as is are was were be been it its this that these those
new how why what who when your you we our they their his her not no but if into over about after than more most up
out via vs says say said will can just now one two three first launches launch launched releases release released
introducing introduces announces announced update updates using use show hn ask""".split())
NUM_WORDS = {"three": "3", "two": "2", "four": "4", "five": "5", "six": "6"}


def norm_url(url):
    p = urlsplit(url.strip())
    host = p.netloc.lower().removeprefix("www.").removeprefix("m.")
    path = re.sub(r"/+$", "", p.path)
    return urlunsplit(("https", host, path, "", ""))


def tokens(text):
    out = []
    for w in re.findall(r"[a-z0-9][a-z0-9.+-]*", text.lower()):
        w = NUM_WORDS.get(w, w).strip(".-")
        if len(w) < 2 or w in STOP:
            continue
        if len(w) > 4 and w.endswith("s") and not w.endswith("ss"):
            w = w[:-1]
        if w.startswith("mathematic"):
            w = "math"
        out.append(w)
    return out


def _vectors(docs):
    df = Counter()
    toks = [tokens(d) for d in docs]
    for t in toks:
        df.update(set(t))
    n = len(docs)
    vecs = []
    for t in toks:
        tf = Counter(t)
        v = {w: (1 + math.log(c)) * math.log((n + 1) / (df[w] + 0.5)) for w, c in tf.items()}
        norm = math.sqrt(sum(x * x for x in v.values())) or 1.0
        vecs.append({w: x / norm for w, x in v.items()})
    return vecs


def cosine(a, b):
    if len(a) > len(b):
        a, b = b, a
    return sum(x * b.get(w, 0.0) for w, x in a.items())


def group(items, threshold=0.32):
    """Return a list of stories: {items:[...], sources:set, buzz, score}."""
    # 1. exact URL duplicates
    by_url = {}
    for it in items:
        key = norm_url(it["url"])
        if key in by_url:
            by_url[key]["also"].append(it)
        else:
            it = dict(it, also=[])
            by_url[key] = it
    uniq = list(by_url.values())

    # 2. text similarity on title plus a little of the text
    # Machine-generated sources (model cards, repos, papers) share boilerplate text, so only
    # their titles are compared. News and blog items also contribute their first sentences.
    templated = {"hf-models", "github", "hf-papers"}
    docs = [f"{u['title']} {u['title']}" + ("" if u["source"] in templated else f" {u['text'][:200]}")
            for u in uniq]
    vecs = _vectors(docs)
    title_vecs = _vectors([u["title"] for u in uniq])
    parent = list(range(len(uniq)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(len(uniq)):
        for j in range(i + 1, len(uniq)):
            # two posts from the same source are usually different stories, so demand near-identical text
            if uniq[i]["source"] == uniq[j]["source"]:
                same = cosine(title_vecs[i], title_vecs[j]) >= 0.6
            else:
                same = cosine(vecs[i], vecs[j]) >= threshold
            if same:
                parent[find(i)] = find(j)

    clusters = {}
    for i, u in enumerate(uniq):
        clusters.setdefault(find(i), []).append(u)

    stories = []
    for members in clusters.values():
        flat = []
        for m in members:
            flat.append(m)
            flat.extend(m["also"])
        sources = {m["source"] for m in flat}
        weight = sum(max(m["weight"] for m in flat if m["source"] == s) for s in sources)
        points = max((m.get("points") or 0) for m in flat)
        score = weight + math.log10(points + 1) + (2 if any(m.get("inbox") for m in flat) else 0)
        stories.append({"items": flat, "sources": sorted(sources), "buzz": len(sources),
                        "score": round(score, 2), "points": points})
    stories.sort(key=lambda s: -s["score"])
    for k, s in enumerate(stories):
        s["cid"] = f"c{k}"
    return stories
