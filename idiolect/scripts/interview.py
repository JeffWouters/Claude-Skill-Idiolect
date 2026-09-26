"""interview: the writer's answers to open questions become texts of a slot (spec §21). A learn run
without inventory: after the answers, the learn pipeline continues from `learn.py measure`.

    python3 interview.py --store S start --profile P --lang L --type T [--facet k=v]
    python3 interview.py --store S add --file answer.md
    python3 interview.py --store S answers                       what has been added so far
"""
import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import learn  # noqa: E402
import measure  # noqa: E402
import stage  # noqa: E402
from common import StoreError, content_hash, count_words, utcnow  # noqa: E402
from store import Store  # noqa: E402

MIN_WORDS = 150


def start(store_root, profile, lang, type_, facets=None):
    store = Store(store_root)
    if not (store.root / "profiles" / profile / "profile.yaml").exists():
        raise StoreError(f"no profile {profile}; a profile is created by learn, with its consent recorded")
    if type_ not in store.config.get("types", []):
        raise StoreError(f"type {type_} is not one of the store's types: {', '.join(store.config.get('types', []))}")
    values = {"lang": lang, "type": type_}
    for name in store.facets[2:]:
        values[name] = (facets or {}).get(name) or "_"
    slot = measure.slot_key(store.facets, values)
    store, pending, got = stage.begin(store_root, "interview", [profile])
    state = {"profile": profile, "since": None, "command": {"lang": lang, "type": type_}, "targets": [],
             "tags": [], "texts": {}, "answers": {"files": {}, "rules": [], "profiles": {}}, "types": {},
             "steps": {"texts": False, "measure": False, "contrast": [], "lessons": [], "vocab": [], "examples": []},
             "interview": {"slot": slot, "facets": values, "answers": []}}
    pending.work("state.json").write_text(json.dumps(state, indent=1, ensure_ascii=False), encoding="utf-8")
    return {"profile": profile, "slot": slot, "lock_taken_over": got["taken_over"],
            "next": f"ask open questions for {slot}; add each answer of {MIN_WORDS}+ words with interview.py add"}


def add(store_root, file):
    run = learn.Run(store_root)
    if run.pending.plan["mode"] != "interview":
        raise StoreError("no interview is running; start one with interview.py start")
    st = run.state
    iv = st["interview"]
    text = "\n\n".join(b.strip() for b in pathlib.Path(file).read_text(encoding="utf-8").split("\n\n") if b.strip())
    n = count_words(text)
    if n < MIN_WORDS:
        raise StoreError(f"only {n} words: an answer needs at least {MIN_WORDS} to say anything about style; "
                         f"answer at more length, or join it with another answer")
    key = content_hash(text)
    if key in run.store.manifest["texts"] or key in iv["answers"]:
        raise StoreError("this answer is already in the store")
    prof = st["profile"]
    today = utcnow().date().isoformat()
    create = {"path": None, "date": today, "origin": "interview",
              "profiles": {prof: {"ownership": "own", "decided": today, "decided_by": "writer"}},
              "facets": iv["facets"], "words": n, "holdout": False, "status": "active", "cached": True}
    run.pending.add("corpus-text", "add", f"corpus/{key}.txt",
                    f"interview answer, {n} words, {iv['slot']}; own for {prof}",
                    {"manifest": [{"key": key, "create": create, "cache": True}], "corpus": {key: text}},
                    profile=prof, ref=key)
    iv["answers"].append(key)
    st["steps"]["texts"] = True
    st["steps"]["measure"] = False
    run.save()
    return {"key": key, "words": n, "answers": len(iv["answers"]),
            "next": "another question, or learn.py measure and the rest of the learn steps"}


def answers(store_root):
    run = learn.Run(store_root)
    iv = run.state.get("interview") or {}
    return {"slot": iv.get("slot"), "answers": iv.get("answers", [])}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--store", required=True)
    ap.add_argument("action", choices=["start", "add", "answers"])
    ap.add_argument("--profile")
    ap.add_argument("--lang")
    ap.add_argument("--type")
    ap.add_argument("--facet", action="append", default=[])
    ap.add_argument("--file")
    a = ap.parse_args(argv)
    try:
        if a.action == "start":
            out = start(a.store, a.profile or Store(a.store).config["default_profile"], a.lang or "en", a.type,
                        dict(f.split("=", 1) for f in a.facet))
        elif a.action == "add":
            out = add(a.store, a.file)
        else:
            out = answers(a.store)
    except StoreError as e:
        print(json.dumps({"status": "error", "message": str(e)}, indent=1, ensure_ascii=False))
        return 1
    print(json.dumps(out, indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
