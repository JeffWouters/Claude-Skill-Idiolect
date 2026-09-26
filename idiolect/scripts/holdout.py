"""test: hold a text out of learning and measure the profile and a draft against it (spec §19).

    python3 holdout.py --store S propose --source PATH_OR_KEY [--profile P] [--type T]
    python3 holdout.py --store S brief-check --key K --brief FILE
    python3 holdout.py --store S examples --key K --brief FILE
    python3 holdout.py --store S packet --key K --brief FILE --draft plain=F --draft fewshot=F --draft idiolect=F
    python3 holdout.py --store S record --key K [--draft FILE]          # no judge
    python3 holdout.py --store S record --test ID --ranking B,A,C       # after the writer ranked a packet
    python3 holdout.py --store S drift --key K [--draft FILE]           # read-only: drift, no row

`propose` builds the holdout proposal (approve it with stage.py diff / decide / commit). `packet`
prints the blind packet and keeps the key in .state/test/<id>.json. `record` appends one row to
eval/results.md. Every command prints JSON.
"""
import argparse
import json
import math
import pathlib
import random
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import check as checkmod  # noqa: E402
import detect  # noqa: E402
import kit as kitmod  # noqa: E402
import lock as lockmod  # noqa: E402
import maintain  # noqa: E402
import measure  # noqa: E402
import stage  # noqa: E402
from adapters import extract  # noqa: E402
from common import (StoreError, atomic_write, count_words, read_store_file, run_id, utcnow,  # noqa: E402
                    words)
from store import Store  # noqa: E402

BRIEF_MAX_WORDS = 60
ARMS = ("plain", "fewshot", "idiolect")
RESULTS_HEAD = ("---\nschema_version: 1\n---\n"
                "| Date | Profile | Slot | Snapshot | Holdout | Blind picks | Drift (primary metrics) |\n"
                "| --- | --- | --- | --- | --- | --- | --- |\n")


# ---------- the proposal ----------

def _owners(entry):
    return sorted(p for p, r in entry["profiles"].items() if r["ownership"] == "own")


def propose(store_root, source, profile=None, type_=None):
    store, pending, _ = stage.begin(store_root, "test", [profile] if profile else [], atomic=True)
    try:
        entries = maintain._entries_for(store, source)
        if entries:
            out = _propose_learned(store, pending, entries, profile)
        else:
            out = _propose_new(store, pending, source, profile, type_)
        out["next"] = "stage.py diff, decide, commit"
        return out
    except Exception:
        stage.discard(store_root)
        raise


def _propose_learned(store, pending, entries, profile):
    live = {k: e for k, e in entries.items() if e["status"] in ("active", "unreachable")}
    if not live:
        st = sorted({e["status"] for e in entries.values()})
        raise StoreError(f"that text is {', '.join(st)}; only a current text can be held out")
    if len(live) > 1:
        raise StoreError("that path holds several texts (language segments): give one key: " + ", ".join(sorted(live)))
    key, e = next(iter(live.items()))
    if e.get("holdout"):
        raise StoreError(f"{e.get('path') or key} is already a holdout")
    owners = _owners(e)
    if not owners:
        raise StoreError(f"{e.get('path') or key} is owned by no profile: nothing to test it against")
    if profile and profile not in owners:
        raise StoreError(f"{e.get('path') or key} is not owned by profile {profile}")
    patch = {"key": key, "set": {"holdout": True}}
    learned = bool(e.get("cached"))
    who = ", ".join(owners)
    pending.add("status", "modify", "corpus/manifest.json",
                f"{e.get('path') or key}: held out for testing ({who}); learning refuses it from now on"
                + ("; the slots it fed are re-measured without it" if learned else ""),
                {"manifest": [patch]}, profile=owners[0], ref=key)
    if learned:
        losing = {key: set(owners)}
        maintain._drop_examples(store, pending, losing)
        maintain._blank_quotes(store, pending, losing)
        maintain._remeasure(store, pending, [patch], set(owners), {})
    slot = measure.slot_key(store.facets, e["facets"])
    return {"key": key, "profile": profile or owners[0], "slot": slot, "was_learned": learned,
            "proposed": len(pending.plan["items"])}


def _propose_new(store, pending, source, profile, type_):
    f = store.sources_root / source
    if not f.is_file():
        raise StoreError(f"no manifest entry and no file {source} under the sources root")
    profile = profile or store.config["default_profile"]
    if not (store.root / "profiles" / profile / "profile.yaml").exists():
        raise StoreError(f"no profile {profile}; a profile is created by learn")
    if not type_:
        raise StoreError("a file not learned yet needs its type (type=...)")
    ex = extract(f)
    parts = detect.split(ex.blocks) if ex else []
    if len(parts) != 1:
        raise StoreError(f"{source} is not one text in one language ({len(parts)} parts); learn it first, then hold out one segment by key")
    t = parts[0]
    known = store.manifest["texts"].get(t.key)
    if known:
        raise StoreError(f"{source} has the text of manifest entry {t.key} ({known['status']})")
    text = t.text
    facets = {"lang": t.lang, "type": type_}
    for name in store.facets[2:]:
        facets[name] = "_"
    today = utcnow().date().isoformat()
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", str(ex.date or ""))
    create = {"path": source, "date": "-".join(m.groups()) if m else None, "origin": "file",
              "profiles": {profile: {"ownership": "own", "decided": today, "decided_by": "writer"}},
              "facets": facets, "words": count_words(text), "holdout": True, "status": "active", "cached": True}
    pending.add("corpus-text", "add", f"corpus/{t.key.replace('#', '-')}.txt",
                f"{source}: new holdout for {profile}, {count_words(text)} words, {facets['lang']}.{type_}; never learned",
                {"manifest": [{"key": t.key, "create": create, "cache": True}], "corpus": {t.key: text}},
                profile=profile, ref=t.key)
    return {"key": t.key, "profile": profile, "slot": measure.slot_key(store.facets, facets), "was_learned": False,
            "proposed": len(pending.plan["items"])}


# ---------- brief, examples ----------

def _holdout(store, key):
    e = store.manifest["texts"].get(key)
    if not e or not e.get("holdout"):
        raise StoreError(f"{key} is not a holdout: run propose and commit first")
    owners = _owners(e)
    if not owners:
        raise StoreError(f"{key} is owned by no profile")
    return e, owners[0], measure.slot_key(store.facets, e["facets"]), store.corpus_text(key)


def runs4(text, lang):
    sw = stage.stopwords(lang)
    ws = [w.lower() for w in words(text) if w.lower() not in sw]
    return {" ".join(ws[i:i + 4]) for i in range(len(ws) - 3)}


def brief_check(store, key, brief):
    e, _, _, text = _holdout(store, key)
    lang = e["facets"]["lang"]
    shared = sorted(runs4(brief, lang) & runs4(text, lang))
    n = count_words(brief)
    ok = not shared and n <= BRIEF_MAX_WORDS
    return {"ok": ok, "words": n, "max_words": BRIEF_MAX_WORDS, "shared_runs": shared[:10],
            "message": "ok" if ok else "rewrite the brief in other words" + (f" and under {BRIEF_MAX_WORDS} words" if n > BRIEF_MAX_WORDS else "")}


def examples(store, key, brief):
    """The few-shot baseline's passages: the same picker as the kit, from the profile's example bank."""
    e, prof, slot, _ = _holdout(store, key)
    picks = kitmod.pick_examples(kitmod.slot_examples(store, prof, slot), brief, e["facets"]["lang"])
    return {"profile": prof, "slot": slot, "examples": [{"id": x["id"], "text": x["text"]} for x in picks]}


# ---------- drift ----------

def _summary(rows):
    logs = [abs(math.log(r["ratio"])) for r in rows if r["ratio"] is not None and r["ratio"] > 0]
    return {"mean_log": round(sum(logs) / len(logs), 4) if logs else None,
            "outside": sum(1 for r in rows if r["flag"] != "ok")}


def _side(vals, refs, fp):
    rows = []
    for m, fm in fp["metrics"].items():
        if m not in vals or m not in refs:
            continue
        g = measure.METRICS[m]
        if refs[m] < g["floor"] or vals[m] < g["floor"]:
            flag, _ = checkmod.flag_metric(m, vals[m], refs[m], fm)
            rows.append({"name": m, "value": round(vals[m], 4), "reference": round(refs[m], 4),
                         "ratio": None, "flag": flag, "primary": fm["primary"]})
            continue
        flag, ratio = checkmod.flag_metric(m, vals[m], refs[m], fm)
        rows.append({"name": m, "value": round(vals[m], 4), "reference": round(refs[m], 4),
                     "ratio": round(vals[m] / refs[m], 3), "flag": flag, "primary": fm["primary"]})
    return {"metrics": rows, **_summary(rows)}


def drift(store, key, draft=None):
    e, prof, slot, text = _holdout(store, key)
    lang = e["facets"]["lang"]
    fp = read_store_file(store.root / "profiles" / prof / f"{slot}.json", "fingerprint")
    hv = measure.metrics(text, lang)
    out = {"key": key, "profile": prof, "slot": slot,
           "profile_drift": _side(hv, {m: v["value"] for m, v in fp["metrics"].items()}, fp)}
    if draft is not None:
        dv = measure.metrics(checkmod.strip_placeholders(draft), lang)
        out["draft_drift"] = _side(dv, hv, fp)
    return out


# ---------- packet and record ----------

def _test_dir(store):
    return store.state("test")


def packet(store_root, key, brief_file, drafts):
    store = Store(store_root)
    e, prof, slot, _ = _holdout(store, key)
    if sorted(drafts) != sorted(ARMS):
        raise StoreError(f"a packet needs one draft for each of {', '.join(ARMS)}")
    tid = "t-" + run_id()
    n = 2
    while (_test_dir(store) / f"{tid}.json").exists():
        tid = f"t-{run_id()}-{n}"
        n += 1
    labels = list(ARMS)
    random.Random(tid).shuffle(labels)
    key_map = dict(zip("ABC", labels))
    lockmod.acquire(str(store.root), "test", prof)
    try:
        d = _test_dir(store)
        d.mkdir(parents=True, exist_ok=True)
        state = {"id": tid, "key": key, "profile": prof, "slot": slot,
                 "brief": str(pathlib.Path(brief_file).resolve()),
                 "drafts": {k: str(pathlib.Path(v).resolve()) for k, v in drafts.items()}, "labels": key_map}
        atomic_write(d / f"{tid}.json", json.dumps(state, indent=1) + "\n")
    finally:
        lockmod.release(str(store.root))
    parts = [f"# Blind test {tid}", "", "Rank the three drafts by which reads most like you (voice, not content).",
             "", "## Brief", "", pathlib.Path(brief_file).read_text(encoding="utf-8").strip()]
    for lab in "ABC":
        txt = checkmod.strip_placeholders(pathlib.Path(drafts[key_map[lab]]).read_text(encoding="utf-8")).strip()
        parts += ["", f"## Draft {lab}", "", txt]
    return {"test": tid, "packet": "\n".join(parts) + "\n"}


def _latest_snapshot(store, prof):
    d = store.root / "profiles" / prof / "snapshots"
    snaps = sorted(p.name for p in d.iterdir()) if d.exists() else []
    return f"snapshots/{snaps[-1]}/" if snaps else "—"


def _drift_cell(dr):
    def side(label, s):
        return f"{label} {s['mean_log']:.2f} ({s['outside']} outside)" if s["mean_log"] is not None else f"{label} —"
    cell = side("profile", dr["profile_drift"])
    ref = dr.get("draft_drift") or dr["profile_drift"]
    if "draft_drift" in dr:
        cell += " · " + side("draft", dr["draft_drift"])
    prim = [f"{r['name']} ×{r['ratio']:.2f}" + ("!" if r["flag"] != "ok" else "")
            for r in ref["metrics"] if r["primary"] and r["ratio"] is not None]
    return cell + (": " + ", ".join(prim) if prim else "")


def record(store_root, key=None, draft_file=None, test_id=None, ranking=None):
    store = Store(store_root)
    picks = "—"
    if test_id:
        f = _test_dir(store) / f"{test_id}.json"
        if not f.exists():
            raise StoreError(f"no blind test {test_id}")
        st = json.loads(f.read_text(encoding="utf-8"))
        rank = [x.strip().upper() for x in (ranking or "").split(",") if x.strip()]
        if sorted(rank) != ["A", "B", "C"]:
            raise StoreError("the ranking names A, B and C once each, best first")
        order = [st["labels"][x] for x in rank]
        picks = " > ".join(order)
        key = st["key"]
        draft_file = st["drafts"]["idiolect"]
    if not key:
        raise StoreError("record needs --key, or --test with --ranking")
    draft = pathlib.Path(draft_file).read_text(encoding="utf-8") if draft_file else None
    dr = drift(store, key, draft)
    prof, slot = dr["profile"], dr["slot"]
    row = (f"| {utcnow().date().isoformat()} | {prof} | {slot} | {_latest_snapshot(store, prof)} | {key[:12]} | "
           f"{picks} | {_drift_cell(dr)} |\n")
    lockmod.acquire(str(store.root), "test", prof)
    try:
        out = store.root / "eval" / "results.md"
        out.parent.mkdir(parents=True, exist_ok=True)
        cur = out.read_text(encoding="utf-8") if out.exists() else RESULTS_HEAD
        atomic_write(out, cur + row)
    finally:
        lockmod.release(str(store.root))
    return {"row": row.strip(), "blind_picks": picks, **dr}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--store", required=True)
    ap.add_argument("action", choices=["propose", "brief-check", "examples", "packet", "record", "drift"])
    ap.add_argument("--source")
    ap.add_argument("--profile")
    ap.add_argument("--type")
    ap.add_argument("--key")
    ap.add_argument("--brief")
    ap.add_argument("--draft", action="append", default=[])
    ap.add_argument("--test")
    ap.add_argument("--ranking")
    a = ap.parse_args(argv)
    try:
        brief = pathlib.Path(a.brief).read_text(encoding="utf-8") if a.brief else None
        if a.action == "propose":
            out = propose(a.store, a.source, a.profile, a.type)
        elif a.action == "brief-check":
            out = brief_check(Store(a.store), a.key, brief)
        elif a.action == "examples":
            out = examples(Store(a.store), a.key, brief)
        elif a.action == "packet":
            drafts = dict(x.split("=", 1) for x in a.draft)
            out = packet(a.store, a.key, a.brief, drafts)
        elif a.action == "drift":
            out = drift(Store(a.store), a.key, pathlib.Path(a.draft[0]).read_text(encoding="utf-8") if a.draft else None)
        else:
            out = record(a.store, a.key, a.draft[0] if a.draft else None, a.test, a.ranking)
    except StoreError as e:
        out = {"status": "error", "message": str(e)}
        print(json.dumps(out, indent=1, ensure_ascii=False))
        return 1
    print(json.dumps(out, indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
