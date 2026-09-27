"""learn: the learning pipeline (design: Learning pipeline; spec §5, §7-§9, §13, §14). Script steps are
here; model steps (ownership questions, type, contrast rewrites, lessons, vocabulary, examples) are
done by Claude following references/modes/learn.md, and their results come back through the
`*-apply` commands. Everything lands in the pending area; nothing is learned until `stage.py commit`.

    learn.py --store S init --sources ../Writing --profile sam [--types essay,post] [--lang en]
    learn.py --store S start [--target REL]... [--tag T]... [--profile P] [--lang L] [--type T]
    learn.py --store S questions                     ownership still undecided
    learn.py --store S answer --file answers.yaml    folder rules, per-file answers, new profiles
    learn.py --store S types                         texts whose type only the model can tell
    learn.py --store S set-types --file types.yaml   {key or path: type}
    learn.py --store S mail-names --file names.yaml  names to redact in this run's mail texts
    learn.py --store S stage-texts                   corpus texts, ledger entries, status changes
    learn.py --store S measure                       fingerprints of affected slots
    learn.py --store S contrast-sample --profile P --slot K
    learn.py --store S contrast-apply --profile P --slot K --rewrites DIR [--fresh false]
    learn.py --store S lessons-sample --profile P --slot K
    learn.py --store S lessons-apply --profile P --slot K --file lessons.yaml
    learn.py --store S vocab-apply --profile P --file vocab.yaml
    learn.py --store S examples-sample --profile P --slot K
    learn.py --store S examples-apply --profile P --slot K --file examples.yaml
    learn.py --store S rule --profile P --text "..." [--slot K] [--from l-002]
    learn.py --store S next                          what is left to do
"""
import argparse
import collections
import json
import pathlib
import random
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import detect  # noqa: E402
import inventory as inv  # noqa: E402
import measure  # noqa: E402
import pages  # noqa: E402
import redact as redactmod  # noqa: E402
import stage  # noqa: E402
import verify  # noqa: E402
from adapters import extract  # noqa: E402
from common import (version_of, StoreError, case_insensitive, content_hash, count_words, load_yaml_text,  # noqa: E402
                    read_store_file, utcnow, words)
from store import Store, path_rules, rule_depth, tag_rules  # noqa: E402

LEARNABLE = {"new", "changed"}
QUAL_CAP = 20000
CONTRAST_PARAS = 8
EXAMPLE_CANDIDATES = 12
REUSE_CHANGE = 0.20


# ---------- state of this run ----------

class Run:
    def __init__(self, store_root):
        self.store = Store(store_root)
        self.pending = stage.Pending(self.store)
        # an interview is a learn run whose texts are the writer's answers (spec §21)
        if not self.pending.exists() or self.pending.plan["mode"] not in ("learn", "interview"):
            raise StoreError("no learn run is waiting; start one with `learn.py start`")
        stage.ensure_owner(self.store, self.pending)   # refreshes the heartbeat (spec §10.2)
        self.state_path = self.pending.work("state.json")
        self.state = json.loads(self.state_path.read_text(encoding="utf-8"))

    def save(self):
        self.state_path.write_text(json.dumps(self.state, indent=1, ensure_ascii=False), encoding="utf-8")

    def text(self, key):
        p = self.pending.work("texts", key.replace("#", "-") + ".txt")
        if p.exists():
            return p.read_text(encoding="utf-8")
        if not hasattr(self, "_staged"):
            self._staged = {}
            for it in self.pending.plan["items"]:
                if self.included(it):
                    self._staged.update(self.pending.payload(it["id"]).get("corpus") or {})
        if key in self._staged:
            return self._staged[key]
        return self.store.corpus_text(key)

    def text_from_source(self, key, path):
        """The cleaned text for key if the source file still gives it, else None."""
        f = self.store.sources_root / path
        if not f.exists():
            return None
        ex = extract(f)
        for t in (detect.split(ex.blocks) if ex else []):
            if t.key == key:
                return t.text
        return None

    def included(self, it):
        return it["decision"] != "rejected"

    def view(self):
        """Manifest after every non-rejected item of this run (for measuring)."""
        texts = json.loads(json.dumps(self.store.manifest["texts"]))
        for it in self.pending.plan["items"]:
            if self.included(it):
                for p in self.pending.payload(it["id"]).get("manifest") or []:
                    stage._apply_manifest_patch(texts, p)
        return texts


# ---------- init (housekeeping: the marker and empty layout, spec §3.3) ----------

def init(store_root, sources_root, profile, types_=("essay",), lang="en"):
    from common import SKILL, check_schema, dump_yaml, write_yaml
    import os
    root = pathlib.Path(store_root)
    if os.path.isabs(sources_root):
        try:
            sources_root = pathlib.PurePath(os.path.relpath(sources_root, root.resolve())).as_posix()
        except ValueError:
            raise StoreError("the store and the sources must be on the same drive (paths are stored relative)")
    if (root / "idiolect.yaml").exists():
        raise StoreError(f"{root} already holds a store")
    cfg = {"schema_version": 1, "sources_root": sources_root, "facets": ["lang", "type"],
           "types": list(types_), "default_profile": profile, "defaults": {"lang": lang}}
    check_schema("idiolect", cfg, "idiolect.yaml")
    src = (root / sources_root).resolve()
    if not src.exists():
        raise StoreError(f"sources_root {sources_root} does not exist relative to {root}")
    root.mkdir(parents=True, exist_ok=True)
    try:
        inside = root.resolve().relative_to(src)
    except ValueError:
        inside = None
    write_yaml(root / "idiolect.yaml", cfg, "idiolect")
    (root / "README.md").write_text((SKILL / "assets" / "templates" / "README.md").read_text(encoding="utf-8"),
                                    encoding="utf-8")
    for d in ("corpus", "profiles", ".state"):
        (root / d).mkdir(exist_ok=True)
    return {"created": str(root), "warning": f"the store sits inside the sources ({inside}); the inventory "
                                             f"always skips it" if inside is not None else None}


# ---------- start ----------

def start(store_root, targets=None, tags=None, profile=None, lang=None, type_=None, since=None):
    store = Store(store_root)
    profile = profile or store.config["default_profile"]
    store, pending, got = stage.begin(store_root, "learn", [profile])
    try:
        joined = {}
        report = inv.inventory(store, targets=targets, tags=tags, command={"lang": lang, "type": type_},
                               dry_run=False, command_line="learn", joined_out=joined)
    except Exception:
        stage.discard(store_root)
        raise
    ci = case_insensitive(store.sources_root)
    texts = {}
    for r in report["rows"]:
        if r["result"] in ("skipped: not prose",):
            continue
        texts.setdefault(r["path"], []).append(r)
    state = {"profile": profile, "since": since, "command": {"lang": lang, "type": type_}, "targets": targets or [],
             "tags": tags or [], "texts": {}, "answers": {"files": {}, "rules": [], "profiles": {}},
             "types": {}, "steps": {"texts": False, "measure": False, "contrast": [], "lessons": [],
                                     "vocab": [], "examples": []}}
    for path, rows in texts.items():
        ex = joined[path] if path in joined else extract(store.sources_root / path)
        parts = {t.key: t for t in detect.split(ex.blocks)} if ex else {}
        ftags = ex.meta.get("tags") or [] if ex else []
        ftags = [ftags] if isinstance(ftags, str) else [str(t).lstrip("#") for t in ftags]
        for r in rows:
            t = parts.get(r["key"])
            info = {"path": path, "result": r["result"], "words": r["words"], "lang": r["lang"],
                    "type": r["type"], "date": (ex.date if ex else None), "tags": ftags, "note": r.get("note"),
                    "origin": (ex.meta.get("origin") if ex else None) or "file"}
            texts_dir = pending.work("texts", r["key"].replace("#", "-") + ".txt")
            if t is not None and r["result"] in LEARNABLE:
                texts_dir.write_text(t.text, encoding="utf-8")
            state["texts"][r["key"]] = info
    state["unreachable"] = report["unreachable"]
    pending.work("inventory.json").write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8")
    pending.work("state.json").write_text(json.dumps(state, indent=1, ensure_ascii=False), encoding="utf-8")
    run = Run(store_root)
    return {"lock_taken_over": got["taken_over"], "summary": inv._summary(report),
            "questions": questions(run), "next": _next(run)}


# ---------- ownership (spec §7) ----------

def _decide(run, key, info):
    """{profile: (ownership, decided_by)} and a list of open questions for this text."""
    store, st = run.store, run.state
    ci = case_insensitive(store.sources_root)
    ans = st["answers"]
    rules = list(store.sources["sources"]) + ans["rules"]
    decided, open_q = {}, []
    profs = {r["profile"] for r in rules if ("path" in r and _covers(r, info["path"], ci))
             or ("tag" in r and r["tag"] in info["tags"])}
    fa = ans["files"].get(info["path"]) or {}
    profs |= set(fa)
    old = store.manifest["texts"]
    prev_file = {}
    for k, e in old.items():
        if e.get("path") == info["path"] and k != key and e["status"] in ("active", "unreachable"):
            for p, rec in e["profiles"].items():
                if rec["decided_by"] == "writer":
                    prev_file[p] = rec["ownership"]
    profs |= set(prev_file)          # spec §7.3: a per-file answer is asked again, never dropped
    if not profs:
        profs = {st["profile"]}
    for p in sorted(profs):
        if p in fa:
            decided[p] = (fa[p], "writer")
            continue
        if p in prev_file:
            open_q.append({"path": info["path"], "profile": p, "default": prev_file[p],
                           "why": "changed file that was decided per file; ask again"})
            continue
        prs = [r for r in rules if "path" in r and r["profile"] == p and _covers(r, info["path"], ci)
               and not _excluded_by(r, info["path"], ci)]
        if prs:
            best = max(rule_depth(r) for r in prs)
            top = {r["ownership"] for r in prs if rule_depth(r) == best}
            if len(top) == 1:
                decided[p] = (top.pop(), "path-rule")
                continue
            open_q.append({"path": info["path"], "profile": p, "why": "two equally specific rules disagree"})
            continue
        trs = [r for r in rules if "tag" in r and r["profile"] == p and r["tag"] in info["tags"]]
        if trs and len({r["ownership"] for r in trs}) == 1:
            decided[p] = (trs[0]["ownership"], "tag-rule")
            continue
        open_q.append({"path": info["path"], "profile": p, "why": "no rule covers it"})
    return decided, open_q


def excluded_now(run, path):
    """Excluded by an exclude glob of a stored or just-answered path rule (spec §5 row 1)."""
    ci = case_insensitive(run.store.sources_root)
    rules = list(run.store.sources["sources"]) + run.state["answers"]["rules"]
    return any("path" in r and _under(r["path"], path, ci) and _excluded_by(r, path, ci) for r in rules)


def _covers(rule, path, ci):
    """The path rule applies to this file: at or under its path, and directly inside it when
    recursive is false."""
    if not _under(rule["path"], path, ci):
        return False
    if rule.get("recursive", True) is False:
        base = "" if rule["path"] in (".", "") else rule["path"].rstrip("/")
        parent = path.rsplit("/", 1)[0] if "/" in path else ""
        return parent.lower() == base.lower() if ci else parent == base
    return True


def _under(rule_path, path, ci):
    from store import under
    return under(rule_path, path, ci)


def _excluded_by(rule, path, ci):
    from store import glob_match
    base = "" if rule["path"] in (".", "") else rule["path"].rstrip("/") + "/"
    inner = path[len(base):] if base and path.startswith(base) else path
    return any(glob_match(g, inner, ci) for g in rule.get("exclude", []))


def questions(run):
    qs = []
    for key, info in sorted(run.state["texts"].items(), key=lambda kv: kv[1]["path"]):
        if info["result"] not in LEARNABLE or excluded_now(run, info["path"]):
            continue
        _, open_q = _decide(run, key, info)
        qs.extend(open_q)
    seen, out = set(), []
    for q in qs:
        k = (q["path"], q["profile"])
        if k not in seen:
            seen.add(k)
            out.append(q)
    folders = collections.Counter(q["path"].rsplit("/", 1)[0] if "/" in q["path"] else "." for q in out)
    missing_profiles = sorted({q["profile"] for q in out} | {run.state["profile"]})
    missing_profiles = [p for p in missing_profiles if not (run.store.root / "profiles" / p / "profile.yaml").exists()
                        and p not in run.state["answers"]["profiles"]]
    return {"undecided": out, "by_folder": dict(folders), "new_profiles_need": missing_profiles}


def answer(store_root, file):
    run = Run(store_root)
    data = load_yaml_text(pathlib.Path(file).read_text(encoding="utf-8")) or {}
    today = utcnow().date().isoformat()
    for r in data.get("folders", []):
        rule = {"path": r["path"], "profile": r.get("profile", run.state["profile"]),
                "ownership": r["ownership"], "decided": today}
        for k in ("recursive", "exclude", "facets"):
            if k in r:
                rule[k] = r[k]
        run.state["answers"]["rules"].append(rule)
    for f in data.get("files", []):
        run.state["answers"]["files"].setdefault(f["path"], {})[f.get("profile", run.state["profile"])] = f["ownership"]
    for p in data.get("profiles", []):
        prof = {"schema_version": 1, "subject": p["subject"], "consent": p["consent"],
                "extends": p.get("extends"), "since": p.get("since")}
        if p.get("description"):
            prof["description"] = p["description"]
        from common import check_schema
        check_schema("profile", prof, f"profile {p['name']}")
        run.state["answers"]["profiles"][p["name"]] = prof
    run.save()
    return {"questions": questions(run), "next": _next(run)}


# ---------- types ----------

def _owned(run, key, info):
    decided, _ = _decide(run, key, info)
    return any(o == "own" for o, _ in decided.values())


def _type_for(run, key, info):
    """Type after this run's answers: a set type, else the inventory's, else an answered rule's facets."""
    if key in run.state["types"]:
        return run.state["types"][key]
    if info["type"] not in ("?", None):
        return info["type"]
    ci = case_insensitive(run.store.sources_root)
    rules = [r for r in run.state["answers"]["rules"] if "path" in r and _covers(r, info["path"], ci)
             and (r.get("facets") or {}).get("type")]
    if rules:
        return max(rules, key=rule_depth)["facets"]["type"]
    return info["type"]


def types(store_root):
    run = Run(store_root)
    out = []
    for key, info in sorted(run.state["texts"].items(), key=lambda kv: kv[1]["path"]):
        if info["result"] in LEARNABLE and not excluded_now(run, info["path"]) and _type_for(run, key, info) in ("?", None) \
                and _owned(run, key, info):
            excerpt = " ".join(words(run.text(key))[:300])
            out.append({"key": key, "path": info["path"], "excerpt": excerpt})
    return {"allowed": run.store.config["types"], "texts": out}


def set_types(store_root, file):
    run = Run(store_root)
    data = load_yaml_text(pathlib.Path(file).read_text(encoding="utf-8")) or {}
    by_path = {info["path"]: k for k, info in run.state["texts"].items() if "#" not in k}
    for k, t in data.items():
        key = k if k in run.state["texts"] else by_path.get(k)
        if not key:
            raise StoreError(f"unknown text {k}")
        if not re.match(r"^[a-z0-9][a-z0-9-]{0,39}$", str(t)):
            raise StoreError(f"not a valid type: {t}")
        run.state["types"][key] = str(t)
    run.save()
    return {"set": len(data), "next": _next(run)}


# ---------- stage texts ----------

def mail_names(store_root, file):
    """Names of people and organisations to redact in this run's mail texts (spec §15.2); run before
    stage-texts. An empty list records that the model looked and found none."""
    run = Run(store_root)
    names = load_yaml_text(pathlib.Path(file).read_text(encoding="utf-8")) or []
    for n in names:
        if not isinstance(n, dict) or not n.get("name"):
            raise StoreError("each entry is {name: ..., placeholder: [person]|[client]|[employer]|[organisation]}")
    run.state["mail_names"] = names
    run.save()
    mails = [i["path"] for i in run.state["texts"].values() if i.get("origin") == "mail"]
    return {"names": len(names), "mail_texts": len(mails), "next": "learn.py stage-texts"}


def stage_texts(store_root):
    run = Run(store_root)
    q = questions(run)
    if q["undecided"] or q["new_profiles_need"]:
        raise StoreError("ownership or new profiles still undecided; run `learn.py questions`")
    pending, store, st = run.pending, run.store, run.state
    pending.remove_items(lambda it: it["kind"] in ("corpus-text", "ownership", "status", "rule", "profile"))
    st["steps"]["measure"] = False
    st["slots"] = []
    today = utcnow().date().isoformat()
    ci = case_insensitive(store.sources_root)
    profile_items, rule_items = {}, []
    for name, prof in sorted(st["answers"]["profiles"].items()):
        profile_items[name] = pending.add("profile", "add", f"profiles/{name}/profile.yaml",
                                          f"new profile {name}: {prof['subject']} (consent: {prof['consent']})",
                                          {"profile_yaml": {"name": name, "data": prof}}, profile=name)
    if st.get("since") is not None:
        prof = st["profile"]
        py = store.root / "profiles" / prof / "profile.yaml"
        if prof in st["answers"]["profiles"]:
            pl = pending.payload(profile_items[prof])
            pl["profile_yaml"]["data"]["since"] = st["since"]
            stage.atomic_write(pending.dir / "items" / f"{profile_items[prof]}.json", json.dumps(pl, indent=1) + "\n")
        elif py.exists():
            data = read_store_file(py, "profile")
            if data.get("since") != st["since"]:
                data["since"] = st["since"]
                profile_items[prof] = pending.add("profile", "modify", f"profiles/{prof}/profile.yaml",
                                                  f"{prof}: weight writing from {st['since']} onward more (since=)",
                                                  {"profile_yaml": {"name": prof, "data": data}}, profile=prof)
    for r in st["answers"]["rules"]:
        iid = pending.add("rule", "add", "sources.yaml",
                          f"{r['ownership']} for {r['profile']}: {r['path']}" + (f" (except {', '.join(r['exclude'])})" if r.get("exclude") else ""),
                          {"sources_rules": [r], "requires": [profile_items[r["profile"]]] if r["profile"] in profile_items and
                           st["answers"]["profiles"].get(r["profile"]) else []}, profile=r["profile"])
        rule_items.append((r, iid))
    new_types = sorted({t for t in st["types"].values() if t not in store.config["types"]})
    if new_types:
        pending.add("rule", "modify", "idiolect.yaml", f"new text types: {', '.join(new_types)}",
                    {"types_add": new_types})
    manifest = store.manifest["texts"]
    for key, info in sorted(st["texts"].items(), key=lambda kv: (kv[1]["path"], kv[0])):
        res = info["result"]
        entry = manifest.get(key)
        needs_cache = bool(entry) and entry["status"] != "forgotten" and not store.corpus_path(key).exists() \
            and any(r["ownership"] == "own" for r in entry["profiles"].values())
        if res == "moved" or (res == "unchanged" and entry and entry["status"] == "active" and needs_cache):
            patch = {"key": key, "set": {"path": info["path"], "status": "active"}}
            pl = {"manifest": [patch]}
            if needs_cache:
                text = run.text_from_source(key, info["path"])
                if text is not None:
                    pl["corpus"] = {key: text}
                    patch["cache"] = True
            what = f"moved from {entry['path']}" if res == "moved" else "text cached again"
            pending.add("status", "modify", "corpus/manifest.json",
                        f"{info['path']}: {what}" + ("; text cached again" if res == "moved" and "corpus" in pl else ""),
                        pl, ref=key, decision="approved")
        elif res == "unchanged" and entry and entry["status"] == "unreachable":
            patch = {"key": key, "set": {"status": "active"}}
            pl = {"manifest": [patch]}
            owned = any(r["ownership"] == "own" for r in entry["profiles"].values())
            if owned and not store.corpus_path(key).exists():
                text = run.text_from_source(key, info["path"])
                if text is not None:
                    pl["corpus"] = {key: text}
                    patch["cache"] = True
            pending.add("status", "modify", "corpus/manifest.json", f"{info['path']}: found again"
                        + ("; text cached again" if "corpus" in pl else ""), pl, ref=key, decision="approved")
        elif res == "reverted":
            cur = [k for k, e in manifest.items() if e.get("path") == info["path"] and e["status"] == "active" and k != key]
            patches = [{"key": key, "set": {"status": "active"}}]
            patches += [{"key": k, "set": {"status": "superseded", "superseded_by": key}} for k in cur]
            pending.add("status", "modify", "corpus/manifest.json", f"{info['path']}: reverted to an earlier version",
                        {"manifest": patches}, ref=key)
        elif res == "skipped: holdout" and entry and entry.get("path") != info["path"]:
            pending.add("status", "modify", "corpus/manifest.json", f"{info['path']}: holdout moved",
                        {"manifest": [{"key": key, "set": {"path": info["path"]}}]}, ref=key, decision="approved")
        if res in ("unchanged", "moved") and entry and entry["status"] in ("active", "unreachable") \
                and not excluded_now(run, info["path"]):
            # a rule now gives this known text to a profile that has no record for it (a new rule, or a
            # record a rollback removed): add the record, never touching existing ones (review I3)
            decided, _ = _decide(run, key, info)
            add = {p: {"ownership": o, "decided": today, "decided_by": by}
                   for p, (o, by) in decided.items() if p not in entry["profiles"]}
            if add:
                patch = {"key": key, "profiles": add}
                pl = {"manifest": [patch], "record_needs": _record_needs(
                    {p: decided[p] for p in add}, info, profile_items, rule_items, st, ci)}
                if any(r["ownership"] == "own" for r in add.values()) and not store.corpus_path(key).exists():
                    text = run.text_from_source(key, info["path"])
                    if text is not None:
                        pl["corpus"] = {key: text}
                        patch["cache"] = True
                who = ", ".join(f"{r['ownership']} for {p}" for p, r in sorted(add.items()))
                pending.add("ownership", "modify", "corpus/manifest.json", f"{info['path']}: {who}", pl,
                            profile=sorted(add)[0], ref=key)
        if res not in LEARNABLE or excluded_now(run, info["path"]):
            continue
        decided, _ = _decide(run, key, info)
        facets = {"lang": info["lang"], "type": _type_for(run, key, info)}
        if facets["type"] in ("?", None) and not any(o == "own" for o, _ in decided.values()):
            facets["type"] = "_"          # recorded, never learned: no type needed
        if facets["type"] in ("?", None):
            raise StoreError(f"{info['path']}: type unknown; run `learn.py types` and `set-types`")
        for f in store.facets[2:]:
            facets[f] = (st["command"] or {}).get(f) or "_"
        profiles = {p: {"ownership": o, "decided": today, "decided_by": by} for p, (o, by) in decided.items()}
        owned = any(o == "own" for o, _ in decided.values())
        origin = info.get("origin") or "file"
        create = {"path": info["path"], "date": _date(info["date"]), "origin": origin, "profiles": profiles,
                  "facets": facets, "words": info["words"], "holdout": False, "status": "active",
                  "cached": owned}
        patches = [{"key": key, "create": create, "cache": owned}]
        olds = [k for k, e in manifest.items() if e.get("path") == info["path"] and e["status"] in ("active", "unreachable")
                and k != key and ("#" in k) == ("#" in key)]
        if "#" not in key and res == "changed":
            # segments of the earlier version that are not in the new file go with it (review I4)
            olds += [k for k, e in manifest.items() if e.get("path") == info["path"] and "#" in k
                     and e["status"] in ("active", "unreachable") and k not in st["texts"]]
        for k in olds:
            patches.append({"key": k, "set": {"status": "superseded", "superseded_by": key}})
        record_needs = _record_needs(decided, info, profile_items, rule_items, st, ci)
        who = ", ".join(f"{o} for {p}" for p, (o, _) in sorted(decided.items()))
        summ = f"{info['path']}{' (segment ' + key.split('#')[1] + ')' if '#' in key else ''}: {res}, {info['words']} words, {facets['lang']}.{facets['type']}; {who}"
        if olds:
            summ += "; supersedes the earlier version"
        payload = {"manifest": patches, "record_needs": record_needs}
        if owned:
            text = run.text(key)
            if origin == "mail":
                # other people's details in mail are redacted in the corpus too (spec §6.4, §15.3)
                names = st.get("mail_names")
                text, _ = redactmod.redact(text, names)
                create["redaction"] = {"redacted": True, "version": redactmod.VERSION, "reviewed": names is not None}
                summ += "; redacted" + ("" if names is not None else " (script pass only: give names with learn.py mail-names)")
            payload["corpus"] = {key: text}
            pending.add("corpus-text", "add", f"corpus/{key.replace('#', '-')}.txt", summ, payload,
                        profile=sorted(decided)[0], ref=key)
        else:
            pending.add("ownership", "add", "corpus/manifest.json", summ + " (recorded, not learned)", payload,
                        profile=sorted(decided)[0], ref=key)
    for u in st.get("unreachable", []):
        pending.add("status", "modify", "corpus/manifest.json", f"{u['path']}: unreachable (still learned until forgotten)",
                    {"manifest": [{"key": u["key"], "set": {"status": "unreachable"}}]}, ref=u["key"],
                    decision="approved")
    st["steps"]["texts"] = True
    run.save()
    return {"items": len(pending.plan["items"]), "next": _next(run)}


def _record_needs(decided, info, profile_items, rule_items, st, ci):
    """Per profile record: the items of this run it stands on (a new profile, the new rule that decided
    it). A record whose need is rejected is dropped; a text with no records left is rejected."""
    out = {}
    for p, (o, by) in decided.items():
        needs = []
        if p in profile_items and p in st["answers"]["profiles"]:
            needs.append(profile_items[p])
        if by == "path-rule":
            needs += [iid for r, iid in rule_items if r["profile"] == p and _covers(r, info["path"], ci)]
        out[p] = needs
    return out


def _date(d):
    if not d:
        return None
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", str(d))
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else None


# ---------- measure ----------

def affected(run):
    """(profile, slot) pairs touched by this run's texts, including pooled generalisations."""
    view = run.view()
    out = set()
    for it in run.pending.plan["items"]:
        if not run.included(it):
            continue
        for p in run.pending.payload(it["id"]).get("manifest") or []:
            e = view.get(p["key"])
            if not e:
                continue
            for prof in e["profiles"]:
                slot = measure.slot_key(run.store.facets, e["facets"])
                out.add((prof, slot))
                for g in measure.generalisations(slot):
                    out.add((prof, g))
    return out


def _existing_fp(store, prof, slot):
    f = store.root / "profiles" / prof / f"{slot}.json"
    return read_store_file(f, "fingerprint") if f.exists() else None


def do_measure(store_root):
    run = Run(store_root)
    if not run.state["steps"]["texts"]:
        raise StoreError("run `learn.py stage-texts` first")
    run.pending.remove_items(lambda it: it["kind"] in ("fingerprint",) or
                             (it["kind"] == "deletion" and it.get("slot")))
    view = run.view()
    pairs = affected(run)
    profiles = sorted({p for p, _ in pairs})
    out = []
    for prof in profiles:
        since = (run.state["answers"]["profiles"].get(prof) or {}).get("since")
        py = run.store.root / "profiles" / prof / "profile.yaml"
        if since is None and py.exists():
            since = read_store_file(py, "profile").get("since")
        if run.state.get("since") is not None and prof == run.state["profile"]:
            since = run.state["since"]
        slots = sorted(s for p, s in pairs if p == prof)
        keep = {s: _existing_fp(run.store, prof, s) for s in slots}
        produced = set()
        for x in measure.fingerprints_view(view, run.text, run.store.facets, prof, only=slots, since=since,
                                           keep={k: v for k, v in keep.items() if v}):
            produced.add(x["fingerprint"]["slot"])
            fp = x["fingerprint"]
            run.pending.add("fingerprint", "modify" if keep.get(fp["slot"]) else "add",
                            f"profiles/{prof}/{fp['slot']}.json",
                            f"{fp['counts']['texts']} texts, {fp['counts']['words']} words, confidence "
                            f"{pages.confidence_line(fp['confidence'])}"
                            + (f"; unstable: {', '.join(x['unstable'])}" if x["unstable"] else ""),
                            {"fingerprint": fp}, profile=prof, slot=fp["slot"])
            out.append({"profile": prof, "slot": fp["slot"], "pooled": fp["pooled"],
                        "texts": fp["counts"]["texts"], "confidence": fp["confidence"]["level"]})
        for slot in slots:
            if slot in produced or not keep.get(slot):
                continue
            run.pending.add("deletion", "remove", f"profiles/{prof}/{slot}.json",
                            f"slot {slot} has no texts left: fingerprint and never-list removed, lessons and "
                            f"examples emptied (edit lessons are kept)",
                            stage.retire_slot_payload(run.store, prof, slot), profile=prof, slot=slot,
                            decision="approved")
    # a pooled slot with exactly the texts of one exact slot mirrors it: contrast and lessons are shared
    for o in out:
        if not o["pooled"]:
            continue
        allsl = measure.slot_texts(view, run.text, run.store.facets, o["profile"])
        mine = {k for k, _, _ in allsl[o["slot"]]["texts"]}
        twin = [sl for sl, v in allsl.items() if not v["pooled"] and {k for k, _, _ in v["texts"]} == mine]
        if twin:
            o["mirrors"] = twin[0]
            lead, follower = _fp_item(run, o["profile"], twin[0]), _fp_item(run, o["profile"], o["slot"])
            if lead and follower:
                fpl = run.pending.payload(follower["id"])
                fpl["follows"] = lead["id"]
                stage.atomic_write(run.pending.dir / "items" / f"{follower['id']}.json",
                                   json.dumps(fpl, ensure_ascii=False, indent=1) + "\n")
    outliers = _outliers(run, out)
    run.state["steps"]["measure"] = True
    run.state["slots"] = out
    run.state["outliers"] = outliers
    run.save()
    res = {"slots": out, "next": _next(run)}
    if outliers:
        res["outliers"] = outliers
    return res


def _outliers(run, slots):
    """Texts that measure unlike the rest of their exact slot (spec §28): shown to the writer, who says
    whether each is theirs. Pooled slots repeat their exact slots and are skipped."""
    found = []
    for o in slots:
        if o["pooled"]:
            continue
        texts = slot_texts(run, o["profile"], o["slot"])
        for x in verify.slot_outliers(texts, o["slot"].split(".")[0]):
            info = run.state["texts"].get(x["key"])
            path = info["path"] if info else (run.store.manifest["texts"].get(x["key"]) or {}).get("path")
            found.append({"profile": o["profile"], "slot": o["slot"], "path": path, "key": x["key"],
                          "new": info is not None, "distance": x["distance"], "threshold": x["threshold"],
                          "off": [f"{y['describe']}: {y['text']}, typically {y['typical']}" for y in x["off"]]})
    return found


# ---------- slot helpers ----------

def slot_texts(run, prof, slot):
    view = run.view()
    all_slots = measure.slot_texts(view, run.text, run.store.facets, prof)
    if slot not in all_slots:
        raise StoreError(f"no texts for {prof}/{slot}")
    return [(k, t) for k, t, _ in all_slots[slot]["texts"]]


def _fp_item(run, prof, slot):
    for it in run.pending.plan["items"]:
        if it["kind"] == "fingerprint" and it.get("profile") == prof and it.get("slot") == slot:
            return it
    return None


def paragraphs(text, lo, hi):
    return [p for p in text.split("\n\n") if lo <= count_words(p) <= hi and not measure.is_heading(p)]


# ---------- contrast (design: pipeline step 6) ----------

def contrast_sample(store_root, prof, slot):
    run = Run(store_root)
    texts = slot_texts(run, prof, slot)
    total = sum(count_words(t) for _, t in texts)
    old = _existing_fp(run.store, prof, slot)
    if old and old.get("contrast"):
        c = old["contrast"]
        active = {k for k, _ in texts}
        if set(c.get("sample_texts", [])) <= active and c.get("corpus_words_at_sample") and \
                abs(total - c["corpus_words_at_sample"]) / c["corpus_words_at_sample"] <= REUSE_CHANGE:
            run.state["steps"]["contrast"] += [f"{prof}/{slot}"] + [f"{prof}/{m}" for m in _mirrors(run, prof, slot)]
            run.save()
            return {"reuse": True, "message": "corpus changed by 20% or less since the last contrast pass; "
                                              "primary metrics and never-list are kept"}
    rng = random.Random(measure.slot_seed(prof, slot) + 1)
    by_text = [(k, paragraphs(t, 60, 200)) for k, t in texts]
    by_text = [(k, ps) for k, ps in by_text if ps]
    rng.shuffle(by_text)
    sample = []
    i = 0
    while len(sample) < CONTRAST_PARAS and by_text:
        k, ps = by_text[i % len(by_text)]
        cand = [p for p in ps if p not in [s["text"] for s in sample]]
        if cand:
            sample.append({"n": len(sample) + 1, "key": k, "text": rng.choice(cand)})
        else:
            by_text.pop(i % len(by_text))
            continue
        i += 1
        if i > 10 * CONTRAST_PARAS:
            break
    d = run.pending.work("contrast", prof, slot, "sample.json")
    d.write_text(json.dumps({"slot": slot, "words_at_sample": total, "paragraphs": sample}, indent=1,
                            ensure_ascii=False), encoding="utf-8")
    rewrites = d.parent / "rewrites"
    rewrites.mkdir(exist_ok=True)
    brief = ("Rewrite each paragraph below clearly, in a neutral, professional style, keeping its meaning "
             "and roughly its length. Do not imitate the original's style. Save rewrite N as N.txt.")
    return {"reuse": False, "sample": str(d), "rewrites_dir": str(rewrites), "brief_for_fresh_agent": brief,
            "paragraphs": sample}


def contrast_apply(store_root, prof, slot, rewrites_dir, fresh=True):
    run = Run(store_root)
    d = run.pending.work("contrast", prof, slot, "sample.json")
    sample = json.loads(d.read_text(encoding="utf-8"))
    rw = pathlib.Path(rewrites_dir)
    ai = [(p["n"], (rw / f"{p['n']}.txt").read_text(encoding="utf-8")) for p in sample["paragraphs"]
          if (rw / f"{p['n']}.txt").exists()]
    if len(ai) < max(3, len(sample["paragraphs"]) // 2):
        raise StoreError(f"only {len(ai)} rewrites found in {rw}")
    lang = slot.split(".")[0]
    it = _fp_item(run, prof, slot)
    if not it:
        raise StoreError(f"no fingerprint item for {prof}/{slot}; run `learn.py measure`")
    pl = run.pending.payload(it["id"])
    fp = pl["fingerprint"]
    ai_vals = measure.metrics("\n\n".join(t for _, t in ai), lang)
    flagged = []
    for m, v in fp["metrics"].items():
        w = v["value"]
        g = measure.METRICS[m]
        if w < g["floor"]:
            if ai_vals[m] - w > 2 * g["floor"]:
                flagged.append((m, 99.0))
            continue
        r = ai_vals[m] / w if w else 0
        sparse = g.get("sparse", g["shortfall"] <= 0.05)
        if r > g["overshoot"]:
            flagged.append((m, r / g["overshoot"]))
        elif not sparse and r < g["shortfall"]:
            flagged.append((m, g["shortfall"] / max(r, 1e-9)))
    primary = [m for m, _ in sorted(flagged, key=lambda x: -x[1])]
    for m in fp["metrics"]:
        fp["metrics"][m]["primary"] = m in primary
    fp["metric_list"] = "contrast"
    fp["contrast"] = {"sample_texts": sorted({p["key"] for p in sample["paragraphs"]}),
                      "corpus_words_at_sample": sample["words_at_sample"], "fresh_context": bool(fresh)}
    pl["fingerprint"] = fp
    stage.atomic_write(run.pending.dir / "items" / f"{it['id']}.json", json.dumps(pl, ensure_ascii=False, indent=1) + "\n")
    # never-list: 2- and 3-word phrases recurring across the rewrites that the writer never uses here
    corpus = "\n\n".join(t for _, t in slot_texts(run, prof, slot)).lower()
    cwords = " " + " ".join(words(corpus)) + " "
    sw = stage.stopwords(lang)
    counts = collections.Counter()
    for _, t in ai:
        ws = [w.lower() for w in words(t)]
        grams = set()
        for n in (2, 3):   # single words are mostly content shared with the originals, not style
            for i in range(len(ws) - n + 1):
                g = ws[i:i + n]
                if all(x in sw for x in g):
                    continue
                grams.add(" ".join(g))
        counts.update(grams)
    ai_words = sum(len(words(t)) for _, t in ai)
    min_rewrites = max(3, -(-3 * len(ai) // 10))   # in at least 3 rewrites, and at least 30% of them
    markers = []
    for g, c in counts.most_common():
        if c < min_rewrites or f" {g} " in cwords:
            continue
        if any(g in m["marker"] or m["marker"] in g for m in markers):
            continue
        total = sum(len(re.findall(r"(?<!\w)" + re.escape(g) + r"(?!\w)", t.lower())) for _, t in ai)
        markers.append({"marker": g, "ai_per_1k": round(total * 1000 / max(1, ai_words), 1), "writer_per_1k": 0.0})
        if len(markers) >= 15:
            break
    run.pending.remove_items(lambda i: i["kind"] == "never-list" and i.get("profile") == prof and i.get("slot") == slot)
    never_id = run.pending.add("never-list", "add", f"profiles/{prof}/{slot}.never.md",
                    f"{len(markers)} markers from {len(ai)} neutral rewrites" + ("" if fresh else " (not a fresh context: less reliable)"),
                    {"never": {"profile": prof, "slot": slot, "markers": markers}}, profile=prof, slot=slot)
    run.state["steps"]["contrast"].append(f"{prof}/{slot}")
    run.save()
    for m in _mirrors(run, prof, slot):
        mit = _fp_item(run, prof, m)
        if mit:
            mpl = run.pending.payload(mit["id"])
            for name in mpl["fingerprint"]["metrics"]:
                mpl["fingerprint"]["metrics"][name]["primary"] = name in primary
            mpl["fingerprint"]["metric_list"] = "contrast"
            mpl["fingerprint"]["contrast"] = fp["contrast"]
            stage.atomic_write(run.pending.dir / "items" / f"{mit['id']}.json",
                               json.dumps(mpl, ensure_ascii=False, indent=1) + "\n")
        run.pending.remove_items(lambda i: i["kind"] == "never-list" and i.get("profile") == prof and i.get("slot") == m)
        run.pending.add("never-list", "add", f"profiles/{prof}/{m}.never.md", f"same as {slot} (same texts)",
                        {"never": {"profile": prof, "slot": m, "markers": markers}, "follows": never_id},
                        profile=prof, slot=m)
        run.state["steps"]["contrast"].append(f"{prof}/{m}")
    run.save()
    return {"primary": primary, "never": [m["marker"] for m in markers], "next": _next(run)}


def _mirrors(run, prof, slot):
    return [o["slot"] for o in run.state.get("slots", []) if o["profile"] == prof and o.get("mirrors") == slot]


# ---------- lessons (spec §14) ----------

def lessons_sample(store_root, prof, slot):
    run = Run(store_root)
    texts = slot_texts(run, prof, slot)
    view = run.view()
    dated = sorted(texts, key=lambda kt: ((view.get(kt[0]) or {}).get("date") or "", kt[0]))
    per = max(300, QUAL_CAP // max(1, len(dated)))
    rng = random.Random(measure.slot_seed(prof, slot) + 2)
    parts, total = [], 0
    for k, t in dated:
        paras = t.split("\n\n")
        if count_words(t) <= per:
            chunk = paras
        else:
            startp = rng.randrange(0, max(1, len(paras)))
            chunk, n = [], 0
            for p in paras[startp:] + paras[:startp]:
                chunk.append(p)
                n += count_words(p)
                if n >= per:
                    break
        body = "\n\n".join(chunk)
        if total + count_words(body) > QUAL_CAP and parts:
            break
        parts.append(f"### text {k}\n\n{body}")
        total += count_words(body)
    existing = []
    page = run.store.root / "profiles" / prof / f"{slot}.md"
    if page.exists():
        _, _, existing = pages.parse_slot_page(page.read_text(encoding="utf-8"))
    out = run.pending.work("lessons", prof, slot, "sample.md")
    out.write_text("\n\n".join(parts), encoding="utf-8")
    return {"sample": str(out), "words": total, "texts_in_slot": len(texts),
            "existing_lessons": [{"id": x["id"], "section": x["section"], "text": x["text"]} for x in existing],
            "rejected": sorted(stage.rejected_normalised(run.store, prof, slot)),
            "sections": pages.SLOT_SECTIONS[:-1],
            "format": "lessons.yaml: list of {section, text, evidence: [text keys], quote}"}


def _norm_ws(s):
    return re.sub(r"\s+", " ", s).strip().lower()


def _rejected_ids(store, prof, slot, prefix):
    rf = store.root / "profiles" / prof / "rejected.yaml"
    if not rf.exists():
        return 0
    return max([0] + [int(e["rejects"].split("-")[1]) for e in read_store_file(rf, "rejected")["entries"]
                      if e.get("rejects", "").startswith(prefix + "-") and e.get("slot") == slot])


def lessons_apply(store_root, prof, slot, file, names=None, follows=None, sampled=None):
    run = Run(store_root)
    data = load_yaml_text(pathlib.Path(file).read_text(encoding="utf-8")) or []
    lang = slot.split(".")[0]
    texts = dict(slot_texts(run, prof, slot))
    # how many texts the lessons sample held: the "of" in "seen in 5 of 9 texts" (markdown contracts).
    # A mirror slot is never sampled; it is handed the sample of the slot it mirrors (review M5).
    if sampled is None:
        sample = run.pending.work("lessons", prof, slot, "sample.md")
        sampled = set(re.findall(r"(?m)^### text (\S+)$", sample.read_text(encoding="utf-8"))) \
            if sample.exists() else set()
    sampled = set(sampled) & set(texts)
    of = len(sampled) or len(texts)
    rejected = stage.rejected_normalised(run.store, prof, slot)
    page = run.store.root / "profiles" / prof / f"{slot}.md"
    meta, existing = {}, []
    if page.exists():
        meta, _, existing = pages.parse_slot_page(page.read_text(encoding="utf-8"))
    ex_by_norm = {stage.normalise_lesson(x["text"], lang): x for x in existing}
    run.pending.remove_items(lambda i: i["kind"] == "lesson" and i.get("profile") == prof and i.get("slot") == slot)
    last = max(meta.get("last_id") or 0, _rejected_ids(run.store, prof, slot, "l"),
               stage._plan_ids(run.pending, "lesson", prof, slot))
    made = {}
    kept, dropped, problems = set(), [], []
    for les in data:
        if les.get("section") not in pages.SLOT_SECTIONS[:-1]:
            problems.append(f"unknown section {les.get('section')!r}: {les.get('text')}")
            continue
        norm = stage.normalise_lesson(les["text"], lang)
        if norm in rejected:
            dropped.append(les["text"])
            continue
        # evidence counts only texts the model was shown, so "N of M" never exceeds the sample
        ev = sorted({k for k in les.get("evidence", []) if k in (sampled or texts)})
        quote = les.get("quote") or ""
        qkey = next((k for k in ev if quote and _norm_ws(quote) in _norm_ws(texts[k])), None)
        if quote and not qkey:
            problems.append(f"quote not found in its evidence texts: {quote[:60]}")
            quote = ""
        repl = []
        if quote:
            quote, repl = redactmod.redact(quote, names)
        count = len(set(ev))
        if count == 0:
            problems.append(f"no valid evidence: {les['text']}")
            continue
        cur = ex_by_norm.get(norm)
        if cur:
            lid = cur["id"]
            kept.add(lid)
        else:
            last += 1
            lid = f"l-{last:03d}"
        lesson = {"profile": prof, "slot": slot, "id": lid, "section": les["section"], "text": les["text"].strip(),
                  "evidence": {"count": count, "of": of, "quote": quote}, "seen_once": count < 2,
                  "unit": "text",
                  "evidence_keys": ev, "quote_key": qkey}
        new_line_ev = pages.evidence_text(lesson)
        if cur and cur["section"] == lesson["section"] and cur["evidence_raw"] == new_line_ev and cur["text"] == lesson["text"] \
                and (cur["section"] != "Seen once") == (count >= 2):
            continue
        shown = "; ".join(f"{r['found']} → {r['placeholder']}" for r in repl)
        payload = {"lesson": lesson}
        if follows and norm in follows:
            payload["follows"] = follows[norm]
        made[norm] = run.pending.add("lesson", "modify" if cur else "add", f"profiles/{prof}/{slot}.md",
                                     f"{lid} ({'Seen once' if count < 2 else les['section']}): {lesson['text']} _({new_line_ev})_"
                                     + (f" [redacted: {shown}]" if shown else ""),
                                     payload, profile=prof, slot=slot, ref=lid)
    for x in existing:
        if x["id"] not in kept and stage.normalise_lesson(x["text"], lang) not in {stage.normalise_lesson(d["text"], lang) for d in data}:
            run.pending.add("lesson", "remove", f"profiles/{prof}/{slot}.md",
                            f"{x['id']} no longer supported: {x['text']}", {"lesson": {**x, "profile": prof, "slot": slot}},
                            profile=prof, slot=slot, ref=x["id"])
    run.state["steps"]["lessons"].append(f"{prof}/{slot}")
    run.save()
    for m in _mirrors(run, prof, slot):
        lessons_apply(store_root, prof, m, file, names, follows=made, sampled=sampled)
    return {"dropped_as_rejected": dropped, "problems": problems, "next": _next(Run(store_root))}


# ---------- vocabulary ----------

def vocab_apply(store_root, prof, file):
    run = Run(store_root)
    data = load_yaml_text(pathlib.Path(file).read_text(encoding="utf-8")) or []
    vf = run.store.root / "profiles" / prof / "vocabulary.yaml"
    base = read_store_file(vf, "vocabulary") if vf.exists() else {"schema_version": version_of("vocabulary"), "entries": []}
    have = {e["text"].lower() for e in base["entries"]}
    rejected = set()
    rf = run.store.root / "profiles" / prof / "rejected.yaml"
    if rf.exists():
        rejected = {e["text"].lower() for e in read_store_file(rf, "rejected")["entries"] if e["kind"] == "vocabulary"}
    run.pending.remove_items(lambda i: i["kind"] == "vocabulary" and i.get("profile") == prof)
    last = max([base.get("last_id") or 0, _rejected_ids(run.store, prof, None, "v"),
                stage._plan_ids(run.pending, "vocab", prof)] + [int(e["id"].split("-")[1]) for e in base["entries"]])
    added, skipped = [], []
    today = utcnow().date().isoformat()
    own = measure.own_texts(run.view(), run.text, run.store.facets, prof)
    # favoured phrases already approved: re-measure their rate on the texts as staged now
    for e in base["entries"]:
        if e["kind"] != "phrase":
            continue
        rate = measure.phrase_rate(e["text"], own, today)
        if rate is None:
            continue            # nothing to measure on: keep the rate it has
        old_rate = {k: v for k, v in (e.get("rate") or {}).items() if k != "measured"}
        if {k: v for k, v in rate.items() if k != "measured"} != old_rate:
            upd = {**e, "rate": rate}
            run.pending.add("vocabulary", "modify", f"profiles/{prof}/vocabulary.yaml",
                            f"{e['id']} phrase: {e['text']}: rate now {rate['per_1k']} per 1,000 words, "
                            f"in {rate['texts']} of {rate['of']} texts" + (" (private)" if e.get("private") else ""),
                            {"vocab": {"profile": prof, "entry": upd}}, profile=prof, ref=e["id"])
    for v in data:
        t = v["text"].strip()
        if t.lower() in have or t.lower() in rejected:
            skipped.append(t)
            continue
        last += 1
        kind = v.get("kind", "term")
        if kind == "keep":
            kind = "phrase"          # the version 1 name (design: Schemas and migrations)
        entry = {"id": f"v-{last:03d}", "text": t, "kind": kind, "private": bool(v.get("private", False)),
                 "created": today}
        if v.get("note"):
            entry["note"] = v["note"]
        if kind == "phrase":
            rate = measure.phrase_rate(t, own, today)
            if rate:
                entry["rate"] = rate
        run.pending.add("vocabulary", "add", f"profiles/{prof}/vocabulary.yaml",
                        f"{entry['id']} {entry['kind']}: {t}" + (" (private)" if entry["private"] else ""),
                        {"vocab": {"profile": prof, "entry": entry}}, profile=prof, ref=entry["id"])
        added.append(t)
    run.state["steps"]["vocab"].append(prof)
    run.save()
    return {"added": added, "skipped": skipped, "next": _next(run)}


# ---------- examples ----------

def examples_sample(store_root, prof, slot):
    run = Run(store_root)
    texts = slot_texts(run, prof, slot)
    rng = random.Random(measure.slot_seed(prof, slot) + 3)
    cands = []
    for k, t in texts:
        for p in paragraphs(t, 60, 180):
            cands.append({"key": k, "text": p})
    rng.shuffle(cands)
    seen, pick = set(), []
    for c in cands:
        if c["key"] in seen and len({x["key"] for x in cands}) > len(seen):
            continue
        seen.add(c["key"])
        pick.append(c)
        if len(pick) >= EXAMPLE_CANDIDATES:
            break
    out = run.pending.work("examples", prof, slot, "candidates.json")
    out.write_text(json.dumps(pick, indent=1, ensure_ascii=False), encoding="utf-8")
    return {"candidates": pick, "format": "examples.yaml: list of {key, text, habit}; names: [{name, placeholder}]"}


def examples_apply(store_root, prof, slot, file):
    run = Run(store_root)
    data = load_yaml_text(pathlib.Path(file).read_text(encoding="utf-8")) or {}
    items = data.get("examples", data if isinstance(data, list) else [])
    names = data.get("names") if isinstance(data, dict) else None
    texts = dict(slot_texts(run, prof, slot))
    ef = run.store.root / "profiles" / prof / f"{slot}.examples.md"
    meta, cur = ({}, [])
    if ef.exists():
        meta, cur = pages.parse_examples(ef.read_text(encoding="utf-8"))
    run.pending.remove_items(lambda i: i["kind"] == "example" and i.get("profile") == prof and i.get("slot") == slot)
    last = max([meta.get("last_id") or 0, _rejected_ids(run.store, prof, slot, "e"),
                stage._plan_ids(run.pending, "example", prof, slot)] + [int(e["id"].split("-")[1]) for e in cur])
    have = {_norm_ws(e["text"]) for e in cur}
    rejected_hashes = set()
    rf = run.store.root / "profiles" / prof / "rejected.yaml"
    if rf.exists():
        rejected_hashes = {e["normalised"] for e in read_store_file(rf, "rejected")["entries"]
                           if e["kind"] == "example" and e.get("slot") == slot}
    problems, added = [], []
    for ex in items:
        if ex["key"] not in texts or _norm_ws(ex["text"]) not in _norm_ws(texts[ex["key"]]):
            problems.append(f"passage not found in text {ex['key'][:12]}: {ex['text'][:50]}")
            continue
        red, repl = redactmod.redact(ex["text"].strip(), names)
        import hashlib
        if _norm_ws(red) in have or "sha256:" + hashlib.sha256(_norm_ws(red).encode("utf-8")).hexdigest() in rejected_hashes:
            continue
        last += 1
        e = {"profile": prof, "slot": slot, "id": f"e-{last:03d}", "source": ex["key"],
             "habit": ex.get("habit", ""), "redaction": redactmod.record(repl), "text": red}
        shown = "; ".join(f"{r['found']} → {r['placeholder']}" for r in repl)
        run.pending.add("example", "add", f"profiles/{prof}/{slot}.examples.md",
                        f"{e['id']} ({e['habit'] or 'example'}): {red[:90]}…" + (f" [redacted: {shown}]" if shown else ""),
                        {"example": e}, profile=prof, slot=slot, ref=e["id"])
        added.append(e["id"])
    for r in data.get("remove", []) if isinstance(data, dict) else []:
        old = next((e for e in cur if e["id"] == r), None)
        if old:
            run.pending.add("example", "remove", f"profiles/{prof}/{slot}.examples.md", f"{r} removed",
                            {"example": {**old, "profile": prof, "slot": slot}}, profile=prof, slot=slot, ref=r)
    run.state["steps"]["examples"].append(f"{prof}/{slot}")
    run.save()
    return {"added": added, "problems": problems, "next": _next(run)}


# ---------- rulings ----------

def add_rule(store_root, prof, text, slot=None, from_lesson=None):
    run = Run(store_root)
    rf = run.store.root / "profiles" / prof / "rulings.yaml"
    base = read_store_file(rf, "rulings") if rf.exists() else {"schema_version": version_of("rulings"), "entries": []}
    last = max([base.get("last_id") or 0] + [int(e["id"].split("-")[1]) for e in base["entries"]])
    for it in run.pending.plan["items"]:
        if it["kind"] == "ruling" and it.get("profile") == prof:
            last = max(last, int(run.pending.payload(it["id"])["ruling"]["entry"]["id"].split("-")[1]))
    entry = {"id": f"r-{last + 1:03d}", "text": text.strip(), "slot": slot,
             "origin": "promoted" if from_lesson else "stated", "created": utcnow().date().isoformat(),
             "personal_data": "none"}
    if from_lesson:
        entry["promoted_from"] = from_lesson
    run.pending.add("ruling", "add", f"profiles/{prof}/rulings.yaml",
                    f"{entry['id']}: {entry['text']}" + (f" (from {from_lesson})" if from_lesson else ""),
                    {"ruling": {"profile": prof, "entry": entry}}, profile=prof, slot=slot, ref=entry["id"],
                    decision="approved")
    return {"ruling": entry["id"]}


# ---------- what next ----------

def _next(run):
    st = run.state["steps"]
    q = questions(run)
    if q["undecided"] or q["new_profiles_need"]:
        return "answer the ownership questions (learn.py questions / answer)"
    unknown = [k for k, i in run.state["texts"].items() if i["result"] in LEARNABLE
               and not excluded_now(run, i["path"]) and _type_for(run, k, i) in ("?", None) and _owned(run, k, i)]
    if unknown:
        return f"assign a type to {len(unknown)} texts (learn.py types / set-types)"
    if not st["texts"]:
        return "learn.py stage-texts"
    if not st["measure"]:
        return "learn.py measure"
    todo = []
    for s in run.state.get("slots", []):
        if s.get("mirrors"):
            continue
        key = f"{s['profile']}/{s['slot']}"
        if key not in st["contrast"]:
            todo.append(f"contrast {key}")
        if key not in st["lessons"]:
            todo.append(f"lessons {key}")
        if not s["pooled"] and key not in st["examples"]:
            todo.append(f"examples {key}")
    for p in {s["profile"] for s in run.state.get("slots", [])}:
        if p not in st["vocab"]:
            todo.append(f"vocabulary {p}")
    if todo:
        return "model steps left: " + "; ".join(todo[:6]) + (f" (+{len(todo) - 6} more)" if len(todo) > 6 else "")
    return "show the diff (stage.py diff), then decide and commit"


def next_step(store_root):
    run = Run(store_root)
    return {"next": _next(run)}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--store", required=True)
    ap.add_argument("action")
    ap.add_argument("--target", action="append")
    ap.add_argument("--tag", action="append")
    ap.add_argument("--profile")
    ap.add_argument("--slot")
    ap.add_argument("--lang")
    ap.add_argument("--type")
    ap.add_argument("--file")
    ap.add_argument("--rewrites")
    ap.add_argument("--fresh", default="true")
    ap.add_argument("--text")
    ap.add_argument("--from", dest="from_lesson")
    ap.add_argument("--names")
    ap.add_argument("--sources", help="init: sources_root relative to the store")
    ap.add_argument("--since", type=int, help="start: weight writing from this year onward more")
    ap.add_argument("--types", help="init: comma-separated text types")
    a = ap.parse_args(argv)
    try:
        s = a.store
        act = a.action
        if act == "init":
            out = init(s, a.sources or "..", a.profile or "me", (a.types or "essay").split(","), a.lang or "en")
        elif act == "start":
            out = start(s, a.target, a.tag, a.profile, a.lang, a.type, a.since)
        elif act == "questions":
            out = questions(Run(s))
        elif act == "answer":
            out = answer(s, a.file)
        elif act == "types":
            out = types(s)
        elif act == "set-types":
            out = set_types(s, a.file)
        elif act == "mail-names":
            out = mail_names(s, a.file)
        elif act == "stage-texts":
            out = stage_texts(s)
        elif act == "measure":
            out = do_measure(s)
        elif act == "contrast-sample":
            out = contrast_sample(s, a.profile, a.slot)
        elif act == "contrast-apply":
            out = contrast_apply(s, a.profile, a.slot, a.rewrites, a.fresh.lower() != "false")
        elif act == "lessons-sample":
            out = lessons_sample(s, a.profile, a.slot)
        elif act == "lessons-apply":
            names = load_yaml_text(pathlib.Path(a.names).read_text(encoding="utf-8")) if a.names else None
            out = lessons_apply(s, a.profile, a.slot, a.file, names)
        elif act == "vocab-apply":
            out = vocab_apply(s, a.profile, a.file)
        elif act == "examples-sample":
            out = examples_sample(s, a.profile, a.slot)
        elif act == "examples-apply":
            out = examples_apply(s, a.profile, a.slot, a.file)
        elif act == "rule":
            out = add_rule(s, a.profile, a.text, a.slot, a.from_lesson)
        elif act == "next":
            out = next_step(s)
        else:
            ap.error(f"unknown action {act}")
    except StoreError as e:
        print(json.dumps({"status": "error", "message": str(e)}))
        return 2
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
