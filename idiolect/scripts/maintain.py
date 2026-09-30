"""forget, rollback, prune and delete: the only modes that delete (spec §8, §11, §35). Each builds a
proposal in the pending area; nothing changes until the writer approves and `stage.py commit` runs.

    python3 maintain.py --store S forget --source REL_PATH_OR_KEY [--profile P] [--ownership own|assisted|exclude]
    python3 maintain.py --store S rollback --profile P [--to SNAPSHOT]
    python3 maintain.py --store S prune --profile P [--keep 10]
    python3 maintain.py --store S delete --profile P
"""
import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import measure  # noqa: E402
import stage  # noqa: E402
from adapters import extract  # noqa: E402
from common import StoreError, content_hash, read_store_file, utcnow  # noqa: E402
import detect  # noqa: E402


def _entries_for(store, source):
    texts = store.manifest["texts"]
    if source in texts:
        return {source: texts[source]}          # by key: exactly that text
    # by path: the current version and its segments; superseded versions are history (spec §8), and
    # forgotten ones count only when nothing else is there
    at = {k: e for k, e in texts.items() if e.get("path") == source and e["status"] != "superseded"}
    live = {k: e for k, e in at.items() if e["status"] != "forgotten"}
    return live or at


def _reextract(store, entry, key):
    """The cleaned text for key if the source file still gives that hash, else None."""
    if not entry.get("path"):
        return None
    f = store.sources_root / entry["path"]
    if not f.exists():
        return None
    ex = extract(f)
    if ex is None:
        return None
    for t in detect.split(ex.blocks):
        if t.key == key:
            return t.text
    return None


def _remeasure(store, pending, patches, profiles, corpus_add):
    """Fingerprint items for every slot of the affected profiles, on the manifest after `patches`."""
    view = json.loads(json.dumps(store.manifest["texts"]))
    for p in patches:
        stage._apply_manifest_patch(view, p)

    def get_text(k):
        return corpus_add[k] if k in corpus_add else store.corpus_text(k)

    for prof in sorted(profiles):
        keep = {}
        pdir = store.root / "profiles" / prof
        for f in pdir.glob("*.json"):
            fp = read_store_file(f, "fingerprint")
            keep[fp["slot"]] = fp
        py = pdir / "profile.yaml"
        since = read_store_file(py, "profile").get("since") if py.exists() else None
        new = measure.fingerprints_view(view, get_text, store.facets, prof, since=since, keep=keep)
        seen = set()
        for x in new:
            fp = x["fingerprint"]
            seen.add(fp["slot"])
            pending.add("fingerprint", "modify" if fp["slot"] in keep else "add",
                        f"profiles/{prof}/{fp['slot']}.json",
                        f"re-measured: {fp['counts']['texts']} texts, confidence {fp['confidence']['level']}",
                        {"fingerprint": fp}, profile=prof, slot=fp["slot"])
        for slot in sorted(set(keep) - seen):
            pending.add("deletion", "remove", f"profiles/{prof}/{slot}.json",
                        "slot has no texts left: fingerprint and never-list removed, lessons and examples emptied",
                        stage.retire_slot_payload(store, prof, slot), profile=prof, slot=slot)


def forget(store_root, source, profile=None, ownership=None):
    store, pending, _ = stage.begin(store_root, "forget", [profile] if profile else [], atomic=True)
    try:
        entries = _entries_for(store, source)
        if not entries:
            raise StoreError(f"no manifest entry for {source}")
        if profile and not (store.root / "profiles" / profile / "profile.yaml").exists():
            raise StoreError(f"no profile {profile}; a new profile is created by learn, with its consent recorded")
        if profile and not ownership and not any(profile in e["profiles"] for e in entries.values()):
            raise StoreError(f"{source} does not feed profile {profile}")
        today = utcnow().date().isoformat()
        patches, corpus_add, affected, losing = [], {}, set(), {}
        for key, e in sorted(entries.items()):
            profs = [profile] if profile else (list(e["profiles"]) or [store.config["default_profile"]])
            affected.update(profs)
            if not ownership or ownership != "own":
                losing.setdefault(key, set()).update(profs)
            if ownership:
                recs = {p: {"ownership": ownership, "decided": today, "decided_by": "writer"} for p in profs}
                if e["status"] == "forgotten":
                    # a forgotten entry's old records are history; re-owning starts from these only
                    after = dict(recs)
                    patch = {"key": key, "replace_profiles": recs}
                else:
                    after = dict(e["profiles"])
                    after.update(recs)
                    patch = {"key": key, "profiles": recs}
                owned = any(r["ownership"] == "own" for r in after.values())
                summary = f"{e.get('path') or key}: ownership {ownership} for {', '.join(profs)}"
                if owned and (not e.get("cached") or e["status"] == "forgotten"):
                    text = _reextract(store, e, key)
                    if text is None:
                        raise StoreError(f"{e.get('path')} no longer gives the same text; learn it again instead")
                    corpus_add[key] = text
                    patch["set"] = {"status": "active"}
                    patch["cache"] = True
                    summary += "; text extracted and cached"
                    pending.add("corpus-text", "add", f"corpus/{key.replace('#', '-')}.txt", summary,
                                {"corpus": {key: text}, "manifest": [patch]}, profile=profs[0], ref=key)
                elif not owned and e.get("cached"):
                    pending.add("deletion", "modify", f"corpus/{key.replace('#', '-')}.txt",
                                summary + "; cached text deleted (no profile owns it now)",
                                {"manifest": [patch], "delete": [f"corpus/{key.replace('#', '-')}.txt"]},
                                profile=profs[0], ref=key)
                else:
                    pending.add("ownership", "modify", "corpus/manifest.json", summary, {"manifest": [patch]},
                                profile=profs[0], ref=key)
                patches.append(patch)
            else:
                remaining = [p for p in e["profiles"] if p not in profs]
                if remaining:
                    # an `exclude` record per file, not a removed record: it outranks the folder rule, so
                    # the next learn does not give the text back to this profile (spec §7.1)
                    patch = {"key": key, "profiles": {p: {"ownership": "exclude", "decided": today,
                                                          "decided_by": "writer"} for p in profs}}
                    after_own = any(e["profiles"][p]["ownership"] == "own" for p in remaining)
                    pl = {"manifest": [patch]}
                    summary = f"{e.get('path') or key}: forgotten for {', '.join(profs)}, kept for {', '.join(remaining)}"
                    if e.get("cached") and not after_own:
                        pl["delete"] = [f"corpus/{key.replace('#', '-')}.txt"]
                        summary += "; cached text deleted"
                    pending.add("deletion" if "delete" in pl else "ownership", "modify", "corpus/manifest.json",
                                summary, pl, profile=profs[0], ref=key)
                else:
                    patch = {"key": key, "set": {"status": "forgotten", "holdout": False},
                             "profiles": {}, "force": {"cached": False}}
                    pl = {"manifest": [patch]}
                    if (store.root / "corpus" / (key.replace("#", "-") + ".txt")).exists():
                        pl["delete"] = [f"corpus/{key.replace('#', '-')}.txt"]
                    pending.add("deletion", "remove", f"corpus/{key.replace('#', '-')}.txt",
                                f"{e.get('path') or key}: forgotten; cached text deleted", pl,
                                profile=profs[0], ref=key)
                patches.append(patch)
        _drop_examples(store, pending, losing)
        _blank_quotes(store, pending, losing)
        _remeasure(store, pending, patches, affected, corpus_add)
        return {"proposed": len(pending.plan["items"]), "next": "stage.py diff, decide, commit"}
    except Exception:
        stage.discard(store_root)
        raise


def _keep_last_id(content, current_path):
    """A restored page or list keeps the highest id the current version used (spec §14.2)."""
    import pages
    from common import dump_yaml, load_yaml_text
    if not current_path.exists():
        return content
    cur = current_path.read_text(encoding="utf-8")
    try:
        if current_path.suffix == ".md" and content.startswith("---"):
            meta_new, secs = pages.split_page(content)
            meta_cur, _ = pages.split_page(cur)
            if "last_id" in meta_new or "last_id" in meta_cur:
                n = max(meta_new.get("last_id") or 0, meta_cur.get("last_id") or 0)
                if n != meta_new.get("last_id"):
                    head, body = content.split("\n---\n", 1)
                    meta_new["last_id"] = n
                    return "---\n" + dump_yaml(meta_new).rstrip() + "\n---\n" + body
        elif current_path.suffix == ".yaml":
            new, old = load_yaml_text(content) or {}, load_yaml_text(cur) or {}
            if "markers" in new:                      # a flavour file (spec §34)
                # rejections are permanent until the writer lifts them, as rejected.yaml is not rolled back
                ids = [int(e["id"].split("-")[1]) for e in old.get("markers", []) + old.get("rejected", [])]
                n = max([new.get("last_id") or 0, old.get("last_id") or 0] + ids)
                have = {r["id"] for r in new.get("rejected", [])}
                extra = [r for r in old.get("rejected", []) if r["id"] not in have]
                gone = {r["id"] for r in extra}
                if n != new.get("last_id") or extra:
                    new["last_id"] = n
                    if extra:
                        new["rejected"] = new.get("rejected", []) + extra
                        new["markers"] = [m for m in new.get("markers", []) if m["id"] not in gone]
                    return dump_yaml(new)
            elif "entries" in new:
                ids = [int(e["id"].split("-")[1]) for e in old.get("entries", [])]
                n = max([new.get("last_id") or 0, old.get("last_id") or 0] + ids)
                if n != new.get("last_id"):
                    new["last_id"] = n
                    return dump_yaml(new)
    except Exception:  # noqa: BLE001 - a page that does not parse is restored as it was
        return content
    return content


def _drop_examples(store, pending, losing):
    """Examples drawn from a text a profile no longer has are removed with it (review I6)."""
    import pages
    for key, profs in losing.items():
        for prof in sorted(profs):
            for f in sorted((store.root / "profiles" / prof).glob("*.examples.md")):
                slot = f.name[: -len(".examples.md")]
                _, exs = pages.parse_examples(f.read_text(encoding="utf-8"))
                for ex in exs:
                    if ex.get("source") == key:
                        pending.add("example", "remove", f"profiles/{prof}/{slot}.examples.md",
                                    f"{ex['id']} came from the forgotten text; removed",
                                    {"example": {**ex, "profile": prof, "slot": slot}}, profile=prof, slot=slot,
                                    ref=ex["id"])


def _blank_quotes(store, pending, losing):
    """A lesson quote taken from a forgotten text loses its quote now; the lesson itself is refreshed at
    the next learn (review I5)."""
    import pages
    import re as _re
    norm = lambda t: _re.sub(r"\s+", " ", t).strip().lower()  # noqa: E731
    for key, profs in losing.items():
        try:
            text = norm(store.corpus_text(key))
        except StoreError:
            continue
        for prof in sorted(profs):
            for f in sorted((store.root / "profiles" / prof).glob("*.md")):
                if f.name.endswith((".examples.md", ".never.md", ".edits.md")) or f.name == "changelog.md":
                    continue
                slot = f.name[:-3]
                _, _, lessons = pages.parse_slot_page(f.read_text(encoding="utf-8"))
                for les in lessons:
                    m = _re.search(r'"(.+)"', les["evidence_raw"])
                    if m and norm(m.group(1)) in text:
                        raw = les["evidence_raw"][: m.start()].rstrip("; ").strip()
                        new = {**les, "profile": prof, "slot": slot, "evidence_raw": raw}
                        pending.add("lesson", "modify", f"profiles/{prof}/{slot}.md",
                                    f"{les['id']}: quote came from the forgotten text; removed",
                                    {"lesson": new}, profile=prof, slot=slot, ref=les["id"])


def _snap_order(name):
    base, _, n = name.partition("Z-")
    return (base if n else name.rstrip("Z"), int(n) if n.isdigit() else 1)


def _snapshots(store, profile):
    d = store.root / "profiles" / profile / "snapshots"
    names = [p.name for p in d.iterdir() if p.is_dir() and not p.name.endswith(".tmp")] if d.exists() else []
    return sorted(names, key=_snap_order)


def rollback(store_root, profile, to=None):
    store, pending, _ = stage.begin(store_root, "rollback", [profile], atomic=True)
    try:
        snaps = _snapshots(store, profile)
        if not snaps:
            raise StoreError(f"profile {profile} has no snapshots")
        name = to or snaps[-1]
        if name not in snaps:
            raise StoreError(f"no snapshot {name}; have: {', '.join(snaps)}")
        sdir = store.root / "profiles" / profile / "snapshots" / name
        pdir = store.root / "profiles" / profile
        snap_files = {p.relative_to(sdir).as_posix() for p in sdir.rglob("*") if p.is_file()}
        snap_files.discard("manifest-entries.json")
        snap_files.discard("rejected.yaml")      # rejections are permanent until the writer lifts them
        cur_files = {p.relative_to(pdir).as_posix() for p in pdir.rglob("*") if p.is_file()
                     and p.relative_to(pdir).parts[0] != "snapshots"} - {"rejected.yaml"}
        for rel in sorted(snap_files):
            content = _keep_last_id((sdir / rel).read_text(encoding="utf-8"), pdir / rel)
            cur = pdir / rel
            if cur.exists() and cur.read_text(encoding="utf-8") == content:
                continue
            pending.add("restore", "modify" if cur.exists() else "add", f"profiles/{profile}/{rel}",
                        f"restore {rel} from {name}", {"restore": {f"profiles/{profile}/{rel}": content}},
                        profile=profile)
        for rel in sorted(cur_files - snap_files):
            slot = rel[:-3] if rel.endswith(".md") and not rel.endswith((".never.md", ".examples.md", ".edits.md")) \
                and rel != "changelog.md" and "/" not in rel else None
            if rel.endswith(".examples.md"):
                slot = rel[: -len(".examples.md")]
            if rel.endswith(".flavour.yaml") and "/" not in rel:
                from common import dump_yaml, load_yaml_text
                cur = load_yaml_text((pdir / rel).read_text(encoding="utf-8")) or {}
                last = max([cur.get("last_id") or 0] + [int(x["id"].split("-")[1]) for x in cur.get("markers", [])])
                empty = {**cur, "last_id": last, "markers": [], "origins": [], "strength": "none",
                         "rate": {**cur.get("rate", {}), "per_1k": 0, "texts": 0, "max_per_1k": 0}}
                pending.add("restore", "modify", f"profiles/{profile}/{rel}",
                            f"{rel} was created after {name}; emptied (ids and rejections stay)",
                            {"restore": {f"profiles/{profile}/{rel}": dump_yaml(empty)}}, profile=profile)
                continue
            if rel in ("vocabulary.yaml", "rulings.yaml"):
                from common import dump_yaml, load_yaml_text, version_of
                cur = load_yaml_text((pdir / rel).read_text(encoding="utf-8")) or {}
                last = max([cur.get("last_id") or 0] + [int(x["id"].split("-")[1]) for x in cur.get("entries", [])])
                pending.add("restore", "modify", f"profiles/{profile}/{rel}",
                            f"{rel} was created after {name}; emptied (ids stay used)",
                            {"restore": {f"profiles/{profile}/{rel}": dump_yaml(
                                {"schema_version": version_of(rel.split(".")[0]), "last_id": last, "entries": []})}},
                            profile=profile)
                continue
            if slot:
                # a page keeps its last_id when emptied, so ids created after the snapshot are never reused
                pl = stage.retire_slot_payload(store, profile, slot)
                content = pl["restore"].get(f"profiles/{profile}/{rel}")
                if content:
                    pending.add("restore", "modify", f"profiles/{profile}/{rel}",
                                f"{rel} was created after {name}; emptied (ids stay used)",
                                {"restore": {f"profiles/{profile}/{rel}": content}}, profile=profile)
                    continue
            pending.add("deletion", "remove", f"profiles/{profile}/{rel}", f"{rel} was created after {name}",
                        {"delete": [f"profiles/{profile}/{rel}"]}, profile=profile)
        then = read_store_file(sdir / "manifest-entries.json", "manifest-entries")["texts"]
        for key, e in sorted(store.manifest["texts"].items()):
            # a forgotten text is used by nobody, whatever records it still carries (review I5)
            others = [] if e["status"] == "forgotten" else \
                [p for p in e["profiles"] if p != profile and e["profiles"][p]["ownership"] == "own"]
            if key in then:
                old = then[key]
                want = {"status": old["status"], "holdout": old.get("holdout", False)}
                if others and (e["status"], e.get("holdout", False)) != (want["status"], want["holdout"]):
                    # status belongs to the text, which other profiles still use: only this profile's
                    # record is restored (spec §8, rollback of a shared text)
                    rec = old["profiles"].get(profile)
                    if e["profiles"].get(profile) != rec:
                        pending.add("status", "modify", "corpus/manifest.json",
                                    f"{e.get('path') or key}: {profile}'s record restored; status kept "
                                    f"because {', '.join(sorted(others))} also use this text",
                                    {"manifest": [{"key": key, "profiles": {profile: rec} if rec else {profile: None}}]},
                                    profile=profile, ref=key)
                    elif e["status"] == "active" and old["status"] == "superseded" and profile in e["profiles"]:
                        pending.add("status", "modify", "corpus/manifest.json",
                                    f"{e.get('path') or key}: newer version removed from {profile}; kept for "
                                    f"{', '.join(sorted(others))}", {"manifest": [{"key": key, "profiles": {profile: None}}]},
                                    profile=profile, ref=key)
                    continue
                if old.get("superseded_by"):
                    want["superseded_by"] = old["superseded_by"]
                rec = old["profiles"].get(profile)
                same = (e["status"] == want["status"] and e.get("holdout", False) == want["holdout"]
                        and e["profiles"].get(profile) == rec)
                if same:
                    continue
                if e["status"] == "forgotten" and rec:
                    patch = {"key": key, "set": want, "replace_profiles": {profile: rec}}
                else:
                    patch = {"key": key, "set": want, "profiles": {profile: rec}}
                pl = {"manifest": [patch]}
                summary = f"{e.get('path') or key}: back to {old['status']}"
                corpus = store.root / "corpus" / (key.replace("#", "-") + ".txt")
                will_own = rec and rec["ownership"] == "own" and old["status"] != "forgotten"
                if not will_own and corpus.exists() and not any(
                        r["ownership"] == "own" for p, r in e["profiles"].items() if p != profile):
                    pl["delete"] = [f"corpus/{key.replace('#', '-')}.txt"]
                    summary += "; cached text deleted"
                if will_own and not corpus.exists():
                    text = _reextract(store, e, key)
                    if text is not None:
                        pl["corpus"] = {key: text}
                        patch["cache"] = True
                        summary += "; text re-extracted"
                    else:
                        patch["set"]["status"] = "unreachable"
                        patch["force"] = {"cached": False}
                        summary += "; source changed or gone, restored as unreachable without text"
                pending.add("status", "modify", "corpus/manifest.json", summary, pl, profile=profile, ref=key)
            elif profile in e["profiles"]:
                others = [p for p in e["profiles"] if p != profile]
                if others:
                    patch = {"key": key, "profiles": {profile: None}}
                    pl = {"manifest": [patch]}
                    if e.get("cached") and not any(e["profiles"][p]["ownership"] == "own" for p in others):
                        pl["delete"] = [f"corpus/{key.replace('#', '-')}.txt"]
                    summary = f"{e.get('path') or key}: added after {name}; removed from {profile}"
                else:
                    # the entry did not exist at the snapshot: rollback removes it, so a later learn sees
                    # the text as new again (it is not "forgotten": the writer never forgot it)
                    patch = {"key": key, "remove": True}
                    pl = {"manifest": [patch]}
                    if (store.root / "corpus" / (key.replace("#", "-") + ".txt")).exists():
                        pl["delete"] = [f"corpus/{key.replace('#', '-')}.txt"]
                    summary = f"{e.get('path') or key}: added after {name}; removed from the ledger"
                pending.add("deletion" if "delete" in pl else "status", "modify", "corpus/manifest.json",
                            summary, pl, profile=profile, ref=key)
        # entries the snapshot had that the manifest no longer has (e.g. removed by an earlier rollback)
        for key, old in sorted(then.items()):
            if key in store.manifest["texts"] or profile not in old["profiles"]:
                continue
            entry = json.loads(json.dumps(old))
            entry["profiles"] = {profile: old["profiles"][profile]}
            patch = {"key": key, "create": entry}
            pl = {"manifest": [patch]}
            summary = f"{old.get('path') or key}: back as {old['status']}"
            owned = entry["profiles"][profile]["ownership"] == "own" and old["status"] != "forgotten"
            if owned:
                text = _reextract(store, entry, key)
                if text is not None:
                    pl["corpus"] = {key: text}
                    patch["cache"] = True
                    summary += "; text re-extracted"
                elif old["status"] == "active":
                    entry["status"] = "unreachable"
                    summary += "; source changed or gone, restored as unreachable without text"
            entry.pop("superseded_by", None) if entry["status"] != "superseded" else None
            pending.add("status", "add", "corpus/manifest.json", summary, pl, profile=profile, ref=key)
        return {"proposed": len(pending.plan["items"]), "snapshot": name, "next": "stage.py diff, decide, commit"}
    except Exception:
        stage.discard(store_root)
        raise


def prune(store_root, profile, keep=10):
    store, pending, _ = stage.begin(store_root, "prune", [profile], atomic=True)
    try:
        snaps = _snapshots(store, profile)
        for name in snaps[: max(0, len(snaps) - keep)]:
            rel = f"profiles/{profile}/snapshots/{name}"
            pending.add("snapshot-prune", "remove", rel, f"remove snapshot {name}", {"delete": [rel]},
                        profile=profile)
        if not pending.plan["items"]:
            stage.discard(store_root)
            return {"proposed": 0, "message": f"{len(snaps)} snapshots; nothing to prune"}
        return {"proposed": len(pending.plan["items"]), "next": "stage.py diff, decide, commit"}
    except Exception:
        stage.discard(store_root)
        raise

def delete(store_root, profile):
    """Delete a whole profile (spec §35): its folder with every slot, ruling, flavour file, rejection and
    snapshot; its ledger records; the cached texts no other profile owns; its source rules, kept drafts,
    queued edits and published sources. Refused for the default profile and for a parent another
    profile extends. Runs as a `forget` (lock and pending mode), approved as a whole, and takes no
    snapshot of the deleted profile: it cannot be rolled back."""
    import copy
    from common import check_schema, dump_yaml, load_yaml_text
    store, pending, _ = stage.begin(store_root, "forget", [profile], atomic=True)
    try:
        pdir = store.root / "profiles" / profile
        if not (pdir / "profile.yaml").exists():
            raise StoreError(f"no profile {profile}")
        if store.config["default_profile"] == profile:
            raise StoreError(f"{profile} is the store's default_profile; set default_profile in idiolect.yaml "
                             f"to another profile first")
        children = [p for p in store.profiles() if p != profile and read_store_file(
            store.root / "profiles" / p / "profile.yaml", "profile").get("extends") == profile]
        if children:
            raise StoreError(f"{', '.join(children)} extend{'s' if len(children) == 1 else ''} {profile}; "
                             f"delete or re-parent {'it' if len(children) == 1 else 'them'} first")
        removed = shared = 0
        for key, e in sorted(store.manifest["texts"].items()):
            if profile not in e["profiles"]:
                continue
            rel = f"corpus/{key.replace('#', '-')}.txt"
            has_text = (store.root / rel).exists()
            others = [p for p in e["profiles"] if p != profile]
            name = e.get("path") or key
            if others:
                shared += 1
                pl = {"manifest": [{"key": key, "profiles": {profile: None}}]}
                summary = f"{name}: {profile}'s record removed; kept for {', '.join(sorted(others))}"
                if has_text and not any(e["profiles"][p]["ownership"] == "own" for p in others):
                    pl["delete"] = [rel]
                    summary += "; cached text deleted (no other profile owns it)"
                pending.add("deletion" if "delete" in pl else "ownership", "modify", "corpus/manifest.json",
                            summary, pl, profile=profile, ref=key)
            else:
                removed += 1
                # removed from the ledger, not `forgotten`: with the profile gone nobody forgot it, and a
                # later learn for another profile sees the text as new
                pl = {"manifest": [{"key": key, "remove": True}]}
                summary = f"{name}: removed from the ledger"
                if has_text:
                    pl["delete"] = [rel]
                    summary += "; cached text deleted"
                pending.add("deletion", "remove", rel, summary, pl, profile=profile, ref=key)
        rules = [r for r in store.sources["sources"] if r.get("profile") == profile]
        if rules:
            src = copy.deepcopy(store.sources)
            src["sources"] = [r for r in src["sources"] if r.get("profile") != profile]
            check_schema("sources", src, "sources.yaml without the deleted profile's rules")
            pending.add("deletion", "modify", "sources.yaml",
                        f"{len(rules)} source rule{'s' if len(rules) != 1 else ''} for {profile} removed",
                        {"restore": {"sources.yaml": dump_yaml(src)}}, profile=profile)
        pub = store.root / "publish.yaml"
        if pub.exists():
            data = read_store_file(pub, "publish")
            mine = [s for s in data.get("sources", []) if s.get("profile") == profile]
            if mine:
                data = {**data, "sources": [s for s in data["sources"] if s.get("profile") != profile]}
                check_schema("publish", data, "publish.yaml without the deleted profile's sources")
                pending.add("deletion", "modify", "publish.yaml",
                            f"{len(mine)} published source{'s' if len(mine) != 1 else ''} for {profile} removed",
                            {"restore": {"publish.yaml": dump_yaml(data)}}, profile=profile)
        idx = store.root / "drafts" / "index.json"
        if idx.exists():
            data = read_store_file(idx, "drafts")
            mine = [d for d in data["entries"] if d.get("profile") == profile]
            if mine:
                data = {**data, "entries": [d for d in data["entries"] if d.get("profile") != profile]}
                check_schema("drafts", data, "drafts/index.json without the deleted profile's drafts")
                pending.add("deletion", "modify", "drafts/index.json",
                            f"{len(mine)} kept draft{'s' if len(mine) != 1 else ''} of {profile} deleted",
                            {"restore": {"drafts/index.json": json.dumps(data, indent=1, ensure_ascii=False) + "\n"},
                             "delete": [f"drafts/{d['file']}" for d in mine]}, profile=profile)
        qdir = store.root / ".state" / "edit-queue"
        queued = []
        for q in sorted(qdir.glob("q-*.json")) if qdir.exists() else []:
            item = json.loads(q.read_text(encoding="utf-8"))
            if item.get("profile") == profile:
                queued += [q.relative_to(store.root).as_posix()] + (
                    [item["final_file"]] if item.get("final_file") else [])
        if queued:
            pending.add("deletion", "remove", ".state/edit-queue",
                        f"queued edits of {profile} deleted", {"delete": queued}, profile=profile)
        pending.add("deletion", "remove", f"profiles/{profile}",
                    f"profile {profile} deleted: its folder, with every slot, ruling, vocabulary, flavour file, "
                    f"rejection, changelog and snapshot ({removed} text{'s' if removed != 1 else ''} removed, "
                    f"{shared} kept for other profiles); it cannot be rolled back",
                    {"delete_profile": profile, "delete": [f"profiles/{profile}"]}, profile=profile)
        return {"proposed": len(pending.plan["items"]), "texts_removed": removed, "texts_shared": shared,
                "next": "stage.py diff, decide, commit"}
    except Exception:
        stage.discard(store_root)
        raise


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--store", required=True)
    ap.add_argument("action", choices=["forget", "rollback", "prune", "delete"])
    ap.add_argument("--source")
    ap.add_argument("--profile")
    ap.add_argument("--ownership", choices=["own", "assisted", "exclude"])
    ap.add_argument("--to")
    ap.add_argument("--keep", type=int, default=10)
    a = ap.parse_args(argv)
    try:
        if a.action == "forget":
            out = forget(a.store, a.source, a.profile, a.ownership)
        elif a.action == "rollback":
            out = rollback(a.store, a.profile, a.to)
        elif a.action == "delete":
            if not a.profile:
                raise StoreError("delete needs --profile")
            out = delete(a.store, a.profile)
        else:
            out = prune(a.store, a.profile, a.keep)
    except StoreError as e:
        print(json.dumps({"status": "error", "message": str(e)}))
        return 2
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
