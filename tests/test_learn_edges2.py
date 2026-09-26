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


# ---------- third review ----------

def _two_profiles(tmp_path, st, idris_ownership="own"):
    learn.start(st, targets=["noor"], profile="noor")
    a = tmp_path / "a.yaml"
    a.write_text("folders:\n  - {path: noor, profile: noor, ownership: own, facets: {type: essay}}\n"
                 f"  - {{path: noor, profile: idris, ownership: {idris_ownership}, facets: {{type: essay}}}}\n"
                 "profiles:\n  - {name: noor, subject: s, consent: self}\n  - {name: idris, subject: t, consent: self}\n")
    learn.answer(st, a)
    learn.stage_texts(st)
    learn.do_measure(st)


def _consistent(st, prof):
    s = Store(st)
    usable = [k for k, e in s.manifest["texts"].items() if e["profiles"].get(prof, {}).get("ownership") == "own"
              and e["status"] in ("active", "unreachable") and e["cached"]]
    fp = json.loads((st / f"profiles/{prof}/en.essay.json").read_text())
    return fp["counts"]["texts"] == len(usable), (fp["counts"]["texts"], len(usable))


def test_rollback_of_a_rollback_restores_the_ledger(tmp_path):
    st = make_store(tmp_path)
    full_learn(tmp_path, st, "noor", "noor")
    shutil.copy(sorted(glob.glob(str(FIX / "synthetic-noor" / "[0-9]*.md")))[10], tmp_path / "Writing" / "noor")
    learn.start(st, targets=["noor"], profile="noor")
    learn.stage_texts(st)
    learn.do_measure(st)
    approve_all(st)
    maintain.rollback(st, "noor")
    approve_all(st)
    assert _consistent(st, "noor")[0]
    maintain.rollback(st, "noor")
    approve_all(st)
    ok, got = _consistent(st, "noor")
    assert ok and got[0] == 11, got


def test_vocabulary_ids_survive_a_rollback(tmp_path):
    st = make_store(tmp_path)
    full_learn(tmp_path, st, "noor", "noor")
    maintain.rollback(st, "noor", to=maintain._snapshots(Store(st), "noor")[0])
    approve_all(st)
    full_learn(tmp_path, st, "noor", "noor")
    vocab = load_yaml_text((st / "profiles/noor/vocabulary.yaml").read_text())
    assert [e["id"] for e in vocab["entries"]] == ["v-002"]


def test_rollback_of_a_shared_changed_text_is_relearned(tmp_path):
    st = make_store(tmp_path)
    _two_profiles(tmp_path, st)
    approve_all(st)
    path = sorted(e["path"] for e in Store(st).manifest["texts"].values())[0]
    f = tmp_path / "Writing" / path
    f.write_text(f.read_text().replace(" the ", " a ", 1))
    learn.start(st, targets=["noor"], profile="noor")
    learn.stage_texts(st)
    learn.do_measure(st)
    approve_all(st)
    maintain.rollback(st, "noor")
    approve_all(st)
    learn.start(st, targets=["noor"], profile="noor")
    learn.stage_texts(st)
    learn.do_measure(st)
    approve_all(st)
    cur = [e for e in Store(st).manifest["texts"].values() if e["path"] == path and e["status"] == "active"]
    assert len(cur) == 1 and set(cur[0]["profiles"]) == {"noor", "idris"}
    assert _consistent(st, "noor")[0] and _consistent(st, "idris")[0]


def test_rejected_examples_leave_no_passage_behind(tmp_path):
    st = make_store(tmp_path)
    basic_learn(tmp_path, st)
    c = learn.examples_sample(st, "noor", "en.essay")["candidates"][0]
    (tmp_path / "ex.yaml").write_text(yaml.safe_dump({"examples": [{"key": c["key"], "text": c["text"], "habit": "x"}]}))
    learn.examples_apply(st, "noor", "en.essay", tmp_path / "ex.yaml")
    approve_all(st, [i["id"] for i, _ in items(st) if i["kind"] == "example"])
    rej = (st / "profiles/noor/rejected.yaml").read_text()
    assert c["text"][:40] not in rej and "sha256:" in rej
    learn.start(st, targets=["noor"], profile="noor")
    learn.stage_texts(st)
    learn.do_measure(st)
    learn.examples_apply(st, "noor", "en.essay", tmp_path / "ex.yaml")
    assert not [i for i, _ in items(st) if i["kind"] == "example"]     # the rejected passage stays out
    stage.discard(st)


def test_rollback_of_forgetting_a_shared_text(tmp_path):
    st = make_store(tmp_path)
    _two_profiles(tmp_path, st)
    approve_all(st)
    key = sorted(Store(st).manifest["texts"])[0]
    path = Store(st).manifest["texts"][key]["path"]
    maintain.forget(st, path)
    approve_all(st)
    maintain.rollback(st, "noor")
    approve_all(st)
    e = Store(st).manifest["texts"][key]
    assert e["status"] == "active" and e["cached"] and list(e["profiles"]) == ["noor"]
    assert _consistent(st, "noor")[0]


def test_forget_for_one_profile_is_not_undone_by_the_next_learn(tmp_path):
    st = make_store(tmp_path)
    _two_profiles(tmp_path, st)
    approve_all(st)
    key = sorted(Store(st).manifest["texts"])[0]
    maintain.forget(st, Store(st).manifest["texts"][key]["path"], profile="idris")
    approve_all(st)
    learn.start(st, targets=["noor"], profile="noor")
    learn.stage_texts(st)
    assert not [i for i, _ in items(st) if i["kind"] == "ownership"]
    stage.discard(st)
    assert Store(st).manifest["texts"][key]["profiles"]["idris"]["ownership"] == "exclude"


def test_rejecting_one_of_two_new_profiles_keeps_the_other(tmp_path):
    st = make_store(tmp_path)
    _two_profiles(tmp_path, st, idris_ownership="assisted")
    approve_all(st, [i["id"] for i, pl in items(st) if i["kind"] == "profile" and pl["profile_yaml"]["name"] == "idris"])
    s = Store(st)
    assert len(s.manifest["texts"]) == 10 and all(list(e["profiles"]) == ["noor"] for e in s.manifest["texts"].values())
    assert _consistent(st, "noor")[0]
    assert not (st / "profiles" / "idris").exists()
