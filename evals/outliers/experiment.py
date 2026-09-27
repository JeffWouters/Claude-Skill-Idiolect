"""Outlier threshold experiment (spec §28, design: decision log 2026-09-27).

For each fixture author: every text's leave-one-out distance to the median of the author's other texts
(mean |ln ratio| over the global metrics, values below a metric's floor raised to the floor). A text is
an outlier when its distance exceeds max(median + k * 1.4826 * MAD, 1.5 * median). Counts false flags
on each author's own texts, and detections when one of another author's first three texts is added.

    python3 evals/outliers/experiment.py > evals/outliers/results.txt
"""
import glob
import pathlib
import re
import statistics
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent / "idiolect" / "scripts"))
import measure  # noqa: E402
import verify  # noqa: E402

FIX = HERE.parent / "fixtures"
AUTHORS = ["synthetic-noor", "synthetic-idris", "katharine-fullerton-gerould", "robert-cortes-holliday",
           "samuel-mcchord-crothers"]


def text(f):
    return re.sub(r"^---.*?---\n", "", pathlib.Path(f).read_text(encoding="utf-8"), flags=re.S)


def main():
    vals = {a: [measure.metrics(text(f), "en") for f in sorted(glob.glob(str(FIX / a / "[0-9]*.md")))] for a in AUTHORS}
    print("k       false flags  own texts judged  detected / intruders")
    for k in (3, 3.5, 4, 5):
        fp = judged = det = tot = 0
        for a in AUTHORS:
            d = verify.loo_distances(vals[a])
            thr = verify.threshold(d, k)
            fp += sum(1 for x in d if x > thr)
            judged += len(d)
            for b in AUTHORS:
                if b == a:
                    continue
                for iv in vals[b][:3]:
                    d = verify.loo_distances(vals[a] + [iv])
                    thr = verify.threshold(d, k)
                    fp += sum(1 for x in d[:-1] if x > thr)
                    judged += len(d) - 1
                    det += d[-1] > thr
                    tot += 1
        print(f"{k:<7} {fp:<12} {judged:<17} {det} / {tot}" + ("   <- chosen" if k == verify.K else ""))
    print()
    for a in AUTHORS:
        d = verify.loo_distances(vals[a])
        print(f"{a}: {len(d)} texts, median distance {statistics.median(d):.3f}, max {max(d):.3f}, "
              f"threshold {verify.threshold(d):.3f}")


if __name__ == "__main__":
    main()
