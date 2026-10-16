# Attention Span

**Today's AI news, traced back to its roots.**

A daily AI news bulletin with a memory. Every story is tagged with the same index as a source-checked history of AI
from 1943 to today, a glossary with lineage, the labs and the people behind it. It runs once a night on a laptop with
free AI tiers and publishes as a static site on GitHub Pages.

- **Today**: the last 24 hours, picked, summarised from the sources, fact-checked, with a "like I'm 5" line for each story.
- **Timeline**: 103 moments from 1943 to 2026 in seven eras. 91 dates are machine-checked against arXiv, Crossref or the source page.
- **Concepts**: 97 terms as an A to Z index, each with its layer in the AI stack, a plain definition and what it evolved from and led to.
- **Labs**: one page per lab with its dated releases and news.
- **Attention Heads**: what 51 people who shape AI posted in the last 7 days, quoted in full, each with a plain
  "What it means" note and a "Most active this week" board. Free sources only: Bluesky's public API and X links you paste.
- **Context Window**: X posts worth reading, picked by an editor each evening and shown through X's own embedded post,
  each with "What it means". A Hall of fame keeps the posts that changed the field. Nothing is scraped from X.
- **Week in Review**: the stories that mattered most each week, the themes, the labs and the most active voices,
  with a one-click plain-text summary to share.
- **People**: ten people who shape the field, with their history and news mentions.
- **Stack map**: nine layers from math and neurons to data and BI.

## The index

Every record (news story, history entry, concept, person) uses the same tags, so each section is a filter over one dataset.

| Tag | Values |
| --- | --- |
| Type | paper, model, product, event, person, concept |
| Lab | OpenAI, Anthropic, Google and DeepMind, Microsoft and GitHub, Meta, Mistral, DeepSeek, Qwen, NVIDIA, IBM, Stability, SSI, academia, governments, others |
| Era | Foundations (1943 to 1969), Winters and expert systems (1970 to 1992), Statistical learning (1993 to 2011), Deep learning (2012 to 2016), Transformers and scale (2017 to 2021), Generative boom (2022 to 2023), Agents and reasoning (2024 to now) |
| Layer | Math and neurons, Learning methods, Architectures, Models, Training and alignment, Building with AI, Evaluation and safety, Infrastructure, Data and BI |
| Lineage | each concept's `evolved_from`; `led_to` is computed so the two directions never disagree |

## How a nightly edition is made

1. **Collect** the last 24 hours from 39 sources (`pipeline/sources.json`): official blogs of OpenAI, Anthropic
   (news, research and the Frontier Red Team), Google, DeepMind, Microsoft, Azure AI Foundry, GitHub, Meta, Mistral,
   Qwen, NVIDIA and Hugging Face; the Power BI and Fabric blogs; feature releases of the tools builders use every day
   (Claude Code, Codex CLI, Ollama and vLLM); Hacker News; Hugging Face daily papers and trending models; new GitHub
   repos; tech press (TechCrunch, The Verge, Ars Technica, VentureBeat, MIT Technology Review, The Decoder, Techmeme);
   the Latent Space AINews digest; the personal blogs of the people tracked; and your own `state/inbox.txt`.
   Release feeds keep only stable feature releases, so a patch or a release candidate never becomes a story.
2. **Group** duplicates into stories (TF-IDF similarity, pure Python). The number of independent sources is the buzz signal.
3. **Edit**: one call to Gemini Flash picks up to 12 stories that matter to builders (Claude Sonnet if both Flash
   models are busy, then Flash-Lite). A rule in code always includes a
   major lab's own announcement with a strong signal, even if the model skips it.
4. **Write** each story only from its fetched source text (Gemini Flash-Lite).
5. **Fact-check** with a different model family (Claude Sonnet, falling back to Groq gpt-oss-120b) and with code:
   every number must appear in the sources. A failing story is rewritten once, then dropped.
6. **Save** to cumulative JSON in `docs/data/editions/`. Nothing is deleted.
7. **Attention Heads**: read the new public Bluesky posts of the people in `seed/heads.py`, plus any links in
   `state/heads_inbox.txt`; keep the posts about AI or data; write a short note on each from the post alone; check every
   note with a second model and every number with code. Saved to `docs/data/heads.json`. A failure here never stops the edition.

Free tiers used: Gemini (Flash for the editor, Flash-Lite for writing) and Groq. A night uses about 25 to 40 calls.
Claude (prepaid credits) checks the facts and stands in for the editor when Gemini is busy, about $0.10 to $0.20 a night.
Attention Heads needs no extra keys: Bluesky's public API and X's embed service are free and open.
Answers are cached in `state/cache/`, so an interrupted run can resume without spending quota twice.

## Setup (once)

```
pip install -r requirements.txt
```

Create `.env` in the repo root (it is git-ignored):

```
GEMINI_API_KEY=your-gemini-key
GROQ_API_KEY=your-groq-key
# optional, both prepaid; the site runs without them
ANTHROPIC_API_KEY=your-claude-key        # Claude checks the facts first, the free models are the fallback
OPENROUTER_API_KEY=your-openrouter-key   # the headline honesty check below
```

Writing stays on the free Gemini and Groq tiers. The fact-checker uses Claude (Sonnet, then Haiku), because the
checker is where a stronger reader matters most, and it is a different model family from the writer. The editor uses
Claude Sonnet only when both Gemini Flash models are busy, which kept happening in October 2026.
If the key is missing or the credits run out, both fall back to the free models on their own.
The nightly log shows how many Claude tokens each run used.

## Every night

```
python run_daily.py
```

It takes about 4 to 8 minutes. If it stops part way (network drop), run `python run_daily.py --resume`.
Then read the report in `state/reports/<date>.md`. To publish:

```
git add docs state
git commit -m "Edition 2026-10-08"
git push
```

By default it looks back to the previous edition (at least 24 hours, at most 72), so a missed night is caught up
automatically. A run before 06:00 is filed under the day that just ended.

Options: `--hours 48` to set the look-back yourself, `--max 12` stories, `--date 2026-10-09` to set the edition date,
`--dry-run` to test without writing.

### Run it automatically every night (Windows)

```
powershell -ExecutionPolicy Bypass -File tools\schedule_nightly.ps1
```

This registers a Task Scheduler job that runs `tools\nightly.bat` at 23:45 each night. If the laptop is asleep at
23:45, it runs when the laptop wakes. It writes the edition and appends to `state\reports\nightly.log`, but never
commits or pushes. Change the end date at the top of the script. To remove it:
`Unregister-ScheduledTask -TaskName "Attention Span nightly" -Confirm:$false`

**Add X posts to the Context Window**: X posts are never fetched or scraped. You pick them while reading X and paste
the links:

```
python tools/add_posts.py                 # paste anything (a WhatsApp chat works), then Ctrl+Z and Enter
python tools/add_posts.py --classic "coined vibe coding" https://x.com/karpathy/status/1886192184808149383
python run_daily.py --heads-only          # publish them now instead of waiting for the night run
```

Links can carry timestamps, text or `?s=20`; twitter.com and fxtwitter.com links are cleaned to x.com. Only posts by the
accounts in `seed/heads.py` (51 people and 32 official accounts) are used. Each post is read through X's official embed
service, gets a fact-checked "What it means" note, and is shown on the site through X's embedded-post widget.
Once a week every X post is checked again; a post its author deleted is removed. `--classic` puts a post in the Hall of fame.

**Add a story the nightly run missed to a past edition**: `python tools/add_story.py URL --date 2026-10-10 --rank 2`.
Put the maker's own post first. It goes through the same writer and fact-checker, and is marked as added by the editor.

**Add a link the feeds missed** (for example an X post): put it in `state/inbox.txt`, one per line, as `URL | short note`.

**Approve new glossary terms** proposed by the writer: `python tools/review_terms.py`, then `python seed/build_seed.py`.

## Headline honesty check (decision model)

```
python tools/check_headlines.py                  # the latest edition
python tools/check_headlines.py --all            # every edition so far
python tools/check_headlines.py --headline "..." --text "..." --original "..."
```

A decision model answers typed questions with probabilities instead of writing text, in one short call.
This uses Microsoft-Decision-1 through OpenRouter to ask three questions about every headline: is each claim backed
by our fact-checked summary (yes or no), is our wording the same, stronger or weaker than the publisher's headline,
and how much hype it has (0 to 4). Flagged headlines go to `state/reports/headline_honesty_<date>.md` for a person
to reread; every answer is kept in `state/reports/headline_honesty.json`. One check costs about $0.00002.
Use `--model` to try another decision model, for example TypeSafe's Jev.

## Pages for search engines

The site is one JavaScript page, which search engines read poorly, so every bundle step also writes plain HTML pages:
`docs/s/` (stories), `docs/e/` (editions), `docs/w/` (weeks), `docs/c/` (concepts), plus `docs/sitemap.xml`,
`docs/robots.txt` and `docs/feed.xml` (RSS). Set `SITE_URL` in `.env` if the site address changes. After the first
publish, add the sitemap in Google Search Console: `https://shashikantdev3.github.io/attention-span/sitemap.xml`.

## Editing the history and glossary

The seed lives in `seed/` as Python lists: `timeline.py`, `concepts.py`, `people.py`, `taxonomy.py`.
After any edit:

```
python tools/verify_seed.py     # checks every date and link (takes about 5 minutes)
python seed/build_seed.py       # validates references and writes docs/data
```

`build_seed.py` refuses to build if a reference is broken, a lineage loops, a date is malformed or text contains an em dash.

## View the site locally

```
python -m http.server -d docs 8000
```

Open http://localhost:8000. On GitHub: Settings, Pages, deploy from branch `main`, folder `/docs`.

## Data and licence

All data is plain JSON in `docs/data/`.

- **Code**: [MIT](LICENSE). Use it for anything, including commercial work.
- **Data and written content**: [CC BY-NC 4.0](LICENSE-DATA.md). Free for non-commercial use with credit:
  "Attention Span by Shashikant, CC BY-NC 4.0".
- **Commercial use of the data**: needs permission, see [COMMERCIAL.md](COMMERCIAL.md).
- Linked articles and papers belong to their publishers and are not covered by either licence.

Built by [Shashikant](https://github.com/shashikantdev3).
