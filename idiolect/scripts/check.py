"""check: compare a text with the writer's fingerprint (spec §17). Read-only; takes no lock.

    python3 check.py --store S --file DRAFT [--brief FILE] [--tone T] [--profile P] [--lang L] [--type T] [--facet k=v] [--json]

Measures against the targets for this piece: the slot's fingerprint blended with the example passages
the brief selects, exactly as kit.py does with the same brief (without --brief, the text itself picks
them). Flags overshoot and shortfall per metric only when the text is outside the band around both the
target and the slot's value (the caricature guard: too much of a habit is flagged too),
fails the draft when the fail count is reached or a ruling's test is broken (spec §27), lists lines
that use a never-list phrase or break a ruling, and names
bunched habits: a paragraph using a countable habit far above the writer's rate. Prints
the check report (check-report.schema.json) with --json, otherwise a readable summary.
"""
import argparse
import json
import math
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import detect  # noqa: E402
import kit as kitmod  # noqa: E402
import measure  # noqa: E402
import resolve  # noqa: E402
import rules  # noqa: E402
from common import StoreError, check_schema, count_words, read_store_file, words  # noqa: E402
from kit import DESCRIBE  # noqa: E402

# write.md's placeholders ([example needed: ...], [number needed: ...]) are not the writer's prose
PLACEHOLDER = re.compile(r"\[[^\[\]\n]{0,120}?\bneeded\b[^\[\]\n]{0,120}?\]", re.I)


def strip_placeholders(text):
    """The text without placeholders. A paragraph that was only a placeholder keeps its place as a
    one-word line, which measurement skips like a heading, so bunched paragraphs keep their numbers."""
    parts = re.split(r"(\n\s*\n)", text)
    out = []
    for part in parts:
        if not part.strip() or not PLACEHOLDER.search(part):
            out.append(part)
            continue
        left = re.sub(r"[ \t]{2,}", " ", PLACEHOLDER.sub("", part))
        out.append(left if left.strip(" \t\n.,;:") else "placeholder")
    return "".join(out)
from store import Store  # noqa: E402

MIN_WORDS = 150
# Bunched habits (design: Guardrails, No caricature): countable habits checked per paragraph.
BUNCH_METRICS = ("hedges_per_1k", "semicolons_per_1k", "dashes_per_1k", "colons_per_1k", "contractions_per_1k")
BUNCH_MIN_WORDS = 40
BUNCH_MIN_COUNT = 3
BUNCH_P = 0.01
PHRASES_MIN_COUNT = 2      # whole text; calibrated on run 1 (design: decision log)


def poisson_tail(k, lam):
    """P(X >= k) for X ~ Poisson(lam). Terms are summed in log space, so a large lam cannot underflow
    to a tail of 1 (review L4)."""
    if k <= 0:
        return 1.0
    if lam <= 0:
        return 0.0
    below = sum(math.exp(-lam + i * math.log(lam) - math.lgamma(i + 1)) for i in range(k))
    return min(1.0, max(0.0, 1.0 - below))


def is_bunch(count, lam):
    return count >= BUNCH_MIN_COUNT and poisson_tail(count, lam) < BUNCH_P


def bunched(text, lang, fp_metrics, phrases=(), targets=None):
    """Blocks (numbered from 1 as they appear, headings included) that use a countable habit far above the writer's rate, and the favoured
    phrases together overused in the whole text (paragraph 0). phrases: vocabulary entries of kind
    phrase; those without a measured rate are skipped."""
    out = []
    rated = [v for v in phrases if v.get("rate") and v["rate"].get("of")]
    pat = measure.phrases_pattern([v["text"] for v in rated])
    numbered = [(i, b) for i, b, heading in measure.blocks(text) if not heading]
    paras = [b for _, b in numbered]
    for i, para in numbered:            # numbered as the reader sees them, headings counted (review L3)
        nw = len(words(para))
        if nw < BUNCH_MIN_WORDS:
            continue
        vals = measure.metrics(para, lang)
        for m in BUNCH_METRICS:
            if m not in vals or m not in fp_metrics:
                continue
            count = round(vals[m] * nw / 1000)
            lam = (targets or {}).get(m, fp_metrics[m]["value"]) * nw / 1000
            if is_bunch(count, lam):
                out.append({"paragraph": i, "habit": m, "count": count, "expected": round(lam, 2)})
        if rated:
            count = len(pat.findall(measure.normalise_quotes(para)))
            lam = sum(v["rate"]["per_1k"] for v in rated) * nw / 1000
            if is_bunch(count, lam):
                out.append({"paragraph": i, "habit": "favoured phrases", "count": count, "expected": round(lam, 2)})
    body = "\n\n".join(paras)
    if rated:
        # the favoured phrases together over the whole text: 2 uses can already be far too many
        count = len(pat.findall(measure.normalise_quotes(body)))
        lam = sum(v["rate"]["per_1k"] for v in rated) * len(words(body)) / 1000
        if count >= PHRASES_MIN_COUNT and poisson_tail(count, lam) < BUNCH_P:
            out.append({"paragraph": 0, "habit": "favoured phrases", "count": count, "expected": round(lam, 2)})
    return out



def flag_metric(name, draft, writer, fp_metric):
    g = measure.METRICS[name]
    if writer < g["floor"]:
        return ("overshoot" if draft - writer > 2 * g["floor"] else "ok"), None
    ratio = draft / writer
    # sparse globally, or the writer's own passages often lack the device (writer band, measure.py)
    sparse = g.get("sparse", g["shortfall"] <= 0.05) or fp_metric["shortfall"] <= measure.NO_SHORTFALL
    if ratio > fp_metric["overshoot"]:
        return "overshoot", ratio
    if not sparse and ratio < fp_metric["shortfall"]:
        return "shortfall", ratio
    return "ok", ratio


def check(store, text, profile=None, facets=None, brief=None, tone=None):
    report = {"schema_version": 1}
    try:
        prof, slot, _ = resolve.resolve(store, profile, facets)
    except resolve.NoSlot as e:
        return check_schema("check-report", {**report, "status": "no_slot", "message": str(e)})
    fp = read_store_file(store.root / "profiles" / prof / f"{slot}.json", "fingerprint")
    lang = slot.split(".")[0]
    n = count_words(text)
    if n >= 20:
        found, conf = detect.identify(text)
        if found and conf >= 0.9 and found != lang and found[:2] != lang[:2]:
            return check_schema("check-report", {**report, "status": "error", "profile": prof, "slot": slot,
                                                 "message": f"the text is in '{found}', the slot is '{lang}'; "
                                                            f"a voice is never carried across languages"})
    measured = strip_placeholders(text)
    n = count_words(measured)
    picks = kitmod.pick_examples(kitmod.slot_examples(store, prof, slot), text if brief is None else brief, lang)
    targets, t_words, t_weight = kitmod.blend(fp["metrics"], [e["text"] for e in picks], lang)
    targets, _ = kitmod.apply_tone(store, prof, slot, targets, tone)     # the same targets as the kit
    vals = measure.metrics(measured, lang)
    rows, flagged = [], 0
    for m, v in fp["metrics"].items():
        if m not in vals:
            continue
        flag, ratio = flag_metric(m, vals[m], targets[m], v)
        if flag != "ok" and flag_metric(m, vals[m], v["value"], v)[0] == "ok":
            flag = "ok"             # inside the slot's own band: the writer's texts vary this much
        flagged += flag != "ok"
        rows.append({"name": m, "draft": round(vals[m], 4), "writer": round(targets[m], 4),
                     "slot": round(v["value"], 4),
                     "ratio": round(ratio, 3) if ratio is not None else None, "flag": flag, "primary": v["primary"]})
    threshold = measure.fail_count(len(rows))
    never_f = store.root / "profiles" / prof / f"{slot}.never.md"
    lines = []
    if never_f.exists():
        import pages
        markers = [m["marker"] for m in pages.parse_never(never_f.read_text(encoding="utf-8"))[1]]
        for i, line in enumerate(text.splitlines(), 1):
            for mk in markers:
                if re.search(r"(?<!\w)" + re.escape(mk) + r"(?!\w)", line, re.I):
                    lines.append({"line": i, "text": line.strip()[:200], "lesson": f"never: {mk}",
                                  "reason": f"uses \"{mk}\", which this writer never does"})
    # rulings with a test (spec §27): any flagged ruling fails the draft
    applicable = rules.applicable(store, prof, slot)
    ruling_lines = rules.flag(measured, applicable, rules.writer_rates(store, prof, slot, applicable), n)
    lines += ruling_lines
    phrases = [v for v in resolve.merged(store, prof, "vocabulary") if v["kind"] == "phrase"]
    bunches = bunched(measured, lang, fp["metrics"], phrases, targets)
    conf = fp["confidence"]["level"]
    if ruling_lines or (flagged >= threshold and n >= MIN_WORDS):
        status = "fail"
    else:
        status = "low_confidence" if conf == "low" else "pass"
    broken = sorted({x["lesson"] for x in ruling_lines})
    report.update({"status": status, "profile": prof, "slot": slot, "confidence": conf, "flagged": flagged,
                   "fail_threshold": threshold, "metrics": rows,
                   "targets": {"examples": [e["id"] for e in picks], "words": t_words, "weight": t_weight,
                               **({"tone": kitmod.parse_tone(tone)} if tone else {})}})
    if lines:
        report["flagged_lines"] = lines
    if bunches:
        report["bunched"] = bunches
    notes = []
    if broken:
        notes.append(f"breaks {len(broken)} ruling{'s' if len(broken) > 1 else ''} ({', '.join(broken)}): "
                     f"a ruling fails the draft whatever the metrics say")
    if n < MIN_WORDS:
        notes.append(f"only {n} words: metric flags are hints, never a fail, below {MIN_WORDS} words")
    if fp["pooled"]:
        notes.append(f"measured against the pooled slot {slot}")
    if notes:
        report["message"] = "; ".join(notes)
    return check_schema("check-report", report, "check report")


def readable(r):
    if r["status"] in ("no_slot", "no_store", "error", "needs_input"):
        return f"{r['status']}: {r.get('message', '')}"
    L = [f"{r['status'].upper()} against {r['profile']} / {r['slot']} (confidence {r['confidence']}): "
         f"{r['flagged']} of {len(r['metrics'])} metrics flagged; fails at {r['fail_threshold']}."]
    for m in r["metrics"]:
        if m["flag"] == "ok":
            continue
        name, fmt = DESCRIBE.get(m["name"], (m["name"], "{:.2f}"))
        L.append(f"- {m['flag']}: {name}: draft {fmt.format(m['draft'])}, writer {fmt.format(m['writer'])}"
                 + (" (primary)" if m["primary"] else ""))
    for b in r.get("bunched", []):
        name = DESCRIBE.get(b["habit"], (b["habit"], ""))[0]
        where = "the whole text" if b["paragraph"] == 0 else f"paragraph {b['paragraph']}"
        L.append(f"- bunched: {name} in {where}: {b['count']} uses where the writer's rate gives about "
                 f"{b['expected']:g} (caricature: spread them out or cut)")
    for x in r.get("flagged_lines", []):
        L.append(f"- line {x['line']}: {x['reason']}")
    if r.get("message"):
        L.append(f"Note: {r['message']}")
    return "\n".join(L)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--store")
    ap.add_argument("--file", required=True)
    ap.add_argument("--brief", help="the brief (write) or source text (rewrite) given to kit.py")
    ap.add_argument("--profile")
    ap.add_argument("--lang")
    ap.add_argument("--type")
    ap.add_argument("--facet", action="append", default=[])
    ap.add_argument("--tone", help="the same tone given to kit.py")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    facets = {"lang": a.lang, "type": a.type}
    for f in a.facet:
        k, _, v = f.partition("=")
        facets[k] = v
    try:
        if not a.store:
            raise StoreError("no store given (discover one first, see SKILL.md)")
        store = Store(a.store)
        brief = pathlib.Path(a.brief).read_text(encoding="utf-8") if a.brief else None
        r = check(store, pathlib.Path(a.file).read_text(encoding="utf-8"), a.profile, facets, brief, a.tone)
    except StoreError as e:
        r = {"schema_version": 1, "status": "no_store" if ("idiolect.yaml" in str(e) or "no store" in str(e)) else "error",
             "message": str(e)}
    print(json.dumps(r, indent=2, ensure_ascii=False) if a.json else readable(r))
    return 0 if r["status"] in ("pass", "low_confidence") else 1


if __name__ == "__main__":
    sys.exit(main())
