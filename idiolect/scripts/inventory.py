"""Inventory: walk the scope, extract, hash and classify every text (spec §5). Learning step 1 and the
whole of `learn dry-run=true`.

    python3 inventory.py --store STORE --dry-run [--target REL ...] [--tag TAG ...] [--lang L] [--type T] [--json]
    python3 inventory.py --sources FOLDER --dry-run [--json]          (no store yet, spec §3.4)

Prints the inventory report (inventory-report.schema.json) as JSON with --json, otherwise a short
readable summary. A dry run never writes anything and never takes the lock.
"""
import argparse
import collections
import datetime as dt
import json
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from adapters import extract as adapter_extract  # noqa: E402
from common import StoreError, case_insensitive, check_schema, content_hash, rel, words  # noqa: E402
import detect  # noqa: E402
from store import MARKER, Store, globally_excluded, path_rules, resolve_facets, rule_facets, under  # noqa: E402

MIN_WORDS = 150
NEAR_DUP = 0.90
SKIP_DIRS = {"node_modules", "_to_delete"}


# ---------- walking (row 1) ----------

def walk(scope_roots, sources_root, store_root, not_listed):
    files = []
    for root in scope_roots:
        root = pathlib.Path(root)
        if root.is_file():
            files.append(root)
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            dp = pathlib.Path(dirpath)
            keep = []
            for d in sorted(dirnames):
                full = dp / d
                why = None
                if store_root and full.resolve() == store_root:
                    why = "the store itself"
                elif d.startswith("."):
                    why = "hidden folder"
                elif d in SKIP_DIRS:
                    why = d
                elif (full / MARKER).exists():
                    why = "another store"
                if why:
                    not_listed.append(f"{rel(full, sources_root)}/ ({why})")
                else:
                    keep.append(d)
            dirnames[:] = keep
            for f in sorted(filenames):
                if f.startswith(".") or f.endswith(".tmp"):
                    continue
                files.append(dp / f)
    seen, out = set(), []
    for f in files:
        k = f.resolve()
        if k not in seen:
            seen.add(k)
            out.append(f)
    return out


def shingles(text):
    w = [x.lower() for x in words(text)]
    return {tuple(w[i:i + 5]) for i in range(len(w) - 4)}


def jaccard(a, b):
    u = len(a | b)
    return len(a & b) / u if u else 0.0


def _doc_date(extract, path):
    if extract.date:
        s = str(extract.date).strip()
        try:
            d = dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
            return d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)
        except ValueError:
            try:
                return dt.datetime.combine(dt.date.fromisoformat(s[:10]), dt.time(), dt.timezone.utc)
            except ValueError:
                pass
    return dt.datetime.fromtimestamp(os.path.getmtime(path), dt.timezone.utc)


# ---------- the inventory ----------

def inventory(store=None, sources_root=None, targets=None, tags=None, command=None, dry_run=True,
              command_line=None):
    command = {k: v for k, v in (command or {}).items() if v}
    if store:
        sources_root = store.sources_root
        store_root = store.root
        facets = store.facets
        manifest = store.manifest["texts"]
        defaults = store.config.get("defaults") or {}
    else:
        sources_root = pathlib.Path(sources_root).resolve()
        store_root, facets, manifest, defaults = None, ["lang", "type"], {}, {}
    ci = case_insensitive(sources_root)
    norm = (lambda p: p.lower()) if ci else (lambda p: p)
    notes, not_listed = [], []

    # scope
    if targets or tags:
        scope_rel = [t.strip("/") or "." for t in (targets or [])]
        scope_desc = "targets: " + ", ".join(list(targets or []) + [f"#{t}" for t in tags or []])
        roots = [sources_root / t for t in scope_rel]
        if tags:
            roots.append(sources_root)
    elif store:
        scope_rel = sorted({r["path"] for r in store.sources["sources"] if "path" in r})
        flat = {r["path"] for r in store.sources["sources"] if "path" in r and r.get("recursive", True) is False}
        # a folder registered only with recursive: false covers its own files, not its subfolders
        scope_rel = [p for p in scope_rel if p not in flat or any(
            r.get("path") == p and r.get("recursive", True) for r in store.sources["sources"])]
        scope_flat = sorted(flat - set(scope_rel))
        scope_desc = "all registered sources"
        roots = [sources_root / p for p in scope_rel + scope_flat]
        if any("tag" in r for r in store.sources["sources"]):
            roots.append(sources_root)
    else:
        scope_rel, scope_desc, roots = ["."], "the whole folder (no store)", [sources_root]

    scope_flat = locals().get("scope_flat", [])

    def in_scope(relpath):
        if any(under(s, relpath, ci) for s in scope_rel):
            return True
        parent = relpath.rsplit("/", 1)[0] if "/" in relpath else "."
        return any((parent.lower() == f.rstrip("/").lower()) if ci else parent == f.rstrip("/") for f in scope_flat)

    rows, texts_found, candidates = [], set(), []
    paths_by_entry = collections.defaultdict(list)
    for key, e in manifest.items():
        if e.get("path"):
            paths_by_entry[norm(e["path"])].append((key, e))

    for f in walk(roots, sources_root, store_root, not_listed):
        relpath = rel(f, sources_root)
        if store and (globally_excluded(store, relpath, ci)
                      or _rule_excluded(store, relpath, ci)):
            not_listed.append(f"{relpath} (excluded glob)")
            continue
        ex = adapter_extract(f)
        if ex is None:
            if tags and not in_scope(relpath):
                continue
            row = {"path": relpath, "key": None, "result": "skipped: not prose",
                   "words": None, "lang": None, "type": None}
            if f.suffix.lower() == ".msg":
                row["note"] = "needs the optional extract-msg package (pip install extract-msg)"
            rows.append(row)
            continue
        ftags = ex.meta.get("tags") or []
        ftags = [ftags] if isinstance(ftags, str) else [str(t).lstrip("#") for t in ftags]
        if not in_scope(relpath) and not (set(ftags) & set(tags or [])) and not (
                store and not (targets or tags) and _tag_rule_match(store, ftags)):
            continue
        front = {k: ex.meta[k] for k in ("lang", "type") if k in ex.meta}
        rule = rule_facets(store, relpath, ftags, ci) if store else {}
        whole_key = content_hash(ex.text)
        main_entry = manifest.get(whole_key, {})
        set_lang = next((s["lang"] for s in (command, main_entry.get("facets", {}), rule, front)
                         if s and s.get("lang")), None)
        parts = detect.split(ex.blocks, set_lang=set_lang)
        for t in parts:
            entry = manifest.get(t.key)
            texts_found.add(t.key)
            is_seg = "#" in t.key
            ef = (entry or {}).get("facets", {})
            if is_seg:
                fac = resolve_facets([x for x in facets if x != "lang"], command, ef, rule, front, None,
                                     defaults, unknown="?")
                fac["lang"] = ef.get("lang") or t.lang
            else:
                fac = resolve_facets(facets, command, ef, rule, front, {"lang": t.lang}, defaults,
                                     unknown="?")
            row = {"path": relpath, "key": t.key, "result": None, "words": t.words,
                   "lang": fac["lang"] if fac["lang"] != "?" else None, "type": fac["type"]}
            if row["lang"] in detect.UNSUPPORTED:
                row.update(result="skipped: language not supported", words=None)
                rows.append(row)
                continue
            if entry:
                _classify_known(row, entry, relpath, sources_root, norm)
                if row.pop("_supersedes_current", False):
                    row["_supersedes"] = [k for k, e in paths_by_entry.get(norm(relpath), [])
                                          if k != t.key and e["status"] == "active"]
                if row["result"]:
                    rows.append(row)
                    continue
                notes.append(f"{relpath}: key {t.key} is in the manifest with status {entry['status']}")
            if t.words < MIN_WORDS:
                row["result"] = "skipped: too short"
                rows.append(row)
                continue
            olds = [(k, e) for k, e in paths_by_entry.get(norm(relpath), [])
                    if k != t.key and e["status"] in ("active", "unreachable")
                    and ("#" in k) == is_seg]
            if olds:
                row["result"] = "changed"
                row["_supersedes"] = [k for k, _ in olds]
                rows.append(row)
                continue
            row["result"] = "new"
            row["_text"] = t.text
            row["_date"] = _doc_date(ex, f)
            rows.append(row)
            candidates.append(row)

    # cache consistency (spec §5)
    cached = {}
    for key, e in manifest.items():
        if e.get("cached") and e["status"] != "forgotten":
            p = store.corpus_path(key)
            if not p.exists():
                msg = f"manifest entry {key} ({e.get('path')}) is cached but corpus/{p.name} is missing"
                if not dry_run:
                    raise StoreError(msg)
                notes.append(msg)
            elif e["status"] == "active":
                cached[key] = (e.get("path"), p.read_text(encoding="utf-8"))

    # near-duplicates (row 12)
    sh = {id(r): shingles(r["_text"]) for r in candidates}
    corpus_sh = {k: (path, shingles(text)) for k, (path, text) in cached.items()}
    remaining = []
    for r in candidates:
        hit = next((path for k, (path, s) in corpus_sh.items()
                    if path and norm(path) != norm(r["path"]) and jaccard(sh[id(r)], s) >= NEAR_DUP), None)
        if hit:
            r["result"] = "skipped: near-duplicate"
            r["note"] = f"of corpus text {hit}"
        else:
            remaining.append(r)
    parent = {id(r): id(r) for r in remaining}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for i, a in enumerate(remaining):
        for b in remaining[i + 1:]:
            if norm(a["path"]) != norm(b["path"]) and jaccard(sh[id(a)], sh[id(b)]) >= NEAR_DUP:
                parent[find(id(a))] = find(id(b))
    groups = collections.defaultdict(list)
    for r in remaining:
        groups[find(id(r))].append(r)
    for g in groups.values():
        if len(g) < 2:
            continue
        keep = sorted(g, key=lambda r: (-r["_date"].timestamp(), norm(r["path"])))[0]
        for r in g:
            if r is not keep:
                r["result"] = "skipped: near-duplicate"
                r["note"] = f"of {keep['path']}, which is newer" if r["_date"] < keep["_date"] \
                    else f"of {keep['path']}"

    # unreachable (spec §5)
    superseded_now = {k for r in rows for k in r.get("_supersedes", [])}
    changed_paths = {norm(r["path"]) for r in rows if r["result"] == "changed" and "#" not in (r["key"] or "")}
    unreachable = []
    for key, e in manifest.items():
        if e["status"] != "active" or not e.get("path") or key in texts_found or key in superseded_now:
            continue
        if "#" in key and norm(e["path"]) in changed_paths:
            continue      # a segment of a changed file goes with its main text (superseded, not unreachable)
        if in_scope(e["path"]):
            unreachable.append({"path": e["path"], "key": key})

    for r in rows:
        for k in [k for k in r if k.startswith("_")]:
            del r[k]
    rows.sort(key=lambda r: (r["path"], r["key"] or ""))
    unreachable.sort(key=lambda u: (u["path"], u["key"]))
    try:
        store_label = rel(store_root, sources_root) if store_root else None
    except ValueError:
        store_label = str(store_root)
    report = {"schema_version": 1, "command": command_line or "", "store": store_label,
              "scope": scope_desc, "not_listed": sorted(set(not_listed)), "rows": rows,
              "unreachable": unreachable, "notes": notes}
    return check_schema("inventory-report", report, "inventory report")


def _rule_excluded(store, relpath, ci):
    from store import glob_match
    for r in store.sources["sources"]:
        if "path" not in r or not under(r["path"], relpath, ci):
            continue
        base = "" if r["path"] in (".", "") else r["path"].rstrip("/") + "/"
        inner = relpath[len(base):] if base else relpath
        if any(glob_match(g, inner, ci) for g in r.get("exclude", [])):
            return True
    return False


def _tag_rule_match(store, ftags):
    return any("tag" in r and r["tag"] in ftags for r in store.sources["sources"])


def _classify_known(row, entry, relpath, sources_root, norm):
    """Rows 4-9b for a text whose key is in the manifest."""
    st, epath = entry["status"], entry.get("path") or ""
    same = norm(epath) == norm(relpath)
    old_found = bool(epath) and (sources_root / epath).exists()
    if st == "forgotten":
        row["result"] = "skipped: forgotten"
    elif entry.get("holdout"):
        row["result"] = "skipped: holdout"
        if not same and not old_found:
            row["note"] = f"moved from {epath}; path updated (housekeeping)"
    elif st in ("active", "unreachable") and same:
        row["result"] = "unchanged"
        if st == "unreachable":
            row["note"] = "unreachable entry returns to active"
    elif st in ("active", "unreachable") and not old_found:
        row["result"] = "moved"
        row["note"] = f"manifest path {epath} becomes {relpath}"
    elif st in ("active", "unreachable"):
        row["result"] = "copy"
        row["note"] = f"same text as {epath}; not learned twice"
    elif st == "superseded" and same:
        row["result"] = "reverted"
        row["_supersedes_current"] = True
    elif st == "superseded":
        row["result"] = "skipped: earlier version"


def _summary(report):
    c = collections.Counter(r["result"] for r in report["rows"])
    lines = [f"Scope: {report['scope']}  ({len(report['rows'])} texts)"]
    for res, n in sorted(c.items()):
        lines.append(f"  {res}: {n}")
    if report["unreachable"]:
        lines.append(f"  unreachable: {len(report['unreachable'])}")
    for n in report["notes"]:
        lines.append(f"  note: {n}")
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--store")
    g.add_argument("--sources", help="dry run without a store (spec §3.4)")
    ap.add_argument("--target", action="append", help="file or folder, relative to sources_root")
    ap.add_argument("--tag", action="append")
    ap.add_argument("--lang")
    ap.add_argument("--type")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    if not a.dry_run:
        print(json.dumps({"status": "error", "message": "only dry runs exist in this build (learning arrives in phase 2)"}))
        return 2
    try:
        store = Store(a.store) if a.store else None
        report = inventory(store, a.sources, a.target, a.tag, {"lang": a.lang, "type": a.type},
                           dry_run=True, command_line="learn dry-run=true" + (f" store={a.store}" if a.store else ""))
    except StoreError as e:
        print(json.dumps({"status": "error", "message": str(e)}))
        return 2
    print(json.dumps(report, indent=2, ensure_ascii=False) if a.json else _summary(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
