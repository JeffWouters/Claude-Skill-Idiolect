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
    old = sorted(p.name for p in (ROOT / "evals" / "runs").iterdir() if (p / "passages").exists())
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
