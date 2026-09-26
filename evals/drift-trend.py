#!/usr/bin/env python3
"""Phase 4 exit, second half (design: decision log): does the profile's drift against held-out text
shrink as texts are added? For each fixture author, over 30 seeded orders of the learned essays,
measure the profile at three stages (a quarter, half, all of them) against the author's held-out
essays (evals/holdouts.json), with the drift summary of `test` (spec §19: mean |ln ratio| over metrics
at or above floor). Prints the mean per stage and whether it never rises by more than TOLERANCE.

    python3 evals/drift-trend.py [--orders 30]
"""
import argparse
import json
import math
import pathlib
import random
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "idiolect" / "scripts"))

import measure  # noqa: E402
from adapters import extract  # noqa: E402

FIX = ROOT / "evals" / "fixtures"
TOLERANCE = 0.01        # a rise this small is level: 30 orders do not resolve a smaller change


def mean_log(vals, refs):
    logs = [abs(math.log(vals[m] / refs[m])) for m in refs
            if m in vals and refs[m] >= measure.METRICS[m]["floor"] and vals[m] >= measure.METRICS[m]["floor"]]
    return sum(logs) / len(logs)


def trend(orders=30):
    hold = json.loads((ROOT / "evals" / "holdouts.json").read_text())["authors"]
    cache = {}

    def text(files):
        return "\n\n".join(cache.setdefault(f, "\n\n".join(extract(f).blocks)) for f in files)

    out = {}
    for author, held in sorted(hold.items()):
        files = sorted((FIX / author).glob("[0-9]*.md"))
        learned = [f for f in files if f.name not in held]
        hv = measure.metrics(text([f for f in files if f.name in held]))
        n = len(learned)
        stages = (max(2, n // 4), n // 2, n)
        acc = [0.0, 0.0, 0.0]
        for s in range(orders):
            order = learned[:]
            random.Random(s).shuffle(order)
            for i, k in enumerate(stages):
                acc[i] += mean_log(hv, measure.metrics(text(order[:k]))) / orders
        means = [round(x, 4) for x in acc]
        out[author] = {"texts": list(stages), "mean_drift": means,
                       "never_rises": all(b <= a + TOLERANCE for a, b in zip(means, means[1:])),
                       "falls_overall": means[-1] < means[0]}
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--orders", type=int, default=30)
    print(json.dumps(trend(ap.parse_args().orders), indent=1))
