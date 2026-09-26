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
        # capped at 1.5: the relative difference cannot exceed 2.0, so a tolerance of 2.0 never fires
        defaults[k]["stability_tolerance"] = min(1.5, round(v[int(0.9 * len(v))], 2))

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

    # 7. check simulation (spec §17): how many metrics flag a genuine passage vs an AI rewrite.
    #    Leave-one-out: the fingerprint never contains the essay the passage comes from.
    #    Genuine passages are cut to the rewrites' length range (matched-length comparison).
    def n_flags(m, ref):
        n = 0
        for k in kept:
            d = defaults[k]
            w = ref[k]
            if w < d["floor"]:
                n += (m[k] - w) > 2 * d["floor"]
                continue
            r = m[k] / w
            sparse = d["shortfall"] <= 0.05
            n += r > d["overshoot"] or (not sparse and r < d["shortfall"])
        return n

    files = {a: sorted(glob.glob(str(FIX / a / "[0-9]*.md"))) for a in authors}
    genuine = {a: [] for a in authors}
    ai = {a: [] for a in authors}
    for a in authors:
        texts = corp[a]
        for i, t in enumerate(texts):
            ref = metrics("\n\n".join(texts[:i] + texts[i + 1:]))
            genuine[a] += [n_flags(metrics(c), ref) for c in chunks([t], 350)]
        for n in range(1, 6):
            s = SPK / "samples" / a / f"{n}.md"
            r = SPK / "rewrites" / a / f"{n}.md"
            if not (s.exists() and r.exists()):
                continue
            src = re.search(r"source: (\S+)", s.read_text()).group(1)
            src_i = next(i for i, f in enumerate(files[a]) if f.endswith(src.split("fixtures/")[-1]))
            ref = metrics("\n\n".join(texts[:src_i] + texts[src_i + 1:]))
            ai[a].append(n_flags(metrics(strip_meta(r.read_text())), ref))
    groups = {"all": authors, "real": [a for a in authors if not a.startswith("synthetic")],
              "synthetic": [a for a in authors if a.startswith("synthetic")]}
    check_table = {}
    for g, members in groups.items():
        gen = [x for a in members for x in genuine[a]]
        aiv = [x for a in members for x in ai[a]]
        check_table[g] = {"genuine_n": len(gen), "ai_n": len(aiv),
                          "genuine_with_any_flag": round(sum(x >= 1 for x in gen) / len(gen), 3),
                          "by_threshold": {K: {"genuine_fail": round(sum(x >= K for x in gen) / len(gen), 3),
                                               "ai_fail": round(sum(x >= K for x in aiv) / len(aiv), 3)}
                                           for K in range(2, 9)}}

    # 8. stability rule calibration (spec §13): a metric is unstable in a split when its relative
    #    difference exceeds its tolerance; it counts when unstable in >= 2 of 5 splits; the slot is
    #    downgraded when >= m metrics count. Rates on genuine single-author corpora.
    def downgraded(texts, m_needed, rnd_):
        unstable = {k: 0 for k in kept}
        for _ in range(5):
            s_ = rnd_.sample(texts, len(texts))
            h1, h2 = s_[: len(s_) // 2], s_[len(s_) // 2:]
            m1, m2 = metrics("\n\n".join(h1)), metrics("\n\n".join(h2))
            for k in kept:
                f = defaults[k]["floor"]
                if abs(m1[k] - m2[k]) / max(f, (m1[k] + m2[k]) / 2) > defaults[k]["stability_tolerance"]:
                    unstable[k] += 1
        return sum(1 for v in unstable.values() if v >= 2) >= m_needed

    stab_rule = {}
    for m_needed in (1, 2, 3, 4):
        row = {}
        for n in (3, 5, 8, 12):
            rnd2 = random.Random(SEED + n)
            hits = total = 0
            for a in authors:
                if len(corp[a]) < n:
                    continue
                for _ in range(10):
                    hits += downgraded(rnd2.sample(corp[a], n), m_needed, rnd2)
                    total += 1
            row[n] = round(hits / total, 2)
        stab_rule[m_needed] = row

    # 8b. the same rule on mixed corpora (half one author, half another): does split-half
    #     stability notice a corpus that mixes two voices?
    mixed_rule = {}
    for m_needed in (1, 2, 3, 4):
        row = {}
        for n in (4, 8, 12):
            rnd3 = random.Random(SEED + 100 + n)
            hits = total = 0
            for i, a in enumerate(authors):
                for b in authors[i + 1:]:
                    if len(corp[a]) < n // 2 or len(corp[b]) < n // 2:
                        continue
                    for _ in range(3):
                        mix = rnd3.sample(corp[a], n // 2) + rnd3.sample(corp[b], n // 2)
                        hits += downgraded(mix, m_needed, rnd3)
                        total += 1
            row[n] = round(hits / total, 2)
        mixed_rule[m_needed] = row

    result = {
        "schema": "phase0-spike/2",
        "check_simulation": check_table,
        "check_flags_per_author": {"genuine_mean": {a: round(st.mean(genuine[a]), 2) for a in authors},
                                   "ai": ai},
        "stability_rule_downgrade_rate": stab_rule,
        "stability_rule_downgrade_rate_mixed_corpora": mixed_rule,
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
    print("\ncheck simulation (matched length, leave-one-out):")
    for g, t in check_table.items():
        print(f"  {g}: genuine n={t['genuine_n']}, AI n={t['ai_n']}, genuine with any flag {t['genuine_with_any_flag']}")
        for K, v in t["by_threshold"].items():
            print(f"    fail if >= {K}: genuine {v['genuine_fail']:.2f}  AI {v['ai_fail']:.2f}")
    print("\nstability rule: downgrade rate by metrics needed (rows) and corpus size (columns)")
    for m_needed, row in stab_rule.items():
        print(f"  m >= {m_needed}: {row}")
    print("same rule on mixed two-author corpora:")
    for m_needed, row in mixed_rule.items():
        print(f"  m >= {m_needed}: {row}")


if __name__ == "__main__":
    main()
