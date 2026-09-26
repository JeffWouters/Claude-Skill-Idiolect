#!/usr/bin/env python3
"""Phase 0 metric experiment (throwaway). Chooses the global metric list and its defaults.

    python3 evals/spike/spike.py

Reads evals/fixtures/<author>/*.md, evals/spike/samples/<author>/N.md and
evals/spike/rewrites/<author>/N.md. Writes evals/spike/metrics.json and prints a report
that is summarised in evals/spike/RESULTS.md. Not part of the skill; measure.py in
phase 1 is written from its result.
"""
import glob
import json
import math
import pathlib
import random
import re
import statistics as st

ROOT = pathlib.Path(__file__).resolve().parents[2]
FIX = ROOT / "evals" / "fixtures"
SPK = ROOT / "evals" / "spike"
SEED = 20261002

HEDGES = r"\b(perhaps|maybe|might|arguably|somewhat|possibly|probably|seems?|seemingly|i suspect|in some sense|it may be|likely|rather|fairly|quite)\b"
FORMAL = r"\b(moreover|furthermore|additionally|consequently|nevertheless|nonetheless|therefore|thus|hence|however|in addition|it is worth noting)\b"
CONTRACTION = r"\b\w+'(s|re|ve|ll|d|t|m)\b"
OPENERS = ("and", "but", "so", "or", "yet", "then")


def strip_meta(t):
    t = re.sub(r"<!--.*?-->", "", t, flags=re.S)
    if t.startswith("---"):
        t = t.split("---", 2)[2]
    return t.replace("’", "'").replace("‘", "'").strip()


def sentences(t):
    t = re.sub(r"\s+", " ", t)
    return [s for s in re.split(r"(?<=[.!?])[\"')\]]*\s+(?=[\"'(\[]?[A-Z0-9])", t) if len(s.split()) > 0]


def words(t):
    return re.findall(r"[A-Za-z][A-Za-z'-]*", t)


def mattr(ws, win=100):
    ws = [w.lower() for w in ws]
    if len(ws) < win:
        return len(set(ws)) / max(1, len(ws))
    vals = [len(set(ws[i:i + win])) / win for i in range(0, len(ws) - win + 1, 10)]
    return st.mean(vals)


def metrics(text):
    paras = [p for p in text.split("\n\n") if p.strip()]
    ss = sentences(text)
    ws = words(text)
    nw = max(1, len(ws))
    k = 1000 / nw
    sl = [len(words(s)) for s in ss] or [0]
    low = text.lower()
    per = lambda pat: len(re.findall(pat, text)) * k
    lper = lambda pat: len(re.findall(pat, low)) * k
    first_words = [(words(s) or [""])[0].lower() for s in ss]
    return {
        "sentence_length_mean": st.mean(sl),
        "sentence_length_sd": st.pstdev(sl),
        "short_sentence_share": sum(1 for x in sl if x < 8) / len(sl),
        "long_sentence_share": sum(1 for x in sl if x > 28) / len(sl),
        "sentences_per_paragraph": len(ss) / max(1, len(paras)),
        "words_per_paragraph": nw / max(1, len(paras)),
        "commas_per_sentence": text.count(",") / max(1, len(ss)),
        "semicolons_per_1k": per(r";"),
        "colons_per_1k": per(r":(?!//)"),
        "dashes_per_1k": per(r"—|--| – "),
        "parentheses_per_1k": per(r"\("),
        "questions_per_1k": per(r"\?"),
        "exclamations_per_1k": per(r"!"),
        "ellipses_per_1k": per(r"\.\.\.|…"),
        "quotes_per_1k": per(r"[\"“]") / 2,
        "first_singular_per_1k": lper(r"\b(i|me|my|mine|myself)\b"),
        "first_plural_per_1k": lper(r"\b(we|us|our|ours|ourselves)\b"),
        "second_person_per_1k": lper(r"\b(you|your|yours|yourself)\b"),
        "contractions_per_1k": lper(CONTRACTION),
        "hedges_per_1k": lper(HEDGES),
        "formal_connectives_per_1k": lper(FORMAL),
        "conjunction_opener_share": sum(1 for w in first_words if w in OPENERS) / max(1, len(ss)),
        "type_token_mattr": mattr(ws),
        "word_length_mean": st.mean(len(w) for w in ws) if ws else 0,
        "long_word_share": sum(1 for w in ws if len(w) >= 7) / nw,
        "ly_adverbs_per_1k": lper(r"\b\w{3,}ly\b"),
        "digits_per_1k": per(r"\b\d+\b"),
        "passive_per_1k": lper(r"\b(is|are|was|were|be|been|being)\s+\w+ed\b"),
    }


NAMES = list(metrics("A test. Another one.").keys())


def load_author(a):
    return [strip_meta(pathlib.Path(f).read_text(encoding="utf-8")) for f in sorted(glob.glob(str(FIX / a / "[0-9]*.md")))]


def chunks(texts, size):
    out = []
    for t in texts:
        cur, w = [], 0
        for p in t.split("\n\n"):
            cur.append(p)
            w += len(p.split())
            if w >= size:
                out.append("\n\n".join(cur))
                cur, w = [], 0
        if cur and w >= 0.6 * size:
            out.append("\n\n".join(cur))
    return out


def eta_squared(groups):
    allv = [v for g in groups for v in g]
    m = st.mean(allv)
    ssb = sum(len(g) * (st.mean(g) - m) ** 2 for g in groups)
    sst = sum((v - m) ** 2 for v in allv)
    return ssb / sst if sst else 0.0


def pearson(x, y):
    mx, my = st.mean(x), st.mean(y)
    num = sum((a - mx) * (b - my) for a, b in zip(x, y))
    den = math.sqrt(sum((a - mx) ** 2 for a in x) * sum((b - my) ** 2 for b in y))
    return num / den if den else 0.0


def main():
    authors = sorted(p.name for p in FIX.iterdir() if p.is_dir() and not p.name.startswith("_"))
    corp = {a: load_author(a) for a in authors}
    ch = {a: chunks(corp[a], 250) for a in authors}
    cm = {a: [metrics(c) for c in ch[a]] for a in authors}

    # 1. author vs AI rewrite of the same passage
    sep = {}
    for a in authors:
        sep[a] = {}
        for n in range(1, 6):
            o = SPK / "samples" / a / f"{n}.md"
            r = SPK / "rewrites" / a / f"{n}.md"
            if not (o.exists() and r.exists()):
                continue
            mo, mr = metrics(strip_meta(o.read_text())), metrics(strip_meta(r.read_text()))
            for k in NAMES:
                sep[a].setdefault(k, []).append((mo[k], mr[k]))
    ai_sep = {}
    for k in NAMES:
        hits = []
        for a in authors:
            pairs = sep[a][k]
            eps = 0.5 if k.endswith("_1k") else 0.02
            ro = st.mean(p[0] for p in pairs) + eps
            rr = st.mean(p[1] for p in pairs) + eps
            ratio = ro / rr
            direction = sum(1 for o, r in pairs if (o > r) == (ratio > 1) and o != r)
            hits.append((a, round(ratio, 2), direction, abs(math.log(ratio)) >= math.log(1.25) and direction >= 4))
        ai_sep[k] = hits

    # 2. between-author separation on 250-word chunks
    eta = {k: eta_squared([[m[k] for m in cm[a]] for a in authors]) for k in NAMES}

    # 3. selection
    score = {k: sum(1 for h in ai_sep[k] if h[3]) for k in NAMES}
    candidates = [k for k in NAMES if score[k] >= 3 or eta[k] >= 0.25]
    allvals = {k: [m[k] for a in authors for m in cm[a]] for k in NAMES}
    candidates.sort(key=lambda k: (score[k], eta[k]), reverse=True)
    kept, dropped_redundant = [], []
    for k in candidates:
        twin = next((j for j in kept if abs(pearson(allvals[k], allvals[j])) > 0.9), None)
        (dropped_redundant.append((k, twin)) if twin else kept.append(k))

    # 4. default thresholds from within-author spread on ~700-word chunks (draft-sized)
    big = {a: [metrics(c) for c in chunks(corp[a], 700)] for a in authors}
    defaults = {}
    for k in kept:
        ratios = []
        floor = 0.5 if k.endswith("_1k") else 0.02
        for a in authors:
            mu = st.mean(m[k] for m in big[a])
            if mu < floor:
                continue
            ratios += [m[k] / mu for m in big[a]]
        ratios.sort()
        q = lambda p: ratios[min(len(ratios) - 1, int(p * len(ratios)))]
        defaults[k] = {"overshoot": round(max(1.25, q(0.95)), 2), "shortfall": round(min(0.8, max(0.05, q(0.05))), 2),
                       "floor": floor}

    # 5. stability: split-half relative differences for corpora of n texts
    rnd = random.Random(SEED)
    stab = {}
    per_metric = {k: [] for k in kept}
    for n in (3, 5, 8, 12):
        diffs = []
        for a in authors:
            texts = corp[a]
            if len(texts) < n:
                continue
            for _ in range(20):
                sample = rnd.sample(texts, n)
                rnd.shuffle(sample)
                h1, h2 = sample[: n // 2], sample[n // 2:]
                m1, m2 = metrics("\n\n".join(h1)), metrics("\n\n".join(h2))
                for k in kept:
                    floor = 0.5 if k.endswith("_1k") else 0.02
                    base = max(floor, (m1[k] + m2[k]) / 2)
                    d = abs(m1[k] - m2[k]) / base
                    diffs.append(d)
                    if n == 8:
                        per_metric[k].append(d)
        diffs.sort()
        stab[n] = {"p50": round(diffs[len(diffs) // 2], 3), "p90": round(diffs[int(0.9 * len(diffs))], 3),
                   "p95": round(diffs[int(0.95 * len(diffs))], 3)}
    tolerance = stab[8]["p90"]
    for k in kept:
        v = sorted(per_metric[k])
        defaults[k]["stability_tolerance"] = round(v[int(0.9 * len(v))], 2)

    # 6. near-duplicate check: max 5-shingle Jaccard between distinct essays
    def sh(t):
        w = [x.lower() for x in words(t)]
        return {tuple(w[i:i + 5]) for i in range(len(w) - 4)}
    maxj = 0.0
    for a in authors:
        S = [sh(t) for t in corp[a]]
        for i in range(len(S)):
            for j in range(i + 1, len(S)):
                u = len(S[i] | S[j])
                if u:
                    maxj = max(maxj, len(S[i] & S[j]) / u)

    result = {
        "schema": "phase0-spike/1",
        "seed": SEED,
        "authors": authors,
        "global_metrics": [{"name": k, **defaults[k]} for k in kept],
        "stability_tolerance": tolerance,
        "stability_by_texts": stab,
        "near_duplicate_max_jaccard_between_distinct_essays": round(maxj, 3),
        "diagnostics": {k: {"ai_separation_authors": score[k], "eta_squared": round(eta[k], 3),
                            "per_author": ai_sep[k]} for k in NAMES},
        "dropped_redundant": dropped_redundant,
    }
    (SPK / "metrics.json").write_text(json.dumps(result, indent=2) + "\n")

    print(f"{'metric':30s} AI-sep eta2   kept")
    for k in sorted(NAMES, key=lambda k: (-score[k], -eta[k])):
        print(f"{k:30s} {score[k]:>3}/6  {eta[k]:.2f}  {'KEEP' if k in kept else ('dup of ' + dict(dropped_redundant)[k] if k in dict(dropped_redundant) else '')}")
    print("\nstability (relative split-half difference):", stab)
    print("tolerance (p90 at 8 texts):", tolerance)
    for k in kept:
        print(f"  {k:28s} {defaults[k]}")
    print("max Jaccard between distinct essays:", round(maxj, 3))


if __name__ == "__main__":
    main()
