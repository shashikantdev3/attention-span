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

1. **Collect** the last 24 hours from about 30 sources (`pipeline/sources.json`): official blogs of OpenAI, Anthropic,
   Google, DeepMind, Microsoft, Azure AI Foundry, GitHub, Meta, Mistral, Qwen, NVIDIA and Hugging Face; the Power BI and
   Fabric blogs; Hacker News; Hugging Face daily papers and trending models; new GitHub repos; tech press; the personal
   blogs of the people tracked; and your own `state/inbox.txt`.
2. **Group** duplicates into stories (TF-IDF similarity, pure Python). The number of independent sources is the buzz signal.
3. **Edit**: one call to Gemini Flash picks up to 12 stories that matter to builders. A rule in code always includes a
   major lab's own announcement with a strong signal, even if the model skips it.
4. **Write** each story only from its fetched source text (Gemini Flash-Lite).
5. **Fact-check** with a different model family (Groq gpt-oss-120b) and with code: every number must appear in the
   sources. A failing story is rewritten once, then dropped.
6. **Save** to cumulative JSON in `docs/data/editions/`. Nothing is deleted.
7. **Attention Heads**: read the new public Bluesky posts of the people in `seed/heads.py`, plus any links in
   `state/heads_inbox.txt`; keep the posts about AI or data; write a short note on each from the post alone; check every
   note with a second model and every number with code. Saved to `docs/data/heads.json`. A failure here never stops the edition.

Free tiers used: Gemini (Flash for the editor, Flash-Lite for writing) and Groq. A night uses about 25 to 40 calls.
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
```

## Every night

```
python run_daily.py
```

It takes about 4 to 8 minutes. If it stops part way (network drop), run `python run_daily.py --resume`.
Then read the report in `state/reports/<date>.md`. To publish:

```
git add docs/data state/seen.json state/pending_terms.json state/heads_skipped.json
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

**Add an X post to Attention Heads**: X's API is paid, so X posts are never fetched automatically. Paste the post link
into `state/heads_inbox.txt`, one per line, as `URL | optional note`. Bluesky post links work too. Only posts by the 51
people in `seed/heads.py` are used. To update only this section: `python run_daily.py --heads-only`.

**Add a link the feeds missed** (for example an X post): put it in `state/inbox.txt`, one per line, as `URL | short note`.

**Approve new glossary terms** proposed by the writer: `python tools/review_terms.py`, then `python seed/build_seed.py`.

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
