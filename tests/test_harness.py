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
