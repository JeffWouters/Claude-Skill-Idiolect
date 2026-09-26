"""Upgrade store files to this engine's schema versions (design: Schemas and migrations).

    python3 migrate.py --store S [--dry-run]

One version step at a time, under the lock (mode migrate). Every file it changes is copied first to
.state/migrations/<timestamp>/<same path>, so an upgrade can be undone by hand, and each affected
profile's changelog gets one entry. Prints JSON: the files upgraded (or that would be, with --dry-run).

Steps so far:
- vocabulary.yaml 1 -> 2: kind keep becomes phrase; each phrase in the live file gets its rate,
  measured on the profile's own cached texts. Copies inside snapshots/ are upgraded too, without a
  rate (it would describe today's corpus, not the snapshot's), so a rollback never restores a file
  this engine cannot read.
"""
import argparse
import json
import pathlib
import shutil
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import lock  # noqa: E402
import measure  # noqa: E402
import pages  # noqa: E402
from common import StoreError, atomic_write, check_schema, dump_yaml, iso, load_yaml_text, utcnow, version_of  # noqa: E402
from store import Store  # noqa: E402


def vocabulary_1_to_2(data, own_texts=None, today=None):
    """Version 1 -> 2. own_texts=None leaves phrases without a rate."""
    out = {**data, "schema_version": 2, "entries": []}
    for e in data.get("entries", []):
        e = dict(e)
        if e.get("kind") == "keep":
            e["kind"] = "phrase"
        if e["kind"] == "phrase" and own_texts is not None:
            e["rate"] = measure.phrase_rate(e["text"], own_texts, today)
        out["entries"].append(e)
    return out


STEPS = {"vocabulary": {1: vocabulary_1_to_2}}


def plan(store):
    """[(path, schema, from_version, profile, is_snapshot)] for every file older than this engine."""
    todo = []
    root = store.root / "profiles"
    if not root.exists():
        return todo
    for prof_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        for f in sorted(prof_dir.rglob("vocabulary.yaml")):
            data = load_yaml_text(f.read_text(encoding="utf-8")) or {}
            v = data.get("schema_version", 1)
            if v < version_of("vocabulary"):
                todo.append((f, "vocabulary", v, prof_dir.name, "snapshots" in f.relative_to(prof_dir).parts))
    return todo


def migrate(store_root, dry_run=False, now=None):
    store = Store(store_root)
    todo = plan(store)
    rel = [str(f.relative_to(store.root)) for f, *_ in todo]
    if dry_run or not todo:
        return {"upgraded": [], "would_upgrade": rel} if dry_run else {"upgraded": []}
    now = now or utcnow()
    stamp = iso(now).replace(":", "").replace("-", "")
    got = lock.acquire(str(store.root), "migrate")
    try:
        if got["pending"]:
            raise StoreError("a run is waiting in .state/pending/; resume or discard it before migrating")
        backup = store.root / ".state" / "migrations" / stamp
        today = now.date().isoformat()
        own = {}
        touched = {}
        for f, schema, v, prof, is_snap in todo:
            dest = backup / f.relative_to(store.root)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, dest)
            data = load_yaml_text(f.read_text(encoding="utf-8"))
            texts = None
            if not is_snap:
                if prof not in own:
                    own[prof] = measure.own_texts(store.manifest["texts"], store.corpus_text, store.facets, prof)
                texts = own[prof]
            while v < version_of(schema):
                data = STEPS[schema][v](data, texts, today)
                v += 1
            check_schema(schema, data, str(f))
            atomic_write(f, dump_yaml(data))
            touched.setdefault(prof, []).append(f"{schema} {data['schema_version']}")
        for prof, what in touched.items():
            cl = store.root / "profiles" / prof / "changelog.md"
            existing = cl.read_text(encoding="utf-8") if cl.exists() else ""
            atomic_write(cl, pages.changelog_append(
                existing, prof, iso(now), "migrate", stamp, [],
                f"format upgrade: {', '.join(sorted(set(what)))}; originals in .state/migrations/{stamp}/", None))
        return {"upgraded": rel, "backup": str(backup.relative_to(store.root))}
    finally:
        lock.release(str(store.root))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--store", required=True)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    try:
        out = migrate(a.store, a.dry_run)
    except StoreError as e:
        print(json.dumps({"status": "error", "message": str(e)}))
        return 2
    print(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
