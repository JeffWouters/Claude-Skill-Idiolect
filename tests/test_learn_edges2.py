"""Second round of phase 2 edge cases (re-review): knock-on decisions, retired slots, rollback and ids,
moved texts without a cache, ghost profiles, forget by path and by key."""
import glob
import json
import shutil

import pytest
import yaml

import learn
import maintain
import pages
import stage
from common import StoreError, load_yaml_text
from store import Store
from test_learn import FIX, answers, full_learn, lesson_file, make_store
from test_learn_edges import approve_all, basic_learn, items


def test_rejecting_a_change_keeps_the_old_slot(tmp_path):
    st = make_store(tmp_path)
    x = tmp_path / "Writing" / "x"
    x.mkdir()
    shutil.copy(sorted(glob.glob(str(FIX / "synthetic-noor" / "[0-9]*.md")))[11], x / "solo.md")
    learn.start(st, targets=["x"], profile="noor")
    a = tmp_path / "a.yaml"
    a.write_text("folders:\n  - {path: x, profile: noor, ownership: own, facets: {type: email}}\n"
                 "profiles:\n  - {name: noor, subject: s, consent: self}\n")
    learn.answer(st, a)
    learn.stage_texts(st)
    learn.do_measure(st)
    approve_all(st)
    f = x / "solo.md"
    f.write_text(f.read_text() + "\n\nOne more closing line for the change.\n")
    learn.start(st, targets=["x"], profile="noor", type_="essay")
    learn.stage_texts(st)
    learn.do_measure(st)
    assert any(i["kind"] == "deletion" and i.get("slot") == "en.email" for i, _ in items(st))
    approve_all(st, [i["id"] for i, _ in items(st) if i["kind"] == "corpus-text"])
    assert (st / "profiles/noor/en.email.json").exists()
    assert "no texts" not in (st / "profiles/noor/en.email.md").read_text()


def test_rejecting_a_new_profile_leaves_no_half_profile_and_no_permanent_rejections(tmp_path):
    st = make_store(tmp_path)
    learn.start(st, targets=["noor"], profile="noor")
    learn.answer(st, answers(tmp_path, "noor", "noor"))
    learn.stage_texts(st)
    learn.do_measure(st)
    learn.lessons_apply(st, "noor", "en.essay", lesson_file(tmp_path, st, "noor", "en.essay"))
    v = tmp_path / "v.yaml"
    v.write_text("- {text: kitchen tap, kind: term}\n")
    learn.vocab_apply(st, "noor", v)
    approve_all(st, [i["id"] for i, _ in items(st) if i["kind"] == "profile"])
    assert not (st / "profiles" / "noor").exists()
    assert Store(st).manifest["texts"] == {}


def test_approving_the_cause_undoes_a_knock_on_rejection(tmp_path):
    st = make_store(tmp_path)
    basic_learn(tmp_path, st)
    p = stage.Pending(Store(st))
    prof = next(i["id"] for i in p.plan["items"] if i["kind"] == "profile")
    p.decide(reject=[prof])
    assert all(i["decision"] == "rejected" for i in p.plan["items"] if i["kind"] == "corpus-text")
    p.decide(approve=[prof])
    assert all(i["decision"] == "pending" for i in p.plan["items"] if i["kind"] == "corpus-text")
    stage.discard(st)


def test_rollback_keeps_rejections_and_ids(tmp_path):
    st = make_store(tmp_path)
    full_learn(tmp_path, st, "noor", "noor")

    def relearn(extra, reject_text=None):
        learn.start(st, targets=["noor"], profile="noor")
        learn.stage_texts(st)
        learn.do_measure(st)
        ks = [k for k, _ in learn.slot_texts(learn.Run(st), "noor", "en.essay")]
        base = yaml.safe_load(lesson_file(tmp_path, st, "noor", "en.essay").read_text())
        f = tmp_path / "l.yaml"
        f.write_text(yaml.safe_dump(base + [{"section": s, "text": x, "evidence": ks[:3]} for s, x in extra]))
        learn.lessons_apply(st, "noor", "en.essay", f)
        approve_all(st, [i["id"] for i, _ in items(st) if reject_text and reject_text in i["summary"]])

    relearn([("Stance", "Distrusts grand plans."), ("Tone", "Uses dry understatement.")], "dry understatement")
    _, _, les = pages.parse_slot_page((st / "profiles/noor/en.essay.md").read_text())
    used = {x["id"] for x in les} | {e["rejects"] for e in load_yaml_text(
        (st / "profiles/noor/rejected.yaml").read_text())["entries"]}
    maintain.rollback(st, "noor")
    approve_all(st)
    assert (st / "profiles/noor/rejected.yaml").exists()
    relearn([("Tone", "Uses dry understatement."), ("Structure", "Builds in three short beats.")])
    _, _, les = pages.parse_slot_page((st / "profiles/noor/en.essay.md").read_text())
    texts = {x["text"]: x["id"] for x in les}
    assert "Uses dry understatement." not in texts
    assert texts["Builds in three short beats."] not in used


def test_relearn_after_rolling_back_the_first_learn(tmp_path):
    st = make_store(tmp_path)
    full_learn(tmp_path, st, "noor", "noor")
    first = maintain._snapshots(Store(st), "noor")[0]
    maintain.rollback(st, "noor", to=first)
    approve_all(st)
    out = learn.start(st, targets=["noor"], profile="noor")
    assert "new: 10" in out["summary"]
    stage.discard(st)


def test_rollback_to_a_forgotten_state_deletes_the_cache(tmp_path):
    st = make_store(tmp_path)
    basic_learn(tmp_path, st)
    approve_all(st)
    key = sorted(Store(st).manifest["texts"])[0]
    path = Store(st).manifest["texts"][key]["path"]
    maintain.forget(st, path)
    approve_all(st)
    maintain.forget(st, path, ownership="own", profile="noor")
    approve_all(st)
    assert (st / "corpus" / f"{key}.txt").exists()
    maintain.rollback(st, "noor")
    approve_all(st)
    e = Store(st).manifest["texts"][key]
    assert e["status"] == "forgotten" and not (st / "corpus" / f"{key}.txt").exists()


def test_a_moved_text_without_cache_is_cached_again(tmp_path):
    st = make_store(tmp_path)
    basic_learn(tmp_path, st)
    approve_all(st)
    key = sorted(Store(st).manifest["texts"])[0]
    path = Store(st).manifest["texts"][key]["path"]
    maintain.forget(st, path)
    approve_all(st)
    src = tmp_path / "Writing" / path
    saved = src.read_text()
    src.unlink()
    maintain.rollback(st, "noor", to=maintain._snapshots(Store(st), "noor")[-1])
    approve_all(st)
    (tmp_path / "Writing/noor/renamed.md").write_text(saved)
    learn.start(st, targets=["noor"], profile="noor")
    learn.stage_texts(st)
    learn.do_measure(st)
    approve_all(st)
    e = Store(st).manifest["texts"][key]
    assert e["status"] == "active" and e["cached"] and (st / "corpus" / f"{key}.txt").exists()
    assert json.loads((st / "profiles/noor/en.essay.json").read_text())["counts"]["texts"] == 10


def test_forget_retires_an_empty_slot_and_blanks_quotes(tmp_path):
    st = make_store(tmp_path)
    x = tmp_path / "Writing" / "x"
    x.mkdir()
    for f in sorted(glob.glob(str(FIX / "synthetic-noor" / "[0-9]*.md")))[10:12]:
        shutil.copy(f, x)
    learn.start(st, targets=["x"], profile="noor")
    a = tmp_path / "a.yaml"
    a.write_text("folders:\n  - {path: x, profile: noor, ownership: own, facets: {type: email}}\n"
                 "profiles:\n  - {name: noor, subject: s, consent: self}\n")
    learn.answer(st, a)
    learn.stage_texts(st)
    learn.do_measure(st)
    learn.lessons_apply(st, "noor", "en.email", lesson_file(tmp_path, st, "noor", "en.email", extra=False))
    approve_all(st)
    for f in sorted(x.iterdir()):
        maintain.forget(st, f"x/{f.name}")
        approve_all(st)
    assert not (st / "profiles/noor/en.email.json").exists()
    meta, conf, les = pages.parse_slot_page((st / "profiles/noor/en.email.md").read_text())
    assert les == [] and meta["last_id"] >= 1 and conf == "no texts"


def test_forget_needs_an_existing_profile(tmp_path):
    st = make_store(tmp_path)
    basic_learn(tmp_path, st)
    approve_all(st)
    path = sorted(e["path"] for e in Store(st).manifest["texts"].values())[0]
    with pytest.raises(StoreError):
        maintain.forget(st, path, profile="ghost", ownership="own")
    with pytest.raises(StoreError):
        maintain.forget(st, path, profile="ghost")
    assert not (st / "profiles/ghost").exists()


def test_rejecting_a_new_type_rejects_the_texts_of_that_type(tmp_path):
    st = make_store(tmp_path)
    learn.start(st, targets=["noor"], profile="noor")
    a = tmp_path / "a.yaml"
    a.write_text("folders:\n  - {path: noor, profile: noor, ownership: own}\n"
                 "profiles:\n  - {name: noor, subject: s, consent: self}\n")
    learn.answer(st, a)
    run = learn.Run(st)
    t = tmp_path / "types.yaml"
    t.write_text("\n".join(f"'{v['path']}': column" for k, v in run.state["texts"].items()) + "\n")
    learn.set_types(st, t)
    learn.stage_texts(st)
    learn.do_measure(st)
    approve_all(st, [i["id"] for i, pl in items(st) if pl.get("types_add")])
    assert Store(st).manifest["texts"] == {}
