"""shape: how a piece is built, measured per text against the writer's own range (spec §41).

The global metrics (measure.py) describe sentences and words over a whole slot. Readers who take a draft
for machine-written point at its build instead: paragraphs of one length, sections of one length, long
quotations of other people, and a text that never turns to the reader. Those vary from one text to the
next, so they are measured per text, and the writer's range is the 10th to 90th percentile of their own
texts in the slot. Nothing is stored: the range is worked out from the cached texts when the kit is built
or a draft is checked, as for the built-in signs (aisigns.writer_usage).

    python3 shape.py --file TEXT [--lang en]                       the shape of one text
    python3 shape.py --store S --profile P [--lang en --type longform]   the writer's ranges (nothing written)

The kit gives the ranges as targets; `check` warns, never fails, when a draft falls outside one.
"""
import argparse
import json
import pathlib
import re
import statistics as st
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import measure  # noqa: E402
from common import LANG_DIR, StoreError, count_words, words  # noqa: E402

MIN_WORDS = 300          # a text (or draft) shorter than this has too few paragraphs to have a shape
MIN_TEXTS = 5            # the writer needs this many texts of MIN_WORDS for a range
MIN_PARAGRAPHS = 5       # paragraph measures need this many paragraphs
MIN_SECTIONS = 3         # section length variation needs this many sections
RANGE_Q = (0.10, 0.90)   # the writer's range: these percentiles of their per-text values
WARN_AT = 4              # check warns when this many measures fall outside the range (design: decision log)

# name: (describe, format, side). side "both": outside the range either way is off the writer;
# "high": only above it (fewer quotations than the writer is never a warning).
FEATURES = {
    "paragraph_length_cv": ("variation in paragraph length (sd / mean of words per paragraph)", "{:.2f}", "both"),
    "paragraph_sentences": ("sentences per paragraph, on average", "{:.1f}", "both"),
    "one_sentence_paragraphs": ("share of paragraphs that are a single sentence", "{:.0%}", "both"),
    "section_length_cv": ("variation in section length (sd / mean of words per section)", "{:.2f}", "both"),
    "reader_address_per_1k": ("words addressing the reader (you, your) per 1,000 words", "{:.0f}", "both"),
    "long_quotes_per_1k": ("quotations of four words or more, per 1,000 words", "{:.1f}", "high"),
    "quoted_share": ("share of the words that are quoted from others", "{:.0%}", "high"),
}

_address = {}


def address_words(lang):
    """The language pack's reader-address list (references/lang/<code>/address.txt), or None."""
    code = (lang or "").split("-")[0]
    if code not in _address:
        f = LANG_DIR / code / "address.txt" if code else None
        _address[code] = ([ln.strip() for ln in f.read_text(encoding="utf-8").splitlines()
                           if ln.strip() and not ln.startswith("#")] if f and f.exists() else None)
    return _address[code]


def _cv(xs):
    return st.pstdev(xs) / st.mean(xs) if len(xs) > 1 and st.mean(xs) else 0.0


def _quoted(text):
    """(long quotations, words inside them, all words) outside the reference list and tables. A block quote
    counts as one quotation; a quotation in the running text counts from QUOTE_MIN_WORDS words."""
    n_quotes = n_quoted = n_all = 0
    for _, b, h in measure.blocks(text):
        if h and measure.REF_HEADING.match(b.strip()):
            break
        lines = [ln for ln in b.split("\n") if ln.strip()]
        if lines and all(ln.lstrip().startswith("|") for ln in lines):
            continue
        n = count_words(b)
        n_all += n
        if lines and all(ln.lstrip().startswith(">") for ln in lines):
            n_quotes += 1
            n_quoted += n
            continue
        for m in measure.QUOTED.finditer(b):
            q = count_words(m.group(0))
            if q >= measure.QUOTE_MIN_WORDS:
                n_quotes += 1
                n_quoted += q
    return n_quotes, n_quoted, n_all


def measures(text, lang="en"):
    """{feature: value} for one text; a feature is left out where the text cannot show it (too few
    paragraphs or sections, no reader-address list for the language). Empty under MIN_WORDS words."""
    blocks = measure.prose_blocks(text)
    paras = [b for _, b, h in blocks if not h]
    prose_words = sum(count_words(p) for p in paras)
    if prose_words < MIN_WORDS:
        return {}
    out = {}
    if len(paras) >= MIN_PARAGRAPHS:
        pl = [count_words(p) for p in paras]
        ps = [max(1, len(measure.sentences(p))) for p in paras]
        out["paragraph_length_cv"] = _cv(pl)
        out["paragraph_sentences"] = st.mean(ps)
        out["one_sentence_paragraphs"] = sum(1 for x in ps if x == 1) / len(ps)
    sections, cur = [], 0
    for _, b, h in blocks:
        if h:
            if cur:
                sections.append(cur)
            cur = 0
        else:
            cur += count_words(b)
    if cur:
        sections.append(cur)
    if len(sections) >= MIN_SECTIONS:
        out["section_length_cv"] = _cv(sections)
    addr = address_words(lang)
    if addr:
        body = "\n".join(paras).lower().replace("’", "'")
        pat = r"(?<!\w)(?:" + "|".join(re.escape(w) for w in sorted(addr, key=len, reverse=True)) + r")(?!\w)"
        out["reader_address_per_1k"] = len(re.findall(pat, body)) * 1000 / prose_words
    n_quotes, n_quoted, n_all = _quoted(text)
    if n_all:
        out["long_quotes_per_1k"] = n_quotes * 1000 / n_all
        out["quoted_share"] = n_quoted / n_all
    return {k: round(v, 4) for k, v in out.items()}


def ranges(texts, lang="en"):
    """{"texts": texts of MIN_WORDS or more, "features": {feature: {"low", "mid", "high", "texts"}}}: the
    writer's range per feature, for features shown by at least MIN_TEXTS texts."""
    per = [m for m in (measures(t, lang) for t in texts) if m]
    feats = {}
    for f in FEATURES:
        vals = [m[f] for m in per if f in m]
        if len(vals) < MIN_TEXTS:
            continue
        feats[f] = {"low": round(measure.quantile(vals, RANGE_Q[0]), 4), "mid": round(st.median(vals), 4),
                    "high": round(measure.quantile(vals, RANGE_Q[1]), 4), "texts": len(vals)}
    return {"texts": len(per), "features": feats}


def writer_ranges(store, prof, slot):
    """ranges() over the slot's own cached texts (holdouts left out, as for rulings and signs)."""
    def text_of(key):
        try:
            return store.corpus_text(key)
        except StoreError:
            return ""
    slots = measure.slot_texts(store.manifest["texts"], text_of, store.facets, prof)
    texts = [t for _, t, _ in (slots.get(slot) or {}).get("texts", []) if count_words(t)]
    return ranges(texts, slot.split(".")[0])


def compare(draft_measures, writer):
    """[{"feature", "draft", "low", "mid", "high", "flag"}] for every feature both sides have; flag is
    "ok", "low" or "high" (a "high"-only feature is never "low")."""
    out = []
    for f, (_, _, side) in FEATURES.items():
        r = writer["features"].get(f)
        if not r or f not in draft_measures:
            continue
        v = draft_measures[f]
        flag = "high" if v > r["high"] else "low" if v < r["low"] and side == "both" else "ok"
        out.append({"feature": f, "draft": v, "low": r["low"], "mid": r["mid"], "high": r["high"], "flag": flag})
    return out


def shown(f, v):
    return FEATURES[f][1].format(v)


def advice(row):
    """One line telling the writer of a draft what to change for a feature outside the range."""
    f, flag = row["feature"], row["flag"]
    rng = f"{shown(f, row['low'])} to {shown(f, row['high'])}"
    tips = {
        ("paragraph_length_cv", "low"): "paragraphs are too even: let some be one or two lines and some run long",
        ("paragraph_length_cv", "high"): "paragraph lengths swing more than the writer's: even them out a little",
        ("paragraph_sentences", "high"): "paragraphs hold too many sentences: split them where the thought turns",
        ("paragraph_sentences", "low"): "paragraphs are shorter than the writer's: join the ones that carry one thought",
        ("one_sentence_paragraphs", "low"): "too few one-sentence paragraphs: give a turn or a verdict its own line",
        ("one_sentence_paragraphs", "high"): "too many one-sentence paragraphs: fold some into their neighbours",
        ("section_length_cv", "low"): "sections are all about one length: let the section that matters most run "
                                      "longer and keep the others short",
        ("section_length_cv", "high"): "section lengths swing more than the writer's",
        ("reader_address_per_1k", "low"): "the text rarely turns to the reader: say \"you\" where the writer would",
        ("reader_address_per_1k", "high"): "the text addresses the reader more than the writer does",
        ("long_quotes_per_1k", "high"): "too many long quotations: paraphrase most, name the source, and quote "
                                        "only the line that has to be exact",
        ("quoted_share", "high"): "too much of the text is other people's words: paraphrase and keep only the "
                                  "quotation that carries the point",
    }
    return (f"{FEATURES[f][0]}: draft {shown(f, row['draft'])}, the writer's texts {rng}; "
            f"{tips.get((f, flag), 'outside the writer range')}")


# ---------- the kit ----------

def kit_lines(writer, export=False):
    """The kit's section on the shape of the piece; empty when the writer has too few texts for a range."""
    feats = writer.get("features") or {}
    if not feats:
        return []
    L = ["", "## Shape of the piece (from the writer's own texts)",
         f"How the writer's texts are built, from {writer['texts']} texts of {MIN_WORDS} words or more: the middle "
         f"10th to 90th percentile per text. Build the piece inside these ranges and near the middle; an even, "
         f"tidy shape is what readers notice first in machine-written text."
         + ("" if export else " `check` warns about a draft outside a range.")]
    for f, (describe, _, side) in FEATURES.items():
        r = feats.get(f)
        if not r:
            continue
        if side == "high" and r["high"] == 0:
            L.append(f"- {describe}: none in the writer's texts")
        elif side == "high":
            L.append(f"- {describe}: at most {shown(f, r['high'])} (the middle text {shown(f, r['mid'])}; fewer is fine)")
        else:
            L.append(f"- {describe}: {shown(f, r['low'])} to {shown(f, r['high'])} (the middle text {shown(f, r['mid'])})")
    if "long_quotes_per_1k" in feats or "quoted_share" in feats:
        L.append("- Paraphrase what others said and name them; quote only the line whose exact words matter.")
    if "reader_address_per_1k" in feats:
        L.append("- Turn to the reader as often as these texts do, in the second person where they would; no more.")
    return L


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--store")
    ap.add_argument("--profile")
    ap.add_argument("--type")
    ap.add_argument("--file")
    ap.add_argument("--lang", default="en")
    a = ap.parse_args(argv)
    try:
        if a.file:
            out = {"lang": a.lang, "shape": measures(pathlib.Path(a.file).read_text(encoding="utf-8"), a.lang)}
        elif a.store and a.profile:
            from store import Store
            import resolve
            store = Store(a.store)
            prof, slot, _ = resolve.resolve(store, a.profile, {"lang": a.lang, "type": a.type})
            out = {"profile": prof, "slot": slot, **writer_ranges(store, prof, slot)}
        else:
            ap.error("give --file, or --store and --profile")
    except StoreError as e:
        print(json.dumps({"status": "error", "message": str(e)}))
        return 2
    print(json.dumps(out, indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
