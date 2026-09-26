#!/usr/bin/env python3
"""Choose the evaluation holdout essays per fixture author (evals/eval-protocol.md: 5 of 12 for synthetic
authors, 3 for public-domain authors) with a fixed seed, and write evals/holdouts.json.

    python3 tools/select_holdouts.py
"""
import json
import pathlib
import random

ROOT = pathlib.Path(__file__).resolve().parent.parent
FIX = ROOT / "evals" / "fixtures"
SEED = 20261003


def main():
    rng = random.Random(SEED)
    out = {"seed": SEED, "authors": {}}
    for d in sorted(p for p in FIX.iterdir() if p.is_dir()):
        files = sorted(f.name for f in d.glob("[0-9]*.md"))
        n = 5 if d.name.startswith("synthetic-") else 3
        out["authors"][d.name] = sorted(rng.sample(files, n))
    (ROOT / "evals" / "holdouts.json").write_text(json.dumps(out, indent=2) + "\n")
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
