# Attention Span

**Today's AI news, traced back to its roots.**

A daily AI news bulletin with a memory. Every story is tagged with the same index as a source-checked history of AI
from 1943 to today, a glossary with lineage, the labs and the people behind it. It runs once a night on a laptop with
free AI tiers and publishes as a static site on GitHub Pages.

- **Today**: the last 24 hours, picked, summarised from the sources, fact-checked, with a "like I'm 5" line for each story.
- **Timeline**: 103 moments from 1943 to 2026 in seven eras. 91 dates are machine-checked against arXiv, Crossref or the source page.
- **Concepts**: 97 terms as an A to Z index, each with its layer in the AI stack, a plain definition and what it evolved from and led to.
- **Labs**: one page per lab with its dated releases and news.
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

Free tiers used: Gemini (Flash for the editor, Flash-Lite for writing) and Groq. A night uses about 25 to 35 calls.
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
git add docs/data state/seen.json state/pending_terms.json
git commit -m "Edition 2026-10-08"
git push
```

Options: `--hours 48` after a missed night, `--max 12` stories, `--dry-run` to test without writing.

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
