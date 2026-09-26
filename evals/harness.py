#!/usr/bin/env python3
"""Evaluation harness (evals/eval-protocol.md). Scripts prepare, shuffle and score; agents write briefs,
drafts, judgments and recognition answers into the run folder.

    python3 evals/harness.py new [--seed N] [--per-author 10] [--arms plain,fewshot,idiolect,lite]
                                 [--avoid R1,R2]      create evals/runs/<run-id>/ with passages
    python3 evals/harness.py overlap  --run R          check briefs against passages (4-word runs)
    python3 evals/harness.py prepare  --run R --scratch DIR [--per-agent 4]
                                                       few-shot packets, an isolated store + skill copies,
                                                       generator assignments and prompts
    python3 evals/harness.py collect  --run R --scratch DIR   drafts back into the run, real ids
    python3 evals/harness.py lengths  --run R          draft lengths against targets
    python3 evals/harness.py shuffle  --run R          judge packets and key.json (balanced labels)
    python3 evals/harness.py export-judge --run R --scratch DIR   packets and passages, anonymous ids
    python3 evals/harness.py import-judge --run R --scratch DIR   verdicts and recognition back, real ids
    python3 evals/harness.py score    --run R          results.md and results.json
    python3 evals/harness.py pool     --runs R1,R2     the pooled binomial check over runs
    python3 evals/harness.py spotcheck --run R         a seeded 10% of judgments for a person to mark

Run layout: passages/<id>.md, briefs/<id>.md, drafts/<arm>/<id>.md, judge/<id>.md (packet) and
judge/<id>.json (verdict), recognition/<id>.json, key.json, flags.json, results.md.

Arms: plain, fewshot, idiolect (the full write procedure) and, from run 4, lite (the kit without the
measurable targets and without the check-and-revise loop; evals/ablation/write-lite.md).
"""
import argparse
import collections
import datetime as dt
import hashlib
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
from common import StoreError, count_words, words  # noqa: E402
from stage import stopwords  # noqa: E402
from store import Store  # noqa: E402

FIX = ROOT / "evals" / "fixtures"
STORE = ROOT / "evals" / "store"
RUNS = ROOT / "evals" / "runs"
PROMPTS = ROOT / "evals" / "prompts"
SEED = 20261004
PER_AUTHOR = 10
LO, HI = 300, 500
KINDS = ("plain", "fewshot", "idiolect")          # runs 1 to 3
ALL_ARMS = ("plain", "fewshot", "idiolect", "lite")
LABELS = "ABCD"


def run_dir(run):
    d = RUNS / run
    if not d.exists():
        sys.exit(f"no run {run}")
    return d


def meta(d):
    return json.loads((d / "run.json").read_text())


def arms(m):
    return tuple(m.get("arms", KINDS))


def text_key(t):
    return hashlib.sha256(" ".join(t.split()).encode("utf-8")).hexdigest()[:16]


# ---------- passages ----------

def cut(blocks, rng):
    """300-500-word passages cut at paragraph boundaries. The first passage starts at a random one of
    the first few paragraphs, so different seeds give different cuts of the same essay (review: the
    seed used to be ignored). A paragraph that would push a passage past 500 words is not lost with
    the paragraphs before it: it starts the next passage."""
    out = []
    paras = [b for b in blocks if count_words(b) > 0]
    i = rng.randrange(0, min(4, len(paras))) if paras else 0
    while i < len(paras):
        cur, n = [], 0
        while i < len(paras) and n < LO:
            cur.append(paras[i])
            n += count_words(paras[i])
            i += 1
        if LO <= n <= HI:
            out.append("\n\n".join(cur))
        elif n > HI and len(cur) > 1:
            i -= 1                                  # the paragraph that overshot starts the next passage
    return out


def new_run(seed=SEED, run_id=None, per_author=PER_AUTHOR, arm_list=KINDS, avoid=()):
    """Passages for a new run. Passages already used in the runs named in `avoid` are taken last, and
    the number reused is recorded, because a run that repeats another's passages is not an independent
    sample (review: runs 2 and 3 shared 38 of 50)."""
    run_id = run_id or dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    used = set()
    for r in avoid:
        for f in (run_dir(r) / "passages").glob("*.md"):
            used.add(text_key(f.read_text(encoding="utf-8")))
    d = RUNS / run_id
    (d / "passages").mkdir(parents=True)
    for sub in ("briefs", "judge", "recognition") + tuple(f"drafts/{k}" for k in arm_list):
        (d / sub).mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)
    hold = json.loads((ROOT / "evals" / "holdouts.json").read_text())["authors"]
    m = {"run": run_id, "seed": seed, "arms": list(arm_list), "avoid": list(avoid), "passages": [], "reused": {}}
    for author, files in sorted(hold.items()):
        pool = []
        for f in files:
            ex = extract(FIX / author / f)
            pool += [(f, p) for p in cut(ex.blocks, rng)]
        rng.shuffle(pool)
        fresh = [x for x in pool if text_key(x[1]) not in used]
        old = [x for x in pool if text_key(x[1]) in used]
        chosen = []
        for part in (fresh, old):                   # fresh passages first, spread over essays
            by = collections.defaultdict(list)
            for f, p in part:
                by[f].append(p)
            while len(chosen) < per_author and any(by.values()):
                for f in sorted(by):
                    if by[f] and len(chosen) < per_author:
                        chosen.append((f, by[f].pop()))
        m["reused"][author] = sum(1 for _, p in chosen if text_key(p) in used)
        for n, (f, p) in enumerate(chosen, 1):
            pid = f"{author}-{n:02d}"
            (d / "passages" / f"{pid}.md").write_text(p + "\n", encoding="utf-8")
            m["passages"].append({"id": pid, "author": author, "essay": f, "words": count_words(p),
                                  "group": "synthetic" if author.startswith("synthetic") else "real"})
    (d / "run.json").write_text(json.dumps(m, indent=1) + "\n")
    counts = collections.Counter(p["author"] for p in m["passages"])
    print(json.dumps({"run": run_id, "passages": dict(counts), "reused_from_avoided_runs": m["reused"]}, indent=1))
    return run_id


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


# ---------- prepare: few-shot packets, the isolated copies, assignments and prompts ----------

def prepare(run, scratch, per_agent=None):
    """Isolated, anonymised material for the generators: author names never reach them (a model may
    know a real author's style by name). Authors become w1..wN (seeded), brief ids <alias>-NN. The
    store copy keeps only idiolect.yaml and profiles, without snapshots, changelogs or the consent and
    subject lines. With per_agent, each author's briefs are split between several generator agents per
    arm, so one agent's drift is not the whole author's result (review: batch effects)."""
    d = run_dir(run)
    scratch = pathlib.Path(scratch)
    if scratch.exists():
        sys.exit(f"{scratch} exists; use a new scratch folder")
    m = meta(d)
    arm_list = arms(m)
    authors = sorted({p["author"] for p in m["passages"]})
    rng = random.Random(m["seed"] + 2)
    order = authors[:]
    rng.shuffle(order)
    alias = {a: f"w{i + 1}" for i, a in enumerate(order)}
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
            if f.name == "profile.yaml":
                t = re.sub(r"(?m)^subject: .*$", f"subject: writer {w}", t)
                t = re.sub(r"(?m)^consent: .*$", "consent: evaluation only", t)
            out.write_text(t, encoding="utf-8")
    shutil.copytree(ROOT / "idiolect", scratch / "idiolect", ignore=shutil.ignore_patterns("__pycache__"))
    if "lite" in arm_list:
        shutil.copytree(ROOT / "idiolect", scratch / "idiolect-lite", ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copy(ROOT / "evals" / "ablation" / "write-lite.md",
                    scratch / "idiolect-lite" / "references" / "modes" / "write.md")
    (scratch / "briefs").mkdir()
    (scratch / "fewshot").mkdir()
    (scratch / "prompts").mkdir()
    anon, agents = {}, {}
    for p in m["passages"]:
        aid = f"{alias[p['author']]}-{p['id'].rsplit('-', 1)[1]}"
        anon[aid] = p["id"]
        brief = (d / "briefs" / f"{p['id']}.md").read_text(encoding="utf-8")
        (scratch / "briefs" / f"{aid}.md").write_text(brief, encoding="utf-8")
        exf = STORE / "profiles" / p["author"] / "en.essay.examples.md"
        exs = kitmod.pick_examples(pages.parse_examples(exf.read_text(encoding="utf-8"))[1], brief, "en", 3)
        body = "\n\n---\n\n".join(e["text"] for e in exs)
        (scratch / "fewshot" / f"{aid}.md").write_text(body + "\n", encoding="utf-8")
        if "fewshot" in arm_list:
            (d / "drafts" / "fewshot" / f"{p['id']}.examples.txt").write_text(body + "\n", encoding="utf-8")
    # generator agents: per author, consecutive blocks of per_agent briefs (one block = one agent per arm)
    for w in sorted(alias.values()):
        ids = sorted(a for a in anon if a.startswith(w + "-"))
        size = per_agent or len(ids)
        for b in range(0, len(ids), size):
            for aid in ids[b:b + size]:
                agents[aid] = f"{w}{'abcdefghij'[b // size]}"
    for k in arm_list:
        (scratch / "out" / k).mkdir(parents=True)
        for g in sorted(set(agents.values())):
            (scratch / "work" / f"{k}-{g}").mkdir(parents=True)
            files = " ".join(f"{a}.md" for a in sorted(agents) if agents[a] == g)
            tmpl = (PROMPTS / f"gen-{k}.txt").read_text(encoding="utf-8")
            w = re.match(r"w\d+", g).group(0)
            (scratch / "prompts" / f"gen-{k}-{g}.txt").write_text(
                tmpl.format(SC=str(scratch), W=w, G=g, FILES=files, ARM=k), encoding="utf-8")
    (d / "anon.json").write_text(json.dumps({"alias": alias, "briefs": anon, "agents": agents}, indent=1) + "\n")
    print(json.dumps({"scratch": str(scratch), "aliases": sorted(alias.values()),
                      "agents_per_arm": len(set(agents.values()))}, indent=1))


def collect(run, scratch):
    """Copy the generators' drafts (anonymous ids) back into the run under the real ids."""
    d = run_dir(run)
    anon = json.loads((d / "anon.json").read_text())["briefs"]
    scratch = pathlib.Path(scratch)
    n = collections.Counter()
    for k in arms(meta(d)):
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
        for k in arms(meta(d)):
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
    """Judge packets. With the run's arms given explicitly (run 4 on), labels are balanced: briefs are
    taken in a seeded order and each gets the next rotation of one seeded order of the arms, so every
    arm sits at every label equally often (review: position bias in run 2). Runs 1 to 3 keep their
    original independent shuffles."""
    d = run_dir(run)
    m = meta(d)
    arm_list = list(arms(m))
    rng = random.Random(m["seed"] + 1)
    labels = list(LABELS[:len(arm_list)])
    key = {}
    balanced = "arms" in m
    base = arm_list[:]
    order = [p["id"] for p in m["passages"]]
    if balanced:                # runs 1-3 drew one shuffle per passage from this rng; keep that intact
        rng.shuffle(base)
        rng.shuffle(order)
    rot = {pid: j for j, pid in enumerate(order)}
    typo = balanced            # runs 1-3 were judged with spacing normalised only
    for p in m["passages"]:
        if balanced:
            j = rot[p["id"]] % len(base)
            kinds = base[j:] + base[:j]
        else:
            kinds = list(KINDS)
            rng.shuffle(kinds)
        key[p["id"]] = dict(zip(labels, kinds))
        norm = normalise_typography if typo else plain_spaces
        parts = [f"# Judge packet {p['id']}", "", "## The passage (by the author)", "",
                 norm((d / "passages" / f"{p['id']}.md").read_text(encoding="utf-8").strip())]
        for lab in labels:
            txt = draft_path(d, key[p["id"]][lab], p["id"]).read_text(encoding="utf-8").strip()
            parts += ["", f"## Draft {lab}", "", norm(strip_notes(txt))]
        (d / "judge" / f"{p['id']}.md").write_text("\n".join(parts) + "\n", encoding="utf-8")
    (d / "key.json").write_text(json.dumps(key, indent=1) + "\n")
    print(f"{len(key)} packets")


def plain_spaces(text):
    """Typography is not voice: two spaces after a full stop (a habit of the source editions) would let
    a judge match drafts to the passage by spacing alone, so runs of spaces become one everywhere."""
    return re.sub(r"(?<=\S)[ \t]{2,}", " ", text)


def normalise_typography(text):
    """Everything plain_spaces does, plus one glyph for each mark: straight quotes and apostrophes,
    ordinary spaces, and one dash ("—", unspaced) for "--", "—" and a spaced "–". The judge then sees
    whether a draft uses a dash, not how the source edition typeset it (review: typography by arm)."""
    t = text.replace(" ", " ")
    t = t.translate(str.maketrans({"’": "'", "‘": "'", "“": '"', "”": '"'}))
    t = re.sub(r"\s*(?:--|—|\s–\s)\s*", "—", t)
    return plain_spaces(t)


def export_judge(run, scratch):
    """Judge packets into DIR/judge-in under anonymous ids, so a judge never sees the author's name."""
    d = run_dir(run)
    anon = json.loads((d / "anon.json").read_text())["briefs"]
    out = pathlib.Path(scratch) / "judge-in"
    out.mkdir(parents=True, exist_ok=True)
    (pathlib.Path(scratch) / "judge-out").mkdir(exist_ok=True)
    (pathlib.Path(scratch) / "recognition-out").mkdir(exist_ok=True)
    shutil.copy(ROOT / "evals" / "judge.md", out / "_judge.md")
    norm = normalise_typography if "arms" in meta(d) else plain_spaces
    for aid, pid in anon.items():
        txt = (d / "judge" / f"{pid}.md").read_text(encoding="utf-8").replace(f"# Judge packet {pid}", f"# Judge packet {aid}")
        (out / f"{aid}.md").write_text(txt, encoding="utf-8")
        passage = norm((d / "passages" / f"{pid}.md").read_text(encoding="utf-8").strip())
        (out / f"{aid}.passage.md").write_text(passage + "\n", encoding="utf-8")
    print(f"{len(anon)} packets in {out}")


def import_judge(run, scratch):
    """Verdicts and recognition answers back into the run under the real ids."""
    d = run_dir(run)
    anon = json.loads((d / "anon.json").read_text())["briefs"]
    labels = sorted(LABELS[:len(arms(meta(d)))])
    n = collections.Counter()
    for sub, dest in (("judge-out", "judge"), ("recognition-out", "recognition")):
        for aid, pid in anon.items():
            f = pathlib.Path(scratch) / sub / f"{aid}.json"
            if f.exists():
                v = json.loads(f.read_text())
                if dest == "judge" and sorted(v.get("ranking", [])) != labels:
                    raise SystemExit(f"{f}: ranking must hold {', '.join(labels)} once each")
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
    labs = ", ".join(LABELS[:len(arms(m))])
    L = [f"# Spot-check, run {run}", "",
         f"{len(pick)} of {sum(len(v) for v in by.values())} judgments, chosen by seed, at least one per author. "
         f"For each: read the passage and drafts {labs}, then the judge's ranking. Mark **agree** if the "
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


REPORT_TAIL = re.compile(r"\n+(?:#+ *(?:Check|Report|Notes?|Explain)\b|\{\s*\n\s*\"schema_version\"|Check report:)", re.I)


def strip_notes(text):
    """Only the draft goes to the judge: cut a report or notes block appended after the draft (a
    heading such as '## Check report', or a JSON report). A '---' rule inside a draft is kept (review:
    it used to cut real text)."""
    m = REPORT_TAIL.search(text)
    return (text[:m.start()] if m else text).strip()


# ---------- scoring ----------

def binom_p(k, n):
    """One-sided exact binomial P(X >= k) for p = 0.5."""
    return sum(math.comb(n, i) for i in range(k, n + 1)) / 2 ** n


def draft_flags(run, d, rows_by_id):
    """check flags per draft, computed once and kept in flags.json, so a run can be rescored after the
    store changes (review: run 1 could no longer be scored once its authors were retired)."""
    f = d / "flags.json"
    cache = json.loads(f.read_text()) if f.exists() else {}
    s = Store(STORE)
    for p in meta(d)["passages"]:
        for k in arms(meta(d)):
            if p["id"] in cache and k in cache[p["id"]]:
                continue
            try:
                r = checkmod.check(s, strip_notes(draft_path(d, k, p["id"]).read_text(encoding="utf-8")),
                                   p["author"], {"type": "essay"})
                val = r.get("flagged")
            except StoreError:
                val = ((rows_by_id.get(p["id"]) or {}).get("flags") or {}).get(k)
            cache.setdefault(p["id"], {})[k] = val
    f.write_text(json.dumps(cache, indent=1) + "\n")
    return cache


def beats(rank, a, b):
    return rank.index(a) < rank.index(b)


def cluster_ci(rows, a, b, cluster, n_boot=4000, seed=7):
    """Win rate of arm a over arm b with a 95% interval from resampling generator clusters, since one
    agent writes several drafts (review: the unit of replication is the agent, not the brief)."""
    by = collections.defaultdict(list)
    for r in rows:
        by[cluster(r)].append(beats(r["rank"], a, b))
    keys = sorted(by)
    if not keys:
        return None
    rate = sum(sum(v) for v in by.values()) / sum(len(v) for v in by.values())
    rng = random.Random(seed)
    boots = []
    for _ in range(n_boot):
        pick = [by[rng.choice(keys)] for _ in keys]
        tot = sum(len(v) for v in pick)
        boots.append(sum(sum(v) for v in pick) / tot)
    boots.sort()
    return {"rate": round(rate, 3), "ci95": [round(boots[int(0.025 * n_boot)], 3), round(boots[int(0.975 * n_boot) - 1], 3)],
            "clusters": len(keys), "briefs": sum(len(v) for v in by.values())}


def score(run):
    d = run_dir(run)
    m = meta(d)
    arm_list = arms(m)
    key = json.loads((d / "key.json").read_text())
    anon = json.loads((d / "anon.json").read_text())
    agents = {pid: anon.get("agents", {}).get(aid) for aid, pid in anon["briefs"].items()}
    old_rows = {}
    if (d / "results.json").exists():
        old_rows = {r["id"]: r for r in json.loads((d / "results.json").read_text())["rows"]}
    flags = draft_flags(run, d, old_rows)
    recognition_run = any((d / "recognition").glob("*.json"))
    rows = []
    for p in m["passages"]:
        v = json.loads((d / "judge" / f"{p['id']}.json").read_text())
        rank = [key[p["id"]][lab] for lab in v["ranking"]]
        rec_f = d / "recognition" / f"{p['id']}.json"
        rec = json.loads(rec_f.read_text()) if rec_f.exists() else {"confidence": "not run"}
        rows.append({**p, "rank": rank, "agent": agents.get(p["id"]) or p["author"],
                     "win_plain": beats(rank, "idiolect", "plain"),
                     "win_fewshot": beats(rank, "idiolect", "fewshot"),
                     "recognised": rec.get("confidence") in ("medium", "high"),
                     "recognition": rec, "flags": flags[p["id"]]})
    res = {"run": run, "arms": list(arm_list), "recognition_checks": "run" if recognition_run else "not run",
           "authors": {}, "groups": {}, "pairs": {}}
    for level, keyf in (("authors", "author"), ("groups", "group")):
        for name in sorted({r[keyf] for r in rows}):
            rs = [r for r in rows if r[keyf] == name and not r["recognised"]]
            n = len(rs)
            wp = sum(r["win_plain"] for r in rs)
            wf = sum(r["win_fewshot"] for r in rs)
            mean = {k: round(sum(r["flags"][k] or 0 for r in rs) / max(1, n), 2) for k in arm_list}
            allr = [r for r in rows if r[keyf] == name]
            res[level][name] = {"briefs": len(allr), "counted": n,
                                "excluded_recognised": sum(1 for r in allr if r["recognised"]),
                                "wins_vs_plain": wp, "wins_vs_fewshot": wf,
                                "rate_vs_plain": round(wp / n, 3) if n else None,
                                "rate_vs_fewshot": round(wf / n, 3) if n else None, "mean_flags": mean,
                                "all_briefs": {"vs_plain": sum(r["win_plain"] for r in allr),
                                               "vs_fewshot": sum(r["win_fewshot"] for r in allr)}}
    group_of = {r["author"]: r["group"] for r in rows}
    for g, v in res["groups"].items():
        # an author whose every brief was excluded has no rate and does not count against the floor
        rated = [a for a, x in res["authors"].items() if group_of[a] == g and x["counted"]]
        v["pass"] = bool(v["counted"]) and v["rate_vs_plain"] >= 0.70 and v["rate_vs_fewshot"] >= 0.60 and all(
            res["authors"][a]["rate_vs_fewshot"] >= 0.5 for a in rated)
    counted = [r for r in rows if not r["recognised"]]
    pairs = [("idiolect", "plain"), ("idiolect", "fewshot")]
    if "lite" in arm_list:
        pairs += [("lite", "plain"), ("lite", "fewshot"), ("idiolect", "lite")]
    for a, b in pairs:
        name = f"{a} vs {b}"
        res["pairs"][name] = {g: cluster_ci([r for r in counted if r["group"] == g], a, b, lambda r: r["agent"])
                              for g in sorted({r["group"] for r in rows})}
        res["pairs"][name]["all"] = cluster_ci(counted, a, b, lambda r: r["agent"])
        by_author = {}
        for au in sorted({r["author"] for r in rows}):
            rs = [r for r in counted if r["author"] == au]
            by_author[au] = round(sum(beats(r["rank"], a, b) for r in rs) / len(rs), 3) if rs else None
        res["pairs"][name]["by_author"] = by_author
    positions = collections.Counter()
    for p in m["passages"]:
        v = json.loads((d / "judge" / f"{p['id']}.json").read_text())
        positions[v["ranking"][0]] += 1
    res["first_place_by_label"] = dict(sorted(positions.items()))
    (d / "results.json").write_text(json.dumps({"summary": res, "rows": rows}, indent=1) + "\n")
    write_results_md(d, run, res)
    return res


def write_results_md(d, run, res):
    pct = lambda x: "n/a" if x is None else f"{x:.0%}"  # noqa: E731
    arm_list = res["arms"]
    excl = ("Counted briefs exclude those whose passage a separate agent recognised with medium or high confidence."
            if res["recognition_checks"] == "run" else
            "**Recognition checks were not run for this run: every brief is counted, none was screened.**")
    L = [f"# Results, run {run}", "", excl,
         "The last column (all briefs, recognised included) is reported for information and decides nothing.", "",
         f"| Author | Briefs | Excluded (recognised) | vs plain | vs few-shot | Mean flags: {' / '.join(arm_list)} | All briefs: vs plain, vs few-shot |",
         "| --- | --- | --- | --- | --- | --- | --- |"]
    for a, v in res["authors"].items():
        ex = v["excluded_recognised"] if res["recognition_checks"] == "run" else "not run"
        L.append(f"| {a} | {v['briefs']} | {ex} | {v['wins_vs_plain']}/{v['counted']} "
                 f"({pct(v['rate_vs_plain'])}) | {v['wins_vs_fewshot']}/{v['counted']} ({pct(v['rate_vs_fewshot'])}) | "
                 f"{' / '.join(str(v['mean_flags'][k]) for k in arm_list)} | "
                 f"{v['all_briefs']['vs_plain']}/{v['briefs']}, {v['all_briefs']['vs_fewshot']}/{v['briefs']} |")
    L += ["", "| Group | Counted | vs plain (bar 70%) | vs few-shot (bar 60%) | Pass this run |", "| --- | --- | --- | --- | --- |"]
    for g, v in res["groups"].items():
        L.append(f"| {g} | {v['counted']} | {pct(v['rate_vs_plain'])} | {pct(v['rate_vs_fewshot'])} | {'yes' if v['pass'] else 'no'} |")
    L += ["", "Pairwise win rates with 95% intervals from resampling generator agents (one agent writes several "
          "drafts, so the agent, not the brief, is the unit):", "",
          "| Comparison | All | " + " | ".join(g for g in res["groups"]) + " | By author |",
          "| --- | --- | " + " | ".join("---" for _ in res["groups"]) + " | --- |"]
    for name, v in res["pairs"].items():
        cell = lambda c: "n/a" if not c else f"{c['rate']:.0%} ({c['ci95'][0]:.0%}-{c['ci95'][1]:.0%}, {c['clusters']} agents)"  # noqa: E731
        auth = ", ".join(f"{a} {pct(x)}" for a, x in v["by_author"].items())
        L.append(f"| {name} | {cell(v['all'])} | " + " | ".join(cell(v[g]) for g in res["groups"]) + f" | {auth} |")
    L += ["", f"First place by label: {res['first_place_by_label']}"]
    (d / "results.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))


def pool(runs):
    """The pooled binomial over runs. A passage used in more than one run counts once (its first run),
    since repeated passages are not independent briefs (review)."""
    seen = set()
    tot = collections.defaultdict(lambda: [0, 0, 0])
    per_run, repeats = {}, 0
    for r in runs:
        d = run_dir(r)
        data = json.loads((d / "results.json").read_text())
        res, rows = data["summary"], data["rows"]
        per_run[r] = {g: v["pass"] for g, v in res["groups"].items()}
        for row in rows:
            k = text_key((d / "passages" / f"{row['id']}.md").read_text(encoding="utf-8"))
            if k in seen:
                repeats += 1
                continue
            seen.add(k)
            if row["recognised"]:
                continue
            tot[row["group"]][0] += 1
            tot[row["group"]][1] += row["win_plain"]
            tot[row["group"]][2] += row["win_fewshot"]
    out = {"repeated_passages_skipped": repeats}
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
    ap.add_argument("--per-author", type=int, default=PER_AUTHOR)
    ap.add_argument("--per-agent", type=int)
    ap.add_argument("--arms")
    ap.add_argument("--avoid", default="")
    a = ap.parse_args()
    if a.action == "new":
        new_run(a.seed, per_author=a.per_author, arm_list=tuple(a.arms.split(",")) if a.arms else KINDS,
                avoid=[r for r in a.avoid.split(",") if r])
    elif a.action == "overlap":
        overlap(a.run)
    elif a.action == "prepare":
        prepare(a.run, a.scratch, a.per_agent)
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
