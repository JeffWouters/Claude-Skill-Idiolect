"""aisigns: the built-in signs of machine-written text (spec §37). Part of the skill, not of a profile:
every write, rewrite and check uses them, whatever the profile.

    python3 aisigns.py list [--lang L]                       the signs and the guidance for a language
    python3 aisigns.py scan --file F [--lang L] [--json]     the signs a text shows (no store, no writer)
    python3 aisigns.py --store S allow --profile P --sign a-009 [--text T]
                                                             switch a sign off for a writer (a ruling, after approval)

Signs live in assets/ai-signs/: universal.yaml (any language, plus the guidance for what no script can
test) and <lang>.yaml. Tier `always` fails a draft whatever the writer does; tier `unless_writer` fails
it unless the writer's own texts of the slot do it, and then only above about twice their rate. A
profile decides instead of the built-in sign when it holds the starter rule the sign extends (or
declined it, §27.5), or a ruling that overrides the sign (`allow`). An `always` sign cannot be switched
off. check.py and kit.py use the functions below.
"""
import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import measure  # noqa: E402
import resolve  # noqa: E402
import rules  # noqa: E402
from common import StoreError, count_words, load_yaml_text, read_store_file, utcnow  # noqa: E402

SIGN_DIR = pathlib.Path(__file__).resolve().parent.parent / "assets" / "ai-signs"
TIERS = ("always", "unless_writer")
_cache = {}


# ---------- the lists ----------

def _read(name):
    if name not in _cache:
        f = SIGN_DIR / f"{name}.yaml"
        _cache[name] = load_yaml_text(f.read_text(encoding="utf-8")) if f.exists() else None
    return _cache[name]


def base_lang(lang):
    return (lang or "").split("-")[0]


def load(lang):
    """{"version", "lang", "covered", "signs", "guidance"}: the universal signs plus the language's own.
    `covered` is False when the language has no list (then only the universal signs apply)."""
    uni = _read("universal")
    own = _read(base_lang(lang)) if base_lang(lang) and base_lang(lang) != "universal" else None
    signs = list(own["signs"] if own else []) + list(uni["signs"])
    for s in signs:
        s.setdefault("min_hits", 1)
        s["_pat"] = s.get("_pat") or rules.compile_test(s["test"], f"AI sign {s['id']}")
    version = uni["version"] if not own else f"{own['version']}"
    return {"version": version, "lang": base_lang(lang), "covered": own is not None, "signs": signs,
            "guidance": list(uni.get("guidance", []))}


def problems(name):
    """What is wrong with one sign file: tests that do not compile, examples the test misses and
    not-examples it catches, duplicate ids, unknown tiers. Empty when the file is sound."""
    data = _read(name)
    if data is None:
        return [f"no sign file {name}.yaml"]
    out, seen = [], set()
    for s in data.get("signs", []):
        sid = s.get("id", "?")
        if sid in seen:
            out.append(f"{sid}: duplicate id")
        seen.add(sid)
        if s.get("tier") not in TIERS:
            out.append(f"{sid}: tier is one of {', '.join(TIERS)}")
        try:
            pat = rules.compile_test(s["test"], f"AI sign {sid}")
        except (StoreError, KeyError) as e:
            out.append(f"{sid}: {e}")
            continue
        need = s.get("min_hits", 1)
        for ex in s.get("examples", []):
            if rules.count(pat, ex) < need:
                out.append(f"{sid}: misses its example {ex!r}")
        for ex in s.get("not", []):
            if rules.count(pat, ex) >= need:
                out.append(f"{sid}: catches its not-example {ex!r}")
        if not s.get("examples"):
            out.append(f"{sid}: no examples")
    return out


def find(sign_id):
    """(sign, file name) for an id in any list."""
    for f in sorted(SIGN_DIR.glob("*.yaml")):
        data = _read(f.stem)
        for s in data.get("signs", []):
            if s["id"] == sign_id:
                return s, f.stem
    raise StoreError(f"no built-in AI sign {sign_id}; `aisigns.py list` shows them")


# ---------- what applies to a profile ----------

def _profile_decisions(store, prof):
    """(allowed sign ids, starter ids held, starter ids declined) down the profile's chain."""
    rulings = resolve.merged(store, prof, "rulings")
    allowed = {r["overrides"] for r in rulings if str(r.get("overrides") or "").startswith("a-")}
    held = {r["starter"]["id"] for r in rulings if r.get("starter")}
    declined = set()
    for p in resolve.chain(store, prof):
        f = store.root / "profiles" / p / "rulings.yaml"
        if f.exists():
            declined |= {d["starter"] for d in read_store_file(f, "rulings").get("declined", [])}
    return allowed, held, declined


def applicable(store, prof, slot):
    """{"signs": the signs check applies, "allowed": signs this writer switched off, "deferred": signs
    the profile's own copy of a starter rule decides, "version", "covered", "guidance"}."""
    data = load(slot.split(".")[0])
    allowed, held, declined = _profile_decisions(store, prof)
    signs, off, deferred = [], [], []
    for s in data["signs"]:
        if s.get("starter") in held:
            deferred.append(s)              # the profile's ruling (perhaps edited) decides
        elif s["tier"] == "unless_writer" and (s["id"] in allowed or s.get("starter") in declined):
            off.append(s)
        else:
            signs.append(s)
    return {**data, "signs": signs, "allowed": off, "deferred": deferred}


def writer_rates(store, prof, slot, signs):
    """{sign id: uses per 1,000 words in the writer's own texts of the slot} for the unless_writer
    signs (holdouts left out, as for rulings)."""
    want = [s for s in signs if s["tier"] == "unless_writer"]
    if not want:
        return {}
    def text_of(key):
        try:
            return store.corpus_text(key)
        except StoreError:
            return ""                       # a missing cache counts as no text; the check still runs
    slots = measure.slot_texts(store.manifest["texts"], text_of, store.facets, prof)
    texts = [t for _, t, _ in (slots.get(slot) or {}).get("texts", [])]
    n = sum(count_words(t) for t in texts)
    if not n:
        return {s["id"]: 0.0 for s in want}
    return {s["id"]: round(sum(rules.count(s["_pat"], t) for t in texts) * 1000 / n, 2) for s in want}


def without_front_matter(text):
    """The text with a leading YAML front matter block blanked, so its --- lines are not read as
    horizontal rules; line numbers stay the same."""
    lines = text.split("\n")
    if lines and lines[0].strip() == "---":
        for i in range(1, min(len(lines), 80)):
            if lines[i].strip() in ("---", "..."):
                return "\n".join([""] * (i + 1) + lines[i + 1:])
    return text


def flag(text, signs, rates, n_words):
    """Flagged lines for every sign the text shows beyond what this writer's own texts allow."""
    text = without_front_matter(text)
    lines = []
    for s in signs:
        found = rules.hits_per_line(s["_pat"], text)
        total = sum(n for _, _, n in found)
        if total < s["min_hits"]:
            continue
        rate = rates.get(s["id"], 0.0) if s["tier"] == "unless_writer" else 0.0
        if rate > 0:
            draft_rate = total * 1000 / max(n_words, 1)
            if total < max(s["min_hits"], rules.MIN_HITS) or draft_rate <= rules.RATE_FACTOR * rate:
                continue
            why = (f"sounds like AI ({s['id']}, {s['category']}): {total} uses, {draft_rate:.1f} per 1,000 words; "
                   f"the writer's texts about {rate:g}")
        elif s["min_hits"] > 1:
            why = f"sounds like AI ({s['id']}, {s['category']}): {total} together in one text"
        else:
            why = f"sounds like AI ({s['id']}, {s['category']})"
        for i, line, _ in found:
            lines.append({"line": i, "text": line.strip()[:200], "lesson": s["id"], "reason": f"{why}: {s['text']}"})
    return lines


def scan(text, lang="en"):
    """The signs a text shows, with no writer to compare with: every sign at a rate of zero."""
    data = load(lang)
    return {"version": data["version"], "lang": data["lang"], "covered": data["covered"],
            "lines": flag(text, data["signs"], {}, count_words(text))}


# ---------- the kit ----------

def kit_part(store, prof, slot):
    part = applicable(store, prof, slot)
    rates = writer_rates(store, prof, slot, part["signs"])
    return {"version": part["version"], "lang": part["lang"], "covered": part["covered"],
            "signs": [{"id": s["id"], "text": s["text"], "tier": s["tier"],
                       "rate": rates.get(s["id"], 0.0)} for s in part["signs"]],
            "allowed": [{"id": s["id"], "text": s["text"]} for s in part["allowed"]],
            "deferred": [s["id"] for s in part["deferred"]], "guidance": part["guidance"]}


def kit_lines(part, export=False):
    """The kit's section; with export=True, worded for another tool that has no `check` (spec §22)."""
    whose = "the writer's texts" if export else "your texts"
    L = ["", f"## Never sound like AI (built into Idiolect, signs {part['version']})",
         ("These are signs of machine-written text. Never write them, except where the writer's own texts do "
          "(then never more often than the rate given). Before handing over a draft, reread it for each one."
          if export else
          "These apply to every voice. `check` fails a draft that shows one; where the writer's own texts do "
          "it, only above about twice their rate.")]
    for s in part["signs"]:
        note = (f" ({whose} do this about {s['rate']:g} times per 1,000 words: never more)"
                if s["tier"] == "unless_writer" and s["rate"] else "")
        L.append(f"- {s['text']}{note}")
    if not part["covered"]:
        L.append(f"- No list of signs for '{part['lang']}' yet: only the language-independent ones are listed. "
                 f"Watch for the same kinds of sign in this language.")
    if part["allowed"]:
        L.append(("- Allowed for this writer (their own choice): " if export else
                  "- Switched off for this writer (their own choice): ")
                 + "; ".join(f"{s['id']} ({s['text'][:60]}…)" for s in part["allowed"]))
    if part["guidance"]:
        L += ["", "Also, where no script can check it:"] + [f"- {g}" for g in part["guidance"]]
    return L


# ---------- switching a sign off for a writer ----------

def allow(store_root, profile, sign_id, text=None):
    """Propose a ruling that switches an unless_writer sign off for this profile (and its children)."""
    from store import Store
    import stage
    sign, lang = find(sign_id)
    if sign["tier"] == "always":
        raise StoreError(f"{sign_id} is a leftover no writer means to keep ({sign['category']}); it cannot be "
                         f"switched off")
    store = Store(store_root)
    prof = profile or store.config["default_profile"]
    rules._check_profile(store, prof)
    store, pending = rules._open_run(store_root, prof)
    try:
        _, last = rules._profile_rulings(store, prof, pending)
        entry = {"id": f"r-{last + 1:03d}",
                 "text": (text or f"Allowed for this writer: built-in AI sign {sign_id} does not apply "
                                  f"({sign['text']})").strip(),
                 "slot": None, "overrides": sign_id, "origin": "stated",
                 "created": utcnow().date().isoformat(), "personal_data": "none"}
        if lang != "universal":
            entry["lang"] = lang
        pending.add("ruling", "add", f"profiles/{prof}/rulings.yaml",
                    f"{entry['id']}: switch built-in AI sign {sign_id} off for {prof} ({sign['category']})",
                    {"ruling": {"profile": prof, "entry": entry}}, profile=prof, ref=entry["id"])
        return {"profile": prof, "proposed": entry["id"], "sign": sign_id,
                "next": "show the diff (stage.py diff); approve or reject; then commit"}
    except Exception:
        if len(pending.plan["items"]) == 0:
            stage.discard(store_root)
        raise


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--store")
    ap.add_argument("action", choices=["list", "scan", "allow"])
    ap.add_argument("--lang", default="en")
    ap.add_argument("--file")
    ap.add_argument("--profile")
    ap.add_argument("--sign")
    ap.add_argument("--text")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    try:
        if a.action == "list":
            d = load(a.lang)
            out = {"version": d["version"], "lang": d["lang"], "covered": d["covered"],
                   "signs": [{k: s[k] for k in ("id", "category", "tier", "text")} for s in d["signs"]],
                   "guidance": d["guidance"]}
        elif a.action == "scan":
            if not a.file:
                raise StoreError("scan needs --file")
            out = scan(pathlib.Path(a.file).read_text(encoding="utf-8"), a.lang)
            if not a.json:
                print(f"{len(out['lines'])} line(s) with signs of machine-written text (signs {out['version']}, "
                      f"{out['lang']}{'' if out['covered'] else ', language-independent signs only'})")
                for x in out["lines"]:
                    print(f"- line {x['line']}: {x['reason']}")
                return 0
        else:
            if not (a.store and a.sign):
                raise StoreError("allow needs --store, --profile and --sign")
            out = allow(a.store, a.profile, a.sign, a.text)
    except StoreError as e:
        print(json.dumps({"status": "error", "message": str(e)}))
        return 2
    print(json.dumps(out, indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
