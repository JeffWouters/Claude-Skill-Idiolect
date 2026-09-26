"""The writing kit: everything `write` and `rewrite` load, and nothing more (design: Write and rewrite,
step by step). Never the corpus, never the whole example bank.

    python3 kit.py --store S [--profile P] [--lang L] [--type T] [--brief FILE] [--examples 3] [--json]

Prints a Markdown kit (or JSON with --json): profile and slot used (and why), confidence, rulings,
vocabulary, lessons, edit lessons, never-list, what to aim for in measurable terms, and the example
passages best matching the brief.
"""
import argparse
import json
import math
import pathlib
import re
import sys
from collections import Counter

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import pages  # noqa: E402
import resolve  # noqa: E402
from common import StoreError, read_store_file, words  # noqa: E402
from stage import stopwords  # noqa: E402
from store import Store  # noqa: E402

RULINGS_CAP = 30
VOCAB_CAP = 40

DESCRIBE = {
    "sentence_length_mean": ("average sentence length", "{:.0f} words"),
    "sentence_length_sd": ("variation in sentence length (standard deviation)", "{:.0f} words"),
    "short_sentence_share": ("sentences under 8 words", "{:.0%}"),
    "long_sentence_share": ("sentences over 28 words", "{:.0%}"),
    "sentences_per_paragraph": ("sentences per paragraph", "{:.1f}"),
    "commas_per_sentence": ("commas per sentence", "{:.1f}"),
    "semicolons_per_1k": ("semicolons per 1,000 words", "{:.1f}"),
    "colons_per_1k": ("colons per 1,000 words", "{:.1f}"),
    "dashes_per_1k": ("dashes per 1,000 words", "{:.1f}"),
    "digits_per_1k": ("numbers written as digits per 1,000 words", "{:.1f}"),
    "long_word_share": ("words of 7+ letters", "{:.0%}"),
    "contractions_per_1k": ("contractions per 1,000 words", "{:.1f}"),
    "hedges_per_1k": ("hedges (perhaps, might, rather...) per 1,000 words", "{:.1f}"),
    "conjunction_opener_share": ("sentences opening with And/But/So...", "{:.0%}"),
}


def pick_examples(examples, brief, lang, n=3):
    """The n example passages whose words best match the brief (IDF-weighted overlap); ties by id.
    The same function chooses the few-shot baseline's passages in the evaluation."""
    if not examples:
        return []
    sw = stopwords(lang)
    toks = lambda t: [w.lower() for w in words(t) if w.lower() not in sw and len(w) > 2]  # noqa: E731
    docs = [Counter(toks(e["text"])) for e in examples]
    df = Counter(w for d in docs for w in d)
    q = set(toks(brief or ""))
    scored = []
    for e, d in zip(examples, docs):
        score = sum(math.log(1 + len(docs) / df[w]) for w in q if w in d)
        scored.append((-score, e["id"], e))
    return [e for _, _, e in sorted(scored)[:n]]


def build(store, profile=None, facets=None, brief=None, n_examples=3):
    prof, slot, tried = resolve.resolve(store, profile, facets)
    base = store.root / "profiles" / prof
    fp = read_store_file(base / f"{slot}.json", "fingerprint")
    lang = slot.split(".")[0]
    kit = {"profile": prof, "requested_profile": profile or store.config["default_profile"], "slot": slot,
           "pooled": fp["pooled"], "tried": tried, "confidence": fp["confidence"],
           "counts": fp["counts"], "warnings": []}
    if prof != kit["requested_profile"]:
        kit["warnings"].append(f"no slot in {kit['requested_profile']} matched; using its parent {prof}")
    if fp["pooled"]:
        kit["warnings"].append(f"no exact slot; using the pooled slot {slot}")
    if fp["confidence"]["level"] == "low":
        kit["warnings"].append("confidence is low: say so with the draft")
    page = base / f"{slot}.md"
    kit["lessons"] = pages.parse_slot_page(page.read_text(encoding="utf-8"))[2] if page.exists() else []
    edits = base / f"{slot}.edits.md"
    kit["edit_lessons"] = pages.parse_slot_page(edits.read_text(encoding="utf-8"))[2] if edits.exists() else []
    never = base / f"{slot}.never.md"
    kit["never"] = [m["marker"] for m in pages.parse_never(never.read_text(encoding="utf-8"))[1]] if never.exists() else []
    rulings = [r for r in resolve.merged(store, prof, "rulings") if r.get("slot") in (None, slot)]
    kit["rulings"] = rulings[:RULINGS_CAP]
    kit["vocabulary"] = resolve.merged(store, prof, "vocabulary")[:VOCAB_CAP]
    kit["inherited_rulings"] = [r for r in rulings if r["profile"] != prof]
    targets = []
    for m, v in fp["metrics"].items():
        name, fmt = DESCRIBE.get(m, (m, "{:.2f}"))
        targets.append({"metric": m, "primary": v["primary"], "describe": name, "value": v["value"],
                        "shown": fmt.format(v["value"])})
    targets.sort(key=lambda t: (not t["primary"], t["metric"]))
    kit["targets"] = targets
    exf = base / f"{slot}.examples.md"
    examples = pages.parse_examples(exf.read_text(encoding="utf-8"))[1] if exf.exists() else []
    kit["examples"] = pick_examples(examples, brief, lang, n_examples)
    return kit


def markdown(kit):
    L = [f"# Writing kit: {kit['profile']} / {kit['slot']}", ""]
    c = kit["confidence"]
    L.append(f"Confidence {c['level']} (count {c['count_level']}, stability {c['stability_level']}); "
             f"{kit['counts']['texts']} texts, {kit['counts']['words']} words.")
    for w in kit["warnings"]:
        L.append(f"- **Warning:** {w}")
    if kit["rulings"]:
        L += ["", "## Rulings (always obey)"] + [f"- {r['text']}" + (f" _(from {r['profile']})_" if r in kit["inherited_rulings"] else "")
                                                for r in kit["rulings"]]
    if kit["vocabulary"]:
        L += ["", "## Vocabulary (use exactly as written)"] + [f"- {v['text']}" + (f" — {v['note']}" if v.get("note") else "")
                                                              for v in kit["vocabulary"]]
    if kit["edit_lessons"]:
        L += ["", "## Edit lessons (outrank observed lessons)"] + [f"- {x['text']}" for x in kit["edit_lessons"]]
    if kit["lessons"]:
        L += ["", "## Observed lessons"]
        for x in kit["lessons"]:
            tag = " _(seen once: weak)_" if x["section"] == "Seen once" else ""
            L.append(f"- [{x['id']}] ({x['section']}) {x['text']}{tag}")
    if kit["never"]:
        L += ["", "## Never-list (phrases this writer never uses)"] + [f"- \"{m}\"" for m in kit["never"]]
    L += ["", "## Measurable targets (the check compares against these)",
          "Primary metrics first: they separate this writer most from neutral text."]
    for t in kit["targets"]:
        L.append(f"- {'**' if t['primary'] else ''}{t['describe']}: about {t['shown']}{'**' if t['primary'] else ''}")
    if kit["examples"]:
        L += ["", "## Example passages (style reference only: never reuse their content)"]
        for e in kit["examples"]:
            L += ["", f"### {e['id']} — {e.get('habit') or ''}", "", e["text"]]
    return "\n".join(L) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--store", required=True)
    ap.add_argument("--profile")
    ap.add_argument("--lang")
    ap.add_argument("--type")
    ap.add_argument("--facet", action="append", default=[])
    ap.add_argument("--brief")
    ap.add_argument("--examples", type=int, default=3)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    facets = {"lang": a.lang, "type": a.type}
    for f in a.facet:
        k, _, v = f.partition("=")
        facets[k] = v
    brief = pathlib.Path(a.brief).read_text(encoding="utf-8") if a.brief else ""
    try:
        kit = build(Store(a.store), a.profile, facets, brief, a.examples)
    except resolve.NoSlot as e:
        print(json.dumps({"status": "no_slot", "message": str(e)}))
        return 3
    except StoreError as e:
        print(json.dumps({"status": "no_store" if "idiolect.yaml" in str(e) else "error", "message": str(e)}))
        return 2
    print(json.dumps(kit, indent=2, ensure_ascii=False) if a.json else markdown(kit))
    return 0


if __name__ == "__main__":
    sys.exit(main())
