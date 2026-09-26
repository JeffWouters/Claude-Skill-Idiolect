"""Phase 5: learn-edit (spec §20). The six scripted edit pairs in evals/edit-pairs produce the expected
edit lessons, which survive a relearn and reach the writing kit."""
import json
import pathlib
import shutil

import pytest
import yaml

import kit
import learn
import learn_edit
import pages
import stage
from common import StoreError
from store import Store
from test_learn import full_learn, lesson_file, make_store

PAIRS = pathlib.Path(__file__).resolve().parent.parent / "evals" / "edit-pairs"
DESCRIBE = {"cut-hedge": "Cuts hedges before a claim.", "split-sentence": "Splits a sentence joined by 'and' into two.",
            "numerals": "Writes numbers as digits."}


def norm(t):
    return " ".join(t.split()).lower()


def kinds_file(tmp_path, pair_dir, changes):
    """What the model would answer: each change's kind, from the pair's expected.yaml."""
    exp = yaml.safe_load((pair_dir / "expected.yaml").read_text())["changes"]
    named = {}
    for c in changes:
        hit = next((e["kind"] for e in exp if norm(e["draft"]) in norm(c["before"]) and norm(e["final"]) in norm(c["after"])), "other")
        named[c["id"]] = hit
    f = tmp_path / f"kinds-{pair_dir.name}.yaml"
    f.write_text(yaml.safe_dump({"changes": named, "describe": DESCRIBE}))
    return f


def run_pair(tmp_path, st, n, approve=True):
    d = PAIRS / f"pair-{n:02d}"
    out = learn_edit.start(st, d / "draft.md", d / "final.md", profile="noor", type_="essay")
    got = learn_edit.kinds(st, kinds_file(tmp_path, d, out["changes"]))
    stage.Pending(Store(st)).decide(all_decision="approved" if approve else "rejected")
    stage.commit(st)
    return out, got


def edits(st):
    return pages.parse_edits((st / "profiles" / "noor" / "en.essay.edits.md").read_text())[1]


def test_six_pairs_give_the_expected_edit_lessons_and_they_survive_a_relearn(tmp_path):
    st = make_store(tmp_path)
    full_learn(tmp_path, st, "noor", "noor")
    out, got = run_pair(tmp_path, st, 1)
    assert out["slot"] == "en.essay" and out["pair"] == "p-001"
    assert all(x["seen_once"] for x in got["edit_lessons"])          # one pair: nothing confirmed yet
    for n in range(2, 7):
        run_pair(tmp_path, st, n)
    les = {x["kind"]: x for x in edits(st)}
    expected = yaml.safe_load((PAIRS / "expected-lessons.yaml").read_text())
    assert {k for k, v in les.items() if not v["seen_once"]} == set(expected["edit_lessons"])
    assert {k for k, v in les.items() if v["seen_once"]} == set(expected["seen_once"])
    assert len(les["cut-hedge"]["pairs"]) == 6 and len(les["split-sentence"]["pairs"]) == 5
    ids = {k: v["id"] for k, v in les.items()}
    assert len(set(ids.values())) == 3 and all(i.startswith("d-") for i in ids.values())
    # the pairs keep changes only, redacted and reviewed; never the draft or final texts
    pairs = sorted((st / "profiles" / "noor" / "edits").glob("p-*/pair.yaml"))
    assert len(pairs) == 6 and all(sorted(x.name for x in p.parent.iterdir()) == ["pair.yaml"] for p in pairs)
    p1 = yaml.safe_load(pairs[0].read_text())
    assert p1["redaction"]["reviewed"] and all("kind" in c for c in p1["changes"])
    # the kit shows the two confirmed edit lessons, not the kind seen once
    k = kit.build(Store(st), "noor", {"type": "essay"}, "An essay about a kitchen")
    assert sorted(x["text"] for x in k["edit_lessons"]) == sorted([DESCRIBE["cut-hedge"], DESCRIBE["split-sentence"]])
    # a relearn with one more text leaves edit lessons and pairs untouched
    before = (st / "profiles" / "noor" / "en.essay.edits.md").read_text()
    fix = sorted((PAIRS.parent / "fixtures" / "synthetic-noor").glob("[0-9]*.md"))[10]
    shutil.copy(fix, tmp_path / "Writing" / "noor")
    learn.start(st, targets=["noor"], profile="noor")
    learn.stage_texts(st)
    learn.do_measure(st)
    for slot in ("en.essay", "en._"):
        learn.lessons_apply(st, "noor", slot, lesson_file(tmp_path, st, "noor", slot))
    stage.Pending(Store(st)).decide(all_decision="approved")
    stage.commit(st)
    assert (st / "profiles" / "noor" / "en.essay.edits.md").read_text() == before
    assert len(list((st / "profiles" / "noor" / "edits").glob("p-*/pair.yaml"))) == 6
    # a seventh pair keeps every id
    run_pair(tmp_path, st, 3)
    assert {x["kind"]: x["id"] for x in edits(st)} == ids


def test_rejecting_the_pair_rejects_its_lessons_and_a_rejected_lesson_stays_gone(tmp_path):
    st = make_store(tmp_path)
    full_learn(tmp_path, st, "noor", "noor")
    run_pair(tmp_path, st, 1)
    d = PAIRS / "pair-02"
    out = learn_edit.start(st, d / "draft.md", d / "final.md", profile="noor", type_="essay")
    learn_edit.kinds(st, kinds_file(tmp_path, d, out["changes"]))
    p = stage.Pending(Store(st))
    pair_item = next(i["id"] for i in p.plan["items"] if i["kind"] == "edit-pair")
    plan = p.decide(reject=[pair_item])
    assert all(i["decision"] == "rejected" for i in plan["items"] if i["kind"] == "edit-lesson")
    stage.commit(st)
    assert not (st / "profiles" / "noor" / "edits" / "p-002").exists()
    stage.discard(st) if (st / ".state" / "pending").exists() else None


def test_a_rejected_edit_lesson_is_not_proposed_again(tmp_path):
    st = make_store(tmp_path)
    full_learn(tmp_path, st, "noor", "noor")
    d = PAIRS / "pair-01"
    out = learn_edit.start(st, d / "draft.md", d / "final.md", profile="noor", type_="essay")
    learn_edit.kinds(st, kinds_file(tmp_path, d, out["changes"]))
    p = stage.Pending(Store(st))
    hedge = next(i["id"] for i in p.plan["items"] if i["kind"] == "edit-lesson" and "cut-hedge" in i["summary"])
    p.decide(reject=[hedge], all_decision="approved")
    stage.commit(st)
    rej = yaml.safe_load((st / "profiles" / "noor" / "rejected.yaml").read_text())
    assert [e["kind"] for e in rej["entries"]] == ["edit"]
    _, got = run_pair(tmp_path, st, 2)
    assert "cut-hedge" in got["not_proposed_rejected"]
    kinds = {x["kind"] for x in edits(st)}
    assert "cut-hedge" not in kinds and "split-sentence" in kinds


def test_start_needs_a_type_and_a_difference(tmp_path):
    st = make_store(tmp_path)
    full_learn(tmp_path, st, "noor", "noor")
    d = PAIRS / "pair-01"
    with pytest.raises(StoreError, match="needs_input"):
        learn_edit.start(st, d / "draft.md", d / "final.md", profile="noor")
    assert not (st / ".state" / "lock").exists()
    with pytest.raises(StoreError, match="no differences"):
        learn_edit.start(st, d / "final.md", d / "final.md", profile="noor", type_="essay")
    out = learn_edit.start(st, d / "draft.md", d / "final.md", profile="noor", type_="essay")
    f = tmp_path / "k.yaml"
    f.write_text(yaml.safe_dump({"changes": {c["id"]: "brand-new" for c in out["changes"]}}))
    with pytest.raises(StoreError, match="describe"):
        learn_edit.kinds(st, f)
    stage.discard(st)
