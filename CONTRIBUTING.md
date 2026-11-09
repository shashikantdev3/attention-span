# Contributing to Attention Span

Thanks for helping. Small, focused changes are easiest to review.

## Run it yourself first

1. Fork the repo and clone your fork.
2. `pip install -r requirements.txt`
3. Create `.env` with at least one key: `ANTHROPIC_API_KEY`, `OPENAI_API_KEY` (with `OPENAI_MODEL`),
   `GEMINI_API_KEY` or `GROQ_API_KEY`. Never commit `.env`.
4. `python run_daily.py --dry-run` for a first run that writes nothing, then `python run_daily.py` for a real edition.
5. Open `docs/index.html` through a local server (`python -m http.server -d docs`) to see the site.

## What to propose

- **Sources**: a feed in `pipeline/sources.json`, with a reason it adds news the others miss.
- **Model providers**: a new entry in `PROVIDERS` in `pipeline/llm.py`, plus a fallback chain that still works without it.
- **Quality**: better picking (`pipeline/signals.py`, `pipeline/curate.py`), fact-checking or duplicate detection.
- **Pages and design**: anything under `docs/`.
- **Your own digest**: if you build one on this code for another topic, open an issue with the link.

## Rules

- Open an issue first for anything large, so we agree on the approach before you build.
- One change per pull request, with a short note on what it changes and how you tested it.
- No secrets, keys or personal data in commits.
- Stories must stay faithful to their sources: attribute claims, prefer the maker's own post, no paywalled-only sources.
- X posts are shown only through X's official embed (oEmbed and widgets.js). Never add code that scrapes X or logs in to it.
- Code is MIT. Contributions to the data and written content are licensed CC BY-NC 4.0, like the rest of it.
