"""The evaluation harness (evals/harness.py): the fixes from the review of runs 1 to 3."""
import pathlib
import random
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "evals"))

import harness  # noqa: E402


def paras(n, size=120):
    return [" ".join(f"w{i}x{j}" for j in range(size)) + "." for i in range(n)]


def test_cut_depends_on_the_seed_and_keeps_an_overshooting_paragraph():
    blocks = paras(31)       # starts 0 and 1 both give ten passages
    cuts = {tuple(harness.cut(blocks, random.Random(s))) for s in range(12)}
    assert len(cuts) > 1
    big = [" ".join(["a"] * 200) + ".", " ".join(["z"] * 350) + "."] + paras(6, 60)
    out = harness._cut_from(big, 0)
    assert out and out[0].startswith("z z")
    # the seed chooses only among starts that give the most passages
    n = max(len(harness._cut_from(blocks, i)) for i in range(4))
    assert all(len(harness.cut(blocks, random.Random(s))) == n for s in range(12))


def test_strip_notes_keeps_a_scene_break_and_cuts_a_report():
    assert harness.strip_notes("Para one.\n---\nPara two.") == "Para one.\n---\nPara two."
    assert harness.strip_notes("The draft.\n\n## Check report\nflagged 1") == "The draft."
    assert harness.strip_notes('The draft.\n{\n "schema_version": 1}') == "The draft."


def test_typography_is_one_glyph_per_mark():
    t = harness.normalise_typography("He said “no” -- and left—twice – then, it’s  done. Yes")
    assert t == 'He said "no"—and left—twice—then, it\'s done. Yes'


def test_labels_are_balanced_in_a_four_arm_run(tmp_path, monkeypatch):
    import json
    monkeypatch.setattr(harness, "RUNS", tmp_path)
    d = tmp_path / "r"
    arms = ["plain", "fewshot", "idiolect", "lite"]
    for sub in ["passages", "judge"] + [f"drafts/{a}" for a in arms]:
        (d / sub).mkdir(parents=True)
    ps = []
    for i in range(8):
        pid = f"x-{i:02d}"
        (d / "passages" / f"{pid}.md").write_text("Passage.\n")
        for a in arms:
            (d / "drafts" / a / f"{pid}.md").write_text(f"Draft {a}.\n")
        ps.append({"id": pid, "author": "x", "words": 1, "group": "real"})
    (d / "run.json").write_text(json.dumps({"run": "r", "seed": 1, "arms": arms, "passages": ps}))
    harness.shuffle("r")
    key = json.loads((d / "key.json").read_text())
    for lab in "ABCD":
        counts = {a: sum(1 for k in key.values() if k[lab] == a) for a in arms}
        assert set(counts.values()) == {2}


def test_cluster_interval_uses_agents():
    rows = [{"rank": ["idiolect", "fewshot"], "agent": "a"}] * 4 + [{"rank": ["fewshot", "idiolect"], "agent": "b"}] * 4
    ci = harness.cluster_ci(rows, "idiolect", "fewshot", lambda r: r["agent"])
    assert ci["rate"] == 0.5 and ci["clusters"] == 2 and ci["ci95"] == [0.0, 1.0]


def test_later_runs_use_only_fresh_paragraphs_and_the_caps(tmp_path, monkeypatch):
    """Runs 5 and 6: the later holdout source, no paragraph of an avoided run's passage, per-author caps."""
    import json
    monkeypatch.setattr(harness, "RUNS", tmp_path)
    old = ["20260926T133739Z", "20260926T144759Z", "20260926T144808Z", "20260926T154434Z"]
    for r in old:                                  # the real runs 1 to 4, as the runs to avoid
        (tmp_path / r / "passages").mkdir(parents=True)
        for f in (ROOT / "evals" / "runs" / r / "passages").glob("*.md"):
            (tmp_path / r / "passages" / f.name).write_text(f.read_text())
    caps = {"katharine-fullerton-gerould": 4, "synthetic-idris": 8, "synthetic-noor": 8}
    arms = ("plain", "fewshot", "idiolect", "bare")

    def count(run):
        m = json.loads((tmp_path / run / "run.json").read_text())
        c = {}
        for p in m["passages"]:
            c[p["author"]] = c.get(p["author"], 0) + 1
        keys = set().union(*(harness.para_keys((tmp_path / run / "passages" / f"{p['id']}.md").read_text())
                             for p in m["passages"]))
        return m, c, keys

    used = set()
    for r in old:
        for f in (tmp_path / r / "passages").glob("*.md"):
            used |= harness.para_keys(f.read_text())
    harness.new_run(5, "r5", 10, arms, old, "later", True, caps)
    m5, c5, k5 = count("r5")
    assert c5 == {"katharine-fullerton-gerould": 4, "robert-cortes-holliday": 10, "samuel-mcchord-crothers": 10,
                  "synthetic-idris": 8, "synthetic-noor": 8}
    assert not k5 & used and not any(m5["reused"].values())
    harness.new_run(6, "r6", 10, arms, old + ["r5"], "later", True, caps)
    m6, c6, k6 = count("r6")
    assert c6["katharine-fullerton-gerould"] >= 3 and all(c6[a] == c5[a] for a in c5 if a != "katharine-fullerton-gerould")
    assert not k6 & k5 and not k6 & used


# ---------- forced-choice recognition (runs 7 on) ----------

def fc_run(tmp_path, monkeypatch):
    """A small forced-choice run: four real passages, two synthetic, three arms, judged."""
    import json
    monkeypatch.setattr(harness, "RUNS", tmp_path)
    d = tmp_path / "fc"
    arms = ["plain", "fewshot", "idiolect"]
    for sub in ["passages", "judge", "recognition"] + [f"drafts/{a}" for a in arms]:
        (d / sub).mkdir(parents=True)
    ps = [{"id": f"katharine-fullerton-gerould-{i:02d}", "author": "katharine-fullerton-gerould", "words": 3,
           "group": "real"} for i in range(1, 5)]
    ps += [{"id": f"synthetic-noor-{i:02d}", "author": "synthetic-noor", "words": 3, "group": "synthetic"}
           for i in range(1, 3)]
    key, anon, flags = {}, {}, {}
    for n, p in enumerate(ps):
        (d / "passages" / f"{p['id']}.md").write_text("A passage -- of sorts.\n")
        key[p["id"]] = {"A": "idiolect", "B": "fewshot", "C": "plain"}
        anon[f"w{n}-01"] = p["id"]
        flags[p["id"]] = {a: 0 for a in arms}
        (d / "judge" / f"{p['id']}.json").write_text(json.dumps({"ranking": ["A", "B", "C"]}))
    (d / "run.json").write_text(json.dumps({"run": "fc", "seed": 3, "arms": arms, "recognition": "forced-choice",
                                            "passages": ps}))
    (d / "key.json").write_text(json.dumps(key))
    (d / "anon.json").write_text(json.dumps({"briefs": anon, "agents": {}}))
    (d / "flags.json").write_text(json.dumps(flags))
    return d, anon


def test_candidate_list_holds_the_true_author_or_only_distractors():
    import random
    pool = [f"W{i}" for i in range(20)]
    c = harness.candidate_list("W3", random.Random(1), pool)
    assert len(c) == 10 and "W3" in c and c == sorted(c)
    c = harness.candidate_list(None, random.Random(1), pool)
    assert len(c) == 10 and len(set(c)) == 10


def test_forced_choice_answers_are_checked(tmp_path):
    import json
    import pytest
    f = tmp_path / "a.json"
    f.write_text(json.dumps({"p": {"X": 60, "Y": 30, "none": 12}, "cues": "c"}))
    p, cues = harness.read_fc(f, ["X", "Y"])
    assert round(sum(p.values())) == 100 and cues == "c"
    f.write_text(json.dumps({"p": {"X": 60, "none": 40}}))
    with pytest.raises(SystemExit):
        harness.read_fc(f, ["X", "Y"])
    f.write_text(json.dumps({"p": {"X": 60, "Y": 60, "none": 40}}))
    with pytest.raises(SystemExit):
        harness.read_fc(f, ["X", "Y"])


def test_forced_choice_run_counts_every_brief_and_reports_controls_and_sensitivity(tmp_path, monkeypatch):
    import json
    d, anon = fc_run(tmp_path, monkeypatch)
    sc = tmp_path / "sc"
    harness.recognition("fc", sc)
    rkey = json.loads((d / "recognition-key.json").read_text())
    assert len(rkey) == 7 and sum(v["kind"] == "positive" for v in rkey.values()) == 1
    for rid, k in rkey.items():
        prompt = (sc / "recognition-prompts" / f"{rid}.txt").read_text()
        assert "gerould" not in prompt.lower() or "Katharine Fullerton Gerould" in k["candidates"]
        assert "synthetic" not in prompt and "katharine-fullerton" not in prompt
        assert "—" in (sc / "recognition-in" / f"{rid}.md").read_text() or k["kind"] == "positive"
        if k["kind"] == "passage" and k["id"].startswith("synthetic"):
            assert k["truth"] == "none" and len(k["candidates"]) == 10
        # well-known control named, real passages half-known, synthetic passages placed with no one
        truth_p = {"positive": 90}.get(k["kind"], 0 if k["truth"] == "none" else 50)
        p = {c: 0 for c in k["candidates"]}
        p["none"] = 100 - truth_p if k["truth"] != "none" else 100
        if k["truth"] != "none":
            p[k["truth"]] = truth_p
        (sc / "recognition-out" / f"{rid}.json").write_text(json.dumps({"p": p, "cues": "x"}))
    (sc / "judge-in").mkdir()
    (sc / "judge-in" / "_judge.md").write_text("instructions")
    harness.sensitivity("fc", sc, 4)
    skey = json.loads((d / "sensitivity-key.json").read_text())
    assert len(skey) == 4 and all(pid.startswith("katharine") for pid in skey.values())
    named = (sc / "sensitivity-prompts" / f"named-{next(iter(skey))}.txt").read_text()
    assert "Katharine Fullerton Gerould (American essayist" in named
    assert "Gerould" not in (sc / "sensitivity-prompts" / f"blind-{next(iter(skey))}.txt").read_text()
    for aid in skey:                      # blind agrees with the original; named puts few-shot first
        (sc / "sensitivity-out" / f"blind-{aid}.json").write_text(json.dumps({"ranking": ["A", "B", "C"]}))
        (sc / "sensitivity-out" / f"named-{aid}.json").write_text(json.dumps({"ranking": ["B", "A", "C"]}))
    harness.import_judge("fc", sc)
    assert (d / "recognition" / "_controls.json").exists()
    res = harness.score("fc")
    assert res["recognition_method"] == "forced-choice"
    assert res["groups"]["real"]["counted"] == 4 and res["authors"]["katharine-fullerton-gerould"]["excluded_recognised"] == 0
    assert res["familiarity"]["real"]["bins"] == {"30-59%": {"briefs": 4, "vs_plain": 4, "vs_fewshot": 4}}
    assert "synthetic" not in res["familiarity"]
    assert res["detector"]["ok"] and res["detector"]["mean_none"] == 100
    s = res["sensitivity"]
    assert s["wins_vs_fewshot"] == {"original": 4, "blind": 4, "named": 0} and s["unreliable"]
    assert s["agreement"]["original_blind"] == 1.0 and s["agreement"]["original_named"] < 1
    assert res["groups"]["real"]["reliable"] is False
    md = (d / "results.md").read_text()
    assert "known-author (real)" in md and "unreliable" in md and "Detector check" in md


def test_sensitivity_within_noise_is_reliable():
    rows = [{"id": f"p{i}", "rank": ["idiolect", "fewshot", "plain"]} for i in range(12)]
    import json
    import tempfile
    with tempfile.TemporaryDirectory() as t:
        d = pathlib.Path(t)
        (d / "sensitivity").mkdir()
        key = {r["id"]: {"A": "idiolect", "B": "fewshot", "C": "plain"} for r in rows}
        for i, r in enumerate(rows):
            (d / "sensitivity" / f"blind-{r['id']}.json").write_text(json.dumps({"ranking": ["A", "B", "C"]}))
            named = ["B", "A", "C"] if i < 2 else ["A", "B", "C"]       # a shift of 2: judge noise
            (d / "sensitivity" / f"named-{r['id']}.json").write_text(json.dumps({"ranking": named}))
        s = harness.sensitivity_result(d, key, rows)
        assert s["shift"] == 2 and s["limit"] == 3 and not s["unreliable"]


def test_screening_accepts_an_author_the_model_cannot_place(tmp_path):
    import json
    files = []
    for i in range(4):
        f = tmp_path / f"p{i}.md"
        f.write_text("Some prose, names removed.\n")
        files.append(f)
    sc = tmp_path / "sc"
    harness.screen(sc, "A. Writer", files, seed=1)
    key = json.loads((sc / "screen-key.json").read_text())
    assert len(key["items"]) == 5
    for sid, k in key["items"].items():
        t = 90 if k["kind"] == "positive" else 10
        p = {c: 0 for c in k["candidates"]}
        p[k["truth"]] = t
        p["none"] = 100 - t
        (sc / "screen-out" / f"{sid}.json").write_text(json.dumps({"p": p}))
    out = harness.screen(sc)
    assert out["accept"] and out["mean"] == 10 and out["detector_ok"]
