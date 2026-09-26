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

def begin(store_root, mode, profiles=(), atomic=False):
    """Start a store-writing run: take the lock (spec §10), refuse to start over a leftover pending area
    (spec §9.7: the caller offers resume or discard), create an empty proposal. `atomic` proposals
    (forget, rollback, prune) are approved or rejected as a whole."""
    store = Store(store_root)
    got = lockmod.acquire(str(store.root), mode, profiles[0] if profiles else None)
    pending = Pending(store)
    if pending.exists() or (pending.dir.exists() and any(pending.dir.iterdir())):
        # The lock stays with this run, so `stage.py resume` or `discard` can follow straight away.
        if pending.dir.exists():
            _write_owner(pending, got["lock"])
        raise StoreError("a pending area is waiting: offer resume or discard first (spec §9.7)")
    pending.create(mode, profiles)
    _write_owner(pending, got["lock"])
    if atomic:
        pending.work("meta.json").write_text(json.dumps({"atomic": True}), encoding="utf-8")
    return store, pending, got


def _write_owner(pending, lock):
    pending.work("owner.json").write_text(json.dumps({"started": lock["started"], "mode": lock["mode"]}),
                                          encoding="utf-8")


def ensure_owner(store, pending):
    """The run working on this pending area must hold the lock (spec §10). Refreshes the heartbeat; takes
    an abandoned lock over; refuses when another live run holds it."""
    root = str(store.root)
    own = pending.dir / "work" / "owner.json"
    mine = json.loads(own.read_text(encoding="utf-8")) if own.exists() else {}
    data, damaged, _ = lockmod.read(root)
    st = lockmod.state(root)
    if data and not damaged and st == "held" and data["started"] == mine.get("started") \
            and data["mode"] == mine.get("mode"):
        lockmod.heartbeat(root)
        return
    if st in ("held", "damaged"):
        raise lockmod.Locked("another run holds the lock; wait for it or for its heartbeat to be an hour old")
    got = lockmod.acquire(root, (mine.get("mode") or (pending.plan["mode"] if pending.exists() else "learn")))
    if pending.dir.exists():
        _write_owner(pending, got["lock"])


class Pending:
    def __init__(self, store):
        self.store = store
        self.dir = store.root / ".state" / "pending"
        self.plan_path = self.dir / "plan.json"

    def exists(self):
        return self.plan_path.exists()

    def create(self, mode, profiles=()):
        if self.exists():
            raise StoreError("a pending area already exists; resume or discard it first (spec §9.7)")
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
        ensure_owner(self.store, self)
        plan = self.plan
        if "commit" in plan:
            raise StoreError("the commit has started; decisions can no longer change")
        ids = {i["id"] for i in plan["items"]}
        for x in list(approve) + list(reject):
            if x not in ids:
                raise StoreError(f"no pending item {x}")
        for it in plan["items"]:
            if it["id"] in approve:
                it["decision"] = "approved"
            if it["id"] in reject:
                it["decision"] = "rejected"
        self.cascade(plan)
        for it in plan["items"]:
            if all_decision and it["decision"] == "pending":
                it["decision"] = all_decision
        self.cascade(plan)
        self.save(plan)
        return plan

    def atomic(self):
        m = self.dir / "work" / "meta.json"
        return m.exists() and json.loads(m.read_text(encoding="utf-8")).get("atomic", False)

    def cascade(self, plan):
        """Decisions that follow from others (spec §9.2): an item whose requirement is rejected is
        rejected; a mirrored item takes the decision of the item it follows; an example drawn from a
        rejected text is rejected; an atomic proposal is rejected as a whole."""
        by_id = {i["id"]: i for i in plan["items"]}
        payloads = {i["id"]: self.payload(i["id"]) for i in plan["items"]}
        if self.atomic() and any(i["decision"] == "rejected" for i in plan["items"]):
            for i in plan["items"]:
                i["decision"] = "rejected"
            return plan
        changed = True
        while changed:
            changed = False
            rejected_keys = {i.get("ref") for i in plan["items"] if i["decision"] == "rejected"
                             and i["kind"] in ("corpus-text", "ownership")}
            for i in plan["items"]:
                pl = payloads[i["id"]]
                want = None
                if any(by_id.get(r, {}).get("decision") == "rejected" for r in pl.get("requires", [])):
                    want = "rejected"
                elif pl.get("follows") and by_id.get(pl["follows"], {}).get("decision") in ("approved", "rejected"):
                    want = by_id[pl["follows"]]["decision"]
                elif (pl.get("example") or {}).get("source") in rejected_keys:
                    want = "rejected"
                elif pl.get("lesson") and pl["lesson"].get("evidence_keys") and \
                        not set(pl["lesson"]["evidence_keys"]) - rejected_keys:
                    want = "rejected"
                if want and i["decision"] != want and not (want == "approved" and i["decision"] == "rejected"):
                    i["decision"] = want
                    changed = True
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
        texts[key]["cached"] = False
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
    if "replace_profiles" in patch:
        e["profiles"] = copy.deepcopy(patch["replace_profiles"])
    owned = any(r["ownership"] == "own" for r in e["profiles"].values())
    if not owned or e["status"] == "forgotten":
        e["cached"] = False
    elif not e.get("cached"):
        # cached turns true only when the same payload writes corpus/<key>.txt (spec §5 cache consistency)
        e["cached"] = bool(patch.get("cache"))
    for k, v in (patch.get("force") or {}).items():   # e.g. cached: false when a text cannot be restored
        e[k] = v
    if e["status"] != "superseded":
        e.pop("superseded_by", None)


def _plan_ids(pending, field, prof, slot=None):
    """Highest id number any item of this plan uses in one file, rejected ones included, so an id is
    never handed out twice (spec §14.2)."""
    n = 0
    for it in pending.plan["items"]:
        pl = pending.payload(it["id"])
        body = pl.get(field)
        if not body:
            continue
        if field in ("vocab", "ruling"):
            if body["profile"] != prof:
                continue
            body = body["entry"]
        elif body.get("profile") != prof or body.get("slot") != slot:
            continue
        m = re.match(r"^[a-z]-(\d+)$", body.get("id", ""))
        if m:
            n = max(n, int(m.group(1)))
    return n


def rejected_keys(pending):
    return {i.get("ref") for i in pending.plan["items"] if i["decision"] == "rejected"
            and i["kind"] in ("corpus-text", "ownership") and i.get("ref")}


def render(store, pending, include, final=False):
    """{store-relative path: new content, or None to delete} for the included items. `final` marks the
    commit rendering: approved examples are marked reviewed, and lesson evidence drops rejected texts."""
    plan = pending.plan
    items = [(it, pending.payload(it["id"])) for it in plan["items"] if include(it)]
    gone = rejected_keys(pending)
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

    # idiolect.yaml: new text types
    new_types = sorted({t for it, pl in items for t in pl.get("types_add") or []})
    if new_types:
        cfg = copy.deepcopy(store.config)
        cfg["types"] = cfg["types"] + [t for t in new_types if t not in cfg["types"]]
        check_schema("idiolect", cfg, "rendered idiolect.yaml")
        out["idiolect.yaml"] = dump_yaml(cfg)

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
                continue
            if les.get("evidence_keys") and gone & set(les["evidence_keys"]):
                les = copy.deepcopy(les)
                keys = [k for k in les["evidence_keys"] if k not in gone]
                les["evidence_keys"] = keys
                les["evidence"]["count"] = len(set(keys))
                les["seen_once"] = len(set(keys)) < 2
                if les.get("quote_key") in gone:
                    les["evidence"]["quote"] = ""
            byid[les["id"]] = les
        fp = new_fp.get(key)
        if fp is None:
            fpt = _read(store, f"profiles/{prof}/{slot}.json")
            fp = json.loads(fpt) if fpt else None
        conf = pages.confidence_line(fp["confidence"]) if fp else ""
        meta["last_id"] = max([meta.get("last_id") or 0, _plan_ids(pending, "lesson", prof, slot)]
                              + [int(i.split("-")[1]) for i in byid])
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
                if final:
                    ex = copy.deepcopy(ex)
                    ex["redaction"]["reviewed"] = True
                byid[ex["id"]] = ex
        meta["last_id"] = max([meta.get("last_id") or 0, _plan_ids(pending, "example", prof, slot)]
                              + [int(i.split("-")[1]) for i in byid])
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
            base["last_id"] = max([base.get("last_id") or 0, _plan_ids(pending, field, prof)]
                                  + [int(i.split("-")[1]) for i in byid])
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
    if pending.atomic():
        lines.append("This proposal is approved or rejected as a whole.")
    for where in sorted(groups, key=lambda w: (w != "store", w)):
        lines.append(f"\n{where}")
        followers = 0
        for it in groups[where]:
            if pending.payload(it["id"]).get("follows"):
                followers += 1
                continue
            lines.append(f"  [{MARK[it['decision']]}] {it['id']} {OPS[it['op']]} {it['kind']}: {it['summary']}")
        if followers:
            lines.append(f"  (+{followers} items that follow the decisions on the slot with the same texts)")
    counts = collections.Counter(i["decision"] for i in plan["items"])
    lines.append(f"\n{counts['approved']} approved, {counts['rejected']} rejected, {counts['pending']} undecided")
    return "\n".join(lines)


# ---------- commit (spec §9.5) ----------

def _snapshot_name(store, profile, now):
    base = now.strftime("%Y-%m-%dT%H%M%SZ")
    name, n = base, 1
    while (store.root / "profiles" / profile / "snapshots" / name).exists():
        n += 1
        name = f"{base}-{n}"
    return name


def affected_profiles(store, pending, include):
    """Profiles whose files or ledger records the included items change (and only those)."""
    profs = set()
    for it in pending.plan["items"]:
        if not include(it):
            continue
        pl = pending.payload(it["id"])
        for body in (pl.get("lesson"), pl.get("example"), pl.get("never"), pl.get("fingerprint")):
            if body:
                profs.add(body["profile"])
        for field in ("vocab", "ruling"):
            if pl.get(field):
                profs.add(pl[field]["profile"])
        if pl.get("profile_yaml"):
            profs.add(pl["profile_yaml"]["name"])
        for rel in list(pl.get("restore") or {}) + list(pl.get("delete") or []):
            if rel.startswith("profiles/"):
                profs.add(rel.split("/")[1])
        for p in pl.get("manifest") or []:
            profs.update((p.get("profiles") or {}).keys())
            profs.update((p.get("replace_profiles") or {}).keys())
            profs.update(((p.get("create") or {}).get("profiles") or {}).keys())
            if p.get("set") and "status" in p["set"]:
                e = store.manifest["texts"].get(p["key"]) or {}
                profs.update((e.get("profiles") or {}).keys())
    return sorted(profs)


def rederive_fingerprints(store, pending):
    """Re-measure approved fingerprints on the approved corpus only, so a rejected text never counts
    (spec §9.5). Primary flags, contrast block and metric list are kept."""
    import measure
    plan = pending.plan
    approved = [i for i in plan["items"] if i["decision"] == "approved"]
    view = copy.deepcopy(store.manifest["texts"])
    texts = {}
    for it in approved:
        pl = pending.payload(it["id"])
        for p in pl.get("manifest") or []:
            _apply_manifest_patch(view, p)
        texts.update(pl.get("corpus") or {})

    def get_text(k):
        return texts[k] if k in texts else store.corpus_text(k)

    for it in approved:
        if it["kind"] != "fingerprint":
            continue
        pl = pending.payload(it["id"])
        old = pl["fingerprint"]
        prof = old["profile"]
        since = None
        py = store.root / "profiles" / prof / "profile.yaml"
        if py.exists():
            since = read_store_file(py, "profile").get("since")
        for a in approved:
            pp = pending.payload(a["id"]).get("profile_yaml")
            if pp and pp["name"] == prof:
                since = pp["data"].get("since")
        slots = measure.slot_texts(view, get_text, store.facets, prof)
        if old["slot"] not in slots:
            it["decision"] = "rejected"
            it["summary"] += " (dropped: no approved texts left)"
            continue
        v = slots[old["slot"]]
        primary = [m for m, x in old["metrics"].items() if x.get("primary")]
        fp, _ = measure.build_fingerprint(prof, old["slot"], v["pooled"], v["texts"], since, primary,
                                          old.get("metric_list", "global"), old.get("contrast"), old["built"])
        if fp != old:
            pl["fingerprint"] = fp
            atomic_write(pending.dir / "items" / f"{it['id']}.json", json.dumps(pl, ensure_ascii=False, indent=1) + "\n")
    pending.save(plan)


def prepare_commit(store, pending):
    """Render approved items into .state/pending/commit/ and write the journal (spec §9.5 steps 1-2)."""
    plan = pending.plan
    if "commit" in plan:
        return plan
    approved = lambda it: it["decision"] == "approved"  # noqa: E731
    undecided = [i["id"] for i in plan["items"] if i["decision"] == "pending"]
    if undecided:
        raise StoreError(f"undecided items: {', '.join(undecided)}; approve or reject them first")
    pending.save(pending.cascade(plan))
    rederive_fingerprints(store, pending)
    plan = pending.plan
    files = render(store, pending, approved, final=True)
    files.update(render_rejections(store, pending))
    any_approved = any(approved(i) for i in plan["items"])
    now = utcnow()
    steps = []
    profs = affected_profiles(store, pending, approved) if any_approved else []
    snaps = {}
    for p in profs:
        if plan["mode"] != "prune":   # pruning is not undone by a snapshot
            # a profile's first learn gets an empty snapshot, so it can be rolled back too
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
        for p in profs:
            mine = [i for i in plan["items"] if i.get("profile") == p]
            counts = collections.Counter((i["kind"], i["decision"]) for i in mine)
            slots = sorted({i["slot"] for i in mine if i.get("slot") and approved(i)})
            summ = ", ".join(f"{n} {k} {d}" for (k, d), n in sorted(counts.items())) or "ledger changes only"
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
    for f in (pdir.iterdir() if pdir.exists() else []):
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
    ensure_owner(store, pending)
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
    ensure_owner(store, pending)
    return run_journal(store, pending)


def discard(store_root):
    store = Store(store_root)
    pending = Pending(store)
    if pending.exists() and "commit" in pending.plan:
        raise StoreError("a commit was interrupted; it can only be resumed (spec §9.7)")
    if pending.dir.exists():
        ensure_owner(store, pending)
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
