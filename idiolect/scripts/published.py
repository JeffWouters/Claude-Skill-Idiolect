"""published: learn from what the writer publishes (spec §33).

    python3 published.py --store S show
    python3 published.py --store S add-source (--folder F | --feed URL) --profile P [--type T] [--lang L]
    python3 published.py --store S remove-source --id pub-001
    python3 published.py --store S keep-drafts on|off
    python3 published.py --store S keep --file DRAFT --profile P --slot K --mode write|rewrite
    python3 published.py --store S scan [--since YYYY-MM-DD]
    python3 published.py --store S queue
    python3 published.py --store S done --id q-001 [--skipped]

`keep` keeps a draft Idiolect wrote; `scan` reads the writer's published folders and feeds and queues
each published text that holds at least 40% of a kept draft's wording, for learn-edit. Nothing is
learned here: lessons change only through learn-edit, after the writer's approval, so `scan` can run
unattended as a scheduled task. Texts matching no draft are listed as candidates for learn.
"""
import argparse
import datetime as dt
import difflib
import json
import pathlib
import re
import shutil
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import lock as lockmod  # noqa: E402
from common import (StoreError, atomic_write, check_schema, count_words, dump_yaml, iso, parse_iso,  # noqa: E402
                    read_store_file, utcnow)
from store import Store  # noqa: E402

SETTINGS = "publish.yaml"
MATCH = 0.40            # share of a draft's words found, in order, in the published text (design: decision log)
MIN_WORDS = 150
EXPIRE_DAYS = 90
TEXT_SUFFIXES = (".md", ".markdown", ".docx", ".pdf", ".txt")
SKIP_DIRS = {"node_modules", "_to_delete"}


# ---------- settings ----------

def settings(store):
    f = store.root / SETTINGS
    if not f.exists():
        return {"schema_version": 1, "keep_drafts": False, "last_scan": None, "sources": []}
    return read_store_file(f, "publish")


def _save_settings(store, data):
    check_schema("publish", data, SETTINGS)
    atomic_write(store.root / SETTINGS, dump_yaml(data))


def add_source(store_root, profile, folder=None, feed=None, type_=None, lang=None):
    store = Store(store_root)
    if bool(folder) == bool(feed):
        raise StoreError("give either --folder or --feed")
    if not (store.root / "profiles" / profile / "profile.yaml").exists():
        raise StoreError(f"no profile {profile}; a profile is created by learn")
    data = settings(store)
    last = max([int(s["id"].split("-")[1]) for s in data["sources"]] + [0])
    src = {"id": f"pub-{last + 1:03d}", "profile": profile}
    if folder:
        src["folder"] = str(folder)
        where = pathlib.Path(folder).expanduser()
        if not where.is_dir():
            raise StoreError(f"no folder {folder}")
        if store.root.resolve() == where.resolve() or store.root.resolve() in where.resolve().parents:
            raise StoreError("a published folder cannot be inside the store")
    else:
        src["feed"] = feed
    if type_:
        src["type"] = type_
    if lang:
        src["lang"] = lang
    same = [s for s in data["sources"] if s.get("folder") == src.get("folder") and s.get("feed") == src.get("feed")
            and s["profile"] == profile]
    if same:
        return {"added": None, "message": f"already a source: {same[0]['id']}", "sources": data["sources"]}
    data["sources"].append(src)
    _save_settings(store, data)
    return {"added": src["id"], "sources": data["sources"]}


def remove_source(store_root, sid):
    store = Store(store_root)
    data = settings(store)
    kept = [s for s in data["sources"] if s["id"] != sid]
    if len(kept) == len(data["sources"]):
        raise StoreError(f"no source {sid}")
    data["sources"] = kept
    _save_settings(store, data)
    return {"removed": sid, "sources": kept}


def keep_drafts(store_root, on):
    store = Store(store_root)
    data = settings(store)
    data["keep_drafts"] = bool(on)
    _save_settings(store, data)
    return {"keep_drafts": data["keep_drafts"]}


# ---------- kept drafts ----------

def _index(store):
    f = store.root / "drafts" / "index.json"
    if not f.exists():
        return {"schema_version": 1, "last_id": 0, "entries": []}
    return read_store_file(f, "drafts")


def _save_index(store, data):
    check_schema("drafts", data, "drafts/index.json")
    (store.root / "drafts").mkdir(exist_ok=True)
    atomic_write(store.root / "drafts" / "index.json", json.dumps(data, indent=1, ensure_ascii=False) + "\n")


def keep(store_root, file, profile, slot, mode, now=None):
    store = Store(store_root)
    if not settings(store)["keep_drafts"]:
        return {"kept": None, "message": "keep_drafts is off in publish.yaml; nothing kept"}
    text = pathlib.Path(file).read_text(encoding="utf-8")
    idx = _index(store)
    n = max([idx.get("last_id") or 0] + [int(e["id"].split("-")[1]) for e in idx["entries"]]) + 1
    did = f"dr-{n:03d}"
    (store.root / "drafts").mkdir(exist_ok=True)
    atomic_write(store.root / "drafts" / f"{did}.md", text if text.endswith("\n") else text + "\n")
    idx["entries"].append({"id": did, "file": f"{did}.md", "profile": profile, "slot": slot, "mode": mode,
                           "created": iso(now or utcnow()), "words": count_words(text), "status": "open"})
    idx["last_id"] = n
    _save_index(store, idx)
    return {"kept": did}


# ---------- matching ----------

def _words(text):
    return re.findall(r"\w+", text.lower())


def share(draft, published):
    """Share of the draft's words found, in order, in the published text."""
    a, b = _words(draft), _words(published)
    if not a:
        return 0.0
    m = difflib.SequenceMatcher(a=a, b=b, autojunk=False)
    return sum(x.size for x in m.get_matching_blocks()) / len(a)


def _folder_texts(folder, since):
    root = pathlib.Path(folder).expanduser()
    if not root.is_dir():
        raise StoreError(f"published folder {folder} is not reachable")
    from adapters import extract
    out = []
    for f in sorted(root.rglob("*")):
        rel = f.relative_to(root)
        if not f.is_file() or f.suffix.lower() not in TEXT_SUFFIXES \
                or any(p.startswith(".") or p in SKIP_DIRS for p in rel.parts):
            continue
        # changed after the whole second the last scan started in (times are kept to the second)
        if since and dt.datetime.fromtimestamp(f.stat().st_mtime, dt.timezone.utc) < since + dt.timedelta(seconds=1):
            continue
        if f.suffix.lower() == ".txt":
            text = f.read_text(encoding="utf-8", errors="replace")
        else:
            ex = extract(f)
            text = "\n\n".join(b for b in (ex.blocks if ex else []) if b.strip())
        out.append((str(f), text))
    return out


def _feed_texts(url, since, fetch=None):
    import web
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="idiolect-feed-"))
    try:
        (fetch or web.fetch)(url, 50, tmp)
        rows = json.loads((tmp / "index.json").read_text(encoding="utf-8"))
        out = []
        for r in rows:
            if "file" not in r:
                continue
            if since and r.get("date"):
                try:
                    when = dt.datetime.fromisoformat(str(r["date"])[:10]).replace(tzinfo=dt.timezone.utc)
                    if when < since.replace(hour=0, minute=0, second=0, microsecond=0):
                        continue
                except ValueError:
                    pass
            out.append((r["url"], pathlib.Path(r["file"]).read_text(encoding="utf-8")))
        return out
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _queue_dir(store):
    return store.root / ".state" / "edit-queue"


def _next_q(store):
    d = _queue_dir(store)
    nums = [int(p.stem.split("-")[1].split(".")[0]) for p in d.rglob("q-*.json")] if d.exists() else []
    return f"q-{max(nums + [0]) + 1:03d}"


def scan(store_root, since=None, now=None, fetch=None):
    store = Store(store_root)
    st = lockmod.state(str(store.root))
    if st in ("held", "damaged"):
        raise StoreError("another run holds the lock; scan again when it has finished")
    now = now or utcnow()
    data = settings(store)
    if not data["sources"]:
        raise StoreError("no published sources yet: add one with add-source (--folder or --feed)")
    after = dt.datetime.fromisoformat(since).replace(tzinfo=dt.timezone.utc) if since else \
        (parse_iso(data["last_scan"]) if data.get("last_scan") else None)
    idx = _index(store)
    expired = []
    for e in idx["entries"]:
        if e["status"] == "open" and now - parse_iso(e["created"]) > dt.timedelta(days=EXPIRE_DAYS):
            e["status"] = "expired"
            expired.append(e["id"])
    drafts = {e["id"]: (e, (store.root / "drafts" / e["file"]).read_text(encoding="utf-8"))
              for e in idx["entries"] if e["status"] == "open" and (store.root / "drafts" / e["file"]).exists()}
    matched, unmatched, skipped = [], [], []
    for src in data["sources"]:
        texts = _folder_texts(src["folder"], after) if src.get("folder") else _feed_texts(src["feed"], after, fetch)
        for where, text in texts:
            if count_words(text) < MIN_WORDS:
                skipped.append({"source": where, "why": f"under {MIN_WORDS} words"})
                continue
            best, best_share = None, 0.0
            for did, (e, dtext) in drafts.items():
                if e["profile"] != src["profile"] or (src.get("lang") and e["slot"].split(".")[0] != src["lang"]):
                    continue
                sh = share(dtext, text)
                if sh > best_share:
                    best, best_share = did, sh
            if best and best_share >= MATCH:
                e, dtext = drafts.pop(best)
                qid = _next_q(store)
                qd = _queue_dir(store)
                qd.mkdir(parents=True, exist_ok=True)
                atomic_write(qd / f"{qid}.final.md", text if text.endswith("\n") else text + "\n")
                item = {"schema_version": 1, "id": qid, "draft": best, "draft_file": f"drafts/{e['file']}",
                        "final_file": f".state/edit-queue/{qid}.final.md", "source": where, "found": iso(now),
                        "profile": e["profile"], "slot": e["slot"], "share": round(best_share, 3), "status": "waiting"}
                check_schema("edit-queue", item, qid)
                atomic_write(qd / f"{qid}.json", json.dumps(item, indent=1, ensure_ascii=False) + "\n")
                e["status"], e["matched"] = "matched", qid
                matched.append({"queue": qid, "draft": best, "source": where, "share": item["share"]})
            else:
                unmatched.append({"source": where, "profile": src["profile"], "words": count_words(text),
                                  "best_share": round(best_share, 3)})
    _save_index(store, idx)
    data["last_scan"] = iso(now)
    _save_settings(store, data)
    waiting = queue(store_root)["waiting"]
    return {"matched": matched, "unmatched": unmatched, "skipped": skipped, "expired": expired,
            "queue": len(waiting),
            "next": ("process the edit queue with learn-edit (published.py queue)" if waiting else
                     "nothing waiting") + ("; unmatched texts can be learned with learn" if unmatched else "")}


def queue(store_root):
    store = Store(store_root)
    d = _queue_dir(store)
    items = [read_store_file(f, "edit-queue") for f in sorted(d.glob("q-*.json"))] if d.exists() else []
    return {"waiting": [i for i in items if i["status"] == "waiting"]}


def done(store_root, qid, skipped=False):
    store = Store(store_root)
    d = _queue_dir(store)
    f = d / f"{qid}.json"
    if not f.exists():
        raise StoreError(f"no queue item {qid} waiting")
    item = read_store_file(f, "edit-queue")
    item["status"] = "skipped" if skipped else "done"
    (d / "done").mkdir(exist_ok=True)
    atomic_write(f, json.dumps(item, indent=1, ensure_ascii=False) + "\n")
    f.replace(d / "done" / f.name)                       # moved, never deleted
    fin = d / f"{qid}.final.md"
    if fin.exists():
        fin.replace(d / "done" / fin.name)
    return {"id": qid, "status": item["status"]}


def show(store_root):
    store = Store(store_root)
    data = settings(store)
    idx = _index(store)
    counts = {}
    for e in idx["entries"]:
        counts[e["status"]] = counts.get(e["status"], 0) + 1
    return {"keep_drafts": data["keep_drafts"], "sources": data["sources"], "last_scan": data.get("last_scan"),
            "drafts": counts, "queue": len(queue(store_root)["waiting"])}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--store", required=True)
    ap.add_argument("action", choices=["show", "add-source", "remove-source", "keep-drafts", "keep", "scan",
                                       "queue", "done"])
    ap.add_argument("value", nargs="?", help="keep-drafts: on or off")
    ap.add_argument("--folder")
    ap.add_argument("--feed")
    ap.add_argument("--profile")
    ap.add_argument("--type")
    ap.add_argument("--lang")
    ap.add_argument("--id")
    ap.add_argument("--file")
    ap.add_argument("--slot")
    ap.add_argument("--mode", choices=["write", "rewrite"], default="write")
    ap.add_argument("--since")
    ap.add_argument("--skipped", action="store_true")
    a = ap.parse_args(argv)
    try:
        if a.action == "show":
            out = show(a.store)
        elif a.action == "add-source":
            if not a.profile:
                raise StoreError("add-source needs --profile")
            out = add_source(a.store, a.profile, a.folder, a.feed, a.type, a.lang)
        elif a.action == "remove-source":
            out = remove_source(a.store, a.id)
        elif a.action == "keep-drafts":
            if a.value not in ("on", "off"):
                raise StoreError("keep-drafts takes on or off")
            out = keep_drafts(a.store, a.value == "on")
        elif a.action == "keep":
            if not (a.file and a.profile and a.slot):
                raise StoreError("keep needs --file, --profile and --slot")
            out = keep(a.store, a.file, a.profile, a.slot, a.mode)
        elif a.action == "scan":
            out = scan(a.store, a.since)
        elif a.action == "queue":
            out = queue(a.store)
        else:
            out = done(a.store, a.id, a.skipped)
    except StoreError as e:
        print(json.dumps({"status": "error", "message": str(e)}, indent=1, ensure_ascii=False))
        return 1
    print(json.dumps(out, indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
