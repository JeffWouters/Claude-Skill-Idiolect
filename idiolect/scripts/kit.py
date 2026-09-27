"""The writing kit: everything `write` and `rewrite` load, and nothing more (design: Write and rewrite,
step by step). Never the corpus, never the whole example bank.

    python3 kit.py --store S [--profile P] [--lang L] [--type T] [--brief FILE] [--examples 3]
                   [--notes brief|full|none] [--json]

Prints a Markdown kit (or JSON with --json): profile and slot used (and why), confidence, the example
passages best matching the brief (first: they show the voice), rulings, edit lessons, the measurable
targets for this piece, the never-list and forms, then the observed lessons as background.

--notes brief (default): background shows only habits seen in at least half the texts.
--notes full: every lesson, split into usual and optional habits, and the favoured phrases.
--notes none: no observed lessons and no favoured phrases.
The JSON always holds everything.
"""
import argparse
import json
import math
import pathlib
import re
import sys
from collections import Counter

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import measure  # noqa: E402
import pages  # noqa: E402
import resolve  # noqa: E402
from common import StoreError, count_words, read_store_file, words  # noqa: E402
from stage import stopwords  # noqa: E402
from store import Store  # noqa: E402

RULINGS_CAP = 30
VOCAB_CAP = 40
BLEND_WORDS = 300           # design: targets follow the piece; tuned on evaluation runs 1-3
NOTES = ("brief", "full", "none")

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


def blend(fp_metrics, example_texts, lang):
    """Targets for this piece (design: Write and rewrite, step 2): each metric's slot value blended with
    its value on the chosen example passages, weight words / (words + BLEND_WORDS). Returns
    ({metric: value}, words, weight); without examples the slot values, 0, 0.0."""
    joined = "\n\n".join(t for t in example_texts if t and t.strip())
    n = count_words("\n\n".join(measure.prepare(joined))) if joined else 0
    if not n:
        return {m: v["value"] for m, v in fp_metrics.items()}, 0, 0.0
    w = n / (n + BLEND_WORDS)
    ex = measure.metrics(joined, lang)
    return ({m: round(w * ex[m] + (1 - w) * v["value"], 6) if m in ex else v["value"]
             for m, v in fp_metrics.items()}, n, round(w, 4))


def slot_examples(store, prof, slot):
    exf = store.root / "profiles" / prof / f"{slot}.examples.md"
    return pages.parse_examples(exf.read_text(encoding="utf-8"))[1] if exf.exists() else []


EVIDENCE = re.compile(r"^(\d+)(?: of (\d+))? (?:text|paragraph)s?\b")


def with_share(lesson, n_texts):
    """A lesson plus how many texts show it (design: Write and rewrite, step 2): "N of M" from the
    page, where M is the texts the lessons sample held; an older page's "N texts" is read as N of
    every text in the slot."""
    m = EVIDENCE.match(lesson.get("evidence_raw") or "")
    n = int(m.group(1)) if m else (1 if lesson["section"] == "Seen once" else None)
    of = int(m.group(2)) if m and m.group(2) else n_texts
    out = {**lesson, "texts": n, "of": of}
    # a habit seen once is weak evidence, however small the sample (review L1)
    out["default"] = bool(lesson["section"] != "Seen once" and n and n >= 2 and of and n * 2 >= of)
    return out


def seen(x):
    if x.get("texts") is None:
        return "count not recorded"
    return f"seen in {x['texts']} of {x['of']} texts"


def phrase_rate_text(v):
    r = v.get("rate")
    if not r:
        return "rate not measured yet: use sparingly, at most once in a piece"
    return (f"about {r['per_1k']:g} per 1,000 words; in {r['texts']} of {r['of']} texts")


# Tone within the voice (spec §31): each tone moves a few targets to the writer's own quartile, so a
# draft can be warmer or firmer without leaving the range the writer's texts show.
TONES = {
    "warm": {"contractions_per_1k": 1, "short_sentence_share": 1, "long_word_share": -1},
    "cool": {"contractions_per_1k": -1, "short_sentence_share": -1, "long_word_share": 1},
    "firm": {"hedges_per_1k": -1, "sentence_length_mean": -1, "short_sentence_share": 1},
    "soft": {"hedges_per_1k": 1, "sentence_length_mean": 1},
    "formal": {"contractions_per_1k": -1, "long_word_share": 1, "conjunction_opener_share": -1, "sentence_length_mean": 1},
    "casual": {"contractions_per_1k": 1, "long_word_share": -1, "conjunction_opener_share": 1, "sentence_length_mean": -1},
}
TONE_MIN_TEXTS = 5
TONE_WORDS = {"warm": "warmer", "cool": "cooler, more reserved", "firm": "firmer, more direct",
              "soft": "softer, more tentative", "formal": "more formal", "casual": "more casual"}


def parse_tone(tone):
    """'firm' or 'firm,formal' -> ['firm', 'formal']; refuses unknown tones. The order matters: see
    tone_pulls."""
    if not tone:
        return []
    names = [t.strip().lower() for t in (tone if isinstance(tone, (list, tuple)) else str(tone).split(",")) if t.strip()]
    bad = [t for t in names if t not in TONES]
    if bad:
        raise StoreError(f"unknown tone {', '.join(bad)}; tones: {', '.join(TONES)}")
    return sorted(set(names), key=names.index)


def tone_pulls(names):
    """({metric: (direction, tone)}, [conflicts]). Where two tones pull a measure both ways, the tone
    named first decides (the writer's decision): firm,formal gives shorter sentences, formal,firm longer."""
    pulls, conflicts = {}, []
    for t in names:
        for m, d in TONES[t].items():
            if m not in pulls:
                pulls[m] = (d, t)
            elif pulls[m][0] != d:
                conflicts.append({"metric": m, "describe": DESCRIBE.get(m, (m,))[0], "decided_by": pulls[m][1],
                                  "overruled": t})
    return pulls, conflicts


def apply_tone(store, prof, slot, targets, tone):
    """targets with each toned metric moved to the writer's own quartile (25th or 75th percentile of
    their texts of this slot) when that lies further in the asked direction.
    Returns (targets, moved, conflicts)."""
    names = parse_tone(tone)
    if not names:
        return targets, [], []
    lang = slot.split(".")[0]
    own = measure.slot_texts(store.manifest["texts"], store.corpus_text, store.facets, prof).get(slot, {})
    texts = [t for _, t, _ in own.get("texts", [])]
    if len(texts) < TONE_MIN_TEXTS:
        raise StoreError(f"a tone needs at least {TONE_MIN_TEXTS} texts in {prof}/{slot} to know the writer's range; "
                         f"it has {len(texts)}")
    vals = [measure.metrics(t, lang) for t in texts]
    pulls, conflicts = tone_pulls(names)
    out, moved = dict(targets), []
    for m, (d, t) in pulls.items():
        if m not in out or any(m not in v for v in vals):
            continue
        xs = [v[m] for v in vals]
        lo, hi = measure.quantile(xs, 0.25), measure.quantile(xs, 0.75)
        to = hi if d > 0 else lo
        if (d > 0 and to > out[m]) or (d < 0 and to < out[m]):
            fmt = DESCRIBE.get(m, (m, "{:.2f}"))[1]
            moved.append({"metric": m, "tone": t, "describe": DESCRIBE.get(m, (m,))[0],
                          "from": out[m], "to": to, "shown": f"{fmt.format(out[m])} -> {fmt.format(to)}",
                          "range": f"{fmt.format(lo)} to {fmt.format(hi)}"})
            out[m] = to
    return out, moved, conflicts


def build(store, profile=None, facets=None, brief=None, n_examples=3, tone=None):
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
    n_texts = fp["counts"]["texts"]
    kit["lessons"] = [with_share(x, n_texts) for x in
                      (pages.parse_slot_page(page.read_text(encoding="utf-8"))[2] if page.exists() else [])]
    edits = base / f"{slot}.edits.md"
    # confirmed edit lessons only (two or more pairs); a kind seen once is not yet a lesson (spec §20)
    kit["edit_lessons"] = [x for x in pages.parse_edits(edits.read_text(encoding="utf-8"))[1]
                           if not x["seen_once"]] if edits.exists() else []
    never = base / f"{slot}.never.md"
    kit["never"] = [m["marker"] for m in pages.parse_never(never.read_text(encoding="utf-8"))[1]] if never.exists() else []
    import rules
    rulings = rules.applicable(store, prof, slot)
    rates = rules.writer_rates(store, prof, slot, rulings)
    rulings = [{**r, "note": rules.note(r, rates)} for r in rulings]
    kit["rulings"] = rulings[:RULINGS_CAP]
    vocab = resolve.merged(store, prof, "vocabulary")
    # one cap for the whole vocabulary (design: capped in size); phrases first, forms fill the rest
    phrases = [v for v in vocab if v["kind"] == "phrase"][:VOCAB_CAP]
    kit["phrases"] = phrases
    kit["forms"] = [v for v in vocab if v["kind"] != "phrase"][:VOCAB_CAP - len(phrases)]
    kit["inherited_rulings"] = [r for r in rulings if r["profile"] != prof]
    kit["examples"] = pick_examples(slot_examples(store, prof, slot), brief, lang, n_examples)
    local, n_words, weight = blend(fp["metrics"], [e["text"] for e in kit["examples"]], lang)
    local, moved, conflicts = apply_tone(store, prof, slot, local, tone)
    kit["tone"] = {"asked": parse_tone(tone), "moved": moved, "conflicts": conflicts}
    kit["blend"] = {"examples": [e["id"] for e in kit["examples"]], "words": n_words, "weight": weight}
    targets = []
    for m, v in fp["metrics"].items():
        name, fmt = DESCRIBE.get(m, (m, "{:.2f}"))
        t = {"metric": m, "primary": v["primary"], "describe": name, "value": local[m],
             "slot_value": v["value"], "shown": fmt.format(local[m])}
        g = measure.METRICS.get(m, {})
        if (v["overshoot"], v["shortfall"]) != (g.get("overshoot"), g.get("shortfall")):
            # a writer band: this writer's own passages vary this much (measure.writer_bands)
            lo = v["value"] * v["shortfall"] if v["shortfall"] > measure.NO_SHORTFALL else 0
            t["range"] = [round(lo, 6), round(v["value"] * v["overshoot"], 6)]
            t["shown_range"] = f"{fmt.format(lo)} to {fmt.format(t['range'][1])}"
        targets.append(t)
    targets.sort(key=lambda t: (not t["primary"], t["metric"]))
    kit["targets"] = targets
    return kit


def markdown(kit, notes="brief"):
    """Examples first, then what binds (rulings, edit lessons), the targets for this piece, the
    never-list and forms; the observed lessons last, as background (design: Write and rewrite, step 2;
    decision log, run 4)."""
    L = [f"# Writing kit: {kit['profile']} / {kit['slot']}", ""]
    c = kit["confidence"]
    L.append(f"Confidence {c['level']} (count {c['count_level']}, stability {c['stability_level']}); "
             f"{kit['counts']['texts']} texts, {kit['counts']['words']} words.")
    for w in kit["warnings"]:
        L.append(f"- **Warning:** {w}")
    if kit["examples"]:
        L += ["", "## Example passages: this is the voice",
              "Match how these read: sentence movement, tone, and how sparingly each device appears. They are "
              "style references only; never reuse their content, facts, names or phrasing."]
        for e in kit["examples"]:
            L += ["", f"### {e['id']}", "", e["text"]]
    if kit["rulings"]:
        L += ["", "## Rulings (always obey)"] + [f"- {r['text']}" + r.get("note", "") + (f" _(from {r['profile']})_" if r in kit["inherited_rulings"] else "")
                                                for r in kit["rulings"]]
    if kit["edit_lessons"]:
        L += ["", "## Edit lessons (from the writer's own corrections)"] + [
            f"- {x['text']}" for x in kit["edit_lessons"]]
    if kit["targets"]:
        L += ["", "## Measurable targets for this piece (the check compares against these)",
              "Set from the writer's texts and the example passages above. Primary metrics first: they "
              "separate this writer most from neutral text."]
        if any("range" in t for t in kit["targets"]):
            L.append("Where a range is given, the writer's own passages of this length vary that much: "
                     "anywhere inside it is the writer. Follow the example passages there, not the middle.")
        for t in kit["targets"]:
            rng = f" (the writer's own passages: {t['shown_range']})" if "range" in t else ""
            L.append(f"- {'**' if t['primary'] else ''}{t['describe']}: about {t['shown']}{'**' if t['primary'] else ''}{rng}")
    tone = kit.get("tone") or {}
    if tone.get("asked"):
        L += ["", f"## Tone: {', '.join(TONE_WORDS[t] for t in tone['asked'])}",
              "Still this writer: the targets above already sit where the writer's own texts go in this "
              "direction, never beyond. Get the tone from word choice and stance within them; do not exaggerate."]
        L += [f"- {m['describe']}: {m['shown']} (the writer's texts range {m['range']})" for m in tone["moved"]]
        if not tone["moved"]:
            L.append("- The targets already lean this way; no measure moved.")
        for c in tone.get("conflicts", []):
            L.append(f"- {c['decided_by']} and {c['overruled']} pull {c['describe']} both ways: {c['decided_by']}, "
                     f"named first, decides.")
    if kit["never"]:
        L += ["", "## Never-list (phrases this writer never uses)"] + [f"- \"{m}\"" for m in kit["never"]]
    if kit["forms"]:
        L += ["", "## Forms (when you use one of these words, write it exactly so; never required)"]
        L += [f"- {v['text']}" + (f" ({v['note']})" if v.get("note") else "") for v in kit["forms"]]
    if notes == "none" or not kit["lessons"] and not (notes == "full" and kit["phrases"]):
        return "\n".join(L) + "\n"
    defaults = [x for x in kit["lessons"] if x["default"]]
    optional = [x for x in kit["lessons"] if not x["default"]]
    if notes == "brief":
        if defaults:
            L += ["", "## Background: what most of the writer's texts show",
                  "These describe what the example passages already show. They are not a checklist: never add a "
                  "habit because it is listed here, and never use one more densely than the examples do."]
            L += [f"- {x['text']} _({seen(x)})_" for x in defaults]
        return "\n".join(L) + "\n"
    L += ["", "## Background: the writer's habits",
          f"They describe what the writer's {kit['counts']['texts']} texts show, and how often. **Habits are "
          "sampled, not stacked.** A habit seen in at least half the texts is the writer's default; one seen in "
          "fewer is optional and usually left out. No single text of the writer uses every habit, so no piece "
          "should. Never use a device more densely than the examples do."]
    if defaults:
        L += ["", "### Habits the writer usually shows"]
        L += [f"- [{x['id']}] ({x['section']}) {x['text']} _({seen(x)})_" for x in defaults]
    if optional:
        L += ["", "### Habits the writer sometimes shows (optional; usually leave out)"]
        L += [f"- [{x['id']}] ({x['section']}) {x['text']} _({seen(x)})_" for x in optional]
    if kit["phrases"]:
        L += ["", "### Favoured phrases (never required; at most at the writer's rate)"]
        L += [f"- \"{v['text']}\": {phrase_rate_text(v)}" + (f"; {v['note']}" if v.get("note") else "")
              for v in kit["phrases"]]
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
    ap.add_argument("--tone", help="warm, cool, firm, soft, formal or casual; two may be combined, and where they pull a measure both ways the first named decides: firm,formal")
    ap.add_argument("--notes", choices=NOTES, default="brief",
                    help="how much of the observed lessons the Markdown kit shows (default brief)")
    ap.add_argument("--omit", action="append", default=[], choices=["targets"],
                    help="leave a section out of the Markdown kit (targets: the measurable targets)")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    facets = {"lang": a.lang, "type": a.type}
    for f in a.facet:
        k, _, v = f.partition("=")
        facets[k] = v
    brief = pathlib.Path(a.brief).read_text(encoding="utf-8") if a.brief else ""
    try:
        kit = build(Store(a.store), a.profile, facets, brief, a.examples, a.tone)
    except resolve.NoSlot as e:
        print(json.dumps({"status": "no_slot", "message": str(e)}))
        return 3
    except StoreError as e:
        print(json.dumps({"status": "no_store" if "idiolect.yaml" in str(e) else "error", "message": str(e)}))
        return 2
    if "targets" in a.omit:
        kit["targets"] = []
    print(json.dumps(kit, indent=2, ensure_ascii=False) if a.json else markdown(kit, a.notes))
    return 0


if __name__ == "__main__":
    sys.exit(main())
