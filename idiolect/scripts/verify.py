"""verify: does a text read like the writer's own texts of a slot? (spec §28). Read-only; takes no lock.

    python3 verify.py --store S --file TEXT [--profile P] [--lang L] [--type T] [--facet k=v] [--json]

Measures how far the text sits from the typical text of the slot (mean |ln ratio| over the metrics,
against the median of the writer's texts) and compares that with how far the writer's own texts sit
from each other. The same measure flags outliers during `learn` (learn.py measure). One text is weak
evidence: the verdict says "looks like", never "is" or "is not" the writer's.
"""
import argparse
import json
import math
import pathlib
import statistics
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import measure  # noqa: E402
import resolve  # noqa: E402
from common import StoreError, count_words  # noqa: E402

MIN_TEXTS = 5     # fewer texts give no stable picture of the spread
K = 4             # robust deviations above the median distance (evals/outliers: about 1% false flags)
MIN_FACTOR = 1.5  # and at least 1.5 times the median distance
TOP = 3


def _floor(m):
    return measure.METRICS[m]["floor"]


def ratio(a, b, m):
    return max(a, _floor(m)) / max(b, _floor(m))


def distance(vals, ref):
    """Mean |ln ratio| over the metrics both sides have; values below a metric's floor count as the
    floor, so a device the writer never uses does not blow up the distance."""
    ms = [m for m in ref if m in vals]
    if not ms:
        return 0.0
    return sum(abs(math.log(ratio(vals[m], ref[m], m))) for m in ms) / len(ms)


def median_ref(values):
    ms = set.intersection(*(set(v) for v in values)) if values else set()
    return {m: statistics.median(v[m] for v in values) for m in ms}


def loo_distances(values):
    """Each text's distance to the median of the others."""
    return [distance(v, median_ref(values[:i] + values[i + 1:])) for i, v in enumerate(values)]


def threshold(dists, k=K):
    med = statistics.median(dists)
    mad = statistics.median(abs(x - med) for x in dists)
    return max(med + k * 1.4826 * mad, MIN_FACTOR * med)


def off(vals, ref):
    """The metrics furthest from the typical text, described for a person."""
    from kit import DESCRIBE
    rows = []
    for m in ref:
        if m not in vals:
            continue
        r = ratio(vals[m], ref[m], m)
        name, fmt = DESCRIBE.get(m, (m, "{:.2f}"))
        rows.append({"metric": m, "describe": name, "text": fmt.format(vals[m]), "typical": fmt.format(ref[m]),
                     "ratio": round(r, 2), "direction": "more" if r > 1 else "fewer"})
    rows.sort(key=lambda x: -abs(math.log(x["ratio"])))
    return [x for x in rows if abs(math.log(x["ratio"])) >= math.log(1.25)][:TOP]


def slot_outliers(texts, lang):
    """texts: [(key, text)] of one slot. [{key, distance, threshold, median, off}] for the texts that sit
    unusually far from the others; [] below MIN_TEXTS."""
    if len(texts) < MIN_TEXTS:
        return []
    vals = [measure.metrics(t, lang) for _, t in texts]
    d = loo_distances(vals)
    thr, med = threshold(d), statistics.median(d)
    out = []
    for i, ((key, _), x) in enumerate(zip(texts, d)):
        if x > thr:
            out.append({"key": key, "distance": round(x, 3), "threshold": round(thr, 3), "median": round(med, 3),
                        "off": off(vals[i], median_ref(vals[:i] + vals[i + 1:]))})
    return out


def verify(store, text, profile=None, facets=None):
    prof, slot, _ = resolve.resolve(store, profile, facets)
    lang = slot.split(".")[0]
    own = measure.slot_texts(store.manifest["texts"], store.corpus_text, store.facets, prof).get(slot, {})
    texts = [t for _, t, _ in own.get("texts", [])]
    if len(texts) < MIN_TEXTS:
        raise StoreError(f"{prof}/{slot} has {len(texts)} texts; verify needs at least {MIN_TEXTS} to know how "
                         f"much the writer's own texts vary")
    n = count_words(text)
    vals = [measure.metrics(t, lang) for t in texts]
    own_d = loo_distances(vals)
    thr, med = threshold(own_d), statistics.median(own_d)
    ref = median_ref(vals)
    tv = measure.metrics(text, lang)
    d = distance(tv, ref)
    closer = sum(1 for x in own_d if x >= d) / len(own_d)
    if d <= med:
        verdict = "looks like the writer's texts: closer to the typical text than most of their own"
    elif d <= thr:
        verdict = "within the range of the writer's own texts"
    else:
        verdict = "unlike the writer's texts: further from the typical text than their own texts go"
    notes = ["one text is weak evidence: this says how the text measures, not who wrote it"]
    if n < 300:
        notes.append(f"only {n} words: short texts vary more, so read the verdict loosely")
    return {"profile": prof, "slot": slot, "texts_compared": len(texts), "distance": round(d, 3),
            "own_median": round(med, 3), "threshold": round(thr, 3), "share_of_own_texts_further": round(closer, 2),
            "verdict": verdict, "off": off(tv, ref), "notes": notes}


def readable(r):
    L = [f"{r['verdict'].capitalize()}.",
         f"Measured against {r['profile']} / {r['slot']} ({r['texts_compared']} texts): distance {r['distance']}, "
         f"the writer's own texts typically {r['own_median']}, unusual beyond {r['threshold']}."]
    for o in r["off"]:
        L.append(f"- {o['describe']}: {o['text']} here, typically {o['typical']}")
    L += [f"Note: {x}" for x in r["notes"]]
    return "\n".join(L)


def main(argv=None):
    from store import Store
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--store", required=True)
    ap.add_argument("--file", required=True)
    ap.add_argument("--profile")
    ap.add_argument("--lang")
    ap.add_argument("--type")
    ap.add_argument("--facet", action="append", default=[])
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    facets = {"lang": a.lang, "type": a.type}
    for f in a.facet:
        k, _, v = f.partition("=")
        facets[k] = v
    try:
        r = verify(Store(a.store), pathlib.Path(a.file).read_text(encoding="utf-8"), a.profile, facets)
    except (StoreError, resolve.NoSlot) as e:
        print(json.dumps({"status": "error", "message": str(e)}, indent=1, ensure_ascii=False))
        return 1
    print(json.dumps(r, indent=1, ensure_ascii=False) if a.json else readable(r))
    return 0


if __name__ == "__main__":
    sys.exit(main())
