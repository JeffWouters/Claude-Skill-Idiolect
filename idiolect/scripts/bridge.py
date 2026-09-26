"""File-bridge helpers (spec §26.2): used only when the writer's computer is reachable through a file
bridge without a usable shell. With a shell, the scripts run on the computer and none of this is needed.

    python3 bridge.py plan --store S --listing L [--batch 50]     which source files to copy, in batches
    python3 bridge.py snapshot --store S --out B.json             store file hashes before a run
    python3 bridge.py changed --store S --before B.json [--batch 50]   store files to write back / delete
    python3 bridge.py record --store S --listing L                remember what was copied

A listing is JSON {"root": "<the sources root as the bridge names it>", "entries": [{"name": "a/b.md",
"type": "file", "size": 123, "mtimeMs": 1700000000000}, ...]}: a recursive directory listing of the
sources root, names relative to it.
"""
import argparse
import hashlib
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from adapters import HANDLED  # noqa: E402
from common import StoreError, check_schema, iso, read_store_file, utcnow, write_json  # noqa: E402
from store import Store  # noqa: E402

BATCH = 50
SKIP_PARTS = {"node_modules", "_to_delete"}


def _learnable(name):
    parts = pathlib.PurePosixPath(name).parts
    if any(p.startswith(".") or p in SKIP_PARTS for p in parts):
        return False
    low = name.lower()
    return any(low.endswith(ext) for ext in HANDLED)


def _known(store):
    f = store.root / ".state" / "bridge.json"
    return read_store_file(f, "bridge")["files"] if f.exists() else {}


def _batches(items, size):
    return [items[i:i + size] for i in range(0, len(items), size)]


def plan(store, listing, batch=BATCH):
    known = _known(store)
    root = listing["root"].rstrip("/")
    todo, same = [], 0
    for e in listing["entries"]:
        if e.get("type") != "file" or not _learnable(e["name"]):
            continue
        k = known.get(e["name"])
        if k and k["size"] == e.get("size") and abs(k["mtime"] - e.get("mtimeMs", 0)) < 1:
            same += 1
            continue
        todo.append(f"{root}/{e['name']}")
    return {"to_copy": len(todo), "unchanged": same, "batches": _batches(sorted(todo), batch)}


def snapshot(store):
    """{store-relative path: sha256} of every store file outside .state/ (run state never goes back)."""
    out = {}
    for f in sorted(store.root.rglob("*")):
        rel = f.relative_to(store.root)
        if f.is_file() and rel.parts[0] != ".state":
            out["/".join(rel.parts)] = hashlib.sha256(f.read_bytes()).hexdigest()
    return out


def changed(store, before, batch=BATCH):
    now = snapshot(store)
    write = sorted(p for p, h in now.items() if before.get(p) != h)
    delete = sorted(p for p in before if p not in now)
    return {"write": len(write), "delete": len(delete), "write_batches": _batches(write, batch),
            "delete_batches": _batches(delete, batch),
            "note": "deleting on the computer needs the writer's permission" if delete else ""}


def record(store, listing):
    known = _known(store)
    for e in listing["entries"]:
        if e.get("type") == "file" and _learnable(e["name"]):
            known[e["name"]] = {"size": int(e.get("size", 0)), "mtime": float(e.get("mtimeMs", 0))}
    data = {"schema_version": 1, "updated": iso(utcnow()), "files": dict(sorted(known.items()))}
    check_schema("bridge", data, ".state/bridge.json")
    write_json(store.root / ".state" / "bridge.json", data, "bridge")
    return {"recorded": len(known)}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("action", choices=["plan", "snapshot", "changed", "record"])
    ap.add_argument("--store", required=True)
    ap.add_argument("--listing")
    ap.add_argument("--before")
    ap.add_argument("--out")
    ap.add_argument("--batch", type=int, default=BATCH)
    a = ap.parse_args(argv)
    try:
        s = Store(a.store)
        if a.action == "plan":
            out = plan(s, json.loads(pathlib.Path(a.listing).read_text(encoding="utf-8")), a.batch)
        elif a.action == "snapshot":
            pathlib.Path(a.out).write_text(json.dumps(snapshot(s), indent=1) + "\n", encoding="utf-8")
            out = {"snapshot": a.out}
        elif a.action == "changed":
            out = changed(s, json.loads(pathlib.Path(a.before).read_text(encoding="utf-8")), a.batch)
        else:
            out = record(s, json.loads(pathlib.Path(a.listing).read_text(encoding="utf-8")))
    except (StoreError, OSError, ValueError) as e:
        print(json.dumps({"status": "error", "message": str(e)}))
        return 1
    print(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
