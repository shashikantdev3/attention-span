"""Add X or Bluesky post links to the Attention Heads inbox. Paste anything: it finds the links.

    python tools/add_posts.py                     paste text, then press Ctrl+Z and Enter (Windows) or Ctrl+D
    python tools/add_posts.py links.txt           read a file, for example an exported WhatsApp chat
    python tools/add_posts.py --classic "coined vibe coding" https://x.com/karpathy/status/1886192184808149383

Links can come with WhatsApp timestamps, text, tracking parameters (?s=20) or from twitter.com, mobile.x.com,
fxtwitter.com or vxtwitter.com: they are all cleaned to https://x.com/<user>/status/<id>.
A link already in the inbox, already handled, or already on the site is ignored.
--classic puts the posts in the Hall of fame on the Context Window page.
The next nightly run (or: python run_daily.py --heads-only) reads them through X's official embed service.
"""
import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INBOX = ROOT / "state" / "heads_inbox.txt"
DONE = ROOT / "state" / "heads_inbox_done.txt"
HEADS = ROOT / "docs" / "data" / "heads.json"

X_ANY = re.compile(r"https?://(?:www\.|mobile\.)?(?:x|twitter|fxtwitter|vxtwitter|fixupx|fixvx)\.com/"
                   r"([A-Za-z0-9_]{1,15})/status(?:es)?/(\d{5,25})")
BSKY_ANY = re.compile(r"https?://bsky\.app/profile/([A-Za-z0-9._:-]+)/post/([A-Za-z0-9]+)")


def find_links(text):
    """Every post link in the text, cleaned, in the order found, without duplicates."""
    found = []
    for m in re.finditer(f"{X_ANY.pattern}|{BSKY_ANY.pattern}", text):
        if m.group(2):
            found.append((f"x-{m.group(2)}", f"https://x.com/{m.group(1)}/status/{m.group(2)}"))
        else:
            found.append((f"bsky-{m.group(3)}-{m.group(4)}", f"https://bsky.app/profile/{m.group(3)}/post/{m.group(4)}"))
    seen, out = set(), []
    for sid, url in found:
        if sid not in seen:
            seen.add(sid)
            out.append((sid, url))
    return out


def known_ids():
    ids = set()
    for path in (INBOX, DONE):
        if path.exists():
            for sid, _ in find_links(path.read_text(encoding="utf-8")):
                ids.add(sid)
    try:
        ids |= {p["id"] for p in json.loads(HEADS.read_text(encoding="utf-8")).get("posts", [])}
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    return ids


def main():
    ap = argparse.ArgumentParser(description="Add post links to the Attention Heads inbox")
    ap.add_argument("inputs", nargs="*", help="files to read, or links; nothing means read what you paste")
    ap.add_argument("--classic", metavar="WHY", help="put these posts in the Hall of fame, with a short reason")
    ap.add_argument("--note", default="", help="a short note for these posts (context for the editor only)")
    args = ap.parse_args()

    if args.inputs:
        parts = []
        for x in args.inputs:
            p = Path(x)
            parts.append(p.read_text(encoding="utf-8", errors="replace") if p.exists() else x)
        text = "\n".join(parts)
    else:
        print("Paste the links or the chat, then press Ctrl+Z and Enter (Windows) or Ctrl+D (Mac and Linux):")
        text = sys.stdin.read()

    links = find_links(text)
    have = known_ids()
    new = [(sid, url) for sid, url in links if sid not in have]
    note = f"classic: {args.classic}" if args.classic else args.note
    if new:
        INBOX.parent.mkdir(parents=True, exist_ok=True)
        existing = INBOX.read_text(encoding="utf-8") if INBOX.exists() else ""
        with INBOX.open("a", encoding="utf-8") as f:
            if existing and not existing.endswith("\n"):
                f.write("\n")
            for _, url in new:
                f.write(f"{url} | {note}\n" if note else f"{url}\n")
    print(f"{len(links)} post links found, {len(links) - len(new)} already known, {len(new)} added to state/heads_inbox.txt")
    for _, url in new:
        print(f"  + {url}")
    if new:
        print("They go live after the next nightly run, or now with: python run_daily.py --heads-only")


if __name__ == "__main__":
    main()
