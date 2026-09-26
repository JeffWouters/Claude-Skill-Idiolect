"""learn-edit: learn from how the writer edited a draft (spec §20). Store-writing; nothing changes
until the writer approves the diff.

    python3 learn_edit.py --store S start --draft DRAFT --final FINAL [--profile P] [--type T] [--facet k=v] [--names names.yaml]
    python3 learn_edit.py --store S kinds --file kinds.yaml

`start` takes the lock, aligns the two versions and prints the candidate changes (redacted). The model
then writes kinds.yaml:

    changes: {c-001: cut-hedge, c-002: split-sentence, c-003: other}
    describe: {cut-hedge: "Cuts hedges before a claim."}      # every kind without an edit lesson yet

and `kinds` stages the pair and the edit lessons rebuilt from every stored pair of the slot. Then
stage.py diff / decide / commit, as for learn.
"""
import argparse
import difflib
import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import detect  # noqa: E402
import measure  # noqa: E402
import pages  # noqa: E402
import redact  # noqa: E402
import stage  # noqa: E402
from adapters import extract  # noqa: E402
from common import StoreError, load_yaml_text, read_store_file, utcnow  # noqa: E402
from store import Store  # noqa: E402

KIND = re.compile(r"^[a-z][a-z0-9-]{0,39}$")
OTHER = "other"


def _blocks(path):
    """Paragraph blocks of a draft or final version, with frontmatter lang/type when it has any."""
    p = pathlib.Path(path)
    ex = extract(p)
    if ex is not None:
        return [b for b in ex.blocks if b.strip()], ex.meta or {}
    return [b.strip() for b in re.split(r"\n\s*\n", p.read_text(encoding="utf-8")) if b.strip()], {}


def sentences(blocks):
    out = []
    for b in blocks:
        out += [s.strip() for s in measure.sentences(b) if s.strip()]
    return out


STEPS = ((1, 1), (1, 2), (2, 1), (1, 3), (3, 1), (1, 0), (0, 1))


def _align(a, b):
    """Pair the sentences of one changed run: a split, a merge or a one-to-one edit each becomes its own
    unit, so neighbouring edits are not lumped into one change. Dynamic programming over the STEPS,
    scored by character similarity (a cut or an insertion scores 0)."""
    n, m = len(a), len(b)
    best = {(0, 0): (0.0, None)}
    for i in range(n + 1):
        for j in range(m + 1):
            if (i, j) not in best:
                continue
            for di, dj in STEPS:
                ni, nj = i + di, j + dj
                if ni > n or nj > m:
                    continue
                x, y = " ".join(a[i:ni]), " ".join(b[j:nj])
                score = difflib.SequenceMatcher(a=x, b=y, autojunk=False).ratio() * max(di, dj) if di and dj else 0.0
                total = best[(i, j)][0] + score
                if (ni, nj) not in best or total > best[(ni, nj)][0]:
                    best[(ni, nj)] = (total, (i, j))
    units, at = [], (n, m)
    while at != (0, 0):
        prev = best[at][1]
        units.append((a[prev[0]:at[0]], b[prev[1]:at[1]]))
        at = prev
    return units[::-1]


def changes(draft_blocks, final_blocks):
    """[{before, after}] for every edit between the two versions (spec §20.2): sentences aligned with
    SequenceMatcher, each non-equal run split into units by _align."""
    a, b = sentences(draft_blocks), sentences(final_blocks)
    norm = lambda xs: [" ".join(x.split()) for x in xs]  # noqa: E731
    sm = difflib.SequenceMatcher(a=norm(a), b=norm(b), autojunk=False)
    out = []
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            continue
        for x, y in _align(a[i1:i2], b[j1:j2]):
            if norm(x) != norm(y):
                out.append({"before": " ".join(x), "after": " ".join(y)})
    return out


def _pairs(store, prof):
    d = store.root / "profiles" / prof / "edits"
    out = []
    for f in sorted(d.glob("p-*/pair.yaml")) if d.exists() else []:
        out.append(read_store_file(f, "edit-pair"))
    return out


def _next_pair_id(store, prof):
    d = store.root / "profiles" / prof / "edits"
    nums = [int(x.name.split("-")[1]) for x in d.glob("p-*")] if d.exists() else []
    return f"p-{max(nums + [0]) + 1:03d}"


def start(store_root, draft, final, profile=None, type_=None, facets=None, names=None):
    store = Store(store_root)
    profile = profile or store.config["default_profile"]
    if not (store.root / "profiles" / profile / "profile.yaml").exists():
        raise StoreError(f"no profile {profile}; a profile is created by learn")
    store, pending, _ = stage.begin(store_root, "learn-edit", [profile])
    try:
        db, _ = _blocks(draft)
        fb, meta = _blocks(final)
        final_text = "\n\n".join(fb)
        lang, conf = detect.identify(final_text) if len(final_text.split()) >= 20 else (None, 0.0)
        lang = (facets or {}).get("lang") or meta.get("lang") or lang
        type_ = type_ or (facets or {}).get("type") or meta.get("type")
        if not lang:
            raise StoreError("needs_input: the language of the final version (lang=...)")
        if not type_:
            raise StoreError("needs_input: the type of text (type=...), from the store's types: "
                             + ", ".join(store.config.get("types", [])))
        values = {"lang": lang, "type": type_}
        for name in store.facets[2:]:
            values[name] = (facets or {}).get(name) or "_"
        slot = measure.slot_key(store.facets, values)
        found = changes(db, fb)
        if not found:
            raise StoreError("the two versions have no differences to learn from")
        rows, repl = [], []
        for n, c in enumerate(found, 1):
            before, r1 = redact.redact(c["before"], names)
            after, r2 = redact.redact(c["after"], names)
            repl += r1 + r2
            rows.append({"id": f"c-{n:03d}", "before": before, "after": after})
        pair = {"schema_version": 1, "id": _next_pair_id(store, profile), "slot": slot,
                "date": utcnow().date().isoformat(),
                "redaction": {"redacted": True, "version": redact.VERSION, "reviewed": False},
                "changes": rows}
        pending.work("learn-edit.json").write_text(json.dumps({"profile": profile, "slot": slot, "pair": pair},
                                                              indent=1, ensure_ascii=False), encoding="utf-8")
        return {"profile": profile, "slot": slot, "pair": pair["id"], "changes": rows, "replacements": repl,
                "next": "name a kind for every change and describe new kinds (kinds.yaml), then learn_edit.py kinds"}
    except Exception:
        stage.discard(store_root)
        raise


def kinds(store_root, file):
    store = Store(store_root)
    pending = stage.Pending(store)
    stage.ensure_owner(store, pending)
    wf = pending.dir / "work" / "learn-edit.json"
    if not wf.exists():
        raise StoreError("no learn-edit run: start one first")
    st = json.loads(wf.read_text(encoding="utf-8"))
    prof, slot, pair = st["profile"], st["slot"], st["pair"]
    k = load_yaml_text(pathlib.Path(file).read_text(encoding="utf-8")) or {}
    named, describe = k.get("changes") or {}, k.get("describe") or {}
    ids = [c["id"] for c in pair["changes"]]
    missing = [i for i in ids if i not in named]
    if missing:
        raise StoreError(f"no kind for {', '.join(missing)}")
    bad = [v for v in named.values() if not KIND.match(str(v))]
    if bad:
        raise StoreError(f"kinds are slugs such as cut-hedge: {', '.join(map(str, bad))}")
    for c in pair["changes"]:
        c["kind"] = named[c["id"]]
    pending.remove_items(lambda it: it["kind"] in ("edit-pair", "edit-lesson"))
    pid = pending.add("edit-pair", "add", f"profiles/{prof}/edits/{pair['id']}/pair.yaml",
                      f"edit pair {pair['id']} for {slot}: {len(pair['changes'])} changes "
                      f"({', '.join(sorted(set(named.values())))})",
                      {"edit_pair": {"profile": prof, "pair": pair}}, profile=prof, slot=slot, ref=pair["id"])
    # every stored pair of this slot, plus this one
    by_kind = {}
    for p in [x for x in _pairs(store, prof) if x["slot"] == slot] + [pair]:
        for c in p["changes"]:
            kd = c.get("kind")
            if kd and kd != OTHER:
                by_kind.setdefault(kd, set()).add(p["id"])
    page = store.root / "profiles" / prof / f"{slot}.edits.md"
    meta, cur = pages.parse_edits(page.read_text(encoding="utf-8")) if page.exists() else ({}, [])
    existing = {x["kind"]: x for x in cur if x.get("kind")}
    rejected = stage.rejected_normalised(store, prof, slot)
    lang = slot.split(".")[0]
    last = max([meta.get("last_id") or 0] + [int(x["id"].split("-")[1]) for x in cur])
    need, proposed, skipped = [], [], []
    for kd, prs in sorted(by_kind.items()):
        old = existing.get(kd)
        text = old["text"] if old else describe.get(kd)
        if not text:
            need.append(kd)
            continue
        if not old and stage.normalise_lesson(text, lang) in rejected:
            skipped.append(kd)
            continue
        prs = sorted(prs)
        if old and old["pairs"] == prs:
            continue
        if old:
            lid = old["id"]
        else:
            last += 1
            lid = f"d-{last:03d}"
        les = {"id": lid, "profile": prof, "slot": slot, "text": text.strip(), "kind": kd, "pairs": prs,
               "seen_once": len(prs) < 2}
        what = "seen once" if les["seen_once"] else f"edit lesson ({len(prs)} pairs)"
        pending.add("edit-lesson", "modify" if old else "add", f"profiles/{prof}/{slot}.edits.md",
                    f"[{lid}] {les['text']} ({kd}): {what}", {"edit_lesson": les, "requires": [pid]},
                    profile=prof, slot=slot, ref=lid)
        proposed.append({"id": lid, "kind": kd, "pairs": prs, "seen_once": les["seen_once"], "new": not old})
    if need:
        pending.remove_items(lambda it: it["kind"] in ("edit-pair", "edit-lesson"))
        raise StoreError(f"describe the new kinds in one sentence each (describe:): {', '.join(need)}")
    return {"pair": pair["id"], "edit_lessons": proposed, "not_proposed_rejected": skipped,
            "next": "show the diff (stage.py diff), then decide and commit"}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--store", required=True)
    ap.add_argument("action", choices=["start", "kinds"])
    ap.add_argument("--draft")
    ap.add_argument("--final")
    ap.add_argument("--profile")
    ap.add_argument("--type")
    ap.add_argument("--facet", action="append", default=[])
    ap.add_argument("--names")
    ap.add_argument("--file")
    a = ap.parse_args(argv)
    try:
        if a.action == "start":
            facets = dict(f.split("=", 1) for f in a.facet)
            names = (load_yaml_text(pathlib.Path(a.names).read_text(encoding="utf-8")) or []) if a.names else None
            out = start(a.store, a.draft, a.final, a.profile, a.type, facets, names)
        else:
            out = kinds(a.store, a.file)
    except StoreError as e:
        msg = str(e)
        out = {"status": "needs_input" if msg.startswith("needs_input") else "error", "message": msg}
        print(json.dumps(out, indent=1, ensure_ascii=False))
        return 1
    print(json.dumps(out, indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
