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
    """Authors already in holdouts.json keep their holdouts (their profiles were learned without them);
    a new author gets holdouts from a seed of its own, so adding or retiring an author never moves
    another author's holdouts. Retired authors drop out."""
    path = ROOT / "evals" / "holdouts.json"
    old = json.loads(path.read_text())["authors"] if path.exists() else {}
    out = {"seed": SEED,
           "how": ("authors present since phase 2 were drawn in one pass with random.Random(seed) over the "
                   "six original authors in name order; authors added later use random.Random('<seed>/<author>')"),
           "authors": {}}
    for d in sorted(p for p in FIX.iterdir() if p.is_dir()):
        if d.name in old:
            missing = [f for f in old[d.name] if not (d / f).exists()]
            if missing:
                raise SystemExit(f"{d.name}: holdout files no longer exist: {', '.join(missing)}")
            out["authors"][d.name] = old[d.name]
            continue
        files = sorted(f.name for f in d.glob("[0-9]*.md"))
        n = 5 if d.name.startswith("synthetic-") else 3
        out["authors"][d.name] = sorted(random.Random(f"{SEED}/{d.name}").sample(files, n))
    (ROOT / "evals" / "holdouts.json").write_text(json.dumps(out, indent=2) + "\n")
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
