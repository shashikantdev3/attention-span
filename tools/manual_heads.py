"""Update Attention Heads and the Context Window with notes written by an editor instead of an AI model.

The collection is the same as `python run_daily.py --heads-only`: public Bluesky posts of the people in
seed/heads.py, plus X or Bluesky links pasted into state/heads_inbox.txt (X is read only through the official
oEmbed endpoint). Only the "What it means" notes come from a file instead of the LLM chain.

  python tools/manual_heads.py collect                 # writes state/tmp/heads_pending.json: new posts needing a note
  python tools/manual_heads.py apply --notes notes.json

notes.json is a list of {"id", "keep" (true/false), "meaning", "concepts" (ids), "story" (story id or null)}.
A note must say only what the post (and its link or quote) says, attribute opinions to the author, be at most
45 words and use no long dashes. Numbers in a note must appear in the post. Posts left out of notes.json stay
pending and come back on the next collect. Then run python tools/bundle_data.py.
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from pipeline import heads  # noqa: E402

PENDING = ROOT / "state" / "tmp" / "heads_pending.json"
EDITOR = "editor (written by hand from the post)"
DASHES = ("—", "–", " -- ")


def collect(args):
    def dump(posts, names, concept_ids, stories, log):
        PENDING.parent.mkdir(parents=True, exist_ok=True)
        rows = [{"id": p["id"], "author": names.get(p["person"], p["person"]), "platform": p["platform"],
                 "via": p["via"], "url": p["url"], "posted_at": p["posted_at"], "text": p["text"],
                 "context": p.get("context"), "editor_note": p.get("note")} for p in posts]
        PENDING.write_text(json.dumps({"stories": stories, "posts": rows}, ensure_ascii=False, indent=1), encoding="utf-8")
        log(f"   {len(rows)} posts need a note: {PENDING.relative_to(ROOT)}")
        return {}
    heads.explain = dump
    heads.update(log=print)


def apply(args):
    notes = {n["id"]: n for n in json.loads(Path(args.notes).read_text(encoding="utf-8"))}
    errors = []

    def from_file(posts, names, concept_ids, stories, log):
        out = {}
        for p in posts:
            n = notes.get(p["id"])
            if not n:
                continue
            meaning = (n.get("meaning") or "").strip()
            if n.get("keep"):
                bad = heads._bad_numbers(meaning, p)
                if bad or any(d in meaning for d in DASHES) or len(meaning.split()) > 45 or not meaning:
                    errors.append(f"{p['id']}: note rejected (numbers not in post: {bad}, words: {len(meaning.split())})")
                    continue
            out[p["id"]] = {"id": p["id"], "keep": bool(n.get("keep")), "meaning": meaning,
                            "concepts": n.get("concepts") or [], "story": n.get("story"),
                            "model": EDITOR, "checked": EDITOR}
        unused = set(notes) - {p["id"] for p in posts}
        if unused:
            log(f"   {len(unused)} notes did not match a new post (already added or not collected): {sorted(unused)[:5]}")
        return out
    heads.explain = from_file
    heads.update(log=print)
    for e in errors:
        print("ERROR", e)
    sys.exit(1 if errors else 0)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("collect")
    p = sub.add_parser("apply")
    p.add_argument("--notes", required=True)
    a = ap.parse_args()
    {"collect": collect, "apply": apply}[a.cmd](a)


if __name__ == "__main__":
    main()
