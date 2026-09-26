#!/usr/bin/env python3
"""Evaluation harness (evals/eval-protocol.md). Scripts prepare, shuffle and score; agents write briefs,
drafts, judgments and recognition answers into the run folder.

    python3 evals/harness.py new [--seed N] [--per-author 10] [--arms plain,fewshot,idiolect,lite]
                                 [--avoid R1,R2] [--source later] [--fresh-only] [--cap author=N]
                                                       create evals/runs/<run-id>/ with passages
    python3 evals/harness.py overlap  --run R          check briefs against passages (4-word runs)
    python3 evals/harness.py prepare  --run R --scratch DIR [--per-agent 4]
                                                       few-shot packets, an isolated store + skill copies,
                                                       generator assignments and prompts
    python3 evals/harness.py collect  --run R --scratch DIR   drafts back into the run, real ids
    python3 evals/harness.py lengths  --run R          draft lengths against targets
    python3 evals/harness.py shuffle  --run R          judge packets and key.json (balanced labels)
    python3 evals/harness.py export-judge --run R --scratch DIR   packets and passages, anonymous ids
    python3 evals/harness.py recognition --run R --scratch DIR    forced-choice recognition prompts, with
                                                       the positive controls, under shuffled ids
    python3 evals/harness.py sensitivity --run R --scratch DIR [--n 12]
                                                       blind and author-named re-judging prompts for a
                                                       seeded sample of real-author packets
    python3 evals/harness.py import-judge --run R --scratch DIR   verdicts, recognition and sensitivity
                                                       answers back, real ids
    python3 evals/harness.py score    --run R          results.md and results.json
    python3 evals/harness.py pool     --runs R1,R2     the pooled binomial check over runs
    python3 evals/harness.py spotcheck --run R         a seeded 10% of judgments for a person to mark
    python3 evals/harness.py screen --scratch DIR --name "A. Writer" --files a.md,b.md,c.md,d.md
    python3 evals/harness.py screen --scratch DIR      screen a candidate author: prompts, then the score

Run layout: passages/<id>.md, briefs/<id>.md, drafts/<arm>/<id>.md, judge/<id>.md (packet) and
judge/<id>.json (verdict), recognition/<id>.json, key.json, flags.json, results.md; forced-choice
runs (run 7 on) add recognition-key.json, recognition/_controls.json, sensitivity-key.json and
sensitivity/{blind,named}-<id>.json.

Arms: plain, fewshot, idiolect (the full write procedure) and the ablations: lite (run 4: the kit
without the measurable targets and without the check-and-revise loop; evals/ablation/write-lite.md) and
bare (runs 5 and 6: the full procedure with the kit's --notes none, no observed lessons;
evals/ablation/write-bare.md).

Holdout sources (evals/holdouts.json): "authors" (essays set aside from the fixture books, runs 1 to 4)
or "later" (runs 5 and 6: other books by the same authors and new synthetic essays, in
evals/holdouts-later/, plus fixture holdouts with unused paragraphs). A passage is fresh when none of
its paragraphs appeared in a passage of an avoided run.
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
ALL_ARMS = ("plain", "fewshot", "idiolect", "lite", "bare")
ABLATIONS = ("lite", "bare")
LABELS = "ABCD"
CANDIDATES = ROOT / "evals" / "recognition-candidates.json"
N_CANDIDATES = 10                 # forced choice: ten writers and "none"
BINS = ((0, 30, "under 30%"), (30, 60, "30-59%"), (60, 101, "60% or more"))
POSITIVE_MIN = 60                 # a positive control must get at least this on its author
NONE_MIN = 80                     # synthetic passages (negative controls) must average this on "none"
SENS_N = 12
SCREEN_MAX = 30                   # an author is usable when the mean on the true author is below this


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
    """300-500-word passages cut at paragraph boundaries. The first passage starts at one of the first
    few paragraphs, chosen by the seed among the starts that give the most passages, so different
    seeds give different cuts of the same essay without losing passages (review: the seed used to be
    ignored). A paragraph that would push a passage past 500 words is not lost with the paragraphs
    before it: it starts the next passage."""
    paras = [b for b in blocks if count_words(b) > 0]
    if not paras:
        return []
    options = [_cut_from(paras, start) for start in range(min(4, len(paras)))]
    best = max(len(o) for o in options)
    return rng.choice([o for o in options if len(o) == best])


def _cut_from(paras, i):
    out = []
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


def para_keys(text):
    return {text_key(p) for p in re.split(r"\n\s*\n", text) if p.strip()}


def holdout_files(source):
    """[(author, path)] for a holdout source (evals/holdouts.json)."""
    h = json.loads((ROOT / "evals" / "holdouts.json").read_text())
    if source == "authors":
        return {a: [FIX / a / f for f in files] for a, files in h["authors"].items()}
    return {a: [ROOT / "evals" / f for f in files] for a, files in h[source]["authors"].items()}


def new_run(seed=SEED, run_id=None, per_author=PER_AUTHOR, arm_list=KINDS, avoid=(), source="authors",
            fresh_only=False, caps=None):
    """Passages for a new run. Passages sharing a paragraph with a passage of the runs named in `avoid`
    are taken last (or, with fresh_only, not at all), and the number reused is recorded, because a run
    that repeats another's text is not an independent sample (review: runs 2 and 3 shared 38 of 50;
    a different cut of the same paragraphs is the same text). caps: {author: n} below per_author."""
    run_id = run_id or dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    used = set()
    for r in avoid:
        for f in (run_dir(r) / "passages").glob("*.md"):
            used |= para_keys(f.read_text(encoding="utf-8"))
    d = RUNS / run_id
    (d / "passages").mkdir(parents=True)
    for sub in ("briefs", "judge", "recognition") + tuple(f"drafts/{k}" for k in arm_list):
        (d / sub).mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)
    hold = holdout_files(source)
    caps = caps or {}
    m = {"run": run_id, "seed": seed, "arms": list(arm_list), "avoid": list(avoid), "source": source,
         "fresh_only": fresh_only, "caps": caps, "recognition": "forced-choice", "passages": [], "reused": {}}
    for author, files in sorted(hold.items()):
        pool = []
        for f in files:
            ex = extract(f)
            name = str(f.relative_to(FIX / author)) if f.is_relative_to(FIX / author) else str(f.relative_to(ROOT / "evals"))
            if fresh_only:                          # cut each unbroken stretch of unused paragraphs
                stretches, cur = [], []
                for b in ex.blocks:
                    if text_key(b) in used:
                        stretches.append(cur)
                        cur = []
                    else:
                        cur.append(b)
                stretches.append(cur)
                pool += [(name, p) for st in stretches if st for p in cut(st, rng)]
            else:
                pool += [(name, p) for p in cut(ex.blocks, rng)]
        rng.shuffle(pool)
        fresh = [x for x in pool if not para_keys(x[1]) & used]
        old = [] if fresh_only else [x for x in pool if para_keys(x[1]) & used]
        want = min(per_author, caps.get(author, per_author))
        chosen = []
        for part in (fresh, old):                   # fresh passages first, spread over essays
            by = collections.defaultdict(list)
            for f, p in part:
                by[f].append(p)
            while len(chosen) < want and any(by.values()):
                for f in sorted(by):
                    if by[f] and len(chosen) < want:
                        chosen.append((f, by[f].pop()))
        m["reused"][author] = sum(1 for _, p in chosen if para_keys(p) & used)
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
    for k in ABLATIONS:
        if k in arm_list:
            shutil.copytree(ROOT / "idiolect", scratch / f"idiolect-{k}", ignore=shutil.ignore_patterns("__pycache__"))
            shutil.copy(ROOT / "evals" / "ablation" / f"write-{k}.md",
                        scratch / f"idiolect-{k}" / "references" / "modes" / "write.md")
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


def forced_choice(m):
    """Runs from run 7 on record "recognition": "forced-choice" (eval-protocol.md, Recognition). Older
    runs keep the confidence label they were judged with, and their recorded exclusions."""
    return m.get("recognition") == "forced-choice"


def candidates_file():
    return json.loads(CANDIDATES.read_text(encoding="utf-8"))


def candidate_list(true_name, rng, pool, n=N_CANDIDATES):
    """n writers in alphabetical order: the true author (when there is one) and seeded distractors from
    the pool. A synthetic passage gets n distractors, so its right answer is "none"."""
    others = sorted(x for x in pool if x != true_name)
    picks = rng.sample(others, n - (1 if true_name else 0)) + ([true_name] if true_name else [])
    return sorted(picks)


def fc_prompt(passage, cands, out):
    tmpl = (PROMPTS / "recognition.txt").read_text(encoding="utf-8")
    return tmpl.format(PASSAGE=passage, CANDIDATES="; ".join(cands), OUT=out)


def read_fc(f, cands):
    """A forced-choice answer, checked and scaled to sum to 100. Raises SystemExit on a bad answer."""
    v = json.loads(pathlib.Path(f).read_text())
    p = v.get("p", {})
    want = set(cands) | {"none"}
    if set(p) != want:
        raise SystemExit(f"{f}: probabilities must name exactly: {', '.join(sorted(want))}")
    tot = sum(float(x) for x in p.values())
    if not 95 <= tot <= 105:
        raise SystemExit(f"{f}: probabilities add up to {tot:g}, not 100")
    return {k: round(100 * float(x) / tot, 1) for k, x in p.items()}, v.get("cues", "")


def recognition(run, scratch):
    """Forced-choice recognition prompts: one per passage, plus the positive controls, all under
    shuffled ids r01.. so no agent can tell a control from a passage. The key stays in the run folder."""
    d = run_dir(run)
    m = meta(d)
    if not forced_choice(m):
        sys.exit(f"run {run} uses the confidence label; forced choice starts with runs that record it")
    sc = pathlib.Path(scratch).resolve()
    if (sc / "recognition-in").exists():
        sys.exit(f"{sc / 'recognition-in'} exists")
    cf = candidates_file()
    rng = random.Random(m["seed"] + 4)
    items = [{"kind": "passage", "id": p["id"], "file": d / "passages" / f"{p['id']}.md",
              "truth": None if p["group"] == "synthetic" else cf["authors"][p["author"]]["name"]}
             for p in m["passages"]]
    items += [{"kind": "positive", "id": c["file"], "file": ROOT / "evals" / c["file"], "truth": c["name"]}
              for c in cf["controls"]]
    rng.shuffle(items)
    for sub in ("recognition-in", "recognition-prompts", "recognition-out"):
        (sc / sub).mkdir(parents=True, exist_ok=True)
    key = {}
    for i, it in enumerate(items, 1):
        rid = f"r{i:02d}"
        cands = candidate_list(it["truth"], rng, cf["pool"])
        text = normalise_typography(it["file"].read_text(encoding="utf-8").strip())
        (sc / "recognition-in" / f"{rid}.md").write_text(text + "\n", encoding="utf-8")
        (sc / "recognition-prompts" / f"{rid}.txt").write_text(
            fc_prompt(sc / "recognition-in" / f"{rid}.md", cands, sc / "recognition-out" / f"{rid}.json"), encoding="utf-8")
        key[rid] = {"kind": it["kind"], "id": it["id"], "truth": it["truth"] or "none", "candidates": cands}
    (d / "recognition-key.json").write_text(json.dumps(key, indent=1) + "\n")
    print(f"{len(key)} recognition prompts in {sc / 'recognition-prompts'} "
          f"({sum(1 for v in key.values() if v['kind'] == 'positive')} positive controls)")


def sensitivity(run, scratch, n=SENS_N):
    """The sensitivity test: a seeded sample of real-author packets judged again, once blind and once told
    the author. Needs export-judge first (it reuses judge-in/). The key stays in the run folder."""
    d = run_dir(run)
    m = meta(d)
    sc = pathlib.Path(scratch).resolve()
    if not (sc / "judge-in" / "_judge.md").exists():
        sys.exit("run export-judge first")
    cf = candidates_file()
    anon = json.loads((d / "anon.json").read_text())["briefs"]
    group = {p["id"]: p for p in m["passages"]}
    real = sorted(aid for aid, pid in anon.items() if group[pid]["group"] == "real")
    rng = random.Random(m["seed"] + 5)
    pick = sorted(rng.sample(real, min(n, len(real))))
    for sub in ("sensitivity-prompts", "sensitivity-out"):
        (sc / sub).mkdir(parents=True, exist_ok=True)
    for aid in pick:
        a = cf["authors"][group[anon[aid]]["author"]]
        for kind in ("blind", "named"):
            tmpl = (PROMPTS / f"sens-{kind}.txt").read_text(encoding="utf-8")
            (sc / "sensitivity-prompts" / f"{kind}-{aid}.txt").write_text(tmpl.format(
                JUDGE=sc / "judge-in" / "_judge.md", PACKET=sc / "judge-in" / f"{aid}.md", NAME=a["name"],
                ABOUT=a["about"], OUT=sc / "sensitivity-out" / f"{kind}-{aid}.json"), encoding="utf-8")
    (d / "sensitivity-key.json").write_text(json.dumps({aid: anon[aid] for aid in pick}, indent=1) + "\n")
    print(f"{len(pick)} packets, {2 * len(pick)} prompts in {sc / 'sensitivity-prompts'}")


def import_judge(run, scratch):
    """Verdicts, recognition answers and sensitivity verdicts back into the run under the real ids."""
    d = run_dir(run)
    m = meta(d)
    anon = json.loads((d / "anon.json").read_text())["briefs"]
    labels = sorted(LABELS[:len(arms(m))])
    sc = pathlib.Path(scratch)
    n = collections.Counter()

    def verdict(f):
        v = json.loads(f.read_text())
        if sorted(v.get("ranking", [])) != labels:
            raise SystemExit(f"{f}: ranking must hold {', '.join(labels)} once each")
        return v

    subs = (("judge-out", "judge"),) + ((() if forced_choice(m) else (("recognition-out", "recognition"),)))
    for sub, dest in subs:
        for aid, pid in anon.items():
            f = sc / sub / f"{aid}.json"
            if f.exists():
                v = verdict(f) if dest == "judge" else json.loads(f.read_text())
                (d / dest / f"{pid}.json").write_text(json.dumps(v, indent=1, ensure_ascii=False) + "\n")
                n[dest] += 1
    if forced_choice(m) and (d / "recognition-key.json").exists():
        key = json.loads((d / "recognition-key.json").read_text())
        controls = {}
        for rid, k in sorted(key.items()):
            f = sc / "recognition-out" / f"{rid}.json"
            if not f.exists():
                continue
            p, cues = read_fc(f, k["candidates"])
            # a synthetic passage has no author to know: its answer is a negative control (p["none"])
            rec = {"method": "forced-choice", "candidates": k["candidates"], "truth": k["truth"], "p": p,
                   "p_true": None if k["truth"] == "none" else p[k["truth"]], "cues": cues}
            if k["kind"] == "passage":
                (d / "recognition" / f"{k['id']}.json").write_text(json.dumps(rec, indent=1, ensure_ascii=False) + "\n")
                n["recognition"] += 1
            else:
                controls[k["id"]] = rec
                n["controls"] += 1
        if controls:
            (d / "recognition" / "_controls.json").write_text(json.dumps(controls, indent=1, ensure_ascii=False) + "\n")
    if (d / "sensitivity-key.json").exists():
        (d / "sensitivity").mkdir(exist_ok=True)
        for aid, pid in json.loads((d / "sensitivity-key.json").read_text()).items():
            for kind in ("blind", "named"):
                f = sc / "sensitivity-out" / f"{kind}-{aid}.json"
                if f.exists():
                    (d / "sensitivity" / f"{kind}-{pid}.json").write_text(
                        json.dumps(verdict(f), indent=1, ensure_ascii=False) + "\n")
                    n["sensitivity"] += 1
    print(json.dumps(dict(n)))


# ---------- screening new authors ----------

def screen(scratch, name=None, files=(), seed=SEED):
    """Screen a candidate author (eval-protocol.md, Screening). With --name and --files (passages of
    about 300 words, the author's and other people's names already removed): forced-choice prompts, one
    per passage, plus the positive controls, under shuffled ids. Without them: score the answers."""
    sc = pathlib.Path(scratch).resolve()
    kf = sc / "screen-key.json"
    if not files:
        key = json.loads(kf.read_text())
        rows = {"passages": [], "controls": []}
        for sid, k in sorted(key["items"].items()):
            p, _ = read_fc(sc / "screen-out" / f"{sid}.json", k["candidates"])
            rows["passages" if k["kind"] == "passage" else "controls"].append(round(p[k["truth"]], 1))
        mean = sum(rows["passages"]) / len(rows["passages"])
        ok = all(x >= POSITIVE_MIN for x in rows["controls"])
        out = {"author": key["name"], "p_true": rows["passages"], "mean": round(mean, 1),
               "controls": rows["controls"], "detector_ok": ok,
               "accept": ok and mean < SCREEN_MAX and len(rows["passages"]) >= 4}
        print(json.dumps(out, indent=1))
        return out
    if kf.exists():
        sys.exit(f"{kf} exists; use a new scratch folder")
    cf = candidates_file()
    rng = random.Random(seed)
    items = [{"kind": "passage", "file": pathlib.Path(f), "truth": name} for f in files]
    items += [{"kind": "positive", "file": ROOT / "evals" / c["file"], "truth": c["name"]} for c in cf["controls"]]
    rng.shuffle(items)
    for sub in ("screen-in", "screen-prompts", "screen-out"):
        (sc / sub).mkdir(parents=True, exist_ok=True)
    key = {"name": name, "items": {}}
    for i, it in enumerate(items, 1):
        sid = f"s{i:02d}"
        cands = candidate_list(it["truth"], rng, cf["pool"])
        text = normalise_typography(it["file"].read_text(encoding="utf-8").strip())
        (sc / "screen-in" / f"{sid}.md").write_text(text + "\n", encoding="utf-8")
        (sc / "screen-prompts" / f"{sid}.txt").write_text(
            fc_prompt(sc / "screen-in" / f"{sid}.md", cands, sc / "screen-out" / f"{sid}.json"), encoding="utf-8")
        key["items"][sid] = {"kind": it["kind"], "file": str(it["file"]), "truth": it["truth"], "candidates": cands}
    kf.write_text(json.dumps(key, indent=1) + "\n")
    print(f"{len(items)} screening prompts in {sc / 'screen-prompts'}")


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


def familiarity(rows):
    """Win rates by how sure a forced-choice agent was of the true author (p_true, 0 to 100): the
    known-author result read beside how well the model knows each passage's author. Synthetic passages
    have no author to know and are the negative controls instead (detector)."""
    out = {}
    for g in sorted({r["group"] for r in rows if r["group"] != "synthetic"}):
        rs = [r for r in rows if r["group"] == g]
        known = [r["familiarity"] for r in rs if r.get("familiarity") is not None]
        v = {"mean_p_true": round(sum(known) / len(known), 1) if known else None, "bins": {}}
        for lo, hi, label in BINS + ((None, None, "not run"),):
            b = [r for r in rs if (r.get("familiarity") is None if lo is None
                                   else r.get("familiarity") is not None and lo <= r["familiarity"] < hi)]
            if b:
                v["bins"][label] = {"briefs": len(b), "vs_plain": sum(r["win_plain"] for r in b),
                                    "vs_fewshot": sum(r["win_fewshot"] for r in b)}
        out[g] = v
    return out


def detector(d, rows):
    """Does the recognition check work this run? The positive controls (well-known writers) must be named
    with at least POSITIVE_MIN, and the synthetic passages (negative controls: no one to name) must
    average at least NONE_MIN on "none"."""
    f = d / "recognition" / "_controls.json"
    pos = {k: v["p_true"] for k, v in json.loads(f.read_text()).items()} if f.exists() else {}
    neg = [r["recognition"]["p"]["none"] for r in rows
           if r["group"] == "synthetic" and r["recognition"].get("method") == "forced-choice"]
    mean_none = round(sum(neg) / len(neg), 1) if neg else None
    ok = bool(pos) and bool(neg) and all(x >= POSITIVE_MIN for x in pos.values()) and mean_none >= NONE_MIN
    return {"positive": pos, "negatives": len(neg), "mean_none": mean_none, "ok": ok}


def pair_agreement(r1, r2):
    """The share of arm pairs two rankings put in the same order."""
    ps = [(a, b) for i, a in enumerate(r1) for b in r1[i + 1:]]
    return sum(beats(r2, a, b) for a, b in ps) / len(ps)


def sensitivity_result(d, key, rows):
    """Blind and author-named re-judgments of the sampled packets. If naming the author moves Idiolect's
    wins over few-shot by at least max(3, a quarter of the sample), the known-author result is flagged
    unreliable: the judge is then reading the author's reputation, not the passage."""
    sd = d / "sensitivity"
    if not sd.exists():
        return None
    orig = {r["id"]: r["rank"] for r in rows}
    got = []
    for f in sorted(sd.glob("blind-*.json")):
        pid = f.stem[len("blind-"):]
        g = sd / f"named-{pid}.json"
        if not g.exists():
            continue
        blind = [key[pid][lab] for lab in json.loads(f.read_text())["ranking"]]
        named = [key[pid][lab] for lab in json.loads(g.read_text())["ranking"]]
        got.append((orig[pid], blind, named))
    if not got:
        return None
    n = len(got)
    w = lambda i: sum(beats(x[i], "idiolect", "fewshot") for x in got)  # noqa: E731
    shift = abs(w(2) - w(1))
    limit = max(3, math.ceil(n / 4))
    return {"packets": n, "wins_vs_fewshot": {"original": w(0), "blind": w(1), "named": w(2)},
            "agreement": {"original_blind": round(sum(pair_agreement(o, b) for o, b, _ in got) / n, 2),
                          "original_named": round(sum(pair_agreement(o, nm) for o, _, nm in got) / n, 2)},
            "shift": shift, "limit": limit, "unreliable": shift >= limit}


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
    fc = forced_choice(m)
    rows = []
    for p in m["passages"]:
        v = json.loads((d / "judge" / f"{p['id']}.json").read_text())
        rank = [key[p["id"]][lab] for lab in v["ranking"]]
        rec_f = d / "recognition" / f"{p['id']}.json"
        rec = json.loads(rec_f.read_text()) if rec_f.exists() else {"confidence": "not run"}
        row = {**p, "rank": rank, "agent": agents.get(p["id"]) or p["author"],
               "win_plain": beats(rank, "idiolect", "plain"),
               "win_fewshot": beats(rank, "idiolect", "fewshot"),
               # forced-choice runs exclude nothing: familiarity is reported, not screened out
               "recognised": False if fc else rec.get("confidence") in ("medium", "high"),
               "recognition": rec, "flags": flags[p["id"]]}
        if fc:
            row["familiarity"] = rec.get("p_true")
        rows.append(row)
    res = {"run": run, "arms": list(arm_list), "recognition_checks": "run" if recognition_run else "not run",
           "recognition_method": "forced-choice" if fc else "confidence",
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
    for k in ABLATIONS:
        if k in arm_list:
            pairs += [(k, "plain"), (k, "fewshot"), ("idiolect", k)]
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
    if fc:
        res["familiarity"] = familiarity(rows)
        res["detector"] = detector(d, rows)
        res["sensitivity"] = sensitivity_result(d, key, rows)
        if "real" in res["groups"]:
            s = res["sensitivity"]
            res["groups"]["real"]["reliable"] = None if s is None else not s["unreliable"]
    (d / "results.json").write_text(json.dumps({"summary": res, "rows": rows}, indent=1) + "\n")
    write_results_md(d, run, res)
    return res


GROUP_NAMES = {"real": "known-author (real)", "synthetic": "unknown-author (synthetic)"}


def write_results_md(d, run, res):
    pct = lambda x: "n/a" if x is None else f"{x:.0%}"  # noqa: E731
    arm_list = res["arms"]
    fc = res.get("recognition_method") == "forced-choice"
    gname = (lambda g: GROUP_NAMES.get(g, g)) if fc else (lambda g: g)  # noqa: E731
    if fc:
        head = ["Every brief is counted. Familiarity is the probability a separate forced-choice agent gave the "
                "true author (ten writers and \"none\"); it is reported beside the result and excludes nothing."]
        col = "Mean familiarity"
    else:
        head = [("Counted briefs exclude those whose passage a separate agent recognised with medium or high confidence."
                 if res["recognition_checks"] == "run" else
                 "**Recognition checks were not run for this run: every brief is counted, none was screened.**"),
                "The last column (all briefs, recognised included) is reported for information and decides nothing."]
        col = "Excluded (recognised)"
    L = [f"# Results, run {run}", ""] + head + ["",
         f"| Author | Briefs | {col} | vs plain | vs few-shot | Mean flags: {' / '.join(arm_list)} | All briefs: vs plain, vs few-shot |",
         "| --- | --- | --- | --- | --- | --- | --- |"]
    fam = {}
    if fc:
        rows = json.loads((d / "results.json").read_text())["rows"]
        for a in res["authors"]:
            xs = [r["familiarity"] for r in rows if r["author"] == a and r.get("familiarity") is not None]
            fam[a] = f"{sum(xs) / len(xs):.0f}%" if xs else "not run"
    for a, v in res["authors"].items():
        ex = fam[a] if fc else (v["excluded_recognised"] if res["recognition_checks"] == "run" else "not run")
        L.append(f"| {a} | {v['briefs']} | {ex} | {v['wins_vs_plain']}/{v['counted']} "
                 f"({pct(v['rate_vs_plain'])}) | {v['wins_vs_fewshot']}/{v['counted']} ({pct(v['rate_vs_fewshot'])}) | "
                 f"{' / '.join(str(v['mean_flags'][k]) for k in arm_list)} | "
                 f"{v['all_briefs']['vs_plain']}/{v['briefs']}, {v['all_briefs']['vs_fewshot']}/{v['briefs']} |")
    L += ["", "| Group | Counted | vs plain (bar 70%) | vs few-shot (bar 60%) | Pass this run |", "| --- | --- | --- | --- | --- |"]
    for g, v in res["groups"].items():
        mark = "yes" if v["pass"] else "no"
        if v.get("reliable") is False:
            mark += " (unreliable: sensitivity test)"
        elif fc and g == "real" and v.get("reliable") is None:
            mark += " (sensitivity test not run)"
        L.append(f"| {gname(g)} | {v['counted']} | {pct(v['rate_vs_plain'])} | {pct(v['rate_vs_fewshot'])} | {mark} |")
    if fc:
        L += ["", "Win rates by familiarity (the probability given to the true author):", "",
              "| Group | Familiarity | Briefs | vs plain | vs few-shot |", "| --- | --- | --- | --- | --- |"]
        for g, v in res["familiarity"].items():
            for label, b in v["bins"].items():
                L.append(f"| {gname(g)} | {label} | {b['briefs']} | {b['vs_plain']}/{b['briefs']} | {b['vs_fewshot']}/{b['briefs']} |")
        det = res["detector"]
        pos = ", ".join(f"{k.rsplit('/', 1)[-1]} {x:.0f}%" for k, x in det["positive"].items()) or "none run"
        L += ["", f"Detector check: positive controls {pos} (need {POSITIVE_MIN}%); "
                  f"{det['negatives']} synthetic passages average {det['mean_none'] if det['mean_none'] is not None else 'n/a'}% "
                  f"on \"none\" (need {NONE_MIN}%): **{'works' if det['ok'] else 'FAILED: the familiarity figures are not trustworthy this run'}**."]
        sens = res["sensitivity"]
        if sens is None:
            L += ["", "Sensitivity test: **not run**."]
        else:
            w = sens["wins_vs_fewshot"]
            L += ["", f"Sensitivity test ({sens['packets']} real-author packets judged again): Idiolect over few-shot "
                      f"{w['original']} (original), {w['blind']} (blind), {w['named']} (author named); agreement with "
                      f"the original {sens['agreement']['original_blind']:.2f} blind, {sens['agreement']['original_named']:.2f} named. "
                      f"Shift {sens['shift']} against a limit of {sens['limit']}: "
                      f"**{'unreliable' if sens['unreliable'] else 'within judge noise'}**."]
    L += ["", "Pairwise win rates with 95% intervals from resampling generator agents (one agent writes several "
          "drafts, so the agent, not the brief, is the unit):", "",
          "| Comparison | All | " + " | ".join(gname(g) for g in res["groups"]) + " | By author |",
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
    per_run, repeats, unreliable = {}, 0, {}
    for r in runs:
        d = run_dir(r)
        data = json.loads((d / "results.json").read_text())
        res, rows = data["summary"], data["rows"]
        per_run[r] = {g: v["pass"] for g, v in res["groups"].items()}
        for g, v in res["groups"].items():
            if v.get("reliable") is False:
                unreliable.setdefault(g, []).append(r)
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
        if g in unreliable:
            out[g]["unreliable_runs"] = unreliable[g]      # the sensitivity test flagged these runs
    print(json.dumps(out, indent=1))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("action", choices=["new", "overlap", "prepare", "collect", "lengths", "shuffle",
                                       "export-judge", "import-judge", "recognition", "sensitivity", "score", "pool",
                                       "spotcheck", "screen"])
    ap.add_argument("--run")
    ap.add_argument("--runs")
    ap.add_argument("--scratch")
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--per-author", type=int, default=PER_AUTHOR)
    ap.add_argument("--per-agent", type=int)
    ap.add_argument("--arms")
    ap.add_argument("--avoid", default="")
    ap.add_argument("--source", default="authors", choices=["authors", "later"])
    ap.add_argument("--fresh-only", action="store_true")
    ap.add_argument("--cap", action="append", default=[], help="author=N: fewer passages for this author")
    ap.add_argument("--n", type=int, default=SENS_N, help="sensitivity: packets to judge again")
    ap.add_argument("--name", help="screen: the candidate author's name")
    ap.add_argument("--files", default="", help="screen: comma-separated passage files, names removed")
    a = ap.parse_args()
    if a.action == "new":
        new_run(a.seed, per_author=a.per_author, arm_list=tuple(a.arms.split(",")) if a.arms else KINDS,
                avoid=[r for r in a.avoid.split(",") if r], source=a.source, fresh_only=a.fresh_only,
                caps={k: int(v) for k, v in (c.split("=") for c in a.cap)})
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
    elif a.action == "recognition":
        recognition(a.run, a.scratch)
    elif a.action == "sensitivity":
        sensitivity(a.run, a.scratch, a.n)
    elif a.action == "screen":
        screen(a.scratch, a.name, [f for f in a.files.split(",") if f], a.seed)
    elif a.action == "spotcheck":
        spotcheck(a.run)
    elif a.action == "score":
        score(a.run)
    else:
        pool(a.runs.split(","))


if __name__ == "__main__":
    main()
