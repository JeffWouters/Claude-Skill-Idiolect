"""export: one self-contained prompt for writing in a learned voice, for use in another tool (spec §22).
Read-only: writes nothing to the store and takes no lock.

    python3 export.py --store S [--profile P] [--lang L] [--type T] [--facet k=v] [--include-parent] [--out FILE]

Prints JSON: the file written (or the prompt, without --out), the profile and slot, and what was left
out. Refuses when the slot belongs to a parent profile (without --include-parent) or when an example
lacks a reviewed redaction record.
"""
import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import kit as kitmod  # noqa: E402
from common import StoreError, utcnow  # noqa: E402
from store import Store  # noqa: E402

ALL_EXAMPLES = 1000


def build(store, profile=None, facets=None, include_parent=False):
    requested = profile or store.config["default_profile"]
    k = kitmod.build(store, requested, facets, None, ALL_EXAMPLES)
    if k["profile"] != requested and not include_parent:
        raise StoreError(f"{requested} has no slot for this request; the nearest is {k['profile']}/{k['slot']}, "
                         f"a parent profile's. Export it with include_parent=true, or learn this slot first")
    bad = [e["id"] for e in k["examples"]
           if not (e.get("redaction") or {}).get("redacted") or not (e.get("redaction") or {}).get("reviewed")]
    if bad:
        raise StoreError(f"examples without a reviewed redaction record: {', '.join(bad)}; review them "
                         f"(learn) before exporting. Nothing was exported")
    vocab = [v for v in k["forms"] + k["phrases"] if not v.get("private")]
    private = len(k["forms"]) + len(k["phrases"]) - len(vocab)
    c = k["confidence"]
    L = [f"# Writing voice: {k['profile']} / {k['slot']}", "",
         f"Exported {utcnow().date().isoformat()} from an Idiolect profile. Confidence {c['level']}, "
         f"learned from {k['counts']['texts']} texts ({k['counts']['words']} words)."
         + (f" This slot belongs to the parent profile {k['profile']} of {requested}." if k["profile"] != requested else ""),
         "", "## How to use this",
         "You are writing as this writer. The example passages at the end are the voice: match how they read,",
         "their sentence movement, tone and how sparingly each device appears. Never reuse their content, facts,",
         "names or turns of phrase. Never invent facts, names, numbers or anecdotes: where the voice wants one",
         "you were not given, write a placeholder such as [example needed: a real incident].",
         "Obey the rulings. Apply the edit lessons: they are the writer's own corrections. Aim at the targets.",
         "Never use a phrase from the never-list. The notes on habits describe what the examples show; they are",
         "not a checklist, and a draft that uses every habit reads less like the writer than a plain one."]
    if k["rulings"]:
        L += ["", "## Rulings (always obey)"] + [f"- {r['text']}" + r.get("note", "").replace("your texts", "the writer's texts") for r in k["rulings"]]
    if k["edit_lessons"]:
        L += ["", "## Edit lessons (the writer's own corrections)"] + [f"- {x['text']}" for x in k["edit_lessons"]]
    L += ["", "## Targets (measured on the writer's texts)"]
    for t in k["targets"]:
        rng = f" (the writer's own passages: {t['shown_range']})" if "range" in t else ""
        L.append(f"- {t['describe']}: about {kitmod.DESCRIBE.get(t['metric'], ('', '{:.2f}'))[1].format(t['slot_value'])}{rng}")
    if k["never"]:
        L += ["", "## Never-list (this writer never writes these)"] + [f'- "{m}"' for m in k["never"]]
    forms = [v for v in vocab if v["kind"] != "phrase"]
    phrases = [v for v in vocab if v["kind"] == "phrase"]
    if forms:
        L += ["", "## Forms (when you use one of these words, write it exactly so; never required)"]
        L += [f"- {v['text']}" + (f" ({v['note']})" if v.get("note") else "") for v in forms]
    if phrases:
        L += ["", "## Favoured phrases (never required)"]
        L += [f"- \"{v['text']}\": at most {kitmod.phrase_rate_text(v)}" for v in phrases]
    if k.get("flavour"):
        import flavour
        L += flavour.kit_lines(k["flavour"])
    notes = [x for x in k["lessons"] if x["default"]]
    if notes:
        L += ["", "## Habits most of the writer's texts show (background, not a checklist)"]
        L += [f"- {x['text']} ({kitmod.seen(x)})" for x in notes]
    if k["examples"]:
        L += ["", "## Example passages (the voice; never reuse their content)"]
        for e in k["examples"]:
            L += ["", f"### {e['id']}", "", e["text"]]
    return {"profile": k["profile"], "slot": k["slot"], "examples": len(k["examples"]),
            "left_out": {"private_vocabulary": private, "lesson_quotes": "all", "corpus": "all"},
            "prompt": "\n".join(L) + "\n"}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--store", required=True)
    ap.add_argument("--profile")
    ap.add_argument("--lang")
    ap.add_argument("--type")
    ap.add_argument("--facet", action="append", default=[])
    ap.add_argument("--include-parent", action="store_true")
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    facets = {"lang": a.lang, "type": a.type}
    for f in a.facet:
        key, _, v = f.partition("=")
        facets[key] = v
    try:
        out = build(Store(a.store), a.profile, facets, a.include_parent)
    except StoreError as e:
        print(json.dumps({"status": "error", "message": str(e)}, indent=1, ensure_ascii=False))
        return 1
    if a.out:
        pathlib.Path(a.out).write_text(out.pop("prompt"), encoding="utf-8")
        out["file"] = a.out
    print(json.dumps(out, indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
