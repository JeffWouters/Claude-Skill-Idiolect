"""status: what the active store holds (read-only, takes no lock).

    python3 status.py --store STORE [--profile P] [--json]
"""
import argparse
import collections
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import lock as lockmod  # noqa: E402
import pending  # noqa: E402
from common import StoreError, load_yaml_text, read_store_file  # noqa: E402
from store import Store  # noqa: E402


def _chain(store, profile):
    chain, seen = [], set()
    while profile and profile not in seen:
        seen.add(profile)
        chain.append(profile)
        p = store.root / "profiles" / profile / "profile.yaml"
        profile = read_store_file(p, "profile").get("extends") if p.exists() else None
    return chain


def status(store, only=None):
    texts = store.manifest["texts"]
    by_status = collections.Counter(e["status"] for e in texts.values())
    out = {"store": str(store.root), "sources_root": str(store.sources_root),
           "facets": store.facets, "default_profile": store.config["default_profile"],
           "texts": dict(by_status), "holdout": sum(1 for e in texts.values() if e.get("holdout")),
           "unreachable": sorted(e["path"] for e in texts.values()
                                 if e["status"] == "unreachable" and e.get("path")),
           "lock": lockmod.state(str(store.root)), "pending": pending.status(str(store.root)),
           "profiles": []}
    for name in store.profiles():
        if only and name != only:
            continue
        d = store.root / "profiles" / name
        prof = read_store_file(d / "profile.yaml", "profile")
        slots = []
        for f in sorted(d.glob("*.json")):
            fp = read_store_file(f, "fingerprint")
            slots.append({"slot": fp["slot"], "pooled": fp["pooled"], "texts": fp["counts"]["texts"],
                          "words": fp["counts"]["words"], "confidence": fp["confidence"]["level"]})
        rej = read_store_file(d / "rejected.yaml", "rejected")["entries"] if (d / "rejected.yaml").exists() else []
        chain = _chain(store, name)
        inherited = []
        import resolve
        foreign = {(r["profile"], r["id"]) for r in resolve.foreign_rulings(store, name)}
        for parent in chain[1:]:
            rp = store.root / "profiles" / parent / "rulings.yaml"
            if rp.exists():
                inherited += [f"{parent}:{r['id']} {r['text']}"
                              + (" [from a profile that is not the writer's own]" if (parent, r["id"]) in foreign else "")
                              for r in read_store_file(rp, "rulings")["entries"]]
        own = sum(1 for e in texts.values() if e["profiles"].get(name, {}).get("ownership") == "own"
                  and e["status"] == "active")
        out["profiles"].append({"name": name, "subject": prof["subject"], "consent": prof["consent"],
                                "extends": chain[1:], "own_active_texts": own, "slots": slots,
                                "rejections": len(rej), "inherited_rulings": inherited})
    return out


def readable(s):
    lines = [f"Store: {s['store']}", f"Sources: {s['sources_root']}",
             f"Texts: " + ", ".join(f"{v} {k}" for k, v in sorted(s["texts"].items())) + f"; {s['holdout']} holdout",
             f"Lock: {s['lock']}" + ("; a pending area is waiting: " + ", ".join(s["pending"]["choices"])
                                     if s["pending"]["pending"] else "")]
    for p in s["profiles"]:
        lines.append(f"Profile {p['name']} ({p['subject']}; consent: {p['consent']})"
                     + (f", extends {' > '.join(p['extends'])}" if p["extends"] else ""))
        for sl in p["slots"]:
            lines.append(f"  {sl['slot']}{' (pooled)' if sl['pooled'] else ''}: {sl['texts']} texts, "
                         f"{sl['words']} words, confidence {sl['confidence']}")
        if not p["slots"]:
            lines.append("  nothing learned yet")
        if p["rejections"]:
            lines.append(f"  {p['rejections']} rejected proposals")
        for r in p["inherited_rulings"]:
            lines.append(f"  inherited ruling {r}")
    if s["unreachable"]:
        lines.append("Unreachable sources: " + ", ".join(s["unreachable"]))
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--store", required=True)
    ap.add_argument("--profile")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    try:
        s = status(Store(a.store), a.profile)
    except StoreError as e:
        print(json.dumps({"status": "error", "message": str(e)}))
        return 2
    print(json.dumps(s, indent=2, ensure_ascii=False) if a.json else readable(s))
    return 0


if __name__ == "__main__":
    sys.exit(main())
