"""Steps 3 to 5: pick the day's stories, write them from source text, and fact-check them.

Editor  (1 call)       : merges duplicate groups, picks the stories that matter to builders.
Writer  (1 per story)  : writes title, one-liner, summary, ELI5 and tags from SOURCE TEXT only.
Checker (1 per story)  : a separate call lists any claim the sources do not support.
                         One rewrite is allowed; a story that still fails is dropped, not published.
Code checks             : every number must appear in the sources, tags must be known ids,
                         length limits, and no em dashes.
"""
import json
import re

from urllib.parse import urlsplit

from .extract import article_text
from .group import tokens
from .llm import ask_json

HYPE = ["revolutionary", "game-changer", "game changer", "groundbreaking", "unprecedented", "supercharge",
        "seamless", "unlock", "cutting-edge", "paradigm shift", "next-level", "mind-blowing"]

STYLE = ("Write plain, simple English for working developers and data people. Short sentences. "
         "No hype words (" + ", ".join(HYPE) + "). Never use em dashes; use commas or full stops. "
         "Never invent facts, numbers, dates, names or quotes.")


# ---------------------------------------------------------------- editor
def editor(stories, meta, max_stories, log):
    rows = []
    for s in stories:
        titles = " || ".join(dict.fromkeys(i["title"][:110] for i in s["items"]))[:330]
        snippet = next((i["text"][:160] for i in s["items"] if i["text"]), "")
        rows.append(f"{s['cid']} | sources={s['buzz']} ({','.join(s['sources'][:4])}) | {titles} | {snippet}")
    topics = ", ".join(t["id"] for t in meta["topics"])
    system = ("You are the editor of Attention Span, a daily AI news bulletin for AI builders, developers and data "
              "professionals. " + STYLE)
    user = f"""Below are candidate story groups collected in the last 24 hours, one per line:
cid | how many independent sources | titles | snippet

{chr(10).join(rows)}

These are real items from today's feeds. Many releases are newer than anything you know about; never skip a story
because you do not recognise a model or product name.

Tasks:
1. "merge": list groups of cids that are clearly about the SAME event, for example an official launch post and press
   coverage of it. Titles often describe the same launch differently (a product name versus a description of the
   feature), so look at the snippets too.
2. "picks": choose up to {max_stories} stories that matter most to people who build with AI today. Prefer official
   launches of models, products, APIs and tools; research with practical impact; major safety, policy or legal events;
   big industry moves. Skip pure marketing, event promos, minor funding rounds under 100 million dollars unless the
   company is notable, opinion pieces, generic tutorials and gadget reviews. At most 3 research papers. If there is a
   substantive Power BI or Microsoft Fabric item, include one with topic "data-bi".
   When the day has enough real news, pick at least {min(8, max_stories)}. Launches by major labs (OpenAI, Anthropic,
   Google, Microsoft, Meta, Mistral, DeepSeek, Qwen, NVIDIA) and stories carried by several sources usually lead.
   Order picks by importance. For each pick give the cid (use the first cid of a merged group), a topic from
   [{topics}], and a one-sentence reason.
3. "spotlight": at most 2 cids that introduce a genuinely new KIND of thing (a new category of model, interface,
   protocol or method), not a bigger or better version of something that exists. Usually empty or one.
Return JSON: {{"merge": [["c1","c7"]], "picks": [{{"cid": "c0", "topic": "models", "reason": "..."}}],
"spotlight": [{{"cid": "c0", "reason": "..."}}]}}"""
    result, model = ask_json(system, user, max_tokens=3000, tag="editor", reasoning="medium")
    log(f"  editor ({model}): {len(result.get('picks', []))} picks, {len(result.get('merge', []))} merges")
    return result


MAJOR_LABS = ("openai.com", "anthropic.com", "claude.com", "blog.google", "deepmind.google", "googleblog.com",
              "microsoft.com", "github.blog", "ai.meta.com", "about.fb.com", "mistral.ai", "deepseek.com",
              "qwenlm.github.io", "qwen.ai", "nvidia.com", "x.ai")


def must_include(stories, picked_cids, limit=3):
    """Safety net: a major lab's own announcement with a strong signal is always published,
    even if the AI editor leaves it out."""
    out = []
    for s in stories:
        if s["cid"] in picked_cids:
            continue
        official = any(urlsplit(i["url"]).netloc.lower().removeprefix("www.").endswith(MAJOR_LABS) for i in s["items"])
        if official and (s["points"] >= 300 or s["buzz"] >= 3):
            out.append(s)
    return out[:limit]


def _keywords(story):
    words = set()
    for it in story["items"]:
        words |= {w for w in tokens(it["title"]) if not w.replace(".", "").isdigit() and len(w) > 2}
    return words


def apply_merges(stories, merges, log=print):
    """Apply the editor's merges, but only when the groups share at least one real keyword."""
    by_cid = {s["cid"]: s for s in stories}
    for group in merges or []:
        group = [c for c in group if c in by_cid]
        if len(group) < 2:
            continue
        head = by_cid[group[0]]
        for cid in group[1:]:
            if not (_keywords(head) & _keywords(by_cid[cid])):
                log(f"    merge refused: {head['cid']} and {cid} share no keyword")
                continue
            other = by_cid.pop(cid)
            head["items"].extend(other["items"])
            head["sources"] = sorted(set(head["sources"]) | set(other["sources"]))
            head["buzz"] = len(head["sources"])
            head["score"] = round(head["score"] + other["score"] / 2, 2)
    return by_cid


# ---------------------------------------------------------------- sources
# A link on one of these sites is the maker's own post, so it is listed first as the original.
OFFICIAL = ("openai.com", "anthropic.com", "claude.com", "blog.google", "deepmind.google", "googleblog.com",
            "ai.google.dev", "microsoft.com", "github.blog", "ai.meta.com", "about.fb.com", "mistral.ai",
            "deepseek.com", "qwenlm.github.io", "qwen.ai", "nvidia.com", "x.ai", "huggingface.co", "arxiv.org",
            "github.com", "aws.amazon.com", "apple.com", "stability.ai", "nobelprize.org")


def is_official(url):
    host = urlsplit(url).netloc.lower().removeprefix("www.")
    return any(host == d or host.endswith("." + d) for d in OFFICIAL)


def order_sources(story, labs_by_feed=None):
    """The maker's own post first, then other originals, then press, then discussions. One entry per URL."""
    seen, ranked = set(), []

    def rank(i):
        official = is_official(i["url"])
        return (not official, not (i["original"] or official), -i["weight"], -(i.get("points") or 0))

    for it in sorted(story["items"], key=rank):
        if it["url"] in seen:
            continue
        seen.add(it["url"])
        original = it["original"] or is_official(it["url"])
        name = it["source_name"]
        if it["source"] == "hn" and original:
            name = urlsplit(it["url"]).netloc.lower().removeprefix("www.")
        ranked.append({"title": it["title"], "url": it["url"], "name": name,
                       "kind": "original" if original else "press"})
        if it.get("discussion") and it["discussion"] not in seen:
            seen.add(it["discussion"])
            ranked.append({"title": f"Discussion on {it['source_name']}", "url": it["discussion"],
                           "name": it["source_name"], "kind": "discussion"})
    return ranked[:8]


def source_text(story, sources, limit=9000):
    """Text the writer may use: the fetched original article plus every feed snippet."""
    parts = []
    first = next((s for s in sources if s["kind"] != "discussion"), None)
    if first:
        body = article_text(first["url"])
        if body:
            parts.append(f"[ARTICLE: {first['name']}] {first['title']}\n{body}")
    for it in story["items"]:
        parts.append(f"[{it['source_name']}] {it['title']}\n{it['text']}")
    text = "\n\n".join(parts)
    return text[:limit]


# ---------------------------------------------------------------- writer and checker
def writer(src_text, meta, concept_ids, people, topic_hint, feedback=None):
    labs = ", ".join(f"{l['id']} ({l['name']})" for l in meta["labs"])
    ppl = ", ".join(f"{p['id']} ({p['name']})" for p in people)
    types = ", ".join(t["id"] for t in meta["types"])
    topics = ", ".join(t["id"] for t in meta["topics"])
    system = ("You write one story for Attention Span, a daily AI bulletin. Use ONLY facts stated in SOURCE TEXT. "
              "If the sources do not say something, leave it out. Copy numbers exactly as written. " + STYLE)
    fix = ""
    if feedback:
        fix = ("\nA fact-checker rejected your previous draft. Remove or correct these claims so every statement "
               "is supported by SOURCE TEXT:\n- " + "\n- ".join(feedback) + "\n")
    user = f"""SOURCE TEXT:
{src_text}
{fix}
Write JSON with these fields:
- "title": factual headline, at most 12 words. If the news is a claim, allegation or report, the title must say so.
- "one_liner": the news in one sentence, at most 25 words.
- "summary": 50 to 110 words. What happened and the key specifics. Only facts from SOURCE TEXT.
- "eli5": one or two sentences explaining the idea to a 5-year-old with a simple everyday analogy. The analogy must not
  add any new facts.
- "why_it_matters": one sentence on what this changes for people who build with AI. State the implication directly;
  do not begin with "Developers", "Data professionals" or "This".
- "topic": one of [{topics}]. Suggested: {topic_hint}.
- "type": one of [paper, model, product, event, person]. Use "event" for incidents, deals, policy and announcements
  that are not a product or model; "person" for a person's move or milestone.
- "labs": ids from [{labs}] that are directly involved. Empty list if none.
- "people": ids from [{ppl}] only if the person is named in SOURCE TEXT.
- "concepts": up to 3 ids from this glossary that the story is centrally about: [{", ".join(concept_ids)}].
- "new_terms": up to 2 GENERAL techniques or categories named in SOURCE TEXT that are not in the glossary and that
  other teams could also use (for example "speculative decoding"). Never a product, model, company or paper name.
  Each {{"term": "...", "definition": "one plain sentence from the sources"}}. Empty list if none.
"""
    return ask_json(system, user, max_tokens=1400, tag="writer")


def checker(src_text, draft):
    system = ("You are a strict fact-checker. Compare a draft news story with its SOURCE TEXT. "
              "A claim is supported only if SOURCE TEXT states it or directly implies it.")
    fields = {k: draft.get(k, "") for k in ("title", "one_liner", "summary", "why_it_matters", "eli5")}
    user = f"""SOURCE TEXT:
{src_text}

DRAFT:
{json.dumps(fields, ensure_ascii=False, indent=1)}

List every factual claim in the DRAFT that SOURCE TEXT does not support (wrong numbers, names, dates, invented details,
overstated certainty). Check the title and eli5 as strictly as the summary. An allegation, a claim by one party, a report
or a rumour in SOURCE TEXT must stay attributed ("allegedly", "says", "reportedly"); stating it as plain fact is unsupported. The eli5 field may use an analogy, but it must not add new facts. "why_it_matters" may give a
reasonable implication but must not state new facts.
Return JSON: {{"supported": true or false, "unsupported": ["claim 1", "..."]}}"""
    result, _ = ask_json(system, user, max_tokens=800, temperature=0.0, tag="checker")
    return result


# ---------------------------------------------------------------- code checks
NUM = re.compile(r"\d[\d,]*(?:\.\d+)?")


def numbers_missing(draft, src_text):
    """Numbers in the story that never appear in the sources. Commas are ignored ('1,000' == '1000')."""
    hay = src_text.replace(",", "")
    missing = []
    for field in ("title", "one_liner", "summary"):
        for n in NUM.findall(draft.get(field, "")):
            n = n.replace(",", "").rstrip(".")
            if n and n not in hay:
                missing.append(f"the number {n} in {field} does not appear in the sources")
    return missing


def tidy(text):
    text = (text or "").replace(" \u2014 ", ", ").replace("\u2014", ", ").strip()
    text = re.sub(r"(\d)times\b", r"\1 times", text)
    return re.sub(r"\s+", " ", text)


def clip_words(text, n):
    words = text.split()
    if len(words) <= n:
        return text
    cut = " ".join(words[:n])
    end = max(cut.rfind(". "), cut.rfind("? "))
    return cut[:end + 1] if end > len(cut) * 0.5 else cut.rstrip(",;:") + "."


def finalize(draft, meta, concept_ids, people, topic_hint):
    lab_ids = {l["id"] for l in meta["labs"]}
    people_ids = {p["id"] for p in people}
    types = {t["id"] for t in meta["types"]}
    topics = {t["id"] for t in meta["topics"]}
    out = {k: tidy(draft.get(k, "")) for k in ("title", "one_liner", "summary", "eli5", "why_it_matters")}
    out["title"] = clip_words(out["title"], 14)
    out["one_liner"] = clip_words(out["one_liner"], 30)
    out["summary"] = clip_words(out["summary"], 125)
    out["eli5"] = clip_words(out["eli5"], 45)
    out["topic"] = draft.get("topic") if draft.get("topic") in topics else (topic_hint if topic_hint in topics else "industry")
    news_types = types - {"concept"}
    out["type"] = draft.get("type") if draft.get("type") in news_types else "event"
    out["labs"] = [x for x in dict.fromkeys(draft.get("labs") or []) if x in lab_ids]
    out["people"] = [x for x in dict.fromkeys(draft.get("people") or []) if x in people_ids]
    out["concepts"] = [x for x in dict.fromkeys(draft.get("concepts") or []) if x in concept_ids][:3]
    out["spotlight"] = False  # decided by the editor, who sees the whole day
    out["spotlight_reason"] = ""
    terms = []
    for t in draft.get("new_terms") or []:
        if isinstance(t, dict) and t.get("term") and t.get("definition"):
            terms.append({"term": tidy(t["term"])[:60], "definition": tidy(t["definition"])[:300]})
    out["new_terms"] = terms[:2]
    flags = [w for w in HYPE if w in (out["summary"] + out["one_liner"] + out["title"]).lower()]
    return out, flags


def mentioned_people(story, people):
    """Tag people by name in the raw items, so mentions are caught even if the writer misses them."""
    blob = " ".join(f"{i['title']} {i['text']}" for i in story["items"])
    found = [i.get("person") for i in story["items"] if i.get("person")]
    for p in people:
        names = [p["name"]] + [a for a in p.get("aliases", []) if len(a) > 5]
        if any(re.search(rf"\b{re.escape(n)}\b", blob) for n in names):
            found.append(p["id"])
    return list(dict.fromkeys(found))


def write_story(story, meta, concept_ids, people, topic_hint, log):
    """Returns (story_fields, report) or (None, report) when the story fails the checks."""
    sources = order_sources(story, None)
    text = source_text(story, sources)
    report = {"cid": story["cid"], "sources": len(sources), "source_chars": len(text), "rounds": []}
    feedback = None
    for round_no in (1, 2):
        draft, model = writer(text, meta, concept_ids, people, topic_hint, feedback)
        problems = numbers_missing(draft, text)
        verdict = checker(text, draft)
        problems += [str(c) for c in (verdict.get("unsupported") or [])]
        report["rounds"].append({"model": model, "problems": problems})
        if not problems:
            fields, flags = finalize(draft, meta, concept_ids, people, topic_hint)
            fields["people"] = list(dict.fromkeys(fields["people"] + mentioned_people(story, people)))
            feed_labs = [i["lab"] for i in story["items"] if i.get("lab")]
            fields["labs"] = list(dict.fromkeys(fields["labs"] + feed_labs))
            fields["sources"] = sources
            fields["buzz"] = story["buzz"]
            fields["published"] = min(i["published"] for i in story["items"])
            fields["checked"] = {"model": model, "rounds": round_no, "hype_flags": flags}
            return fields, report
        feedback = problems[:8]
    log(f"    dropped {story['cid']}: still unsupported after rewrite: {feedback[:2]}")
    return None, report
