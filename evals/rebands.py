#!/usr/bin/env python3
"""Rebuild the writer bands of the evaluation store's fingerprints after the decision to calibrate the
check per writer (design: decision log, after runs 5 and 6). Re-measures every slot exactly as
`learn.py measure` would and copies only the bands (overshoot, shortfall) into the stored fingerprint;
it stops if any metric value would change, since that would be a relearn, not a band rebuild.

    python3 evals/rebands.py [--dry-run]
"""
import argparse
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "idiolect" / "scripts"))

import measure  # noqa: E402
from common import read_store_file  # noqa: E402
from store import Store  # noqa: E402

STORE = ROOT / "evals" / "store"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    s = Store(STORE)
    changed = {}
    for pdir in sorted((STORE / "profiles").iterdir()):
        if not pdir.is_dir():
            continue
        prof = pdir.name
        keep = {}
        for f in pdir.glob("*.json"):
            keep[read_store_file(f, "fingerprint")["slot"]] = f
        py = pdir / "profile.yaml"
        since = read_store_file(py, "profile").get("since") if py.exists() else None
        for x in measure.fingerprints_view(s.manifest["texts"], s.corpus_text, s.facets, prof, since=since):
            new = x["fingerprint"]
            f = keep.get(new["slot"])
            if not f:
                continue
            old = json.loads(f.read_text(encoding="utf-8"))
            for m, v in old["metrics"].items():
                if abs(new["metrics"][m]["value"] - v["value"]) > 1e-6:
                    sys.exit(f"{prof}/{new['slot']}: {m} would change value; relearn instead")
            diff = []
            for m, v in old["metrics"].items():
                nb = (new["metrics"][m]["overshoot"], new["metrics"][m]["shortfall"])
                if nb != (v["overshoot"], v["shortfall"]):
                    diff.append(f"{m} {v['overshoot']}/{v['shortfall']} -> {nb[0]}/{nb[1]}")
                    v["overshoot"], v["shortfall"] = nb
            if diff:
                changed[f"{prof}/{new['slot']}"] = diff
                if not a.dry_run:
                    f.write_text(json.dumps(old, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(changed, indent=1))


if __name__ == "__main__":
    main()
