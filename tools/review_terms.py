"""Review new glossary terms proposed by the nightly run.

    python tools/review_terms.py

For each pending term you choose:
  a  approve: add it to the glossary (you pick its layer and what it evolved from)
  r  reject: never propose it again
  s  skip: decide later
Approved terms go to state/approved_concepts.json; seed/build_seed.py merges them into the site's glossary.
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "state"
DATA = ROOT / "docs" / "data"


def read(p, default):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default


def write(p, obj):
    Path(p).write_text(json.dumps(obj, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def main():
    pending = read(STATE / "pending_terms.json", [])
    approved = read(STATE / "approved_concepts.json", [])
    rejected = read(STATE / "rejected_terms.json", [])
    meta = read(DATA / "meta.json", {})
    concepts = read(DATA / "concepts.json", [])
    ids = {c["id"] for c in concepts} | {c["id"] for c in approved}
    layers = [l["id"] for l in meta.get("layers", [])]
    if not pending:
        print("No pending terms.")
        return
    keep = []
    for t in pending:
        print("\n" + "-" * 70)
        print(f"TERM: {t['term']}\nDEFINITION: {t['definition']}\nSEEN: {t['first_seen']}  SOURCE: {t.get('source', '')}")
        choice = input("[a]pprove, [r]eject, [s]kip, [q]uit: ").strip().lower()
        if choice == "q":
            keep.append(t)
            keep.extend(pending[pending.index(t) + 1:])
            break
        if choice == "r":
            rejected.append(t["term"])
            continue
        if choice != "a":
            keep.append(t)
            continue
        cid = re.sub(r"[^a-z0-9]+", "-", t["term"].lower()).strip("-")
        if cid in ids:
            print(f"'{cid}' already exists, skipped.")
            continue
        print("Layers:", ", ".join(layers))
        layer = input("layer: ").strip()
        while layer not in layers:
            layer = input("layer (one of the list above): ").strip()
        definition = input("definition (Enter keeps the one above): ").strip() or t["definition"]
        eli5 = input("like I'm 5 (one simple sentence): ").strip()
        parents = [p.strip() for p in input("evolved from (concept ids, comma separated, optional): ").split(",") if p.strip()]
        unknown = [p for p in parents if p not in ids]
        if unknown:
            print(f"ignored unknown ids: {unknown}")
        approved.append({"id": cid, "term": t["term"], "layer": layer, "definition": definition,
                         "eli5": eli5 or definition, "evolved_from": [p for p in parents if p in ids],
                         "aka": [], "added": t["first_seen"], "source": t.get("source", "")})
        ids.add(cid)
        print(f"approved {cid}")
    write(STATE / "pending_terms.json", keep)
    write(STATE / "approved_concepts.json", approved)
    write(STATE / "rejected_terms.json", sorted(set(rejected)))
    print("\nSaved. Now run: python seed/build_seed.py")


if __name__ == "__main__":
    sys.exit(main())
