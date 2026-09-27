"""Measurement: the global metrics (references/fingerprint.md), slot fingerprints with pooled slots,
and confidence (spec §13). Seeded and deterministic.

    python3 measure.py --store STORE --profile P [--slot en.essay]   fingerprints as JSON (nothing written)
    python3 measure.py --file TEXT --lang en                         metrics of one text

In the learning pipeline (phase 2) the fingerprints go to the pending area; this script never writes.
"""
import argparse
import hashlib
import json
import math
import pathlib
import random
import re
import statistics as st
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from common import GLOBAL_METRICS, LANG_DIR, StoreError, check_schema, iso, utcnow, words  # noqa: E402

GM = json.loads(GLOBAL_METRICS.read_text(encoding="utf-8"))
METRICS = {m["name"]: m for m in GM["metrics"]}
NEEDS_LIST = {"hedges_per_1k": "hedges.txt", "conjunction_opener_share": "openers.txt",
              "contractions_per_1k": "contractions.txt"}

# Exactly the phase 0 splitter (curly double quotes are deliberately not treated as quotes: the
# thresholds were calibrated this way), plus accented capitals for other Latin-script languages.
SENT_SPLIT = re.compile(r"(?<=[.!?])[\"')\]]*\s+(?=[\"'(\[]?[A-Z0-9À-ÖØ-Þ])")
HEADING_END = re.compile(r"[.!?:;][\"'”’)\]]*$")


# ---------- language lists ----------

_lists = {}


def lang_lists(lang):
    if lang not in _lists:
        d = LANG_DIR / (lang or "")
        out = {}
        for metric, fname in NEEDS_LIST.items():
            f = d / fname
            if lang and f.exists():
                out[metric] = [ln.strip() for ln in f.read_text(encoding="utf-8").splitlines()
                               if ln.strip() and not ln.startswith("#")]
        _lists[lang] = out
    return _lists[lang]


def pack_info(lang):
    """The language pack's pack.yaml (spec §32), or None when the language has no pack."""
    f = LANG_DIR / (lang or "_") / "pack.yaml"
    if not lang or not f.exists():
        return None
    from common import load_yaml_text
    return load_yaml_text(f.read_text(encoding="utf-8")) or {}


def pack_warning(lang):
    """The caveat for a slot in this language, or None."""
    info = pack_info(lang)
    if info is None:
        return (f"no language pack for '{lang}': measured on the {len(applicable(lang))} metrics that need no "
                f"word list")
    if not info.get("calibrated"):
        return f"the thresholds were calibrated on English, not on {info.get('name', lang)}"
    return None


def applicable(lang):
    lists = lang_lists(lang)
    return [m for m in METRICS if m not in NEEDS_LIST or m in lists]


# ---------- metrics ----------

def blocks(text):
    """Every block of the text in order, headings included: [(number, block, is_heading)], numbered
    from 1 as the reader sees them."""
    t = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    if t.startswith("---"):
        parts = t.split("---", 2)
        if len(parts) == 3:
            t = parts[2]
    t = t.replace("\u2019", "'").replace("\u2018", "'")   # fixed by references/fingerprint.md; do not widen
    bs = [b.strip() for b in re.split(r"\n\s*\n", t) if b.strip()]
    return [(i, b, is_heading(b)) for i, b in enumerate(bs, 1)]


def prepare(text):
    return [b for _, b, h in blocks(text) if not h]


def is_heading(block):
    if "\n" in block.strip():
        return False
    return len(words(block)) < 12 and not HEADING_END.search(block.strip())


def sentences(t):
    t = re.sub(r"\s+", " ", t)
    return [s for s in SENT_SPLIT.split(t) if s.split()]


def metrics(text, lang="en"):
    """Values of the applicable global metrics for one text (or several joined with blank lines)."""
    paras = prepare(text)
    body = "\n\n".join(paras)
    ss = sentences(body)
    ws = words(body)
    nw = max(1, len(ws))
    k = 1000 / nw
    sl = [len(words(s)) for s in ss] or [0]
    nss = max(1, len(ss))
    low = body.lower()
    lists = lang_lists(lang)
    out = {
        "sentence_length_mean": st.mean(sl),
        "sentence_length_sd": st.pstdev(sl),
        "short_sentence_share": sum(1 for x in sl if x < 8) / len(sl),
        "long_sentence_share": sum(1 for x in sl if x > 28) / len(sl),
        "sentences_per_paragraph": len(ss) / max(1, len(paras)),
        "commas_per_sentence": body.count(",") / nss,
        "semicolons_per_1k": body.count(";") * k,
        "colons_per_1k": len(re.findall(r":(?!//)", body)) * k,
        "dashes_per_1k": len(re.findall(r"—|--| – ", body)) * k,
        "digits_per_1k": len(re.findall(r"\b\d+\b", body)) * k,
        "long_word_share": sum(1 for w in ws if len(w) >= 7) / nw,
    }
    if "hedges_per_1k" in lists:
        pat = r"\b(?:" + "|".join(re.escape(h) for h in lists["hedges_per_1k"]) + r")\b"
        out["hedges_per_1k"] = len(re.findall(pat, low)) * k
    if "conjunction_opener_share" in lists:
        openers = set(lists["conjunction_opener_share"])
        first = [(words(s) or [""])[0].lower() for s in ss]
        out["conjunction_opener_share"] = sum(1 for w in first if w in openers) / nss
    if "contractions_per_1k" in lists:
        out["contractions_per_1k"] = sum(len(re.findall(p, low)) for p in lists["contractions_per_1k"]) * k
    return {m: round(out[m], 6) for m in METRICS if m in out}


# ---------- counts (spec §17.2, §13.2) ----------

def count_for(fraction, n):
    p = round(fraction * 100)
    return min(n, max(GM["min_count"], -(-p * n // 100)))


def fail_count(n):
    return count_for(GM["fail_fraction"], n)


def downgrade_count(n):
    return count_for(GM["downgrade_fraction"], n)


# ---------- confidence (spec §13) ----------

LEVELS = ["low", "medium", "high"]


def count_level(n_texts, n_words):
    if n_texts < 3 or n_words < 3000:
        return "low"
    if n_texts >= 8 and n_words >= 15000:
        return "high"
    return "medium"


def slot_seed(profile, slot, keys=None):
    """Seed for a slot's splits and samples: from the profile and the slot's sorted text keys, so two
    slots holding the same texts (a pooled slot that mirrors an exact one) get the same result.
    Without keys (samples drawn before measuring), from the profile and the slot key."""
    basis = f"{profile}/" + ("|".join(sorted(keys)) if keys else slot)
    return int(hashlib.sha256(basis.encode("utf-8")).hexdigest()[:8], 16)


def unstable_metrics(texts, lang, seed, splits=5):
    """texts: list of (key, text). Returns the names of unstable metrics."""
    names = applicable(lang)
    if len(texts) < 2:
        return []
    rng = random.Random(seed)
    ordered = [t for _, t in sorted(texts)]
    n = len(ordered)
    over = {m: 0 for m in names}
    for _ in range(splits):
        order = rng.sample(ordered, n)
        a = metrics("\n\n".join(order[: n // 2]), lang)
        b = metrics("\n\n".join(order[n // 2:]), lang)
        for m in names:
            base = max(METRICS[m]["floor"], (a[m] + b[m]) / 2)
            if abs(a[m] - b[m]) / base > METRICS[m]["stability_tolerance"]:
                over[m] += 1
    return sorted(m for m, c in over.items() if c >= 2)


def confidence(texts, lang, seed):
    n_words = sum(len(words(t)) for _, t in texts)
    cl = count_level(len(texts), n_words)
    unstable = unstable_metrics(texts, lang, seed)
    sl = cl
    if len(texts) >= 2 and len(unstable) >= downgrade_count(len(applicable(lang))):
        sl = LEVELS[max(0, LEVELS.index(cl) - 1)]
    level = LEVELS[min(LEVELS.index(cl), LEVELS.index(sl))]
    return {"level": level, "count_level": cl, "stability_level": sl, "splits": 5}, unstable, n_words


# ---------- slots ----------

def slot_key(facet_names, facets):
    return ".".join(str(facets.get(f) or "_") for f in facet_names)


def generalisations(key):
    """en.post.linkedin -> [en.post._, en._._]; lang never becomes _."""
    parts = key.split(".")
    out = []
    for i in range(len(parts) - 1, 0, -1):
        g = parts[:i] + ["_"] * (len(parts) - i)
        if g != parts and ".".join(g) not in out:
            out.append(".".join(g))
    return out


def profile_texts(entries, get_text, facet_names, profile):
    """(key, slot, text, date) for every text that feeds `profile` as own, active, cached, not holdout."""
    out = []
    for key, e in sorted(entries.items()):
        rec = e["profiles"].get(profile)
        # unreachable texts are still learned until forgotten (design: corpus manifest)
        if not rec or rec["ownership"] != "own" or e["status"] not in ("active", "unreachable") or e.get("holdout") \
                or not e.get("cached"):
            continue
        out.append((key, slot_key(facet_names, e["facets"]), get_text(key), e.get("date")))
    return out


QUOTES = str.maketrans({"\u2019": "'", "\u2018": "'", "\u201c": '"', "\u201d": '"', "\u00a0": " "})


def normalise_quotes(text):
    """Curly quotes to straight and non-breaking spaces to spaces, applied to both the phrase and the
    text it is counted in, so a phrase measured in the corpus and counted in a draft is the same
    phrase. Metric measurement keeps its own fixed normalisation (prepare)."""
    return text.translate(QUOTES)


def _phrase_regex(phrase):
    parts = normalise_quotes(phrase).split()
    return r"\s+".join(re.escape(x) for x in parts)


def phrase_pattern(phrase):
    return re.compile(r"(?<!\w)" + _phrase_regex(phrase) + r"(?!\w)", re.I)


def phrases_pattern(phrases):
    """One pattern for several phrases, longest first, so overlapping phrases ("I think", "I think
    that") count once per use, not once per phrase."""
    alts = sorted({_phrase_regex(p) for p in phrases if p.strip()}, key=len, reverse=True)
    return re.compile(r"(?<!\w)(?:" + "|".join(alts) + r")(?!\w)", re.I) if alts else None


def phrase_rate(phrase, texts, today=None):
    """A favoured phrase's rate over a profile's own texts (design: Lessons): uses per 1,000 words and
    how many texts use it at least once. `texts` is a list of strings. None when there is nothing to
    measure on (no texts or no words): a rate of 0 would read as "never use it"."""
    pat = phrase_pattern(phrase)
    texts = [normalise_quotes(t) for t in texts]
    n_words = sum(len(words(t)) for t in texts)
    if not texts or not n_words:
        return None
    uses = [len(pat.findall(t)) for t in texts]
    return {"per_1k": round(sum(uses) * 1000 / n_words, 2), "texts": sum(1 for u in uses if u),
            "of": len(texts), "measured": (today or utcnow().date().isoformat())}


def own_texts(entries, get_text, facet_names, profile):
    """Every text that feeds `profile` as its own, once each, whatever its slot."""
    return [t for _, _, t, _ in profile_texts(entries, get_text, facet_names, profile)]


def weighted(texts, since):
    """since=<year>: texts dated in or after that year count twice in the measurement."""
    if not since:
        return texts
    out = []
    for key, text, date in texts:
        out.append((key, text, date))
        if date and str(date)[:4].isdigit() and int(str(date)[:4]) >= int(since):
            out.append((key + "+", text, date))
    return out


def slot_texts(entries, get_text, facet_names, profile):
    """{slot: {"pooled": bool, "texts": [(key, text, date)]}} including pooled generalisations."""
    slots = {}
    for key, slot, text, date in profile_texts(entries, get_text, facet_names, profile):
        slots.setdefault(slot, {"pooled": False, "texts": []})["texts"].append((key, text, date))
    for slot in [s for s, v in slots.items() if not v["pooled"]]:
        for g in generalisations(slot):
            slots.setdefault(g, {"pooled": True, "texts": []})["texts"].extend(slots[slot]["texts"])
    for v in slots.values():
        v["texts"] = sorted(set(v["texts"]), key=lambda t: t[0])
    return slots


# Writer bands (design: decision log, after runs 5 and 6): the check's tolerance per metric follows how
# much the writer's own passages vary. A window is paragraphs gathered until it holds BAND_WINDOW words
# (about a draft's length); with at least BAND_MIN_WINDOWS windows, a band is widened to the BAND_Q
# quantiles of window value / slot value, never narrowed below the global band.
BAND_WINDOW = 350
BAND_MIN_WINDOWS = 20
BAND_Q = (0.05, 0.95)
NO_SHORTFALL = 0.05          # the marker for "shortfall is not flagged" (references/fingerprint.md)


def windows(texts, size=BAND_WINDOW):
    """Passages of at least `size` words, cut at paragraph boundaries; a short remainder is dropped."""
    out = []
    for t in texts:
        cur, n = [], 0
        for b in prepare(t):
            cur.append(b)
            n += len(words(b))
            if n >= size:
                out.append("\n\n".join(cur))
                cur, n = [], 0
    return out


def quantile(xs, q):
    xs = sorted(xs)
    i = q * (len(xs) - 1)
    a = int(i)
    b = min(a + 1, len(xs) - 1)
    return xs[a] + (xs[b] - xs[a]) * (i - a)


def writer_bands(texts, lang, vals):
    """{metric: (overshoot, shortfall)} for a slot. Global bands unless the texts give at least
    BAND_MIN_WINDOWS windows; then each band is widened to what the writer's own windows show. A
    metric whose writer value is under its floor keeps the global band (check judges it by absolute
    difference). A shortfall at or under NO_SHORTFALL means the writer's own passages often lack the
    device entirely, so a draft without it is not flagged."""
    out = {m: (METRICS[m]["overshoot"], METRICS[m]["shortfall"]) for m in vals}
    wins = [metrics(w, lang) for w in windows(texts)]
    if len(wins) < BAND_MIN_WINDOWS:
        return out
    for m, v in vals.items():
        g = METRICS[m]
        if v < g["floor"]:
            continue
        rs = [w[m] / v for w in wins if m in w]
        over = max(g["overshoot"], round(quantile(rs, BAND_Q[1]), 3))
        short = g["shortfall"]
        if short > NO_SHORTFALL:
            short = max(NO_SHORTFALL, min(short, round(quantile(rs, BAND_Q[0]), 3)))
        out[m] = (over, short)
    return out


def build_fingerprint(profile, slot, pooled, texts, since=None, primary=(), metric_list="global",
                      contrast=None, built=None):
    lang = slot.split(".")[0]
    seed = slot_seed(profile, slot, [k for k, _, _ in texts])
    plain = [(k, t) for k, t, _ in texts]
    conf, unstable, n_words = confidence(plain, lang, seed)
    wt = weighted(texts, since)
    vals = metrics("\n\n".join(t for _, t, _ in wt), lang)
    bands = writer_bands([t for _, t in plain], lang, vals)
    fp = {"schema_version": 1, "profile": profile, "slot": slot, "pooled": pooled,
          "metrics": {m: {"value": v, "overshoot": bands[m][0],
                          "shortfall": bands[m][1], "primary": m in primary}
                      for m, v in vals.items()},
          "counts": {"texts": len(texts), "words": n_words},
          "confidence": conf, "seed": seed, "metric_list": metric_list,
          "built": built or iso(utcnow()), "personal_data": "none"}
    if contrast:
        fp["contrast"] = contrast
    check_schema("fingerprint", fp, f"fingerprint {profile}/{slot}")
    return fp, unstable


def fingerprints_view(entries, get_text, facet_names, profile, only=None, since=None, keep=None):
    """Fingerprints for every slot of `profile` given a manifest view. `keep` maps slot -> existing
    fingerprint, whose primary flags and contrast block are carried over."""
    out = []
    built = iso(utcnow())
    for slot, v in sorted(slot_texts(entries, get_text, facet_names, profile).items()):
        if only and slot not in only:
            continue
        old = (keep or {}).get(slot) or {}
        primary = [m for m, x in (old.get("metrics") or {}).items() if x.get("primary")]
        fp, unstable = build_fingerprint(profile, slot, v["pooled"], v["texts"], since, primary,
                                         old.get("metric_list", "global"), old.get("contrast"), built)
        out.append({"fingerprint": fp, "unstable": unstable})
    return out


def fingerprints(store, profile, only=None):
    since = None
    py = store.root / "profiles" / profile / "profile.yaml"
    if py.exists():
        from common import read_store_file
        since = read_store_file(py, "profile").get("since")
    return fingerprints_view(store.manifest["texts"], store.corpus_text, store.facets, profile,
                             [only] if only else None, since)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--store")
    ap.add_argument("--profile")
    ap.add_argument("--slot")
    ap.add_argument("--file")
    ap.add_argument("--lang", default="en")
    a = ap.parse_args(argv)
    try:
        if a.file:
            text = pathlib.Path(a.file).read_text(encoding="utf-8")
            out = {"lang": a.lang, "applicable": len(applicable(a.lang)), "metrics": metrics(text, a.lang)}
        elif a.store and a.profile:
            from store import Store
            out = fingerprints(Store(a.store), a.profile, a.slot)
        else:
            ap.error("give --file, or --store and --profile")
    except StoreError as e:
        print(json.dumps({"status": "error", "message": str(e)}))
        return 2
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
