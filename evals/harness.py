#!/usr/bin/env python3
"""Evaluation harness (evals/eval-protocol.md). Scripts prepare, shuffle and score; agents write briefs,
drafts, judgments and recognition answers into the run folder.

    python3 evals/harness.py new                       create evals/runs/<run-id>/ with passages
    python3 evals/harness.py overlap  --run R          check briefs against passages (4-word runs)
    python3 evals/harness.py prepare  --run R --scratch DIR
                                                       few-shot packets and an isolated store + skill copy
    python3 evals/harness.py collect  --run R --scratch DIR   drafts back into the run, real ids
    python3 evals/harness.py lengths  --run R          draft lengths against targets
    python3 evals/harness.py shuffle  --run R          judge packets and key.json
    python3 evals/harness.py export-judge --run R --scratch DIR   packets and passages, anonymous ids
    python3 evals/harness.py import-judge --run R --scratch DIR   verdicts and recognition back, real ids
    python3 evals/harness.py score    --run R          results.md and results.json
    python3 evals/harness.py pool     --runs R1,R2     the pooled binomial check over runs
    python3 evals/harness.py spotcheck --run R         a seeded 10% of judgments for a person to mark

Run layout: passages/<id>.md, briefs/<id>.md, drafts/{plain,fewshot,idiolect}/<id>.md,
judge/<id>.md (packet) and judge/<id>.json (verdict), recognition/<id>.json, key.json, results.md.
"""
import argparse
import collections
import datetime as dt
import json
import math
import pathlib
import random
import re
import shutil
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "idiolect" / "scripts"))

import check as checkmod  # noqa: E402
import kit as kitmod  # noqa: E402
import pages  # noqa: E402
from adapters import extract  # noqa: E402
from common import count_words, words  # noqa: E402
from stage import stopwords  # noqa: E402
from store import Store  # noqa: E402

FIX = ROOT / "evals" / "fixtures"
STORE = ROOT / "evals" / "store"
RUNS = ROOT / "evals" / "runs"
SEED = 20261004
PER_AUTHOR = 10
LO, HI = 300, 500
KINDS = ("plain", "fewshot", "idiolect")


def run_dir(run):
    d = RUNS / run
    if not d.exists():
        sys.exit(f"no run {run}")
    return d


# ---------- passages ----------

def cut(blocks, rng):
    """300-500-word passages cut at paragraph boundaries, starting at a random paragraph."""
    out, i = [], 0
    paras = [b for b in blocks if count_words(b) > 0]
    i = 0
    while i < len(paras):
        cur, n = [], 0
        while i < len(paras) and n < LO:
            cur.append(paras[i])
            n += count_words(paras[i])
            i += 1
        if LO <= n <= HI:
            out.append("\n\n".join(cur))
        elif n > HI and len(cur) > 1 and n - count_words(cur[-1]) >= LO:
            out.append("\n\n".join(cur[:-1]))
    return out


def new_run(seed=SEED, run_id=None):
    run_id = run_id or dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    d = RUNS / run_id
    (d / "passages").mkdir(parents=True)
    for sub in ("briefs", "judge", "recognition") + tuple(f"drafts/{k}" for k in KINDS):
        (d / sub).mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)
    hold = json.loads((ROOT / "evals" / "holdouts.json").read_text())["authors"]
    meta = {"run": run_id, "seed": seed, "passages": []}
    for author, files in sorted(hold.items()):
        pool = []
        for f in files:
            ex = extract(FIX / author / f)
            pool += [(f, p) for p in cut(ex.blocks, rng)]
        rng.shuffle(pool)
        # spread over essays: round-robin by essay
        by = collections.defaultdict(list)
        for f, p in pool:
            by[f].append(p)
        chosen = []
        while len(chosen) < PER_AUTHOR and any(by.values()):
            for f in sorted(by):
                if by[f] and len(chosen) < PER_AUTHOR:
                    chosen.append((f, by[f].pop()))
        for n, (f, p) in enumerate(chosen, 1):
            pid = f"{author}-{n:02d}"
            (d / "passages" / f"{pid}.md").write_text(p + "\n", encoding="utf-8")
            meta["passages"].append({"id": pid, "author": author, "essay": f, "words": count_words(p),
                                     "group": "synthetic" if author.startswith("synthetic") else "real"})
    (d / "run.json").write_text(json.dumps(meta, indent=1) + "\n")
    counts = collections.Counter(p["author"] for p in meta["passages"])
    print(json.dumps({"run": run_id, "passages": dict(counts)}, indent=1))
    return run_id


def meta(d):
    return json.loads((d / "run.json").read_text())


# ---------- brief overlap ----------

def runs4(text):
    sw = stopwords("en")
    ws = [w.lower() for w in words(text) if w.lower() not in sw]
    return {" ".join(ws[i:i + 4]) for i in range(len(ws) - 3)}


def overlap(run):
    d = run_dir(run)
    bad, missing = {}, []
    for p in meta(d)["passages"]:
        b = d / "briefs" / f"{p['id']}.md"
        if not b.exists():
            missing.append(p["id"])
            continue
        brief = b.read_text(encoding="utf-8")
        shared = runs4(brief) & runs4((d / "passages" / f"{p['id']}.md").read_text(encoding="utf-8"))
        n = count_words(brief)
        if shared or n > 60:
            bad[p["id"]] = {"shared": sorted(shared), "words": n}
    print(json.dumps({"rewrite": bad, "missing": missing}, indent=1))
    return bad, missing


# ---------- prepare: few-shot packets and the isolated copy ----------

def prepare(run, scratch):
    """Isolated, anonymised material for the generators: author names never reach them (a model may
    know a real author's style by name). Authors become w1..w6 (seeded), brief ids <alias>-NN."""
    d = run_dir(run)
    scratch = pathlib.Path(scratch)
    if scratch.exists():
        sys.exit(f"{scratch} exists; use a new scratch folder")
    m = meta(d)
    authors = sorted({p["author"] for p in m["passages"]})
    rng = random.Random(m["seed"] + 2)
    order = authors[:]
    rng.shuffle(order)
    alias = {a: f"w{i + 1}" for i, a in enumerate(order)}
    # store copy: idiolect.yaml and profiles only, with every author slug replaced by its alias
    (scratch / "store" / "profiles").mkdir(parents=True)
    (scratch / "no-sources").mkdir()
    cfg = (STORE / "idiolect.yaml").read_text().replace("sources_root: ../fixtures", "sources_root: ../no-sources")
    for a, w in alias.items():
        cfg = cfg.replace(a, w)
    (scratch / "store" / "idiolect.yaml").write_text(cfg)
    for a, w in alias.items():
        src, dst = STORE / "profiles" / a, scratch / "store" / "profiles" / w
        for f in src.rglob("*"):
            if f.is_dir() or "snapshots" in f.parts or f.name == "changelog.md":
                continue
            out = dst / f.relative_to(src)
            out.parent.mkdir(parents=True, exist_ok=True)
            t = f.read_text(encoding="utf-8")
            for a2, w2 in alias.items():
                t = t.replace(a2, w2)
            out.write_text(t, encoding="utf-8")
    shutil.copytree(ROOT / "idiolect", scratch / "idiolect", ignore=shutil.ignore_patterns("__pycache__"))
    (scratch / "briefs").mkdir()
    (scratch / "fewshot").mkdir()
    for k in KINDS:
        (scratch / "out" / k).mkdir(parents=True)
        for w in alias.values():
            (scratch / "work" / f"{k}-{w}").mkdir(parents=True)     # each generator's own folder
    anon = {}
    for p in m["passages"]:
        aid = f"{alias[p['author']]}-{p['id'].rsplit('-', 1)[1]}"
        anon[aid] = p["id"]
        brief = (d / "briefs" / f"{p['id']}.md").read_text(encoding="utf-8")
        (scratch / "briefs" / f"{aid}.md").write_text(brief, encoding="utf-8")
        exf = STORE / "profiles" / p["author"] / "en.essay.examples.md"
        exs = kitmod.pick_examples(pages.parse_examples(exf.read_text(encoding="utf-8"))[1], brief, "en", 3)
        body = "\n\n---\n\n".join(e["text"] for e in exs)
        (scratch / "fewshot" / f"{aid}.md").write_text(body + "\n", encoding="utf-8")
        (d / "drafts" / "fewshot" / f"{p['id']}.examples.txt").write_text(body + "\n", encoding="utf-8")
    (d / "anon.json").write_text(json.dumps({"alias": alias, "briefs": anon}, indent=1) + "\n")
    print(json.dumps({"scratch": str(scratch), "aliases": sorted(alias.values())}, indent=1))


def collect(run, scratch):
    """Copy the generators' drafts (anonymous ids) back into the run under the real ids."""
    d = run_dir(run)
    anon = json.loads((d / "anon.json").read_text())["briefs"]
    scratch = pathlib.Path(scratch)
    n = collections.Counter()
    for k in KINDS:
        for aid, pid in anon.items():
            f = scratch / "out" / k / f"{aid}.md"
            if f.exists():
                shutil.copy(f, draft_path(d, k, pid))
                n[k] += 1
        for log in (scratch / "out" / k).glob("_log*"):
            shutil.copy(log, d / "drafts" / k / log.name)
    print(json.dumps(dict(n)))


# ---------- lengths ----------

def draft_path(d, kind, pid):
    return d / "drafts" / kind / f"{pid}.md"


def lengths(run):
    d = run_dir(run)
    out = {}
    for p in meta(d)["passages"]:
        target = p["words"]
        for k in KINDS:
            f = draft_path(d, k, p["id"])
            if not f.exists():
                out.setdefault(p["id"], {})[k] = "missing"
                continue
            n = count_words(f.read_text(encoding="utf-8"))
            if not 0.85 * target <= n <= 1.15 * target:
                out.setdefault(p["id"], {})[k] = f"{n} words (target {target})"
    print(json.dumps(out, indent=1))
    return out


# ---------- shuffle ----------

def shuffle(run):
    d = run_dir(run)
    rng = random.Random(meta(d)["seed"] + 1)
    key = {}
    for p in meta(d)["passages"]:
        labels = ["A", "B", "C"]
        kinds = list(KINDS)
        rng.shuffle(kinds)
        key[p["id"]] = dict(zip(labels, kinds))
        parts = [f"# Judge packet {p['id']}", "", "## The passage (by the author)", "",
                 plain_spaces((d / "passages" / f"{p['id']}.md").read_text(encoding="utf-8").strip())]
        for lab in labels:
            txt = draft_path(d, key[p["id"]][lab], p["id"]).read_text(encoding="utf-8").strip()
            parts += ["", f"## Draft {lab}", "", plain_spaces(strip_notes(txt))]
        (d / "judge" / f"{p['id']}.md").write_text("\n".join(parts) + "\n", encoding="utf-8")
    (d / "key.json").write_text(json.dumps(key, indent=1) + "\n")
    print(f"{len(key)} packets")


def plain_spaces(text):
    """Typography is not voice: two spaces after a full stop (a habit of the source editions) would let
    a judge match drafts to the passage by spacing alone, so runs of spaces become one everywhere."""
    return re.sub(r"(?<=\S)[ \t]{2,}", " ", text)


def export_judge(run, scratch):
    """Judge packets into DIR/judge-in under anonymous ids, so a judge never sees the author's name."""
    d = run_dir(run)
    anon = json.loads((d / "anon.json").read_text())["briefs"]
    out = pathlib.Path(scratch) / "judge-in"
    out.mkdir(parents=True, exist_ok=True)
    (pathlib.Path(scratch) / "judge-out").mkdir(exist_ok=True)
    (pathlib.Path(scratch) / "recognition-out").mkdir(exist_ok=True)
    for aid, pid in anon.items():
        txt = (d / "judge" / f"{pid}.md").read_text(encoding="utf-8").replace(f"# Judge packet {pid}", f"# Judge packet {aid}")
        (out / f"{aid}.md").write_text(txt, encoding="utf-8")
        passage = plain_spaces((d / "passages" / f"{pid}.md").read_text(encoding="utf-8").strip())
        (out / f"{aid}.passage.md").write_text(passage + "\n", encoding="utf-8")
    print(f"{len(anon)} packets in {out}")


def import_judge(run, scratch):
    """Verdicts and recognition answers back into the run under the real ids."""
    d = run_dir(run)
    anon = json.loads((d / "anon.json").read_text())["briefs"]
    n = collections.Counter()
    for sub, dest in (("judge-out", "judge"), ("recognition-out", "recognition")):
        for aid, pid in anon.items():
            f = pathlib.Path(scratch) / sub / f"{aid}.json"
            if f.exists():
                v = json.loads(f.read_text())
                if dest == "judge" and sorted(v.get("ranking", [])) != ["A", "B", "C"]:
                    raise SystemExit(f"{f}: ranking must hold A, B and C once each")
                (d / dest / f"{pid}.json").write_text(json.dumps(v, indent=1, ensure_ascii=False) + "\n")
                n[dest] += 1
    print(json.dumps(dict(n)))


def spotcheck(run, share=0.10):
    """A seeded 10% of judgments (at least one per author) laid out for a person to mark agree or
    disagree (eval-protocol.md, role 6): packet, the judge's ranking and reasons, the key hidden."""
    d = run_dir(run)
    m = meta(d)
    rng = random.Random(m["seed"] + 3)
    by = collections.defaultdict(list)
    for p in m["passages"]:
        if (d / "judge" / f"{p['id']}.json").exists():
            by[p["author"]].append(p["id"])
    n = max(len(by), math.ceil(share * sum(len(v) for v in by.values())))
    pick = [rng.choice(sorted(v)) for _, v in sorted(by.items())]
    rest = sorted(i for v in by.values() for i in v if i not in pick)
    rng.shuffle(rest)
    pick += rest[: n - len(pick)]
    L = [f"# Spot-check, run {run}", "",
         f"{len(pick)} of {sum(len(v) for v in by.values())} judgments, chosen by seed, at least one per author. "
         "For each: read the passage and drafts A, B, C, then the judge's ranking. Mark **agree** if the "
         "draft ranked first is, in your view, the one that reads most like the passage's author "
         "(voice, not content), otherwise **disagree**. More than 20% disagreement invalidates the run.", ""]
    for pid in sorted(pick):
        v = json.loads((d / "judge" / f"{pid}.json").read_text())
        L += ["---", "", f"## {pid}", "", "Your mark: agree / disagree", "",
              f"**Judge's ranking:** {', '.join(v['ranking'])}", ""]
        L += [f"- {lab}: {v.get('reasons', {}).get(lab, '')}" for lab in v["ranking"]]
        L += ["", (d / "judge" / f"{pid}.md").read_text(encoding="utf-8").replace("# Judge packet", "### Packet"), ""]
    (d / "spotcheck.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"{len(pick)} judgments in {d / 'spotcheck.md'}")


def strip_notes(text):
    """Only the draft goes to the judge: drop an appended report, explain notes or a title line."""
    text = re.split(r"\n(?:---\n|#+ (?:Check|Report|Notes|Explain)|\{\n)", text)[0]
    return text.strip()


# ---------- scoring ----------

def binom_p(k, n):
    """One-sided exact binomial P(X >= k) for p = 0.5."""
    return sum(math.comb(n, i) for i in range(k, n + 1)) / 2 ** n


def score(run):
    d = run_dir(run)
    key = json.loads((d / "key.json").read_text())
    s = Store(STORE)
    rows = []
    for p in meta(d)["passages"]:
        v = json.loads((d / "judge" / f"{p['id']}.json").read_text())
        rank = [key[p["id"]][lab] for lab in v["ranking"]]
        rec_f = d / "recognition" / f"{p['id']}.json"
        rec = json.loads(rec_f.read_text()) if rec_f.exists() else {"confidence": "none"}
        flags = {}
        for k in KINDS:
            r = checkmod.check(s, strip_notes(draft_path(d, k, p["id"]).read_text(encoding="utf-8")), p["author"],
                               {"type": "essay"})
            flags[k] = r.get("flagged")
        rows.append({**p, "rank": rank, "win_plain": rank.index("idiolect") < rank.index("plain"),
                     "win_fewshot": rank.index("idiolect") < rank.index("fewshot"),
                     "recognised": rec.get("confidence") in ("medium", "high"),
                     "recognition": rec, "flags": flags})
    res = {"run": run, "authors": {}, "groups": {}}
    for level, keyf in (("authors", "author"), ("groups", "group")):
        for name in sorted({r[keyf] for r in rows}):
            rs = [r for r in rows if r[keyf] == name and not r["recognised"]]
            n = len(rs)
            wp = sum(r["win_plain"] for r in rs)
            wf = sum(r["win_fewshot"] for r in rs)
            mean = {k: round(sum(r["flags"][k] or 0 for r in rs) / max(1, n), 2) for k in KINDS}
            res[level][name] = {"briefs": sum(1 for r in rows if r[keyf] == name), "counted": n,
                                "excluded_recognised": sum(1 for r in rows if r[keyf] == name and r["recognised"]),
                                "wins_vs_plain": wp, "wins_vs_fewshot": wf,
                                "rate_vs_plain": round(wp / n, 3) if n else None,
                                "rate_vs_fewshot": round(wf / n, 3) if n else None, "mean_flags": mean}
    for g, v in res["groups"].items():
        authors = [a for a, x in res["authors"].items() if (a.startswith("synthetic") == (g == "synthetic"))]
        v["pass"] = bool(v["counted"]) and v["rate_vs_plain"] >= 0.70 and v["rate_vs_fewshot"] >= 0.60 and all(
            (res["authors"][a]["rate_vs_fewshot"] or 0) >= 0.5 for a in authors)
    for level, keyf in (("authors", "author"), ("groups", "group")):
        for name, v in res[level].items():
            rs = [r for r in rows if r[keyf] == name]
            v["all_briefs"] = {"vs_plain": sum(r["win_plain"] for r in rs), "vs_fewshot": sum(r["win_fewshot"] for r in rs)}
    (d / "results.json").write_text(json.dumps({"summary": res, "rows": rows}, indent=1) + "\n")
    pct = lambda x: "n/a" if x is None else f"{x:.0%}"  # noqa: E731
    L = [f"# Results, run {run}", "",
         "Counted briefs exclude those whose passage a separate agent recognised with medium or high confidence.",
         "The last column (all briefs, recognised included) is reported for information and decides nothing.", "",
         "| Author | Briefs | Excluded (recognised) | vs plain | vs few-shot | Mean flags: plain / few-shot / Idiolect | All briefs: vs plain, vs few-shot |",
         "| --- | --- | --- | --- | --- | --- | --- |"]
    for a, v in res["authors"].items():
        L.append(f"| {a} | {v['briefs']} | {v['excluded_recognised']} | {v['wins_vs_plain']}/{v['counted']} "
                 f"({pct(v['rate_vs_plain'])}) | {v['wins_vs_fewshot']}/{v['counted']} ({pct(v['rate_vs_fewshot'])}) | "
                 f"{v['mean_flags']['plain']} / {v['mean_flags']['fewshot']} / {v['mean_flags']['idiolect']} | "
                 f"{v['all_briefs']['vs_plain']}/{v['briefs']}, {v['all_briefs']['vs_fewshot']}/{v['briefs']} |")
    L += ["", "| Group | Counted | vs plain (bar 70%) | vs few-shot (bar 60%) | Pass this run |", "| --- | --- | --- | --- | --- |"]
    for g, v in res["groups"].items():
        L.append(f"| {g} | {v['counted']} | {pct(v['rate_vs_plain'])} | {pct(v['rate_vs_fewshot'])} | {'yes' if v['pass'] else 'no'} |")
    (d / "results.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))
    return res


def pool(runs):
    tot = collections.defaultdict(lambda: [0, 0, 0])
    per_run = {}
    for r in runs:
        res = json.loads((run_dir(r) / "results.json").read_text())["summary"]
        per_run[r] = {g: v["pass"] for g, v in res["groups"].items()}
        for g, v in res["groups"].items():
            tot[g][0] += v["counted"]
            tot[g][1] += v["wins_vs_plain"]
            tot[g][2] += v["wins_vs_fewshot"]
    out = {}
    for g, (n, wp, wf) in tot.items():
        out[g] = {"briefs": n, "p_vs_plain": round(binom_p(wp, n), 5), "p_vs_fewshot": round(binom_p(wf, n), 5),
                  "each_run_passed": all(per_run[r].get(g) for r in runs)}
        out[g]["pass"] = out[g]["each_run_passed"] and out[g]["p_vs_plain"] < 0.05 and out[g]["p_vs_fewshot"] < 0.05
    print(json.dumps(out, indent=1))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("action", choices=["new", "overlap", "prepare", "collect", "lengths", "shuffle",
                                       "export-judge", "import-judge", "score", "pool", "spotcheck"])
    ap.add_argument("--run")
    ap.add_argument("--runs")
    ap.add_argument("--scratch")
    ap.add_argument("--seed", type=int, default=SEED)
    a = ap.parse_args()
    if a.action == "new":
        new_run(a.seed)
    elif a.action == "overlap":
        overlap(a.run)
    elif a.action == "prepare":
        prepare(a.run, a.scratch)
    elif a.action == "collect":
        collect(a.run, a.scratch)
    elif a.action == "lengths":
        lengths(a.run)
    elif a.action == "shuffle":
        shuffle(a.run)
    elif a.action == "export-judge":
        export_judge(a.run, a.scratch)
    elif a.action == "import-judge":
        import_judge(a.run, a.scratch)
    elif a.action == "spotcheck":
        spotcheck(a.run)
    elif a.action == "score":
        score(a.run)
    else:
        pool(a.runs.split(","))


if __name__ == "__main__":
    main()
