"""Validate the seed and write the site's reference data to docs/data/.

Run: python seed/build_seed.py
Fails loudly on any broken reference, so bad data never reaches the site.
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "seed"))

from taxonomy import TYPES, ERAS, LAYERS, LABS, TOPICS, era_for  # noqa: E402
from timeline import TIMELINE  # noqa: E402
from concepts import CONCEPTS  # noqa: E402
from people import PEOPLE  # noqa: E402

DATA = ROOT / "docs" / "data"
VERIFY_FILE = ROOT / "state" / "verification.json"
ADDED_CONCEPTS = ROOT / "state" / "approved_concepts.json"
DATE_RE = re.compile(r"^\d{4}(-\d{2}(-\d{2})?)?$")
BANNED = ["\u2014"]  # em dash


def load_json(path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default


def check_text(where, text, errors):
    for b in BANNED:
        if b in text:
            errors.append(f"{where}: contains an em dash")


def build():
    errors = []
    type_ids = {t["id"] for t in TYPES}
    layer_ids = {l["id"] for l in LAYERS}
    lab_ids = {l["id"] for l in LABS}

    concepts = list(CONCEPTS) + load_json(ADDED_CONCEPTS, [])
    concept_ids = [c["id"] for c in concepts]
    dupes = {c for c in concept_ids if concept_ids.count(c) > 1}
    if dupes:
        errors.append(f"duplicate concept ids: {sorted(dupes)}")
    concept_set = set(concept_ids)
    people_set = {p["id"] for p in PEOPLE}

    # ---- concepts ----
    for c in concepts:
        if c["layer"] not in layer_ids:
            errors.append(f"concept {c['id']}: unknown layer {c['layer']}")
        for parent in c["evolved_from"]:
            if parent not in concept_set:
                errors.append(f"concept {c['id']}: evolved_from unknown {parent}")
        for k in ("term", "definition", "eli5"):
            check_text(f"concept {c['id']}.{k}", c[k], errors)

    # cycle check on lineage
    graph = {c["id"]: c["evolved_from"] for c in concepts}

    def has_cycle(node, stack, seen):
        if node in stack:
            return True
        if node in seen:
            return False
        seen.add(node)
        stack.add(node)
        cyc = any(has_cycle(p, stack, seen) for p in graph.get(node, []))
        stack.discard(node)
        return cyc

    seen = set()
    for cid in graph:
        if has_cycle(cid, set(), seen):
            errors.append(f"lineage cycle through {cid}")
            break

    # reverse links
    led_to = {cid: [] for cid in concept_set}
    for c in concepts:
        for parent in c["evolved_from"]:
            if parent in led_to:
                led_to[parent].append(c["id"])

    # ---- timeline ----
    verification = load_json(VERIFY_FILE, {})
    ids = [e["id"] for e in TIMELINE]
    dup_entries = {i for i in ids if ids.count(i) > 1}
    if dup_entries:
        errors.append(f"duplicate timeline ids: {sorted(dup_entries)}")
    used_concepts = set()
    entries = []
    for e in TIMELINE:
        where = f"entry {e['id']}"
        if not DATE_RE.match(e["date"]):
            errors.append(f"{where}: bad date {e['date']}")
        if e["type"] not in type_ids:
            errors.append(f"{where}: unknown type {e['type']}")
        if e["layer"] not in layer_ids:
            errors.append(f"{where}: unknown layer {e['layer']}")
        for lab in e["labs"]:
            if lab not in lab_ids:
                errors.append(f"{where}: unknown lab {lab}")
        for c in e["concepts"]:
            if c not in concept_set:
                errors.append(f"{where}: unknown concept {c}")
            used_concepts.add(c)
        for p in e["people"]:
            if p not in people_set:
                errors.append(f"{where}: unknown person {p}")
        if not e["sources"]:
            errors.append(f"{where}: no source")
        for k in ("title", "one_liner", "summary"):
            check_text(f"{where}.{k}", e[k], errors)
        if len(e["summary"].split()) > 120:
            errors.append(f"{where}: summary over 120 words")
        out = dict(e)
        out["era"] = era_for(e["date"])
        out["precision"] = {4: "year", 7: "month", 10: "day"}[len(e["date"])]
        v = verification.get(e["id"], {})
        out["check"] = {
            "status": v.get("status", "unchecked"),
            "checked_on": v.get("checked_on"),
            "notes": v.get("notes", []),
        }
        entries.append(out)
    entries.sort(key=lambda x: (x["date"], x["id"]))

    # attach timeline ids to concepts
    entries_by_concept = {}
    for e in entries:
        for c in e["concepts"]:
            entries_by_concept.setdefault(c, []).append(e["id"])

    concepts_out = []
    for c in concepts:
        out = dict(c)
        out["led_to"] = sorted(led_to[c["id"]])
        out["entries"] = entries_by_concept.get(c["id"], [])
        out["letter"] = c["term"][0].upper()
        concepts_out.append(out)
    concepts_out.sort(key=lambda x: x["term"].lower())

    # ---- people ----
    people_out = []
    for p in PEOPLE:
        for lab in p["labs"]:
            if lab not in lab_ids:
                errors.append(f"person {p['id']}: unknown lab {lab}")
        for c in p["concepts"]:
            if c not in concept_set:
                errors.append(f"person {p['id']}: unknown concept {c}")
        out = dict(p)
        out["entries"] = [e["id"] for e in entries if p["id"] in e["people"]]
        people_out.append(out)

    orphan = sorted(concept_set - used_concepts - {c for p in PEOPLE for c in p["concepts"]})

    if errors:
        print("SEED ERRORS:")
        for err in errors:
            print("  -", err)
        sys.exit(1)

    DATA.mkdir(parents=True, exist_ok=True)
    meta = {"site": "Attention Span", "tagline": "Today's AI news, traced back to its roots.",
            "types": TYPES, "eras": ERAS, "layers": LAYERS, "labs": LABS, "topics": TOPICS}
    write(DATA / "meta.json", meta)
    write(DATA / "timeline.json", entries)
    write(DATA / "concepts.json", concepts_out)
    write(DATA / "people.json", people_out)

    status_counts = {}
    for e in entries:
        status_counts[e["check"]["status"]] = status_counts.get(e["check"]["status"], 0) + 1
    print(f"OK: {len(entries)} timeline entries, {len(concepts_out)} concepts, {len(people_out)} people")
    print(f"    entry checks: {status_counts}")
    print(f"    concepts not yet used by any timeline entry: {len(orphan)}")


def write(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


if __name__ == "__main__":
    build()
