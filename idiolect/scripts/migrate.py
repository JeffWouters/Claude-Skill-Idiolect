"""Upgrade store files to this engine's schema versions (design: Schemas and migrations).

    python3 migrate.py --store S [--dry-run]
    python3 migrate.py --store S --add-facet NAME [--dry-run]      append a facet (spec §12.7)

One version step at a time, under the lock (mode migrate). Every file it changes is copied first to
.state/migrations/<timestamp>/<same path>, so an upgrade can be undone by hand, and each affected
profile's changelog gets one entry. Prints JSON: the files upgraded (or that would be, with --dry-run).

Steps so far:
- vocabulary.yaml 1 -> 2: kind keep becomes phrase; each phrase in the live file gets its rate,
  measured on the profile's own cached texts. Copies inside snapshots/ are upgraded too, without a
  rate (it would describe today's corpus, not the snapshot's), so a rollback never restores a file
  this engine cannot read.
- rulings.yaml 1 -> 2: only the version changes; version 2 adds optional tests (spec §27). Snapshots
  too.
- corpus/manifest.json and snapshots' manifest-entries.json 1 -> 2: only the version changes; version
  2 lets a web text keep its address (url, spec §36.7). Texts added before it have none: they are
  forgotten by key or path, or their address is added by hand.
"""
import argparse
import json
import pathlib
import re
import shutil
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import lock  # noqa: E402
import measure  # noqa: E402
import pages  # noqa: E402
from common import StoreError, atomic_write, check_schema, dump_yaml, iso, load_yaml_text, utcnow, version_of  # noqa: E402
from store import Store  # noqa: E402


def check_vocabulary_1(data, where):
    """The version 1 schema is gone from assets/, so a version 1 file is checked by hand before it is
    upgraded (spec §1.3: validate before use)."""
    ok = isinstance(data, dict) and isinstance(data.get("entries"), list) and all(
        isinstance(e, dict) and isinstance(e.get("id"), str) and isinstance(e.get("text"), str)
        and e.get("kind") in ("term", "spelling", "coinage", "keep") for e in data["entries"])
    if not ok:
        raise StoreError(f"{where} is not a valid version 1 vocabulary file; nothing was upgraded")


def check_rulings_1(data, where):
    ok = isinstance(data, dict) and isinstance(data.get("entries"), list) and all(
        isinstance(e, dict) and isinstance(e.get("id"), str) and isinstance(e.get("text"), str)
        for e in data["entries"])
    if not ok:
        raise StoreError(f"{where} is not a valid version 1 rulings file; nothing was upgraded")


def check_manifest_1(data, where):
    ok = isinstance(data, dict) and isinstance(data.get("texts"), dict) and all(
        isinstance(e, dict) and isinstance(e.get("profiles"), dict) for e in data["texts"].values())
    if not ok:
        raise StoreError(f"{where} is not a valid version 1 ledger file; nothing was upgraded")


CHECK_1 = {"vocabulary": check_vocabulary_1, "rulings": check_rulings_1, "manifest": check_manifest_1,
           "manifest-entries": check_manifest_1}


def rulings_1_to_2(data, own_texts=None, today=None):
    return {**data, "schema_version": 2}


def vocabulary_1_to_2(data, own_texts=None, today=None):
    """Version 1 -> 2. own_texts=None, or no text to measure on, leaves phrases without a rate."""
    out = {**data, "schema_version": 2, "entries": []}
    for e in data.get("entries", []):
        e = dict(e)
        if e.get("kind") == "keep":
            e["kind"] = "phrase"
        if e["kind"] == "phrase" and own_texts is not None:
            rate = measure.phrase_rate(e["text"], own_texts, today)
            if rate:
                e["rate"] = rate
        out["entries"].append(e)
    return out


def manifest_1_to_2(data, own_texts=None, today=None):
    return {**data, "schema_version": 2}


STEPS = {"vocabulary": {1: vocabulary_1_to_2}, "rulings": {1: rulings_1_to_2}}
JSON_STEPS = {"manifest": {1: manifest_1_to_2}, "manifest-entries": {1: manifest_1_to_2}}


def _load(f):
    text = f.read_text(encoding="utf-8")
    return json.loads(text) if f.suffix == ".json" else (load_yaml_text(text) or {})


def _dump(f, data):
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n" if f.suffix == ".json" else dump_yaml(data)


def _upgrade(schema, data, v, texts=None, today=None):
    steps = {**STEPS, **JSON_STEPS}[schema]
    while v < version_of(schema):
        data = steps[v](data, texts, today)
        v += 1
    return data


def upgraded_manifest(path):
    """The ledger as it will be after the upgrade, validated; for reading an older store before
    migrating it (store.Store(migrating=True))."""
    data = _load(path)
    v = data.get("schema_version", 1) if isinstance(data, dict) else 1
    if v < version_of("manifest"):
        CHECK_1["manifest"](data, str(path))
        data = _upgrade("manifest", data, v)
    return check_schema("manifest", data, str(path))


def plan(store):
    """[(path, schema, from_version, profile, is_snapshot)] for every file older than this engine."""
    todo = []
    mp = store.root / "corpus" / "manifest.json"
    if mp.exists() and _load(mp).get("schema_version", 1) < version_of("manifest"):
        todo.append((mp, "manifest", _load(mp).get("schema_version", 1), None, False))
    root = store.root / "profiles"
    if not root.exists():
        return todo
    for prof_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        for schema in STEPS:
            for f in sorted(prof_dir.rglob(f"{schema}.yaml")):
                data = load_yaml_text(f.read_text(encoding="utf-8")) or {}
                v = data.get("schema_version", 1)
                if v < version_of(schema):
                    todo.append((f, schema, v, prof_dir.name, "snapshots" in f.relative_to(prof_dir).parts))
        for f in sorted(prof_dir.glob("snapshots/*/manifest-entries.json")):
            v = _load(f).get("schema_version", 1)
            if v < version_of("manifest-entries"):
                todo.append((f, "manifest-entries", v, prof_dir.name, True))
    return todo


def migrate(store_root, dry_run=False, now=None):
    store = Store(store_root, migrating=True)
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
        # 1. convert and validate everything in memory; nothing is written if any file fails (review M4)
        own, converted, touched = {}, [], {}
        for f, schema, v, prof, is_snap in todo:
            data = _load(f)
            if v == 1:
                CHECK_1[schema](data, str(f))
            texts = None
            if not is_snap and schema == "vocabulary":
                if prof not in own:
                    own[prof] = measure.own_texts(store.manifest["texts"], store.corpus_text, store.facets, prof)
                texts = own[prof]
            data = _upgrade(schema, data, v, texts, today)
            check_schema(schema, data, str(f))
            converted.append((f, data))
            touched.setdefault(prof, []).append(f"{schema} {data['schema_version']}")
        # 2. back up every original, then write; a re-run after a crash here finds what is left
        for f, _ in converted:
            dest = backup / f.relative_to(store.root)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, dest)
        for f, data in converted:
            atomic_write(f, _dump(f, data))
        for prof, what in touched.items():
            if prof is None:                  # the store's own ledger: no profile changelog
                continue
            cl = store.root / "profiles" / prof / "changelog.md"
            existing = cl.read_text(encoding="utf-8") if cl.exists() else ""
            atomic_write(cl, pages.changelog_append(
                existing, prof, iso(now), "migrate", stamp, [],
                f"format upgrade: {', '.join(sorted(set(what)))}; originals in .state/migrations/{stamp}/", None))
        return {"upgraded": rel, "backup": str(backup.relative_to(store.root))}
    finally:
        lock.release(str(store.root))


# ---------- adding a facet (spec §12.7) ----------

FACET_NAME = re.compile(r"^[a-z][a-z0-9_]{0,29}$")
SLOT_SUFFIXES = (".examples.md", ".never.md", ".edits.md", ".md", ".json")
SLOT_LINE = re.compile(r"(?m)^slot: (\S+)$")


def _slot_of(name):
    """(slot, suffix) for a slot file name such as en.essay.examples.md, else None."""
    for suf in SLOT_SUFFIXES:
        if name.endswith(suf):
            slot = name[: -len(suf)]
            if re.match(r"^[a-z]{2,3}(-[a-z0-9]{2,8})?(\.(_|[a-z0-9][a-z0-9-]{0,39}))+$", slot):
                return slot, suf
    return None


def _profile_dir_changes(d, add, name, is_snapshot):
    """{path: new text or None (removed)} for one profile folder or one snapshot of it."""
    out = {}
    for f in sorted(d.iterdir()):
        if f.is_dir():
            continue
        if f.name in ("rulings.yaml", "rejected.yaml"):
            data = load_yaml_text(f.read_text(encoding="utf-8")) or {}
            for e in data.get("entries", []):
                if e.get("slot"):
                    e["slot"] = add(e["slot"])
            out[f] = dump_yaml(data)
            continue
        if f.name == "manifest-entries.json" and is_snapshot:
            data = json.loads(f.read_text(encoding="utf-8"))
            for e in data.get("texts", {}).values():
                e["facets"][name] = "_"
            out[f] = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
            continue
        hit = _slot_of(f.name)
        if not hit or f.name == "changelog.md":
            continue
        slot, suf = hit
        text = f.read_text(encoding="utf-8")
        if suf == ".json":
            data = json.loads(text)
            data["slot"] = add(data["slot"])
            new = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
        else:
            new = SLOT_LINE.sub(lambda m: "slot: " + add(m.group(1)), text, count=1)
        out[f] = None
        out[f.with_name(add(slot) + suf)] = new
    for pf in sorted(d.glob("edits/p-*/pair.yaml")):
        data = load_yaml_text(pf.read_text(encoding="utf-8")) or {}
        data["slot"] = add(data["slot"])
        out[pf] = dump_yaml(data)
    return out


def add_facet(store_root, name, dry_run=False, now=None):
    store = Store(store_root)
    if not FACET_NAME.match(name or ""):
        raise StoreError(f"a facet name is lower case letters, digits and _: {name!r}")
    if name in store.facets:
        raise StoreError(f"{name} is already a facet")
    add = lambda slot: slot + "._"  # noqa: E731
    changes = {}
    cfg = dict(store.config)
    cfg["facets"] = list(store.facets) + [name]
    check_schema("idiolect", cfg, "idiolect.yaml")
    changes[store.root / "idiolect.yaml"] = dump_yaml(cfg)
    mp = store.root / "corpus" / "manifest.json"
    if mp.exists():
        man = json.loads(mp.read_text(encoding="utf-8"))
        for e in man["texts"].values():
            e["facets"][name] = "_"
        check_schema("manifest", man, "manifest")
        changes[mp] = json.dumps(man, indent=2, ensure_ascii=False) + "\n"
    root = store.root / "profiles"
    dirs = []
    for pd in sorted(p for p in root.iterdir() if p.is_dir()) if root.exists() else []:
        dirs.append((pd, False))
        dirs += [(sd, True) for sd in sorted((pd / "snapshots").iterdir()) if sd.is_dir()] if (pd / "snapshots").exists() else []
    for d, snap in dirs:
        changes.update(_profile_dir_changes(d, add, name, snap))
    rel = sorted(str(f.relative_to(store.root)) for f in changes)
    if dry_run:
        return {"facet": name, "would_change": rel}
    now = now or utcnow()
    stamp = iso(now).replace(":", "").replace("-", "")
    got = lock.acquire(str(store.root), "migrate")
    try:
        if got["pending"]:
            raise StoreError("a run is waiting in .state/pending/; resume or discard it before migrating")
        backup = store.root / ".state" / "migrations" / stamp
        for f in changes:
            if f.exists():
                dest = backup / f.relative_to(store.root)
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(f, dest)
        for f, content in changes.items():          # new files first, then the old names go
            if content is not None:
                atomic_write(f, content)
        for f, content in changes.items():
            if content is None and f.exists():
                f.unlink()
        for pd, snap in dirs:
            if snap:
                continue
            cl = pd / "changelog.md"
            existing = cl.read_text(encoding="utf-8") if cl.exists() else ""
            atomic_write(cl, pages.changelog_append(
                existing, pd.name, iso(now), "migrate", stamp, [],
                f"new facet {name}: every slot key gains ._ (snapshots too); originals in .state/migrations/{stamp}/", None))
        return {"facet": name, "changed": rel, "backup": str(backup.relative_to(store.root))}
    finally:
        lock.release(str(store.root))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--store", required=True)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--add-facet")
    a = ap.parse_args(argv)
    try:
        out = add_facet(a.store, a.add_facet, a.dry_run) if a.add_facet else migrate(a.store, a.dry_run)
    except StoreError as e:
        print(json.dumps({"status": "error", "message": str(e)}))
        return 2
    print(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
