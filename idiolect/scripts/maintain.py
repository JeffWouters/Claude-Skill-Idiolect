"""forget, rollback and prune: the only modes that delete (spec §8, §11). Each builds a proposal in
the pending area; nothing changes until the writer approves and `stage.py commit` runs.

    python3 maintain.py --store S forget --source REL_PATH_OR_KEY [--profile P] [--ownership own|assisted|exclude]
    python3 maintain.py --store S rollback --profile P [--to SNAPSHOT]
    python3 maintain.py --store S prune --profile P [--keep 10]
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
    if source in texts or source.split("#")[0] in texts:
        base = source.split("#")[0]
        return {k: e for k, e in texts.items() if k == source or (source == base and k.split("#")[0] == base)}
    # by path: the current version and its segments; superseded versions are history (spec §8)
    return {k: e for k, e in texts.items() if e.get("path") == source and e["status"] != "superseded"}


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
                        "slot has no texts left; fingerprint removed",
                        {"delete": [f"profiles/{prof}/{slot}.json"]}, profile=prof, slot=slot)


def forget(store_root, source, profile=None, ownership=None):
    store, pending, _ = stage.begin(store_root, "forget", [profile] if profile else [], atomic=True)
    try:
        entries = _entries_for(store, source)
        if not entries:
            raise StoreError(f"no manifest entry for {source}")
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
                    patch = {"key": key, "profiles": {p: None for p in profs}}
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
        _remeasure(store, pending, patches, affected, corpus_add)
        return {"proposed": len(pending.plan["items"]), "next": "stage.py diff, decide, commit"}
    except Exception:
        stage.discard(store_root)
        raise


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
        cur_files = {p.relative_to(pdir).as_posix() for p in pdir.rglob("*") if p.is_file()
                     and p.relative_to(pdir).parts[0] != "snapshots"}
        for rel in sorted(snap_files):
            content = (sdir / rel).read_text(encoding="utf-8")
            cur = pdir / rel
            if cur.exists() and cur.read_text(encoding="utf-8") == content:
                continue
            pending.add("restore", "modify" if cur.exists() else "add", f"profiles/{profile}/{rel}",
                        f"restore {rel} from {name}", {"restore": {f"profiles/{profile}/{rel}": content}},
                        profile=profile)
        for rel in sorted(cur_files - snap_files):
            pending.add("deletion", "remove", f"profiles/{profile}/{rel}", f"{rel} was created after {name}",
                        {"delete": [f"profiles/{profile}/{rel}"]}, profile=profile)
        then = read_store_file(sdir / "manifest-entries.json", "manifest-entries")["texts"]
        for key, e in sorted(store.manifest["texts"].items()):
            others = [p for p in set(e["profiles"]) | set((then.get(key) or {}).get("profiles", {})) if p != profile]
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
                patch = {"key": key, "set": want, "profiles": {profile: rec}}
                pl = {"manifest": [patch]}
                summary = f"{e.get('path') or key}: back to {old['status']}"
                corpus = store.root / "corpus" / (key.replace("#", "-") + ".txt")
                will_own = rec and rec["ownership"] == "own" and old["status"] != "forgotten"
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
                    patch = {"key": key, "set": {"status": "forgotten", "holdout": False},
                             "force": {"cached": False}}
                    pl = {"manifest": [patch]}
                    if (store.root / "corpus" / (key.replace("#", "-") + ".txt")).exists():
                        pl["delete"] = [f"corpus/{key.replace('#', '-')}.txt"]
                    summary = f"{e.get('path') or key}: added after {name}; forgotten"
                pending.add("deletion" if "delete" in pl else "status", "modify", "corpus/manifest.json",
                            summary, pl, profile=profile, ref=key)
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


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--store", required=True)
    ap.add_argument("action", choices=["forget", "rollback", "prune"])
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
        else:
            out = prune(a.store, a.profile, a.keep)
    except StoreError as e:
        print(json.dumps({"status": "error", "message": str(e)}))
        return 2
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
