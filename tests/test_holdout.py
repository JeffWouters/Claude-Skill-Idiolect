"""Phase 4: the test mode (spec §19): holdout proposal, brief check, drift, blind packet, results."""
import glob
import json
import pathlib
import shutil

import pytest

import holdout
import learn
import stage
from common import StoreError
from store import Store
from test_learn import FIX, full_learn, lesson_file, make_store


def approve(st):
    stage.Pending(Store(st)).decide(all_decision="approved")
    return stage.commit(st)


def noor_keys(st):
    return sorted(k for k, e in Store(st).manifest["texts"].items() if "noor" in e["profiles"])


def test_a_learned_text_held_out_is_removed_from_learning_first(tmp_path):
    st = make_store(tmp_path)
    full_learn(tmp_path, st, "noor", "noor")
    fp0 = json.loads((st / "profiles" / "noor" / "en.essay.json").read_text())
    exs = (st / "profiles" / "noor" / "en.essay.examples.md").read_text()
    src = [k for k in noor_keys(st) if k in exs]
    key = src[0] if src else noor_keys(st)[0]
    out = holdout.propose(st, key)
    assert out["was_learned"] and out["slot"] == "en.essay"
    kinds = {i["kind"] for i in stage.Pending(Store(st)).plan["items"]}
    assert {"status", "fingerprint"} <= kinds
    approve(st)
    e = Store(st).manifest["texts"][key]
    assert e["holdout"] and e["status"] == "active" and (st / "corpus" / f"{key}.txt").exists()
    fp1 = json.loads((st / "profiles" / "noor" / "en.essay.json").read_text())
    assert fp1["counts"]["texts"] == fp0["counts"]["texts"] - 1
    if src:
        assert key not in (st / "profiles" / "noor" / "en.essay.examples.md").read_text()
    assert "test" in (st / "profiles" / "noor" / "changelog.md").read_text()
    # a later learn refuses it
    learn.start(st, targets=["noor"], profile="noor")
    assert learn.Run(st).state["texts"][key]["result"] == "skipped: holdout"
    stage.discard(st)
    with pytest.raises(StoreError, match="already a holdout"):
        holdout.propose(st, key)
    assert not (st / ".state" / "lock").exists()


def test_a_new_file_becomes_a_holdout_without_being_learned(tmp_path):
    st = make_store(tmp_path)
    full_learn(tmp_path, st, "noor", "noor")
    new = sorted(glob.glob(str(FIX / "synthetic-noor" / "[0-9]*.md")))[11]
    shutil.copy(new, tmp_path / "Writing" / "noor" / "zz-held.md")
    with pytest.raises(StoreError, match="type"):
        holdout.propose(st, "noor/zz-held.md")
    out = holdout.propose(st, "noor/zz-held.md", type_="essay")
    assert not out["was_learned"]
    fp0 = (st / "profiles" / "noor" / "en.essay.json").read_text()
    approve(st)
    e = Store(st).manifest["texts"][out["key"]]
    assert e["holdout"] and e["profiles"]["noor"]["ownership"] == "own" and e["cached"]
    assert (st / "profiles" / "noor" / "en.essay.json").read_text() == fp0
    learn.start(st, targets=["noor"], profile="noor")
    assert learn.Run(st).state["texts"][out["key"]]["result"] == "skipped: holdout"
    stage.discard(st)


def test_brief_check_refuses_shared_wording_and_long_briefs(tmp_path):
    st = make_store(tmp_path)
    full_learn(tmp_path, st, "noor", "noor")
    key = noor_keys(st)[0]
    holdout.propose(st, key)
    approve(st)
    text = Store(st).corpus_text(key)
    copied = " ".join(text.split()[:30])
    assert not holdout.brief_check(Store(st), key, copied)["ok"]
    assert holdout.brief_check(Store(st), key, "An essay about weather and patience. About 400 words.")["ok"]
    assert not holdout.brief_check(Store(st), key, "word " * 70)["ok"]
    ex = holdout.examples(Store(st), key, "weather and patience")
    assert ex["profile"] == "noor" and 0 < len(ex["examples"]) <= 3


def test_blind_packet_hides_the_key_and_record_maps_the_ranking(tmp_path):
    st = make_store(tmp_path)
    full_learn(tmp_path, st, "noor", "noor")
    key = noor_keys(st)[0]
    holdout.propose(st, key)
    approve(st)
    brief = tmp_path / "brief.md"
    brief.write_text("An essay about weather and patience. About 400 words.")
    drafts = {}
    for n, arm in enumerate(holdout.ARMS):
        f = tmp_path / f"{arm}.md"
        f.write_text(f"Draft text. It rains. We wait. [example needed: a real storm] Marker {n}.\n")
        drafts[arm] = str(f)
    p = holdout.packet(st, key, brief, drafts)
    assert not any(arm in p["packet"].lower() for arm in holdout.ARMS)
    assert "example needed" not in p["packet"]
    assert not (st / ".state" / "lock").exists()
    st_file = json.loads((st / ".state" / "test" / f"{p['test']}.json").read_text())
    idio = next(k for k, v in st_file["labels"].items() if v == "idiolect")
    rest = [k for k in "ABC" if k != idio]
    out = holdout.record(st, test_id=p["test"], ranking=",".join([idio] + rest))
    assert out["blind_picks"].startswith("idiolect > ")
    assert "draft_drift" in out and out["profile_drift"]["mean_log"] is not None
    res = (st / "eval" / "results.md").read_text()
    assert res.startswith("---\nschema_version: 1\n---\n| Date | Profile |")
    assert res.count("\n| 20") == 1 and "idiolect > " in res and "profile " in res and "draft " in res
    with pytest.raises(StoreError, match="A, B and C"):
        holdout.record(st, test_id=p["test"], ranking="A,B")
    # without a judge
    out2 = holdout.record(st, key=key)
    assert out2["blind_picks"] == "—" and "draft_drift" not in out2
    assert (st / "eval" / "results.md").read_text().count("\n| 20") == 2


def test_a_forgotten_text_cannot_be_held_out(tmp_path):
    import maintain
    st = make_store(tmp_path)
    full_learn(tmp_path, st, "noor", "noor")
    key = noor_keys(st)[0]
    maintain.forget(st, key)
    approve(st)
    with pytest.raises(StoreError, match="forgotten"):
        holdout.propose(st, key)
    assert not (st / ".state" / "pending").exists()


def test_drift_shrinks_over_three_learns(tmp_path):
    """Phase 4 exit (design: decision log): three learns with growing texts, the same holdout each
    time; profile drift at the last is below the first, and no metric is outside the band at the last."""
    st = make_store(tmp_path)          # noor: fixture essays 1-10 in the sources folder
    src = tmp_path / "Writing" / "noor"
    files = sorted(src.glob("*.md"))
    held = sorted(glob.glob(str(FIX / "synthetic-noor" / "[0-9]*.md")))[11]
    shutil.copy(held, src / "zz-held.md")
    stash = tmp_path / "stash"
    stash.mkdir()
    for f in files[3:]:
        shutil.move(str(f), stash / f.name)
    full_learn(tmp_path, st, "noor", "noor")                 # run 1: 3 texts
    out = holdout.propose(st, "noor/zz-held.md", type_="essay")
    approve(st)
    key = out["key"]
    drifts = [holdout.record(st, key=key)["profile_drift"]]
    for batch in (files[3:6], files[6:]):                   # runs 2 and 3: 6, then 10 texts
        for f in batch:
            shutil.move(str(stash / f.name), f)
        learn.start(st, targets=["noor"], profile="noor")
        learn.stage_texts(st)
        learn.do_measure(st)
        for slot in ("en.essay", "en._"):
            learn.lessons_apply(st, "noor", slot, lesson_file(tmp_path, st, "noor", slot))
        approve(st)
        drifts.append(holdout.record(st, key=key)["profile_drift"])
    means = [d["mean_log"] for d in drifts]
    assert means[-1] < means[0], means
    assert drifts[-1]["outside"] == 0, drifts[-1]
    assert (st / "eval" / "results.md").read_text().count("\n| 20") == 3


def test_drift_falls_on_average_over_text_orders():
    """Phase 4 exit, second half: evals/drift-trend.py over the fixture authors."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("drift_trend", FIX.parent / "drift-trend.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    out = mod.trend(30)
    assert out and all(v["never_rises"] and v["falls_overall"] for v in out.values()), out
