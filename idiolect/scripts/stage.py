"""The pending area: items with payloads, the diff, decisions, and the commit journal (spec §9).

    python3 stage.py --store S diff [--json]              the proposal, grouped per profile and slot
    python3 stage.py --store S decide --approve all | --approve i-001,i-002 | --reject i-003
    python3 stage.py --store S commit                     apply approved items through the journal
    python3 stage.py --store S resume                     continue an interrupted commit
    python3 stage.py --store S discard                    drop a proposal that has no journal yet

Every item keeps its payload in .state/pending/items/<id>.json. Target files are never patched: they
are rendered from the committed store plus the included items, so rejecting an item simply leaves
it out of the rendering.
"""
import argparse
import collections
import copy
import json
import os
import pathlib
import re
import shutil
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import lock as lockmod  # noqa: E402
import pages  # noqa: E402
from common import (LANG_DIR, StoreError, atomic_write, check_schema, dump_yaml, iso,  # noqa: E402
                    load_yaml_text, read_store_file, run_id, utcnow, write_json)
from store import Store  # noqa: E402

ITEM_KINDS_REJECTABLE = {"lesson": "observed", "edit-lesson": "edit", "vocabulary": "vocabulary",
                         "example": "example"}


# ---------- the pending area ----------

def begin(store_root, mode, profiles=()):
    """Start a store-writing run: take the lock (spec §10), refuse to start over a leftover pending area
    (spec §9.6: the caller offers resume or discard), create an empty proposal."""
    store = Store(store_root)
    got = lockmod.acquire(str(store.root), mode, profiles[0] if profiles else None)
    pending = Pending(store)
    if pending.exists() or (pending.dir.exists() and any(pending.dir.iterdir())):
        # The lock stays with this run, so `stage.py resume` or `discard` can follow straight away.
        raise StoreError("a pending area is waiting: offer resume or discard first (spec §9.6)")
    pending.create(mode, profiles)
    return store, pending, got


class Pending:
    def __init__(self, store):
        self.store = store
        self.dir = store.root / ".state" / "pending"
        self.plan_path = self.dir / "plan.json"

    def exists(self):
        return self.plan_path.exists()

    def create(self, mode, profiles=()):
        if self.exists():
            raise StoreError("a pending area already exists; resume or discard it first (spec §9.6)")
        now = utcnow()
        plan = {"schema_version": 1, "run_id": run_id(now), "mode": mode, "profiles": sorted(set(profiles)),
                "created": iso(now), "items": []}
        (self.dir / "items").mkdir(parents=True, exist_ok=True)
        write_json(self.plan_path, plan, "pending")
        return plan

    @property
    def plan(self):
        return read_store_file(self.plan_path, "pending")

    def save(self, plan):
        write_json(self.plan_path, plan, "pending")

    def add(self, kind, op, path, summary, payload, profile=None, slot=None, ref=None, decision="pending"):
        plan = self.plan
        n = max([int(i["id"][2:]) for i in plan["items"]] + [0]) + 1
        iid = f"i-{n:03d}"
        item = {"id": iid, "kind": kind, "op": op, "path": path, "summary": summary, "decision": decision}
        if profile:
            item["profile"] = profile
            if profile not in plan.setdefault("profiles", []):
                plan["profiles"] = sorted(plan["profiles"] + [profile])
        if slot:
            item["slot"] = slot
        if ref:
            item["ref"] = ref
        atomic_write(self.dir / "items" / f"{iid}.json", json.dumps(payload, ensure_ascii=False, indent=1) + "\n")
        plan["items"].append(item)
        self.save(plan)
        return iid

    def remove_items(self, pred):
        """Withdraw proposals before the diff (e.g. a step re-run). Never after decisions."""
        plan = self.plan
        keep = []
        for it in plan["items"]:
            if pred(it):
                p = self.dir / "items" / f"{it['id']}.json"
                if p.exists():
                    p.unlink()
            else:
                keep.append(it)
        plan["items"] = keep
        self.save(plan)

    def payload(self, iid):
        return json.loads((self.dir / "items" / f"{iid}.json").read_text(encoding="utf-8"))

    def decide(self, approve=(), reject=(), all_decision=None):
        plan = self.plan
        if "commit" in plan:
            raise StoreError("the commit has started; decisions can no longer change")
        ids = {i["id"] for i in plan["items"]}
        for x in list(approve) + list(reject):
            if x not in ids:
                raise StoreError(f"no pending item {x}")
        for it in plan["items"]:
            if all_decision and it["decision"] == "pending":
                it["decision"] = all_decision
            if it["id"] in approve:
                it["decision"] = "approved"
            if it["id"] in reject:
                it["decision"] = "rejected"
        self.save(plan)
        return plan

    def work(self, *parts):
        p = self.dir.joinpath("work", *parts)
        p.parent.mkdir(parents=True, exist_ok=True)
        return p


# ---------- rendering ----------

def _read(store, rel):
    p = store.root / rel
    return p.read_text(encoding="utf-8") if p.exists() else None


def _apply_manifest_patch(texts, patch):
    key = patch["key"]
    if "create" in patch:
        texts[key] = copy.deepcopy(patch["create"])
    if key not in texts:
        return
    e = texts[key]
    for k, v in (patch.get("set") or {}).items():
        if v is None:
            e.pop(k, None)
        else:
            e[k] = v
    for prof, rec in (patch.get("profiles") or {}).items():
        if rec is None:
            e["profiles"].pop(prof, None)
        else:
            e["profiles"][prof] = rec
    owned = any(r["ownership"] == "own" for r in e["profiles"].values())
    e["cached"] = owned and e["status"] != "forgotten"
    for k, v in (patch.get("force") or {}).items():   # e.g. cached: false when a text cannot be restored
        e[k] = v
    if e["status"] != "superseded":
        e.pop("superseded_by", None)


def render(store, pending, include):
    """{store-relative path: new content, or None to delete} for the included items."""
    plan = pending.plan
    items = [(it, pending.payload(it["id"])) for it in plan["items"] if include(it)]
    out = {}

    # corpus texts, deletions and restores
    for it, pl in items:
        for key, text in (pl.get("corpus") or {}).items():
            out["corpus/" + key.replace("#", "-") + ".txt"] = text if text.endswith("\n") else text + "\n"
        for rel, content in (pl.get("restore") or {}).items():
            out[rel] = content
        for rel in pl.get("delete") or []:
            out[rel] = None

    # manifest
    patches = [p for it, pl in items for p in pl.get("manifest") or []]
    if patches:
        texts = copy.deepcopy(store.manifest["texts"])
        for p in patches:
            _apply_manifest_patch(texts, p)
        man = {"schema_version": 1, "texts": dict(sorted(texts.items()))}
        check_schema("manifest", man, "rendered manifest")
        out["corpus/manifest.json"] = json.dumps(man, indent=2, ensure_ascii=False) + "\n"

    # sources.yaml
    rules = [r for it, pl in items for r in pl.get("sources_rules") or []]
    excl = [g for it, pl in items for g in pl.get("sources_exclude") or []]
    if rules or excl:
        src = copy.deepcopy(store.sources)
        for r in rules:
            if r not in src["sources"]:
                src["sources"].append(r)
        if excl:
            src["exclude"] = sorted(set(src.get("exclude", []) + excl))
        check_schema("sources", src, "rendered sources.yaml")
        out["sources.yaml"] = dump_yaml(src)

    # profile.yaml
    for it, pl in items:
        if "profile_yaml" in pl:
            prof = pl["profile_yaml"]
            check_schema("profile", prof["data"], f"profile {prof['name']}")
            out[f"profiles/{prof['name']}/profile.yaml"] = dump_yaml(prof["data"])

    # fingerprints and never-lists
    new_fp = {}
    for it, pl in items:
        if "fingerprint" in pl:
            fp = pl["fingerprint"]
            check_schema("fingerprint", fp, f"fingerprint {fp['profile']}/{fp['slot']}")
            new_fp[(fp["profile"], fp["slot"])] = fp
            out[f"profiles/{fp['profile']}/{fp['slot']}.json"] = json.dumps(fp, indent=2, ensure_ascii=False) + "\n"
        if "never" in pl:
            nv = pl["never"]
            meta = {"schema_version": 1, "profile": nv["profile"], "slot": nv["slot"], "personal_data": "none"}
            out[f"profiles/{nv['profile']}/{nv['slot']}.never.md"] = pages.render_never(meta, nv["markers"])

    # slot pages (lessons) and examples
    lessons = collections.defaultdict(list)
    examples = collections.defaultdict(list)
    for it, pl in items:
        if "lesson" in pl:
            lessons[(pl["lesson"]["profile"], pl["lesson"]["slot"])].append((it["op"], pl["lesson"]))
        if "example" in pl:
            examples[(pl["example"]["profile"], pl["example"]["slot"])].append((it["op"], pl["example"]))
    for key in set(lessons) | set(new_fp):
        prof, slot = key
        rel = f"profiles/{prof}/{slot}.md"
        base = _read(store, rel)
        if base:
            meta, _, cur = pages.parse_slot_page(base)
        else:
            meta, cur = {"schema_version": 1, "profile": prof, "slot": slot, "pooled": "_" in slot.split(".")[1:],
                         "built": iso(utcnow()), "personal_data": "none", "last_id": 0}, []
        byid = {c["id"]: c for c in cur}
        for op, les in lessons.get(key, []):
            if op == "remove":
                byid.pop(les["id"], None)
            else:
                byid[les["id"]] = les
        fp = new_fp.get(key)
        if fp is None:
            fpt = _read(store, f"profiles/{prof}/{slot}.json")
            fp = json.loads(fpt) if fpt else None
        conf = pages.confidence_line(fp["confidence"]) if fp else ""
        meta["last_id"] = max([meta.get("last_id") or 0] + [int(i.split("-")[1]) for i in byid])
        if fp:
            meta["pooled"] = fp["pooled"]
            meta["built"] = fp["built"]
        out[rel] = pages.render_slot_page(meta, conf, list(byid.values()))
    for key, ops in examples.items():
        prof, slot = key
        rel = f"profiles/{prof}/{slot}.examples.md"
        base = _read(store, rel)
        if base:
            meta, cur = pages.parse_examples(base)
        else:
            meta, cur = {"schema_version": 1, "profile": prof, "slot": slot, "last_id": 0}, []
        byid = {c["id"]: c for c in cur}
        for op, ex in ops:
            if op == "remove":
                byid.pop(ex["id"], None)
            else:
                byid[ex["id"]] = ex
        meta["last_id"] = max([meta.get("last_id") or 0] + [int(i.split("-")[1]) for i in byid])
        out[rel] = pages.render_examples(meta, list(byid.values()))

    # rulings and vocabulary
    for fname, schema, field in (("rulings.yaml", "rulings", "ruling"), ("vocabulary.yaml", "vocabulary", "vocab")):
        per = collections.defaultdict(list)
        for it, pl in items:
            if field in pl:
                per[pl[field]["profile"]].append((it["op"], pl[field]["entry"]))
        for prof, ops in per.items():
            rel = f"profiles/{prof}/{fname}"
            base = load_yaml_text(_read(store, rel) or "") or {"schema_version": 1, "entries": []}
            byid = {e["id"]: e for e in base["entries"]}
            for op, entry in ops:
                if op == "remove":
                    byid.pop(entry["id"], None)
                else:
                    byid[entry["id"]] = entry
            base["entries"] = sorted(byid.values(), key=lambda e: e["id"])
            base["last_id"] = max([base.get("last_id") or 0] + [int(i.split("-")[1]) for i in byid])
            check_schema(schema, base, rel)
            out[rel] = dump_yaml(base)
    return out


# ---------- rejections (spec §14.3) ----------

def stopwords(lang):
    f = LANG_DIR / (lang or "") / "stopwords.txt"
    return set(f.read_text(encoding="utf-8").split()) if lang and f.exists() else set()


def normalise_lesson(text, lang):
    t = re.sub(r"[^\w\s]", " ", text.lower())
    sw = stopwords(lang)
    return " ".join(w for w in t.split() if w not in sw)


def render_rejections(store, pending):
    plan = pending.plan
    per = collections.defaultdict(list)
    today = utcnow().date().isoformat()
    for it in plan["items"]:
        kind = ITEM_KINDS_REJECTABLE.get(it["kind"])
        if it["decision"] != "rejected" or not kind or it["op"] != "add":
            continue
        pl = pending.payload(it["id"])
        body = pl.get("lesson") or pl.get("example") or (pl.get("vocab") or {}).get("entry") or {}
        text = body.get("text", "")
        slot = it.get("slot") or (pl.get("lesson") or pl.get("example") or {}).get("slot") or "_"
        lang = slot.split(".")[0]
        per[it["profile"]].append({"slot": it.get("slot"), "kind": kind, "text": text[:500],
                                   "normalised": normalise_lesson(text, lang) or text.lower()[:200],
                                   "rejects": body.get("id") if re.match(r"^(l|d|v|e)-\d{3,6}$", body.get("id", "")) else None,
                                   "rejected": today})
    out = {}
    for prof, rows in per.items():
        rel = f"profiles/{prof}/rejected.yaml"
        base = load_yaml_text(_read(store, rel) or "") or {"schema_version": 1, "entries": []}
        last = max([base.get("last_id") or 0] + [int(e["id"].split("-")[1]) for e in base["entries"]])
        for r in rows:
            if not r["slot"] and r["kind"] != "vocabulary":
                continue
            last += 1
            entry = {"id": f"x-{last:03d}", "slot": r["slot"], "kind": r["kind"], "text": r["text"],
                     "normalised": r["normalised"], "rejected": r["rejected"]}
            if r["rejects"]:
                entry["rejects"] = r["rejects"]
            base["entries"].append(entry)
        base["last_id"] = last
        check_schema("rejected", base, rel)
        out[rel] = dump_yaml(base)
    return out


def rejected_normalised(store, profile, slot):
    """Normalised forms rejected for this slot, including those inherited from parent profiles."""
    out = set()
    prof = profile
    seen = set()
    while prof and prof not in seen:
        seen.add(prof)
        t = _read(store, f"profiles/{prof}/rejected.yaml")
        if t:
            for e in (load_yaml_text(t) or {}).get("entries", []):
                if e["slot"] == slot and e["kind"] in ("observed", "edit"):
                    out.add(e["normalised"])
        py = _read(store, f"profiles/{prof}/profile.yaml")
        prof = (load_yaml_text(py) or {}).get("extends") if py else None
    return out


# ---------- diff ----------

MARK = {"pending": " ", "approved": "✓", "rejected": "✗"}
OPS = {"add": "+", "modify": "~", "remove": "-"}


def diff(store, pending):
    plan = pending.plan
    groups = collections.defaultdict(list)
    for it in plan["items"]:
        where = "store" if not it.get("profile") else it["profile"] + (f" / {it['slot']}" if it.get("slot") else "")
        groups[where].append(it)
    lines = [f"Proposal from {plan['mode']} (run {plan['run_id']}): {len(plan['items'])} items"]
    for where in sorted(groups, key=lambda w: (w != "store", w)):
        lines.append(f"\n{where}")
        for it in groups[where]:
            lines.append(f"  [{MARK[it['decision']]}] {it['id']} {OPS[it['op']]} {it['kind']}: {it['summary']}")
    counts = collections.Counter(i["decision"] for i in plan["items"])
    lines.append(f"\n{counts['approved']} approved, {counts['rejected']} rejected, {counts['pending']} undecided")
    return "\n".join(lines)


# ---------- commit (spec §9.4) ----------

def _snapshot_name(store, profile, now):
    base = now.strftime("%Y-%m-%dT%H%M%SZ")
    name, n = base, 1
    while (store.root / "profiles" / profile / "snapshots" / name).exists():
        n += 1
        name = f"{base}-{n}"
    return name


def affected_profiles(store, pending, include):
    profs = set()
    for it in pending.plan["items"]:
        if not include(it):
            continue
        if it.get("profile"):
            profs.add(it["profile"])
        for p in pending.payload(it["id"]).get("manifest") or []:
            e = store.manifest["texts"].get(p["key"]) or p.get("create") or {}
            profs.update((e.get("profiles") or {}).keys())
            profs.update((p.get("profiles") or {}).keys())
    return sorted(p for p in profs if (store.root / "profiles" / p).exists()
                  or any(it.get("profile") == p for it in pending.plan["items"]))


def prepare_commit(store, pending):
    """Render approved items into .state/pending/commit/ and write the journal (spec §9.4 steps 1-2)."""
    plan = pending.plan
    if "commit" in plan:
        return plan
    approved = lambda it: it["decision"] == "approved"  # noqa: E731
    undecided = [i["id"] for i in plan["items"] if i["decision"] == "pending"]
    if undecided:
        raise StoreError(f"undecided items: {', '.join(undecided)}; approve or reject them first")
    files = render(store, pending, approved)
    files.update(render_rejections(store, pending))
    any_approved = any(approved(i) for i in plan["items"])
    now = utcnow()
    steps = []
    profs = affected_profiles(store, pending, approved) if any_approved else []
    snaps = {}
    for p in profs:
        if (store.root / "profiles" / p).exists() and plan["mode"] != "prune":   # pruning is not undone by a snapshot
            snaps[p] = _snapshot_name(store, p, now)
            steps.append({"op": "snapshot", "path": f"profiles/{p}/snapshots/{snaps[p]}", "state": "todo"})
    staging = pending.dir / "commit"
    order = lambda rel: (0 if rel.startswith("corpus/") and rel.endswith(".txt") else  # noqa: E731
                         1 if rel == "corpus/manifest.json" else 2 if rel == "sources.yaml" else 3)
    for rel in sorted((r for r, c in files.items() if c is not None), key=lambda r: (order(r), r)):
        atomic_write(staging / rel, files[rel])
        steps.append({"op": "write", "path": rel, "state": "todo"})
    for rel in sorted(r for r, c in files.items() if c is None):
        steps.append({"op": "delete", "path": rel, "state": "todo"})
    if any_approved:
        counts = collections.Counter((i["kind"], i["decision"]) for i in plan["items"])
        for p in profs:
            slots = sorted({i["slot"] for i in plan["items"] if i.get("profile") == p and i.get("slot")
                            and approved(i)})
            summ = ", ".join(f"{n} {k} {d}" for (k, d), n in sorted(counts.items()))
            rel = f"profiles/{p}/changelog.md"
            text = pages.changelog_append(_read(store, rel), p, iso(now), plan["mode"], plan["run_id"], slots,
                                          summ, f"snapshots/{snaps[p]}" if p in snaps else None)
            atomic_write(staging / rel, text)
            steps.append({"op": "changelog", "path": rel, "state": "todo"})
    if not steps:
        return None
    plan["commit"] = {"started": iso(now), "steps": steps}
    pending.save(plan)
    return plan


def _snapshot(store, rel):
    final = store.root / rel
    if final.exists():
        return
    profile = rel.split("/")[1]
    pdir = store.root / "profiles" / profile
    tmp = final.with_name(final.name + ".tmp")
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir(parents=True)
    for f in pdir.iterdir():
        if f.name == "snapshots":
            continue
        if f.is_dir():
            shutil.copytree(f, tmp / f.name)
        else:
            shutil.copy2(f, tmp / f.name)
    entries = {k: e for k, e in store.manifest["texts"].items() if profile in e["profiles"]}
    write_json(tmp / "manifest-entries.json", {"schema_version": 1, "profile": profile,
                                                "taken": iso(utcnow()), "texts": entries}, "manifest-entries")
    os.replace(tmp, final)


def run_journal(store, pending):
    plan = pending.plan
    crash_after = int(os.environ.get("IDIOLECT_TEST_CRASH_AFTER", "-1"))
    done_now = 0
    for step in plan["commit"]["steps"]:
        if step["state"] == "done":
            continue
        rel = step["path"]
        target = store.root / rel
        if step["op"] == "snapshot":
            _snapshot(store, rel)
        elif step["op"] in ("write", "changelog"):
            atomic_write(target, (pending.dir / "commit" / rel).read_text(encoding="utf-8"))
        elif step["op"] == "delete":
            if target.is_dir():
                shutil.rmtree(target)
            elif target.exists():
                target.unlink()
        step["state"] = "done"
        pending.save(plan)
        if (store.root / ".state" / "lock").exists():
            try:
                lockmod.heartbeat(str(store.root))
            except StoreError:
                pass
        done_now += 1
        if done_now == crash_after:
            raise RuntimeError("simulated crash (IDIOLECT_TEST_CRASH_AFTER)")
    shutil.rmtree(pending.dir)
    lockmod.release(str(store.root))
    return {"committed": True, "steps": len(plan["commit"]["steps"]),
            "snapshots": [s["path"] for s in plan["commit"]["steps"] if s["op"] == "snapshot"]}


def commit(store_root):
    store = Store(store_root)
    pending = Pending(store)
    if not pending.exists():
        raise StoreError("nothing pending")
    if prepare_commit(store, pending) is None:
        shutil.rmtree(pending.dir)
        lockmod.release(str(store.root))
        return {"committed": True, "steps": 0, "snapshots": []}
    return run_journal(Store(store_root), pending)


def resume(store_root):
    store = Store(store_root)
    pending = Pending(store)
    if not pending.exists() or "commit" not in pending.plan:
        raise StoreError("no interrupted commit to resume")
    return run_journal(store, pending)


def discard(store_root):
    store = Store(store_root)
    pending = Pending(store)
    if pending.exists() and "commit" in pending.plan:
        raise StoreError("a commit was interrupted; it can only be resumed (spec §9.6)")
    if pending.dir.exists():
        shutil.rmtree(pending.dir)
    lockmod.release(str(store.root))
    return {"discarded": True}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--store", required=True)
    ap.add_argument("action", choices=["diff", "decide", "commit", "resume", "discard"])
    ap.add_argument("--approve", default="")
    ap.add_argument("--reject", default="")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    try:
        if a.action == "diff":
            store = Store(a.store)
            p = Pending(store)
            if not p.exists():
                print(json.dumps({"pending": False}))
                return 0
            print(json.dumps(p.plan, indent=2) if a.json else diff(store, p))
            return 0
        if a.action == "decide":
            p = Pending(Store(a.store))
            ap_ids = [x for x in a.approve.split(",") if x and x != "all"]
            rj_ids = [x for x in a.reject.split(",") if x and x != "all"]
            alld = "approved" if a.approve == "all" else "rejected" if a.reject == "all" else None
            plan = p.decide(ap_ids, rj_ids, alld)
            out = dict(collections.Counter(i["decision"] for i in plan["items"]))
        elif a.action == "commit":
            out = commit(a.store)
        elif a.action == "resume":
            out = resume(a.store)
        else:
            out = discard(a.store)
    except StoreError as e:
        print(json.dumps({"status": "error", "message": str(e)}))
        return 2
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
