"""flavour: the writer's language flavour (spec §34). Traces of another language in how the writer writes
this one, how each is recognised, and how often the writer shows them.

    flavour.py detect --lang L --file TEXT            run the pack's detectors over any text (read-only)
    flavour.py --store S show --profile P --lang L     the profile's flavour file, readable

Inside a learn run the steps are `learn.py flavour-sample` and `learn.py flavour-apply` (learn.md);
kit.py and check.py use the approved file. Nothing here writes a store file directly: everything goes
through the pending area and the writer's approval.
"""
import argparse
import collections
import json
import pathlib
import random
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import measure  # noqa: E402
import redact as redactmod  # noqa: E402
from common import (LANG_DIR, StoreError, check_schema, count_words, dump_yaml, iso, load_yaml_text,  # noqa: E402
                    read_store_file, utcnow)

FLAGS = re.I | re.M
SAMPLE_CAP = 20000          # words, as the lessons sample
MAX_PATTERN_RATE = 10.0     # per 1,000 words: a pattern above this is too broad to be a trace
MAX_EXAMPLES = 3
EXAMPLE_WORDS = 25
MIN_WORDS_FOR_MAX = 300     # the highest rate is taken over texts at least this long
CONTEXT = 60


# ---------- detectors (spec §34.2) ----------

def base_lang(lang):
    return (lang or "").split("-")[0]


def detectors(lang):
    """The pack's detectors for this language, [] when the pack has none."""
    f = LANG_DIR / base_lang(lang) / "flavours.yaml"
    if not f.exists():
        return []
    return (load_yaml_text(f.read_text(encoding="utf-8")) or {}).get("detectors") or []


def compile_pattern(p):
    return re.compile(p, FLAGS)


def prep(text):
    return measure.normalise_quotes(text)


PARA = re.compile(r"(?:(?!\n[ \t]*\n).)+", re.S)


def finditer(rx, text):
    """Matches of rx within each paragraph of an already prepared text: a trace never spans a paragraph
    break (a web page's removed code block leaves 'you can see' and 'Now that ...' side by side)."""
    for para in PARA.finditer(text):
        yield from rx.finditer(text, para.start(), para.end())


def hits(rx, text):
    return sum(1 for _ in finditer(rx, prep(text)))


def check_detectors(lang):
    """Problems with a pack's flavours.yaml (langpack.py check)."""
    out, seen = [], set()
    for d in detectors(lang):
        did = d.get("id", "?")
        where = f"{lang}/flavours.yaml {did}"
        for key in ("id", "name", "origins", "how", "pattern", "examples"):
            if not d.get(key):
                out.append(f"{where}: no {key}")
        if did in seen:
            out.append(f"{where}: id used twice")
        seen.add(did)
        if not re.match(r"^[a-z0-9-]+$", did):
            out.append(f"{where}: id must be lower case letters, digits and hyphens")
        for o in d.get("origins") or []:
            if not re.match(r"^[a-z]{2,3}$", o):
                out.append(f"{where}: origin {o!r} is not a language code")
        try:
            rx = compile_pattern(d.get("pattern") or "")
        except re.error as e:
            out.append(f"{where}: pattern does not compile ({e})")
            continue
        for ex in d.get("examples") or []:
            if not rx.search(prep(ex)):
                out.append(f"{where}: misses its example {ex!r}")
        for n in d.get("not") or []:
            if rx.search(prep(n)):
                out.append(f"{where}: matches its counter-example {n!r}")
    return out


# ---------- texts ----------

def own_texts(entries, get_text, facet_names, profile, lang):
    """[(key, text)] of every own text of the profile in this language, whatever the slot."""
    return [(k, t) for k, slot, t, _ in measure.profile_texts(entries, get_text, facet_names, profile)
            if slot.split(".")[0] == lang]


def _norm_ws(s):
    return re.sub(r"\s+", " ", prep(s)).strip().lower()


def normalise_name(name):
    return " ".join(re.sub(r"[^\w\s]", " ", (name or "").lower()).split())


def sentence_at(text, start, end):
    """The sentence around a match, cut to EXAMPLE_WORDS words around it."""
    t = prep(text)
    a = max(t.rfind(". ", 0, start), t.rfind("! ", 0, start), t.rfind("? ", 0, start), t.rfind("\n", 0, start))
    a = 0 if a < 0 else a + 1
    ends = [x for x in (t.find(". ", end), t.find("! ", end), t.find("? ", end), t.find("\n", end)) if x >= 0]
    b = (min(ends) + 1) if ends else len(t)
    s = t[a:b].strip()
    ws = s.split()
    if len(ws) > EXAMPLE_WORDS:
        before = len(t[a:start].split())
        lo = max(0, min(before - EXAMPLE_WORDS // 2, len(ws) - EXAMPLE_WORDS))
        s = " ".join(ws[lo:lo + EXAMPLE_WORDS])
    return s


def matches(rx, texts, n=MAX_EXAMPLES, context=None):
    """Up to n matches as [(key, sentence or context)], one per text first, in text order."""
    out, used = [], set()
    for rnd in range(2):
        for k, t in texts:
            if len(out) >= n:
                return out
            if rnd == 0 and k in used:
                continue
            for m in finditer(rx, prep(t)):
                if context:
                    tt = prep(t)
                    snip = tt[max(0, m.start() - context):m.end() + context].replace("\n", " ")
                    item = (k, snip)
                else:
                    g = m.group(0)      # a pattern may start on the previous sentence's full stop
                    item = (k, sentence_at(t, m.start() + len(g) - len(g.lstrip(".!?:; \t\n")), m.end()))
                if item not in out:
                    out.append(item)
                    used.add(k)
                    break
    return out[:n]


# ---------- counting (spec §34.6-7) ----------

def marker_hits(marker, texts):
    """{key: hits} of one marker over [(key, text)]."""
    if marker.get("pattern"):
        rx = compile_pattern(marker["pattern"])
        return {k: n for k, n in ((k, hits(rx, t)) for k, t in texts) if n}
    have = {k for k, _ in texts}
    out = collections.Counter(k for k in marker.get("sources") or [] if k in have)
    return dict(out)


def count_of(per_text, texts, measured):
    words = sum(count_words(t) for _, t in texts) or 1
    total = sum(per_text.values())
    return {"hits": total, "texts": len(per_text), "per_1k": round(total * 1000 / words, 2), "measured": measured}


def totals(markers, per_marker, texts):
    """rate, origins and strength of a flavour file from its markers' hits."""
    words = {k: count_words(t) for k, t in texts}
    all_words = sum(words.values())
    per_text = collections.Counter()
    by_origin = collections.Counter()
    for m in markers:
        for k, n in per_marker.get(m["id"], {}).items():
            per_text[k] += n
            by_origin[m["origin"]] += n
    total = sum(per_text.values())
    long_ = [k for k in words if words[k] >= MIN_WORDS_FOR_MAX] or list(words)
    mx = max([per_text[k] * 1000 / words[k] for k in long_ if words[k]] or [0])
    per_1k = round(total * 1000 / all_words, 2) if all_words else 0
    rate = {"per_1k": per_1k, "texts": sum(1 for k in per_text if per_text[k]), "of": len(texts),
            "words": all_words, "max_per_1k": round(mx, 2)}
    strength = "none" if not markers else "light" if per_1k < 1 else "moderate" if per_1k < 4 else "strong"
    origins = [o for o, _ in sorted(by_origin.items(), key=lambda x: (-x[1], x[0])) if by_origin[o]]
    return rate, origins, strength


def build(profile, lang, markers, texts, last_id=0, rejected=(), built=None):
    """The flavour file for these markers, recounted over texts; markers with no hit are left out."""
    per, kept = {}, []
    have = {k for k, _ in texts}
    for m in sorted(markers, key=lambda x: x["id"]):
        m = dict(m)
        if m.get("sources"):
            # an example from a text the profile no longer has goes with that text
            pairs = [(e, s) for e, s in zip(m.get("examples", []), m["sources"]) if s in have]
            m["examples"], m["sources"] = [e for e, _ in pairs], [s for _, s in pairs]
        h = marker_hits(m, texts)
        if not h:
            continue
        m["count"] = count_of(h, texts, "pattern" if m.get("pattern") else "examples")
        per[m["id"]] = h
        kept.append(m)
    rate, origins, strength = totals(kept, per, texts)
    data = {"schema_version": 1, "profile": profile, "lang": lang, "built": built or iso(utcnow()),
            "last_id": max([last_id] + [int(m["id"].split("-")[1]) for m in markers]
                           + [int(r["id"].split("-")[1]) for r in rejected]),
            "origins": origins, "strength": strength, "rate": rate, "markers": kept}
    if rejected:
        data["rejected"] = list(rejected)
    return check_schema("flavour", data, f"flavour {profile}/{lang}")


# ---------- the store ----------

def path_of(profile, lang):
    return f"profiles/{profile}/{lang}.flavour.yaml"


def read(store, profile, lang):
    f = store.root / path_of(profile, lang)
    return read_store_file(f, "flavour") if f.exists() else None


def for_profile(store, profile, lang):
    """The flavour file the profile writes with: its own, or the nearest parent's."""
    import resolve
    for p in resolve.chain(store, profile):
        fl = read(store, p, lang)
        if fl is not None:
            return {**fl, "from_profile": p}
    return None


def describe_rate(per_1k):
    if per_1k <= 0:
        return "never"
    every = 1000 / per_1k
    if every >= 1000:
        return f"about once every {round(every, -2):,.0f} words"
    return f"about once every {round(every, -1):,.0f} words"


# ---------- in a learn run (spec §34.4-6) ----------

def _run_texts(run, prof, lang):
    return own_texts(run.view(), run.text, run.store.facets, prof, lang)


def run_langs(run):
    """(profile, lang) pairs whose slots this run measured."""
    return sorted({(s["profile"], s["slot"].split(".")[0]) for s in run.state.get("slots", [])})


def sample(store_root, prof, lang):
    import learn
    run = learn.Run(store_root)
    texts = _run_texts(run, prof, lang)
    if not texts:
        raise StoreError(f"no own texts of {prof} in {lang}")
    words = sum(count_words(t) for _, t in texts)
    found = []
    by_origin = collections.Counter()
    for d in detectors(lang):
        rx = compile_pattern(d["pattern"])
        per = {k: n for k, n in ((k, hits(rx, t)) for k, t in texts) if n}
        if not per:
            continue
        total = sum(per.values())
        for o in d["origins"]:
            by_origin[o] += total
        found.append({"detector": d["id"], "name": d["name"], "origins": d["origins"], "how": d["how"],
                      "hits": total, "texts": len(per), "per_1k": round(total * 1000 / words, 2),
                      "matches": [{"key": k, "context": c} for k, c in matches(rx, texts, 3, CONTEXT)]})
    found.sort(key=lambda x: (-x["hits"], x["detector"]))
    # the sample: as the lessons sample, across every type of text in this language
    rng = random.Random(measure.slot_seed(prof, lang) + 5)
    view = run.view()
    dated = sorted(texts, key=lambda kt: ((view.get(kt[0]) or {}).get("date") or "", kt[0]))
    per = max(300, SAMPLE_CAP // max(1, len(dated)))
    parts, total = [], 0
    for k, t in learn.spread(dated, per, SAMPLE_CAP):
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
        if total + count_words(body) > SAMPLE_CAP and parts:
            break
        parts.append(f"### text {k}\n\n{body}")
        total += count_words(body)
    out = run.pending.work("flavour", prof, lang, "sample.md")
    out.write_text("\n\n".join(parts), encoding="utf-8")
    cur = read(run.store, prof, lang) or {}
    return {"sample": str(out), "words_sampled": total, "texts": len(texts), "words": words,
            "detected": found, "origins": [o for o, _ in by_origin.most_common()],
            "pack_detectors": len(detectors(lang)),
            "existing": [{"id": m["id"], "name": m["name"], "origin": m["origin"], "detector": m.get("detector")}
                         for m in cur.get("markers", [])],
            "rejected": [{"name": r["name"], "detector": r.get("detector")} for r in cur.get("rejected", [])],
            "format": "flavour.yaml: {markers: [{detector: <id>, origin?}, {name, how, origin, pattern?, "
                      "examples: [{key, quote}]}]}; markers: [] when the writer shows no flavour"}


def _plan_last(pending, prof, lang):
    n = 0
    for it in pending.plan["items"]:
        if it["kind"] != "flavour":
            continue
        body = pending.payload(it["id"]).get("flavour") or {}
        if body.get("profile") == prof and body.get("lang") == lang and body.get("marker"):
            n = max(n, int(body["marker"]["id"].split("-")[1]))
    return n


def apply(store_root, prof, lang, file, names=None):
    import learn
    run = learn.Run(store_root)
    data = load_yaml_text(pathlib.Path(file).read_text(encoding="utf-8")) or {}
    proposals = data.get("markers", []) if isinstance(data, dict) else data
    wanted_origins = (data.get("origins") or []) if isinstance(data, dict) else []
    texts = _run_texts(run, prof, lang)
    if not texts:
        raise StoreError(f"no own texts of {prof} in {lang}")
    by_key = dict(texts)
    words = sum(count_words(t) for _, t in texts)
    dets = {d["id"]: d for d in detectors(lang)}
    cur = read(run.store, prof, lang) or {}
    existing = {m["id"]: m for m in cur.get("markers", [])}
    ex_by_det = {m["detector"]: m for m in existing.values() if m.get("detector")}
    ex_by_name = {normalise_name(m["name"]): m for m in existing.values()}
    rej_det = {r["detector"] for r in cur.get("rejected", []) if r.get("detector")}
    rej_name = {r["normalised"] for r in cur.get("rejected", [])}
    run.pending.remove_items(lambda i: i["kind"] == "flavour" and i.get("profile") == prof
                             and (run.pending.payload(i["id"]).get("flavour") or {}).get("lang") == lang)
    last = max(cur.get("last_id") or 0, _plan_last(run.pending, prof, lang))
    problems, dropped, kept_ids, staged = [], [], set(), []
    all_per = {}
    for p in proposals:
        p = p or {}
        if p.get("detector"):
            d = dets.get(p["detector"])
            if not d:
                problems.append(f"unknown detector {p['detector']!r} for {lang}")
                continue
            origin = p.get("origin") or next((o for o in wanted_origins if o in d["origins"]), d["origins"][0])
            m = {"name": p.get("name") or d["name"], "origin": origin, "how": p.get("how") or d["how"],
                 "pattern": d["pattern"], "detector": d["id"]}
            rx = compile_pattern(d["pattern"])
            got = matches(rx, texts)
            quotes = [(k, q) for k, q in got]
        else:
            m = {"name": (p.get("name") or "").strip(), "origin": p.get("origin") or "unknown",
                 "how": (p.get("how") or "").strip()}
            if not m["name"] or not m["how"]:
                problems.append(f"a marker needs a name and how: {p}")
                continue
            if not re.match(r"^([a-z]{2,3}|unknown)$", m["origin"]):
                problems.append(f"{m['name']}: origin {m['origin']!r} is not a language code; set to unknown")
                m["origin"] = "unknown"
            quotes = []
            for ex in p.get("examples") or []:
                k, q = (ex.get("key"), ex.get("quote")) if isinstance(ex, dict) else (None, ex)
                q = (q or "").strip()
                if k in by_key and q and _norm_ws(q) in _norm_ws(by_key[k]):
                    quotes.append((k, q))
                else:
                    problems.append(f"{m['name']}: example not found in its text: {q[:60]!r}")
            if p.get("pattern"):
                try:
                    rx = compile_pattern(p["pattern"])
                except re.error as e:
                    problems.append(f"{m['name']}: pattern does not compile ({e}); counted by its examples")
                    rx = None
                if rx is not None:
                    missed = [q for _, q in quotes if not rx.search(prep(q))]
                    rate = sum(hits(rx, t) for _, t in texts) * 1000 / max(1, words)
                    if missed:
                        problems.append(f"{m['name']}: pattern misses the example {missed[0][:60]!r}; counted by its examples")
                    elif rate > MAX_PATTERN_RATE:
                        problems.append(f"{m['name']}: pattern matches {rate:.1f} per 1,000 words, too broad for a "
                                        f"trace; counted by its examples")
                    else:
                        m["pattern"] = p["pattern"]
            if not quotes and not m.get("pattern"):
                problems.append(f"{m['name']}: no verified example and no pattern; left out")
                continue
            if not quotes and m.get("pattern"):
                quotes = matches(compile_pattern(m["pattern"]), texts)
        norm = normalise_name(m["name"])
        if (m.get("detector") and m["detector"] in rej_det) or norm in rej_name:
            dropped.append(m["name"])
            continue
        # examples: redacted, at most MAX_EXAMPLES
        exs, srcs, shown = [], [], []
        for k, q in quotes[:MAX_EXAMPLES]:
            red, repl = redactmod.redact(q, names)
            exs.append(red)
            srcs.append(k)
            shown += [f"{r['found']} → {r['placeholder']}" for r in repl]
        m["examples"] = exs
        m["sources"] = srcs
        h = marker_hits(m, texts)
        if not h:
            problems.append(f"{m['name']}: no trace in the texts; left out")
            continue
        m["count"] = count_of(h, texts, "pattern" if m.get("pattern") else "examples")
        prev = ex_by_det.get(m.get("detector")) if m.get("detector") else None
        prev = prev or ex_by_name.get(norm)
        if prev and prev["id"] not in kept_ids:
            m["id"] = prev["id"]
        else:
            last += 1
            m["id"] = f"f-{last:03d}"
        kept_ids.add(m["id"])
        m = {k: m[k] for k in ("id", "name", "origin", "how", "pattern", "detector", "examples", "sources", "count")
             if k in m}
        all_per[m["id"]] = h
        if prev and prev["id"] == m["id"] and prev == m:
            continue
        c = m["count"]
        summary = (f"{m['id']} ({m['origin']}) {m['name']}: {c['per_1k']} per 1,000 words, in {c['texts']} of "
                   f"{len(texts)} texts, counted by {'pattern' if c['measured'] == 'pattern' else 'its examples (at least)'}"
                   + (f"; e.g. \"{m['examples'][0]}\"" if m["examples"] else "")
                   + (f" [redacted: {'; '.join(shown)}]" if shown else ""))
        run.pending.add("flavour", "modify" if prev and prev["id"] == m["id"] else "add", path_of(prof, lang),
                        summary, {"flavour": {"profile": prof, "lang": lang, "marker": m}},
                        profile=prof, ref=m["id"])
        staged.append(m["id"])
    for x in existing.values():
        if x["id"] not in kept_ids:
            run.pending.add("flavour", "remove", path_of(prof, lang), f"{x['id']} no longer found or proposed: {x['name']}",
                            {"flavour": {"profile": prof, "lang": lang, "marker": x}}, profile=prof, ref=x["id"])
    run.state["steps"].setdefault("flavour", []).append(f"{prof}/{lang}")
    run.save()
    proposed = []
    for it in run.pending.plan["items"]:
        if it["kind"] == "flavour" and it["op"] != "remove" and it.get("profile") == prof:
            body = run.pending.payload(it["id"])["flavour"]
            if body["lang"] == lang:
                proposed.append(body["marker"])
    unchanged = [x for x in existing.values() if x["id"] in kept_ids and x["id"] not in staged]
    rate, origins, strength = totals(proposed + unchanged,
                                     {m["id"]: marker_hits(m, texts) for m in proposed + unchanged}, texts)
    return {"staged": staged, "dropped_as_rejected": dropped, "problems": problems,
            "if_all_approved": {"strength": strength, "origins": origins, "rate": rate},
            "next": learn._next(learn.Run(store_root))}


# ---------- commit (spec §34.7), called by stage.prepare_commit ----------

def render_commit(store, pending, view, get_text, recount=(), staged=None):
    """{path: yaml} for every flavour file this plan touches, and for the existing flavour files of the
    `recount` profiles (their texts may have changed), whenever the result differs. `staged` holds the
    files this commit already writes: a flavour file restored by a rollback is recounted as restored,
    and one it deletes stays deleted."""
    staged = staged or {}
    plan = pending.plan
    writer = pending.writer_decisions()
    groups = collections.defaultdict(list)
    for it in plan["items"]:
        if it["kind"] != "flavour":
            continue
        body = pending.payload(it["id"]).get("flavour") or {}
        groups[(body["profile"], body["lang"])].append((it, body))
    for prof in recount:
        for f in sorted((store.root / "profiles" / prof).glob("*.flavour.yaml")):
            groups.setdefault((prof, f.name[: -len(".flavour.yaml")]), [])
    today = utcnow().date().isoformat()
    out = {}
    for (prof, lang), items in sorted(groups.items()):
        rel = path_of(prof, lang)
        if rel in staged:
            if staged[rel] is None:
                continue
            cur = check_schema("flavour", load_yaml_text(staged[rel]), rel)
        else:
            cur = read(store, prof, lang)
        markers = {m["id"]: m for m in (cur or {}).get("markers", [])}
        rejected = list((cur or {}).get("rejected", []))
        last = max((cur or {}).get("last_id") or 0, _plan_last(pending, prof, lang))
        for it, body in items:
            m = body.get("marker")
            if not m:
                continue            # a recount
            if it["decision"] == "approved":
                if it["op"] == "remove":
                    markers.pop(m["id"], None)
                    if body.get("reject") and not any(r["id"] == m["id"] for r in rejected):
                        # removed by the writer (maintain.py remove, spec §36): not proposed again
                        entry = {"id": m["id"], "name": m["name"], "normalised": normalise_name(m["name"]),
                                 "rejected": today}
                        if m.get("detector"):
                            entry["detector"] = m["detector"]
                        rejected.append(entry)
                else:
                    markers[m["id"]] = m
            elif writer.get(it["id"]) == "rejected" and it["op"] == "add":
                entry = {"id": m["id"], "name": m["name"], "normalised": normalise_name(m["name"]), "rejected": today}
                if m.get("detector"):
                    entry["detector"] = m["detector"]
                rejected.append(entry)
        if cur is None and not markers and not rejected:
            continue
        texts = own_texts(view, get_text, store.facets, prof, lang)
        data = build(prof, lang, list(markers.values()), texts, last, rejected)
        if cur is not None and rel not in staged and {k: v for k, v in data.items() if k != "built"} == \
                {k: v for k, v in cur.items() if k != "built"}:
            continue
        out[path_of(prof, lang)] = dump_yaml(data)
    return out


# ---------- using it: kit and check (spec §34.8-9) ----------

LANG_NAMES = {"en": "English", "nl": "Dutch", "de": "German", "fr": "French", "es": "Spanish", "it": "Italian",
              "pt": "Portuguese", "pl": "Polish"}


def lang_name(code):
    return LANG_NAMES.get(base_lang(code), code)


def n_of(n, word):
    return f"{n} {word}" + ("" if n == 1 else "s")


def times(n):
    return "once" if n == 1 else "twice" if n == 2 else f"{n} times"


def piece_words(brief, words=None):
    if words:
        return int(words)
    m = re.search(r"(\d{2,5}(?:[.,]\d{3})?)\s*(?:-|to|tot)?\s*(?:\d{2,5}\s*)?(?:words|woorden)\b", brief or "", re.I)
    return int(re.sub(r"[.,]", "", m.group(1))) if m else None


def allowance(fl, words):
    return max(1, round(fl["rate"]["max_per_1k"] * words / 1000))


def kit_lines(fl, words=None, mode="keep"):
    """The kit's section on the language flavour (Markdown lines)."""
    if not fl or not fl.get("markers"):
        return []
    r = fl["rate"]
    origins = ", ".join(lang_name(o) for o in fl["origins"]) or "unknown"
    if mode == "off":
        L = ["", f"## Language flavour: off",
             f"The writer's {lang_name(fl['lang'])} carries traces of another language ({origins}). This piece is asked for "
             "without them: write standard language and avoid these:"]
        L += [f"- {m['name']}: {m['how']}" for m in fl["markers"]]
        return L
    L = ["", f"## Language flavour: {fl['strength']} ({origins})",
         f"The writer's {lang_name(fl['lang'])} carries traces of another language: {r['per_1k']:g} per 1,000 words over "
         f"{r['of']} texts ({describe_rate(r['per_1k'])}), in {r['texts']} of them, never more than "
         f"{r['max_per_1k']:g} per 1,000 words in one text. Use them at that rate, never more: spread out, "
         "each where it reads naturally, never as spelling mistakes, and never several in one paragraph."]
    if words:
        exp = r["per_1k"] * words / 1000
        n = int(exp + 0.5)
        most = allowance(fl, words)
        if n == 0:
            L.append(f"For this piece of about {words} words: none, or at most one (the rate gives {exp:.1f}).")
        else:
            L.append(f"For this piece of about {words} words: about {n} (at most {most}).")
    else:
        L.append(f"Per 1,000 words: about {max(0, int(r['per_1k'] + 0.5))}; the check allows at most "
                 f"{r['max_per_1k']:g} per 1,000 words, and at least one.")
    for m in fl["markers"]:
        c = m["count"]
        ex = f" For example: \"{m['examples'][0]}\"" if m.get("examples") else ""
        L.append(f"- {m['name']} ({m['origin']}; {c['per_1k']:g} per 1,000 words, in {n_of(c['texts'], 'text')}): {m['how']}{ex}")
    return L


def check_text(fl, text, mode="keep"):
    """(report part, flagged lines) for a draft (spec §34.9)."""
    words = count_words(text)
    counted = []
    total = 0
    lines = []
    for m in fl.get("markers", []):
        if not m.get("pattern"):
            continue
        rx = compile_pattern(m["pattern"])
        n = hits(rx, text)
        counted.append({"id": m["id"], "name": m["name"], "count": n})
        total += n
        if n:
            for i, line in enumerate(text.splitlines(), 1):
                if rx.search(prep(line)):
                    lines.append({"line": i, "text": line.strip()[:200], "lesson": m["id"],
                                  "reason": f"language flavour: {m['name']}"})
    allowed = 0 if mode == "off" else allowance(fl, words)
    part = {"mode": mode, "hits": total, "allowed": allowed,
            "expected": round(0 if mode == "off" else fl["rate"]["per_1k"] * words / 1000, 2), "markers": counted}
    return part, (lines if total > allowed else [])


def detect_text(lang, text):
    """Every pack detector over one text: what it finds, for a writer or editor to look at."""
    out = []
    for d in detectors(lang):
        rx = compile_pattern(d["pattern"])
        found = [m.group(0) for m in finditer(rx, prep(text))]
        if found:
            out.append({"detector": d["id"], "name": d["name"], "origins": d["origins"], "count": len(found),
                        "found": found[:5]})
    return {"lang": lang, "words": count_words(text), "detectors": len(detectors(lang)), "found": out}


def readable(fl):
    if not fl:
        return "No language flavour recorded."
    L = [f"{fl['profile']} / {fl['lang']}: {fl['strength']} flavour ({', '.join(fl['origins']) or 'none'}), "
         f"{fl['rate']['per_1k']:g} per 1,000 words, in {fl['rate']['texts']} of {fl['rate']['of']} texts, "
         f"at most {fl['rate']['max_per_1k']:g} in one text."]
    for m in fl["markers"]:
        c = m["count"]
        L.append(f"- [{m['id']}] {m['name']} ({m['origin']}): {c['per_1k']:g} per 1,000 words, {times(c['hits'])} in "
                 f"{n_of(c['texts'], 'text')}, counted by {c['measured']}. {m['how']}")
        L += [f"    e.g. \"{e}\"" for e in m.get("examples", [])]
    for r in fl.get("rejected", []):
        L.append(f"- rejected {r['id']}: {r['name']}")
    return "\n".join(L)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--store")
    ap.add_argument("action", choices=["detect", "show"])
    ap.add_argument("--profile")
    ap.add_argument("--lang", default="en")
    ap.add_argument("--file")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    try:
        if a.action == "detect":
            if not a.file:
                raise StoreError("detect needs --file")
            out = detect_text(a.lang, pathlib.Path(a.file).read_text(encoding="utf-8"))
            print(json.dumps(out, indent=1, ensure_ascii=False))
            return 0
        from store import Store
        if not a.store:
            raise StoreError("show needs --store")
        store = Store(a.store)
        fl = read(store, a.profile or store.config["default_profile"], a.lang)
        print(json.dumps(fl, indent=1, ensure_ascii=False) if a.json else readable(fl))
        return 0
    except StoreError as e:
        print(json.dumps({"status": "error", "message": str(e)}))
        return 2


if __name__ == "__main__":
    sys.exit(main())
