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


def applicable(lang):
    lists = lang_lists(lang)
    return [m for m in METRICS if m not in NEEDS_LIST or m in lists]


# ---------- metrics ----------

def prepare(text):
    t = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    if t.startswith("---"):
        parts = t.split("---", 2)
        if len(parts) == 3:
            t = parts[2]
    t = t.replace("’", "'").replace("‘", "'")
    blocks = [b.strip() for b in re.split(r"\n\s*\n", t) if b.strip()]
    return [b for b in blocks if not is_heading(b)]


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


def slot_seed(profile, slot):
    return int(hashlib.sha256(f"{profile}/{slot}".encode("utf-8")).hexdigest()[:8], 16)


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


def profile_texts(store, profile):
    """(key, slot, text) for every text that feeds `profile` as own, active, cached, not holdout."""
    out = []
    for key, e in sorted(store.manifest["texts"].items()):
        rec = e["profiles"].get(profile)
        if not rec or rec["ownership"] != "own" or e["status"] != "active" or e.get("holdout") \
                or not e.get("cached"):
            continue
        out.append((key, slot_key(store.facets, e["facets"]), store.corpus_text(key)))
    return out


def fingerprints(store, profile, only=None):
    texts = profile_texts(store, profile)
    slots = {}
    for key, slot, text in texts:
        slots.setdefault(slot, {"pooled": False, "texts": []})["texts"].append((key, text))
    exact = list(slots)
    for slot in exact:
        for g in generalisations(slot):
            s = slots.setdefault(g, {"pooled": True, "texts": []})
            s["texts"].extend(slots[slot]["texts"] if not slots[slot]["pooled"] else [])
    for s in slots.values():
        s["texts"] = sorted(set(s["texts"]))
    out = []
    now = iso(utcnow())
    for slot in sorted(slots):
        if only and slot != only:
            continue
        s = slots[slot]
        if not s["texts"]:
            continue
        lang = slot.split(".")[0]
        seed = slot_seed(profile, slot)
        conf, unstable, n_words = confidence(s["texts"], lang, seed)
        vals = metrics("\n\n".join(t for _, t in s["texts"]), lang)
        fp = {"schema_version": 1, "profile": profile, "slot": slot, "pooled": s["pooled"],
              "metrics": {m: {"value": v, "overshoot": METRICS[m]["overshoot"],
                              "shortfall": METRICS[m]["shortfall"], "primary": False}
                          for m, v in vals.items()},
              "counts": {"texts": len(s["texts"]), "words": n_words},
              "confidence": conf, "seed": seed, "metric_list": "global",
              "built": now, "personal_data": "none"}
        check_schema("fingerprint", fp, f"fingerprint {profile}/{slot}")
        out.append({"fingerprint": fp, "unstable": unstable})
    return out


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
