"""Resolution (spec §12): which profile and slot a request uses, and the rulings and vocabulary merged
across the profile's inheritance chain.

    python3 resolve.py --store S [--profile P] [--lang en] [--type essay] [--facet channel=x]
"""
import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import measure  # noqa: E402
from common import StoreError, read_store_file  # noqa: E402
from store import Store  # noqa: E402


class NoSlot(StoreError):
    pass


def chain(store, profile):
    """[profile, parent, parent's parent, ...]; a cycle is refused."""
    out = []
    p = profile
    while p:
        if p in out:
            raise StoreError(f"profiles extend each other in a cycle: {' > '.join(out + [p])}")
        f = store.root / "profiles" / p / "profile.yaml"
        if not f.exists():
            if not out:
                raise StoreError(f"no profile {p}")
            raise StoreError(f"profile {out[-1]} extends {p}, which does not exist")
        out.append(p)
        p = read_store_file(f, "profile").get("extends")
    return out


def has_slot(store, profile, slot):
    return (store.root / "profiles" / profile / f"{slot}.json").exists()


def resolve(store, profile=None, facets=None):
    """(profile, slot, tried) by spec §12.4. facets: {lang, type, ...}; lang is required."""
    profile = profile or store.config["default_profile"]
    facets = dict(facets or {})
    if not facets.get("lang"):
        facets["lang"] = (store.config.get("defaults") or {}).get("lang")
    if not facets.get("lang"):
        raise NoSlot("no language given and no default language in idiolect.yaml")
    key = measure.slot_key(store.facets, {f: facets.get(f) or (store.config.get("defaults") or {}).get(f)
                                          for f in store.facets})
    tried = []
    for prof in chain(store, profile):
        for k in [key] + measure.generalisations(key):
            tried.append(f"{prof}/{k}")
            if has_slot(store, prof, k):
                return prof, k, tried
    raise NoSlot(f"no slot for {profile} {key}; tried {', '.join(tried)}")


def foreign_rulings(store, profile):
    """Rulings `profile` inherits from a profile whose consent is not `self`: not the writer's own
    profile, so they are marked in status and every diff (spec §12.6)."""
    out = []
    for prof in chain(store, profile)[1:]:
        d = store.root / "profiles" / prof
        if read_store_file(d / "profile.yaml", "profile").get("consent") == "self":
            continue
        if (d / "rulings.yaml").exists():
            out += [{"profile": prof, "id": r["id"], "text": r["text"]}
                    for r in read_store_file(d / "rulings.yaml", "rulings")["entries"]]
    return out


def merged(store, profile, field):
    """Rulings or vocabulary merged down the chain: a child's entry overrides a parent's by `overrides`
    (or by the same text for vocabulary). Returns entries with their profile."""
    fname = {"rulings": "rulings.yaml", "vocabulary": "vocabulary.yaml"}[field]
    out, overridden, texts = [], set(), set()
    for depth, prof in enumerate(chain(store, profile)):
        f = store.root / "profiles" / prof / fname
        if not f.exists():
            continue
        entries = read_store_file(f, field)["entries"]
        for e in entries:
            if depth and e["id"] in overridden:
                continue          # a child's entry replaces this one
            if field == "vocabulary" and e["text"].lower() in texts:
                continue
            out.append({**e, "profile": prof})
            texts.add(e["text"].lower())
        overridden |= {e["overrides"] for e in entries if e.get("overrides")}
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--store", required=True)
    ap.add_argument("--profile")
    ap.add_argument("--lang")
    ap.add_argument("--type")
    ap.add_argument("--facet", action="append", default=[])
    a = ap.parse_args(argv)
    facets = {"lang": a.lang, "type": a.type}
    for f in a.facet:
        k, _, v = f.partition("=")
        facets[k] = v
    try:
        store = Store(a.store)
        prof, slot, tried = resolve(store, a.profile, facets)
        out = {"profile": prof, "slot": slot, "tried": tried}
    except NoSlot as e:
        print(json.dumps({"status": "no_slot", "message": str(e)}))
        return 3
    except StoreError as e:
        print(json.dumps({"status": "error", "message": str(e)}))
        return 2
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
