"""guide: a voice guide for people, from what a profile has learned (spec §29). Read-only; no lock.

    python3 guide.py --store S [--profile P] [--lang L] [--type T] [--facet k=v] [--examples N]
                     [--rulings-only] [--include-parent] [--out FILE]

A Markdown document an editor, ghostwriter or colleague can follow: the measurable habits in words,
the rulings (always / never), the writer's own corrections, habits, words and phrases, what the
writer never writes, and a few redacted example passages. With --rulings-only it is the house style
guide: the rulings alone, grouped. Leaves out private vocabulary, lesson quotes and every corpus text;
an example passage without a reviewed redaction record is left out and counted.
"""
import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import kit as kitmod  # noqa: E402
from common import StoreError, read_store_file, utcnow  # noqa: E402
from store import Store  # noqa: E402

LANGS = {"en": "English", "nl": "Dutch", "de": "German", "fr": "French", "es": "Spanish", "it": "Italian",
         "pt": "Portuguese", "pl": "Polish"}


def _plural(word):
    return word if word.endswith("s") else word + "s"


def _cap(text):
    return text[:1].upper() + text[1:]


def _checked(r):
    return " (checked)" if r.get("test") else ""


def _rulings(k, requested):
    out = []
    for r in k["rulings"]:
        src = f" _(from {r['profile']})_" if r["profile"] != requested else ""
        note = r.get("note", "").replace("your texts do this", "this writer's own texts do this") \
            .replace("never more", "stay at or below that")
        out.append(f"- {r['text']}{note}{_checked(r)}{src}")
    return out


def build(store, profile=None, facets=None, n_examples=3, rulings_only=False, include_parent=False):
    requested = profile or store.config["default_profile"]
    k = kitmod.build(store, requested, facets, None, max(n_examples, 1))
    if k["profile"] != requested and not include_parent:
        raise StoreError(f"{requested} has no slot for this request; the nearest is {k['profile']}/{k['slot']}, "
                         f"a parent profile's. Use include_parent=true, or learn this slot first")
    prof = read_store_file(store.root / "profiles" / k["profile"] / "profile.yaml", "profile")
    lang, typ = k["slot"].split(".")[0], (k["slot"].split(".") + ["_"])[1]
    what = f"{_plural(typ) if typ != '_' else 'texts'} in {LANGS.get(lang, lang)}"
    today = utcnow().date().isoformat()
    if rulings_only:
        L = [f"# Style guide: {requested}", "",
             f"The rules that apply to {what}, as of {today}. \"(checked)\" marks a rule the Idiolect check "
             f"tests in every draft."]
        if not k["rulings"]:
            L += ["", "No rulings yet."]
        else:
            L += ["", "## Rules", ""] + _rulings(k, requested)
        return {"profile": k["profile"], "slot": k["slot"], "rulings": len(k["rulings"]),
                "guide": "\n".join(L) + "\n"}
    c = k["confidence"]
    L = [f"# Voice guide: {prof['subject']}", "",
         f"How this voice writes {what}. For an editor, a ghostwriter or a colleague writing in it. Learned "
         f"by Idiolect from {k['counts']['texts']} texts ({k['counts']['words']:,} words); confidence {c['level']}; "
         f"{today}.",
         "", "Follow the rules exactly. Treat the habits as tendencies: a text that uses every habit reads "
         "less like this writer than a plain one."]
    if k["rulings"]:
        L += ["", "## Always and never", ""] + _rulings(k, requested)
    if k["edit_lessons"]:
        L += ["", "## Corrections the writer makes to drafts", ""] + [f"- {x['text']}" for x in k["edit_lessons"]]
    L += ["", "## The shape of the writing", "",
          "Measured on the writer's texts; the most distinctive first."]
    for t in k["targets"]:
        fmt = kitmod.DESCRIBE.get(t["metric"], ("", "{:.2f}"))[1]
        rng = f" (usually {t['shown_range']})" if "shown_range" in t else ""
        L.append(f"- {_cap(t['describe'])}: about {fmt.format(t['slot_value'])}{rng}"
                 + (" (distinctive)" if t["primary"] else ""))
    habits = [x for x in k["lessons"] if x.get("default")]
    if habits:
        L += ["", "## Habits", ""] + [f"- {x['text']} ({kitmod.seen(x)})" for x in habits]
    forms = [v for v in k["forms"] if not v.get("private")]
    phrases = [v for v in k["phrases"] if not v.get("private")]
    if forms:
        L += ["", "## Words and spellings", "", "Written exactly this way whenever they are used; never required."]
        L += [f"- {v['text']}" + (f" ({v['note']})" if v.get("note") else "") for v in forms]
    if phrases:
        L += ["", "## Favoured phrases", "", "Part of the voice, sparingly: never more often than the writer."]
        L += [f"- \"{v['text']}\": at most {kitmod.phrase_rate_text(v)}" for v in phrases]
    fl = k.get("flavour")
    if fl and fl.get("markers"):
        r = fl["rate"]
        L += ["", "## Language flavour", "",
              f"The writer's {LANGS.get(fl['lang'], fl['lang'])} carries a {fl['strength']} trace of "
              f"{', '.join(LANGS.get(o, o) for o in fl['origins']) or 'another language'}: {r['per_1k']:g} per 1,000 "
              f"words, in {r['texts']} of {r['of']} texts, never more than {r['max_per_1k']:g} per 1,000 words in one "
              "text. Keep it at that rate or leave it out; never add more, and never as spelling mistakes."]
        for m in fl["markers"]:
            ex = f" For example: \"{m['examples'][0]}\"" if m.get("examples") else ""
            L.append(f"- {m['name']}: {m['how']}{ex}")
    if k["never"]:
        L += ["", "## Never written", "", "Phrases common in machine-written text that this writer does not use."]
        L += [f"- \"{m}\"" for m in k["never"]]
    shown, left = [], 0
    for e in k["examples"][:n_examples]:
        red = e.get("redaction") or {}
        if red.get("redacted") and red.get("reviewed"):
            shown.append(e)
        else:
            left += 1
    if shown:
        L += ["", "## Example passages", "",
              "The voice in the writer's own words, with names and organisations replaced. Match how they read; "
              "never reuse their content."]
        for e in shown:
            L += ["", f"### {e['id']}", "", e["text"]]
    return {"profile": k["profile"], "slot": k["slot"], "examples": len(shown),
            "left_out": {"private_vocabulary": len(k["forms"]) + len(k["phrases"]) - len(forms) - len(phrases),
                         "unreviewed_examples": left, "lesson_quotes": "all", "corpus": "all"},
            "guide": "\n".join(L) + "\n"}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--store", required=True)
    ap.add_argument("--profile")
    ap.add_argument("--lang")
    ap.add_argument("--type")
    ap.add_argument("--facet", action="append", default=[])
    ap.add_argument("--examples", type=int, default=3)
    ap.add_argument("--rulings-only", action="store_true")
    ap.add_argument("--include-parent", action="store_true")
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    facets = {"lang": a.lang, "type": a.type}
    for f in a.facet:
        key, _, v = f.partition("=")
        facets[key] = v
    try:
        out = build(Store(a.store), a.profile, facets, max(a.examples, 0), a.rulings_only, a.include_parent)
    except StoreError as e:
        print(json.dumps({"status": "error", "message": str(e)}, indent=1, ensure_ascii=False))
        return 1
    if a.out:
        pathlib.Path(a.out).write_text(out.pop("guide"), encoding="utf-8")
        out["file"] = a.out
    print(json.dumps(out, indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
