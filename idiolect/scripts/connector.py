"""Web pages and connector texts (spec §23): texts with no file behind them, added to a learn run that
has no inventory. After the texts, the learn pipeline continues from `learn.py measure`.

    python3 connector.py --store S start --profile P --lang L --type T [--facet k=v]
                                       [--subject S --consent C [--description D]]   # a new profile
    python3 connector.py --store S add --file F --origin web|mail --ownership own|assisted|exclude
                                     [--date YYYY-MM-DD] [--note "URL or subject"] [--strip]
    python3 connector.py --store S list

For mail, give the names to redact first: learn.py mail-names --file names.yaml.
"""
import argparse
import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import learn  # noqa: E402
import measure  # noqa: E402
import redact as redactmod  # noqa: E402
import stage  # noqa: E402
from adapters.mailfile import strip_mail  # noqa: E402
from common import StoreError, content_hash, count_words, utcnow  # noqa: E402
from store import Store  # noqa: E402

MIN_WORDS = 150
ORIGINS = ("web", "mail")
PROFILE_NAME = re.compile(r"^[a-z][a-z0-9-]{0,39}$")
OWNERSHIP = ("own", "assisted", "exclude")


def start(store_root, profile, lang, type_, facets=None, subject=None, consent=None, description=None):
    store = Store(store_root)
    new = None
    if not (store.root / "profiles" / profile / "profile.yaml").exists():
        if not (subject and consent):
            raise StoreError(f"no profile {profile}: to create it, give --subject (who the voice is) and --consent "
                             f"('self' for the writer's own voice, else how that person gave permission)")
        new = {"schema_version": 1, "subject": subject, "consent": consent}
        if description:
            new["description"] = description
        from common import check_schema
        check_schema("profile", new, f"profile {profile}")
        if not PROFILE_NAME.match(profile):
            raise StoreError(f"a profile name is lower case letters, digits and hyphens: {profile!r}")
    if type_ not in store.config.get("types", []):
        raise StoreError(f"type {type_} is not one of the store's types: {', '.join(store.config.get('types', []))}")
    values = {"lang": lang, "type": type_}
    for name in store.facets[2:]:
        values[name] = (facets or {}).get(name) or "_"
    slot = measure.slot_key(store.facets, values)
    store, pending, got = stage.begin(store_root, "learn", [profile])
    state = {"profile": profile, "since": None, "command": {"lang": lang, "type": type_}, "targets": [],
             "tags": [], "texts": {}, "answers": {"files": {}, "rules": [], "profiles": {}}, "types": {},
             "steps": {"texts": False, "measure": False, "contrast": [], "lessons": [], "vocab": [], "examples": []},
             "connector": {"slot": slot, "facets": values, "texts": []}}
    if new:
        # staged like learn's new profiles: every text of the run depends on it (stage.cascade)
        state["answers"]["profiles"][profile] = new
        pending.add("profile", "add", f"profiles/{profile}/profile.yaml",
                    f"new profile {profile}: {subject} (consent: {consent})",
                    {"profile_yaml": {"name": profile, "data": new}}, profile=profile)
    pending.work("state.json").write_text(json.dumps(state, indent=1, ensure_ascii=False), encoding="utf-8")
    return {"profile": profile, "slot": slot, "lock_taken_over": got["taken_over"], "new_profile": bool(new),
            "next": "connector.py add for each text, with the writer's ownership; then learn.py measure"}


def add(store_root, file, origin, ownership, date=None, note=None, strip=False):
    if not pathlib.Path(file).is_file():
        raise StoreError(f"no such file: {file}")
    run = learn.Run(store_root)
    st = run.state
    cn = st.get("connector")
    if not cn:
        raise StoreError("no connector run: start one with connector.py start")
    if origin not in ORIGINS:
        raise StoreError(f"origin is one of {', '.join(ORIGINS)}")
    if ownership not in OWNERSHIP:
        raise StoreError("ownership is the writer's answer: own, assisted or exclude (never assumed)")
    raw = pathlib.Path(file).read_text(encoding="utf-8")
    blocks = strip_mail(raw) if strip else [b.strip() for b in re.split(r"\n\s*\n", raw) if b.strip()]
    text = "\n\n".join(blocks)
    n = count_words(text)
    if n < MIN_WORDS:
        raise StoreError(f"only {n} words: under {MIN_WORDS}, too little to learn from")
    key = content_hash(text)
    if key in run.store.manifest["texts"] or key in cn["texts"]:
        raise StoreError("this text is already in the store")
    prof = st["profile"]
    today = utcnow().date().isoformat()
    if date and not re.match(r"^\d{4}-\d{2}-\d{2}$", date):
        raise StoreError("date is YYYY-MM-DD")
    owned = ownership == "own"
    create = {"path": None, "date": date, "origin": origin,
              "profiles": {prof: {"ownership": ownership, "decided": today, "decided_by": "writer"}},
              "facets": cn["facets"], "words": n, "holdout": False, "status": "active", "cached": owned}
    summary = f"{origin} text{' (' + note + ')' if note else ''}, {n} words, {cn['slot']}; {ownership} for {prof}"
    payload = {"manifest": [{"key": key, "create": create, "cache": owned}]}
    new_prof = [i["id"] for i in run.pending.plan["items"] if i["kind"] == "profile" and i["op"] == "add"
                and i.get("profile") == prof]
    if new_prof:
        # the text's record stands on the new profile: rejecting the profile drops it (stage.cascade)
        payload["record_needs"] = {prof: new_prof}
    if owned:
        if origin == "mail":
            names = st.get("mail_names")
            text, _ = redactmod.redact(text, names)
            create["redaction"] = {"redacted": True, "version": redactmod.VERSION, "reviewed": names is not None}
            summary += "; redacted" + ("" if names is not None else " (script pass only: give names with learn.py mail-names)")
        payload["corpus"] = {key: text}
        run.pending.add("corpus-text", "add", f"corpus/{key}.txt", summary, payload, profile=prof, ref=key)
    else:
        run.pending.add("ownership", "add", "corpus/manifest.json", summary + " (recorded, not learned)", payload,
                        profile=prof, ref=key)
    cn["texts"].append(key)
    st["steps"]["texts"] = True
    st["steps"]["measure"] = False
    run.save()
    return {"key": key, "words": n, "texts": len(cn["texts"]), "cached": owned}


def listing(store_root):
    run = learn.Run(store_root)
    cn = run.state.get("connector") or {}
    return {"slot": cn.get("slot"), "texts": cn.get("texts", [])}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--store", required=True)
    ap.add_argument("action", choices=["start", "add", "list"])
    ap.add_argument("--profile")
    ap.add_argument("--lang")
    ap.add_argument("--type")
    ap.add_argument("--facet", action="append", default=[])
    ap.add_argument("--file")
    ap.add_argument("--origin")
    ap.add_argument("--ownership")
    ap.add_argument("--date")
    ap.add_argument("--note")
    ap.add_argument("--strip", action="store_true")
    ap.add_argument("--subject", help="start, new profile: who the voice is")
    ap.add_argument("--consent", help="start, new profile: 'self', or how that person gave permission")
    ap.add_argument("--description")
    a = ap.parse_args(argv)
    try:
        if a.action == "start":
            out = start(a.store, a.profile or Store(a.store).config["default_profile"], a.lang or "en", a.type,
                        dict(f.split("=", 1) for f in a.facet), a.subject, a.consent, a.description)
        elif a.action == "add":
            out = add(a.store, a.file, a.origin, a.ownership, a.date, a.note, a.strip)
        else:
            out = listing(a.store)
    except StoreError as e:
        print(json.dumps({"status": "error", "message": str(e)}, indent=1, ensure_ascii=False))
        return 1
    print(json.dumps(out, indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
