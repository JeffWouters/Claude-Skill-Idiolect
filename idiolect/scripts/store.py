"""Store discovery and loading (spec §2, §3), sources.yaml rules, globs and facet order (§12.1).

    python3 store.py discover [ROOT ...] [--depth 3]

prints JSON: the stores (folders with a valid idiolect.yaml) found under the roots, at most three
levels deep, skipping hidden folders, node_modules and _to_delete. No roots: the current folder.
"""
import collections
import fnmatch
import pathlib
import re

from common import StoreError, check_schema, load_yaml_text, read_store_file, version_of

MARKER = "idiolect.yaml"
SKIP_DIRS = {"node_modules", "_to_delete"}


# ---------- discovery (spec §3) ----------

def is_store(folder):
    f = pathlib.Path(folder) / MARKER
    if not f.is_file():
        return False
    try:
        check_schema("idiolect", load_yaml_text(f.read_text(encoding="utf-8")))
        return True
    except Exception:  # noqa: BLE001 - an invalid marker does not qualify
        return False


def discover(roots, depth=3):
    """Breadth-first search for stores under roots, at most `depth` levels deep."""
    found = []
    queue = collections.deque((pathlib.Path(r), 0) for r in roots)
    seen = set()
    while queue:
        folder, d = queue.popleft()
        try:
            key = folder.resolve()
        except OSError:
            continue
        if key in seen:
            continue
        seen.add(key)
        if is_store(folder):
            found.append(folder)
        if d >= depth:
            continue
        try:
            children = sorted(p for p in folder.iterdir() if p.is_dir())
        except OSError:
            continue
        for c in children:
            if c.name.startswith(".") or c.name in SKIP_DIRS:
                continue
            queue.append((c, d + 1))
    return found


# ---------- the loaded store ----------

class Store:
    def __init__(self, root, migrating=False):
        self.root = pathlib.Path(root).resolve()
        if not is_store(self.root):
            raise StoreError(f"no valid {MARKER} in {self.root}")
        self.config = read_store_file(self.root / MARKER, "idiolect")
        self.sources_root = (self.root / self.config["sources_root"]).resolve()
        sp = self.root / "sources.yaml"
        self.sources = read_store_file(sp, "sources") if sp.exists() else {"schema_version": 1, "sources": []}
        mp = self.root / "corpus" / "manifest.json"
        if migrating and mp.exists():
            # migrate.py only: an older ledger is read as it will be after the upgrade (spec §36.7)
            import migrate
            self.manifest = migrate.upgraded_manifest(mp)
        elif mp.exists():
            self.manifest = read_store_file(mp, "manifest")
        else:
            self.manifest = {"schema_version": version_of("manifest"), "texts": {}}

    @property
    def facets(self):
        return self.config["facets"]

    def corpus_path(self, key):
        return self.root / "corpus" / (key.replace("#", "-") + ".txt")

    def corpus_text(self, key):
        p = self.corpus_path(key)
        if not p.exists():
            raise StoreError(f"manifest entry {key} is cached but corpus/{p.name} is missing")
        return p.read_text(encoding="utf-8")

    def profiles(self):
        d = self.root / "profiles"
        return sorted(p.name for p in d.iterdir() if (p / "profile.yaml").exists()) if d.exists() else []

    def state(self, *parts):
        return self.root.joinpath(".state", *parts)


# ---------- globs and rules (spec §2.6, §2.7, §7) ----------

def _glob_re(pattern):
    """** = zero or more whole segments, * = within a segment, ? = one character."""
    out, i = "", 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out += "(?:[^/]*/)*"
            i += 3
        elif pattern.startswith("/**", i) and i + 3 == len(pattern):
            out += "(?:/.*)?"
            i += 3
        elif pattern.startswith("**", i):
            out += ".*"
            i += 2
        elif pattern[i] == "*":
            out += "[^/]*"
            i += 1
        elif pattern[i] == "?":
            out += "[^/]"
            i += 1
        else:
            out += re.escape(pattern[i])
            i += 1
    return out


def glob_match(pattern, relpath, ci=False):
    flags = re.I if ci else 0
    if "/" not in pattern:
        return bool(re.fullmatch(_glob_re(pattern), relpath.rsplit("/", 1)[-1], flags))
    return bool(re.fullmatch(_glob_re(pattern), relpath, flags))


def under(rule_path, relpath, ci=False):
    """True when relpath lies at or under rule_path ('.' = everything)."""
    if rule_path in (".", ""):
        return True
    a, b = (rule_path.lower(), relpath.lower()) if ci else (rule_path, relpath)
    a = a.rstrip("/")
    return b == a or b.startswith(a + "/")


def rule_depth(rule):
    p = rule.get("path", "")
    return 0 if p in (".", "") else len(p.rstrip("/").split("/"))


def path_rules(store, relpath, ci=False, recursive_ok=True):
    """Path rules matching relpath, most specific first (longest path)."""
    out = []
    for r in store.sources["sources"]:
        if "path" not in r or not under(r["path"], relpath, ci):
            continue
        if r.get("recursive", True) is False:
            parent = relpath.rsplit("/", 1)[0] if "/" in relpath else ""
            base = "" if r["path"] in (".", "") else r["path"].rstrip("/")
            if parent != base and relpath != base:
                continue
        rp = "" if r["path"] in (".", "") else r["path"].rstrip("/") + "/"
        inner = relpath[len(rp):] if rp and relpath.startswith(rp) else relpath
        if any(glob_match(g, inner, ci) for g in r.get("exclude", [])):
            continue
        out.append(r)
    return sorted(out, key=rule_depth, reverse=True)


def tag_rules(store, tags):
    tags = set(tags or [])
    return [r for r in store.sources["sources"] if "tag" in r and r["tag"] in tags]


def globally_excluded(store, relpath, ci=False):
    return any(glob_match(g, relpath, ci) for g in store.sources.get("exclude", []))


def rule_facets(store, relpath, tags=(), ci=False):
    """Facets from the most specific matching rule that sets any (path rules, then tag rules)."""
    merged = {}
    for r in path_rules(store, relpath, ci) + tag_rules(store, tags):
        for k, v in (r.get("facets") or {}).items():
            merged.setdefault(k, v)
    return merged


# ---------- facet order (spec §12.1) ----------

def resolve_facets(facet_names, command=None, entry=None, rule=None, front=None, detected=None,
                   defaults=None, unknown="_"):
    out = {}
    for f in facet_names:
        val = None
        for source in (command, entry, rule, front, detected, defaults):
            if source and source.get(f) not in (None, ""):
                val = str(source[f])
                break
        out[f] = val if val is not None else unknown
    return out


def main(argv=None):
    import argparse
    import json
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("action", choices=["discover"])
    ap.add_argument("roots", nargs="*")
    ap.add_argument("--depth", type=int, default=3)
    a = ap.parse_args(argv)
    found = [str(f) for f in discover(a.roots or ["."], a.depth)]
    print(json.dumps({"stores": found, "count": len(found)}, indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
