"""rules: rulings with tests, and the optional starter set (spec §27).

    python3 rules.py --store S defaults --profile P [--lang L] [--category C ...]
    python3 rules.py --store S add --profile P --text T [--chars C ...] [--words W ...] [--phrases P ...]
                                  [--pattern R] [--unless-writer-uses] [--slot K] [--lang L]
    python3 rules.py --store S show [--profile P] [--lang L] [--type T] [--facet k=v]
    python3 rules.py starter [--lang L]
    python3 rules.py guide-text --source GUIDE
    python3 rules.py --store S import --profile P --source GUIDE --file proposals.yaml

`defaults` and `add` propose `ruling` items in a learn run (the one waiting in the pending area, or a
new one): nothing changes until the writer approves the diff (stage.py diff / decide / commit). A
starter rule the writer rejects is remembered in rulings.yaml (`declined`) and not proposed again at
the same set version. `import` stages rules the model found in a style guide (each quoting it). `show` lists the rulings that apply to a slot with the writer's own rate for
those marked unless_writer_uses. `starter` prints the starter set. The functions below are also what
check.py and kit.py use to apply rulings.
"""
import argparse
import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import measure  # noqa: E402
import resolve  # noqa: E402
import stage  # noqa: E402
from common import StoreError, count_words, load_yaml_text, read_store_file, utcnow  # noqa: E402
from store import Store  # noqa: E402

STARTER_DIR = pathlib.Path(__file__).resolve().parent.parent / "assets" / "starter-rules"
MIN_HITS = 2          # a writer who does this: a draft is flagged from two hits ...
RATE_FACTOR = 2.0     # ... and above twice the writer's rate per 1,000 words


# ---------- tests ----------

def compile_test(test, where="ruling"):
    """A matcher for one test form: a compiled regex whose findall counts hits in one line. Raises
    StoreError for a malformed test (spec §27.7)."""
    if not isinstance(test, dict) or len(test) != 1:
        raise StoreError(f"{where}: a test has exactly one of chars, words, phrases, pattern")
    (form, val), = test.items()
    if form == "chars":
        return re.compile("|".join(re.escape(measure.normalise_quotes(c)) for c in val))
    if form == "words":
        alts = sorted({re.escape(measure.normalise_quotes(w)) for w in val}, key=len, reverse=True)
        return re.compile(r"(?<!\w)(?:" + "|".join(alts) + r")(?!\w)", re.I)
    if form == "phrases":
        return measure.phrases_pattern(val)
    if form == "pattern":
        try:
            return re.compile(val, re.I)
        except re.error as e:
            raise StoreError(f"{where}: the pattern {val!r} is not a valid regular expression ({e}); "
                             f"fix or remove it in rulings.yaml") from e
    raise StoreError(f"{where}: unknown test form {form!r}; use chars, words, phrases or pattern")


def hits_per_line(pat, text):
    """[(line number, line, hits)] for every line with at least one hit. Quotes are normalised, so a
    curly apostrophe matches a straight one."""
    out = []
    for i, line in enumerate(text.splitlines(), 1):
        n = len(pat.findall(measure.normalise_quotes(line)))
        if n:
            out.append((i, line, n))
    return out


def count(pat, text):
    return sum(n for _, _, n in hits_per_line(pat, text))


# ---------- which rulings apply ----------

def applicable(store, prof, slot):
    """Rulings merged down the chain (spec §12.5) that apply to this slot: slot null or equal, lang
    null or the slot's language."""
    lang = slot.split(".")[0]
    return [r for r in resolve.merged(store, prof, "rulings")
            if r.get("slot") in (None, slot) and r.get("lang") in (None, lang)]


def writer_rates(store, prof, slot, rulings):
    """{ruling id: uses per 1,000 words in the writer's own texts of the slot} for every ruling with a
    test and unless_writer_uses. Holdouts are left out (measure.profile_texts)."""
    want = [r for r in rulings if r.get("test") and r.get("unless_writer_uses")]
    if not want:
        return {}
    slots = measure.slot_texts(store.manifest["texts"], store.corpus_text, store.facets, prof)
    texts = [t for _, t, _ in (slots.get(slot) or {}).get("texts", [])]
    n = sum(count_words(t) for t in texts)
    out = {}
    for r in want:
        pat = compile_test(r["test"], f"{r['profile']}:{r['id']}")
        out[r["id"]] = round(sum(count(pat, t) for t in texts) * 1000 / n, 2) if n else 0.0
    return out


def flag(text, rulings, rates, n_words):
    """Flagged lines for every ruling whose test the text breaks (spec §27.2)."""
    lines = []
    for r in rulings:
        if not r.get("test"):
            continue
        pat = compile_test(r["test"], f"{r['profile']}:{r['id']}")
        found = hits_per_line(pat, text)
        total = sum(n for _, _, n in found)
        if not total:
            continue
        rate = rates.get(r["id"], 0.0) if r.get("unless_writer_uses") else 0.0
        if rate > 0:
            draft_rate = total * 1000 / max(n_words, 1)
            if total < MIN_HITS or draft_rate <= RATE_FACTOR * rate:
                continue
            why = (f"breaks ruling {r['id']} \"{r['text']}\": {total} uses, {draft_rate:.1f} per 1,000 words; "
                   f"the writer's texts about {rate:g}")
        else:
            why = f"breaks ruling {r['id']} \"{r['text']}\""
        for i, line, _ in found:
            lines.append({"line": i, "text": line.strip()[:200], "lesson": r["id"], "reason": why})
    return lines


def note(r, rates):
    """The kit's addition to a ruling the writer's own texts do show (spec §27.3)."""
    rate = rates.get(r["id"])
    if r.get("unless_writer_uses") and rate:
        return f" (your texts do this about {rate:g} times per 1,000 words: never more)"
    return ""


# ---------- the starter set ----------

def starter(lang="en"):
    f = STARTER_DIR / f"{lang}.yaml"
    if not f.exists():
        have = sorted(p.stem for p in STARTER_DIR.glob("*.yaml"))
        raise StoreError(f"no starter set for '{lang}'; there is one for: {', '.join(have) or 'none'}")
    data = load_yaml_text(f.read_text(encoding="utf-8"))
    for r in data["rules"]:
        compile_test(r["test"], f"starter {r['id']}")
    return data


def digest(entry):
    """16 hex digits over what makes a ruling: its text, test and unless_writer_uses."""
    import hashlib
    body = json.dumps([entry.get("text", "").strip(), entry.get("test"), bool(entry.get("unless_writer_uses"))],
                      sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()[:16]


def _open_run(store_root, profile):
    """The learn run waiting in the pending area, or a new one."""
    store = Store(store_root)
    pending = stage.Pending(store)
    if pending.exists():
        if pending.plan["mode"] != "learn" or "commit" in pending.plan:
            raise StoreError("a pending area is waiting: offer resume or discard first (spec §9.7)")
        stage.ensure_owner(store, pending)
        return store, pending
    store, pending, _ = stage.begin(store_root, "learn", [profile])
    return store, pending


def _profile_rulings(store, prof, pending):
    rf = store.root / "profiles" / prof / "rulings.yaml"
    base = read_store_file(rf, "rulings") if rf.exists() else {"entries": []}
    last = max([base.get("last_id") or 0] + [int(e["id"].split("-")[1]) for e in base["entries"]])
    for it in pending.plan["items"]:
        if it["kind"] == "ruling" and it.get("profile") == prof:
            last = max(last, int(pending.payload(it["id"])["ruling"]["entry"]["id"].split("-")[1]))
    return base, last


def _check_profile(store, prof):
    if not (store.root / "profiles" / prof / "profile.yaml").exists():
        raise StoreError(f"no profile {prof}; a profile is created by learn")


def defaults(store_root, profile=None, lang="en", categories=None):
    """Propose the starter rules (spec §27.5)."""
    store = Store(store_root)
    prof = profile or store.config["default_profile"]
    _check_profile(store, prof)
    data = starter(lang)
    cats = sorted({r["category"] for r in data["rules"]})
    if categories:
        bad = [c for c in categories if c not in cats]
        if bad:
            raise StoreError(f"unknown categories: {', '.join(bad)}; the set has: {', '.join(cats)}")
    store, pending = _open_run(store_root, prof)
    try:
        base, last = _profile_rulings(store, prof, pending)
        held = {e["starter"]["id"]: e for e in base["entries"] if e.get("starter")}
        declined = {d["starter"]: d for d in base.get("declined", [])}
        queued = {pending.payload(it["id"])["ruling"]["entry"].get("starter", {}).get("id")
                  for it in pending.plan["items"] if it["kind"] == "ruling" and it.get("profile") == prof}
        ver, today = str(data["version"]), utcnow().date().isoformat()
        proposed, skipped = [], []
        for r in data["rules"]:
            if categories and r["category"] not in categories:
                continue
            sid = r["id"]
            old = held.get(sid)
            if sid in queued:
                skipped.append({"starter": sid, "why": "already proposed in this run"})
                continue
            d = declined.get(sid)
            if d and (d.get("digest") == digest(r) if d.get("digest") else d["version"] == ver):
                skipped.append({"starter": sid, "why": f"declined (set version {d['version']}); unchanged since"})
                continue
            same = old and old["text"] == r["text"] and old.get("test") == r["test"] \
                and bool(old.get("unless_writer_uses")) == bool(r["unless_writer_uses"]) \
                and old.get("lang") == data["lang"]
            if same:
                skipped.append({"starter": sid, "why": "held unchanged"})
                continue
            if old and digest(old) != old["starter"].get("digest"):
                skipped.append({"starter": sid, "why": f"edited by the writer ({old['id']}): never overwritten"})
                continue
            entry = {"id": old["id"] if old else None, "text": r["text"], "slot": old.get("slot") if old else None,
                     "lang": data["lang"], "origin": "starter", "created": old["created"] if old else today,
                     "personal_data": "none", "test": r["test"], "unless_writer_uses": bool(r["unless_writer_uses"]),
                     "starter": {"id": sid, "version": ver}}
            entry["starter"]["digest"] = digest(entry)
            if old and old.get("overrides"):
                entry["overrides"] = old["overrides"]
            if not old:
                last += 1
                entry["id"] = f"r-{last:03d}"
            how = "applies whatever your texts do" if not r["unless_writer_uses"] else \
                "applies unless your own texts do this"
            pending.add("ruling", "modify" if old else "add", f"profiles/{prof}/rulings.yaml",
                        f"{entry['id']} [{sid} {r['category']}] {r['text']} ({how})"
                        + (f"; starter set {old['starter']['version']} -> {ver}" if old else ""),
                        {"ruling": {"profile": prof, "entry": entry}}, profile=prof, ref=entry["id"])
            proposed.append({"id": entry["id"], "starter": sid, "category": r["category"],
                             "op": "modify" if old else "add"})
        if not proposed and len(pending.plan["items"]) == 0:
            stage.discard(store_root)
            return {"proposed": [], "skipped": skipped, "message": "nothing to propose; no run was left open"}
        return {"profile": prof, "set_version": ver, "proposed": proposed, "skipped": skipped,
                "next": "show the diff (stage.py diff); the writer approves or rejects each rule; then commit"}
    except Exception:
        if len(pending.plan["items"]) == 0:
            stage.discard(store_root)
        raise


def add(store_root, profile, text, test=None, unless_writer_uses=False, slot=None, lang=None):
    """Propose one ruling the writer states (spec §27.6)."""
    store = Store(store_root)
    prof = profile or store.config["default_profile"]
    _check_profile(store, prof)
    if not (text or "").strip():
        raise StoreError("a ruling needs its text")
    if test:
        compile_test(test, "the new ruling")
    if unless_writer_uses and not test:
        raise StoreError("unless_writer_uses needs a test to count in the writer's texts")
    store, pending = _open_run(store_root, prof)
    try:
        _, last = _profile_rulings(store, prof, pending)
        entry = {"id": f"r-{last + 1:03d}", "text": text.strip(), "slot": slot, "origin": "stated",
                 "created": utcnow().date().isoformat(), "personal_data": "none"}
        if lang:
            entry["lang"] = lang
        if test:
            entry["test"] = test
            entry["unless_writer_uses"] = bool(unless_writer_uses)
        pending.add("ruling", "add", f"profiles/{prof}/rulings.yaml", f"{entry['id']}: {entry['text']}"
                    + (f" (test: {json.dumps(test, ensure_ascii=False)})" if test else " (no test: the kit only)"),
                    {"ruling": {"profile": prof, "entry": entry}}, profile=prof, slot=slot, ref=entry["id"])
        return {"profile": prof, "proposed": entry["id"],
                "next": "show the diff (stage.py diff); approve or reject; then commit"}
    except Exception:
        if len(pending.plan["items"]) == 0:
            stage.discard(store_root)
        raise


# ---------- importing a style guide (spec §30) ----------

def guide_text(path):
    """The style guide's text as numbered lines, for the model to read and quote. Markdown, Word and
    PDF go through the adapters; anything else is read as plain text."""
    p = pathlib.Path(path)
    if not p.is_file():
        raise StoreError(f"no file {path}")
    from adapters import extract
    ex = extract(p) if p.suffix.lower() in (".md", ".markdown", ".docx", ".pdf") else None
    text = "\n\n".join(b for b in ex.blocks if b.strip()) if ex is not None else p.read_text(encoding="utf-8")
    return [line for line in text.splitlines()]


def _norm(text):
    text = measure.normalise_quotes(text).lower()
    text = re.sub(r"[*_`#>]+", " ", text)
    return " ".join(text.split())


def import_guide(store_root, profile, source, proposals_file):
    """Stage the rules the model found in a style guide. Every proposal quotes the guide; a quote the
    guide does not contain stops the import, so no rule is invented. A rule the profile already holds
    (same wording) is skipped."""
    store = Store(store_root)
    prof = profile or store.config["default_profile"]
    _check_profile(store, prof)
    src = pathlib.Path(source)
    lines = guide_text(src)
    hay = _norm("\n".join(lines)) + " " + _norm(src.read_text(encoding="utf-8", errors="ignore")
                                              if src.suffix.lower() not in (".docx", ".pdf") else "")
    data = load_yaml_text(pathlib.Path(proposals_file).read_text(encoding="utf-8")) or {}
    props = data.get("rules") if isinstance(data, dict) else data
    if not isinstance(props, list) or not props:
        raise StoreError("the proposals file holds no rules (rules: [{text, quote, test?, ...}])")
    problems = []
    for n, r in enumerate(props, 1):
        if not isinstance(r, dict) or not str(r.get("text", "")).strip():
            problems.append(f"rule {n}: no text")
            continue
        q = _norm(str(r.get("quote", "")))
        if len(q) < 3 or q not in hay:
            problems.append(f"rule {n} ({r['text'][:40]}): its quote is not in {src.name}")
        if r.get("test"):
            try:
                compile_test(r["test"], f"rule {n}")
            except StoreError as e:
                problems.append(str(e))
        if r.get("unless_writer_uses") and not r.get("test"):
            problems.append(f"rule {n}: unless_writer_uses needs a test")
    if problems:
        raise StoreError("nothing was staged: " + "; ".join(problems))
    store, pending = _open_run(store_root, prof)
    try:
        base, last = _profile_rulings(store, prof, pending)
        held = {_norm(e["text"]) for e in base["entries"]}
        held |= {_norm(pending.payload(it["id"])["ruling"]["entry"]["text"]) for it in pending.plan["items"]
                 if it["kind"] == "ruling" and it.get("profile") == prof}
        proposed, skipped = [], []
        today = utcnow().date().isoformat()
        for r in props:
            key = _norm(r["text"])
            if key in held:
                skipped.append({"text": r["text"], "why": "the profile already holds this rule"})
                continue
            held.add(key)
            last += 1
            entry = {"id": f"r-{last:03d}", "text": r["text"].strip(), "slot": r.get("slot"), "origin": "stated",
                     "created": today, "personal_data": "none"}
            if r.get("lang"):
                entry["lang"] = r["lang"]
            if r.get("test"):
                entry["test"] = r["test"]
                entry["unless_writer_uses"] = bool(r.get("unless_writer_uses"))
            pending.add("ruling", "add", f"profiles/{prof}/rulings.yaml",
                        f"{entry['id']}: {entry['text']} (from {src.name}: \"{str(r['quote']).strip()[:80]}\")"
                        + (" (checked)" if entry.get("test") else ""),
                        {"ruling": {"profile": prof, "entry": entry}}, profile=prof, slot=entry["slot"],
                        ref=entry["id"])
            proposed.append({"id": entry["id"], "text": entry["text"], "checked": bool(entry.get("test"))})
        if not proposed and not pending.plan["items"]:
            stage.discard(store_root)
        return {"profile": prof, "source": src.name, "proposed": proposed, "skipped": skipped,
                "next": "show the diff (stage.py diff); approve or reject each rule; then commit"
                if proposed else "nothing new to propose"}
    except Exception:
        if len(pending.plan["items"]) == 0:
            stage.discard(store_root)
        raise


def show(store, profile=None, facets=None):
    prof, slot, _ = resolve.resolve(store, profile, facets)
    rs = applicable(store, prof, slot)
    rates = writer_rates(store, prof, slot, rs)
    return {"profile": prof, "slot": slot, "rulings": [
        {"id": r["id"], "from": r["profile"], "text": r["text"], "test": r.get("test"),
         "unless_writer_uses": bool(r.get("unless_writer_uses")),
         "writer_per_1k": rates.get(r["id"]), "starter": (r.get("starter") or {}).get("id")} for r in rs]}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--store")
    ap.add_argument("action", choices=["defaults", "add", "show", "starter", "guide-text", "import"])
    ap.add_argument("--source", help="guide-text / import: the style guide")
    ap.add_argument("--file", help="import: the proposals (YAML)")
    ap.add_argument("--profile")
    ap.add_argument("--lang")
    ap.add_argument("--type")
    ap.add_argument("--facet", action="append", default=[])
    ap.add_argument("--category", action="append")
    ap.add_argument("--text")
    ap.add_argument("--chars", nargs="+")
    ap.add_argument("--words", nargs="+")
    ap.add_argument("--phrases", nargs="+")
    ap.add_argument("--pattern")
    ap.add_argument("--unless-writer-uses", action="store_true")
    ap.add_argument("--slot")
    a = ap.parse_args(argv)
    try:
        if a.action == "starter":
            out = starter(a.lang or "en")
        elif a.action == "guide-text":
            out = {"source": a.source, "lines": [f"{i}: {x}" for i, x in enumerate(guide_text(a.source), 1)]}
        elif not a.store:
            raise StoreError("no store given (discover one first, see SKILL.md)")
        elif a.action == "import":
            out = import_guide(a.store, a.profile, a.source, a.file)
        elif a.action == "defaults":
            out = defaults(a.store, a.profile, a.lang or "en", a.category)
        elif a.action == "add":
            forms = {k: v for k, v in (("chars", a.chars), ("words", a.words), ("phrases", a.phrases),
                                       ("pattern", a.pattern)) if v}
            if len(forms) > 1:
                raise StoreError("give one test form: --chars, --words, --phrases or --pattern")
            out = add(a.store, a.profile, a.text, forms or None, a.unless_writer_uses, a.slot, a.lang)
        else:
            facets = {"lang": a.lang, "type": a.type}
            for f in a.facet:
                k, _, v = f.partition("=")
                facets[k] = v
            out = show(Store(a.store), a.profile, facets)
    except (StoreError, resolve.NoSlot) as e:
        print(json.dumps({"status": "error", "message": str(e)}, indent=1, ensure_ascii=False))
        return 1
    print(json.dumps(out, indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
