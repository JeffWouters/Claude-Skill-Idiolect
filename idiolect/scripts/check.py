"""check: compare a text with the writer's fingerprint (spec §17). Read-only; takes no lock.

    python3 check.py --store S --file DRAFT [--profile P] [--lang L] [--type T] [--facet k=v] [--json]

Flags overshoot and shortfall per metric (the caricature guard: too much of a habit is flagged too),
fails the draft when the fail count is reached, and lists lines that use a never-list phrase. Prints
the check report (check-report.schema.json) with --json, otherwise a readable summary.
"""
import argparse
import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import detect  # noqa: E402
import measure  # noqa: E402
import resolve  # noqa: E402
from common import StoreError, check_schema, count_words, read_store_file  # noqa: E402
from kit import DESCRIBE  # noqa: E402
from store import Store  # noqa: E402

MIN_WORDS = 150


def flag_metric(name, draft, writer, fp_metric):
    g = measure.METRICS[name]
    if writer < g["floor"]:
        return ("overshoot" if draft - writer > 2 * g["floor"] else "ok"), None
    ratio = draft / writer
    sparse = g.get("sparse", g["shortfall"] <= 0.05)
    if ratio > fp_metric["overshoot"]:
        return "overshoot", ratio
    if not sparse and ratio < fp_metric["shortfall"]:
        return "shortfall", ratio
    return "ok", ratio


def check(store, text, profile=None, facets=None):
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
    vals = measure.metrics(text, lang)
    rows, flagged = [], 0
    for m, v in fp["metrics"].items():
        if m not in vals:
            continue
        flag, ratio = flag_metric(m, vals[m], v["value"], v)
        flagged += flag != "ok"
        rows.append({"name": m, "draft": round(vals[m], 4), "writer": round(v["value"], 4),
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
    conf = fp["confidence"]["level"]
    if flagged >= threshold and n >= MIN_WORDS:
        status = "fail"
    else:
        status = "low_confidence" if conf == "low" else "pass"
    report.update({"status": status, "profile": prof, "slot": slot, "confidence": conf, "flagged": flagged,
                   "fail_threshold": threshold, "metrics": rows})
    if lines:
        report["flagged_lines"] = lines
    notes = []
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
    for x in r.get("flagged_lines", []):
        L.append(f"- line {x['line']}: {x['reason']}")
    if r.get("message"):
        L.append(f"Note: {r['message']}")
    return "\n".join(L)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--store")
    ap.add_argument("--file", required=True)
    ap.add_argument("--profile")
    ap.add_argument("--lang")
    ap.add_argument("--type")
    ap.add_argument("--facet", action="append", default=[])
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
        r = check(store, pathlib.Path(a.file).read_text(encoding="utf-8"), a.profile, facets)
    except StoreError as e:
        r = {"schema_version": 1, "status": "no_store" if ("idiolect.yaml" in str(e) or "no store" in str(e)) else "error",
             "message": str(e)}
    print(json.dumps(r, indent=2, ensure_ascii=False) if a.json else readable(r))
    return 0 if r["status"] in ("pass", "low_confidence") else 1


if __name__ == "__main__":
    sys.exit(main())
