"""Edge cases found in the phase 2 review: decision dependencies, shared texts, segments, forget and
rollback corners, id reuse, recursive rules, redaction false positives and lock ownership."""
import glob
import json
import os
import shutil

import pytest
import yaml

import learn
import lock
import maintain
import measure
import pages
import redact
import stage
from common import load_yaml_text
from store import Store
from test_learn import FIX, answers, fake_rewrites, full_learn, lesson_file, make_store


def approve_all(st, reject=()):
    p = stage.Pending(Store(st))
    p.decide(reject=list(reject), all_decision="approved")
    return stage.commit(st)


def items(st):
    p = stage.Pending(Store(st))
    return [(i, p.payload(i["id"])) for i in p.plan["items"]]


def basic_learn(t, st, prof="noor", folder="noor", extra_answers=""):
    learn.start(st, targets=[folder], profile=prof)
    a = answers(t, prof, folder)
    if extra_answers:
        a.write_text(a.read_text() + extra_answers)
    learn.answer(st, a)
    learn.stage_texts(st)
    learn.do_measure(st)


def test_ids_are_never_reused_after_a_rejection(tmp_path):
    st = make_store(tmp_path)
    full_learn(tmp_path, st, "noor", "noor", reject_text="Ends on a plain statement")
    meta, _, les = pages.parse_slot_page((st / "profiles/noor/en.essay.md").read_text())
    rej = load_yaml_text((st / "profiles/noor/rejected.yaml").read_text())["entries"]
    rejected_id = next(e["rejects"] for e in rej if e["text"].startswith("Ends on"))
    assert meta["last_id"] >= int(rejected_id.split("-")[1])
    learn.start(st, targets=["noor"], profile="noor")
    learn.stage_texts(st)
    learn.do_measure(st)
    ks = [k for k, _ in learn.slot_texts(learn.Run(st), "noor", "en.essay")]
    f = tmp_path / "l2.yaml"
    f.write_text(yaml.safe_dump([{"section": "Stance", "text": "Takes the side of the practical person.",
                                  "evidence": ks[:3]}]))
    learn.lessons_apply(st, "noor", "en.essay", f)
    new_ids = [pl["lesson"]["id"] for i, pl in items(st) if i["kind"] == "lesson" and i["op"] == "add"]
    assert new_ids and rejected_id not in new_ids and all(x not in {y["id"] for y in les} for x in new_ids)
    stage.discard(st)


def test_next_is_clear_after_a_contrast_reuse(tmp_path):
    st = make_store(tmp_path)
    full_learn(tmp_path, st, "noor", "noor")
    shutil.copy(sorted(glob.glob(str(FIX / "synthetic-noor" / "[0-9]*.md")))[10], tmp_path / "Writing" / "noor")
    learn.start(st, targets=["noor"], profile="noor")
    learn.stage_texts(st)
    learn.do_measure(st)
    assert learn.contrast_sample(st, "noor", "en.essay")["reuse"]
    learn.lessons_apply(st, "noor", "en.essay", lesson_file(tmp_path, st, "noor", "en.essay"))
    ex = tmp_path / "ex.yaml"
    ex.write_text("examples: []\n")
    learn.examples_apply(st, "noor", "en.essay", ex)
    v = tmp_path / "v.yaml"
    v.write_text("[]\n")
    learn.vocab_apply(st, "noor", v)
    assert learn.next_step(st)["next"] == "model steps left: flavour noor/en"     # always asked (spec §34.3)
    fl = tmp_path / "fl.yaml"
    fl.write_text("markers: []\n")
    import flavour
    flavour.apply(st, "noor", "en", fl)
    assert learn.next_step(st)["next"].startswith("show the diff")
    stage.discard(st)


def test_rejecting_a_text_removes_it_from_fingerprint_and_examples(tmp_path):
    st = make_store(tmp_path)
    basic_learn(tmp_path, st)
    cs = learn.contrast_sample(st, "noor", "en.essay")
    learn.contrast_apply(st, "noor", "en.essay", fake_rewrites(cs))
    learn.lessons_apply(st, "noor", "en.essay", lesson_file(tmp_path, st, "noor", "en.essay"))
    c = learn.examples_sample(st, "noor", "en.essay")["candidates"][0]
    (tmp_path / "ex.yaml").write_text(yaml.safe_dump({"examples": [{"key": c["key"], "text": c["text"], "habit": "x"}]}))
    learn.examples_apply(st, "noor", "en.essay", tmp_path / "ex.yaml")
    rej = [i["id"] for i, pl in items(st) if i["kind"] == "corpus-text" and i.get("ref") == c["key"]]
    approve_all(st, rej)
    s = Store(st)
    assert c["key"] not in s.manifest["texts"]
    fp = json.loads((st / "profiles/noor/en.essay.json").read_text())
    active = sum(1 for e in s.manifest["texts"].values() if e["status"] == "active")
    assert fp["counts"]["texts"] == active == 9
    exf = st / "profiles/noor/en.essay.examples.md"
    assert not exf.exists() or all(e["source"] != c["key"] for e in pages.parse_examples(exf.read_text())[1])


def test_rejecting_a_new_profile_rejects_everything_that_needs_it(tmp_path):
    st = make_store(tmp_path)
    basic_learn(tmp_path, st)
    rej = [i["id"] for i, pl in items(st) if i["kind"] == "profile"]
    approve_all(st, rej)
    assert not (st / "profiles" / "noor" / "en.essay.json").exists()
    assert Store(st).manifest["texts"] == {}
    assert not (st / "sources.yaml").exists()


def test_segments_of_a_changed_file_are_superseded(tmp_path):
    st = make_store(tmp_path)
    nl = ("Vandaag heb ik de hele middag in de tuin gewerkt, omdat het eindelijk droog was en de grond niet meer zo "
          "zwaar aan mijn laarzen bleef plakken. Ik heb de bonen opgebonden, het onkruid tussen de uien weggehaald "
          "en de gieter drie keer gevuld bij de regenton achter de schuur.")
    f = tmp_path / "Writing" / "noor" / "50-mixed.md"
    base = (FIX / "synthetic-noor" / "02-lentil-soup-on-a-tuesday.md").read_text()
    f.write_text(base + "\n\n" + "\n\n".join([nl, nl.replace("Vandaag", "Gisteren"), nl.replace("middag", "ochtend"),
                                              nl.replace("bonen", "erwten")]) + "\n")
    learn.start(st, targets=["noor"], profile="noor")
    run = learn.Run(st)
    segs = [k for k, v in run.state["texts"].items() if "#" in k]
    assert segs
    learn.answer(st, answers(tmp_path, "noor", "noor"))
    learn.stage_texts(st)
    learn.do_measure(st)
    approve_all(st)
    f.write_text(base.replace("Tuesday", "Wednesday") + "\n")
    learn.start(st, targets=["noor"], profile="noor")
    assert learn.Run(st).state["unreachable"] == []
    learn.stage_texts(st)
    learn.do_measure(st)
    approve_all(st)
    e = Store(st).manifest["texts"][segs[0]]
    assert e["status"] == "superseded"


def test_reowning_a_forgotten_text_for_another_profile_does_not_revive_the_old_one(tmp_path):
    st = make_store(tmp_path)
    basic_learn(tmp_path, st)
    approve_all(st)
    s = Store(st)
    key = sorted(s.manifest["texts"])[0]
    path = s.manifest["texts"][key]["path"]
    maintain.forget(st, path)
    approve_all(st)
    (st / "profiles/other").mkdir()
    (st / "profiles/other/profile.yaml").write_text("schema_version: 1\nsubject: x\nconsent: self\n")
    maintain.forget(st, path, profile="other", ownership="own")
    approve_all(st)
    e = Store(st).manifest["texts"][key]
    assert list(e["profiles"]) == ["other"] and e["status"] == "active" and e["cached"]
    assert json.loads((st / "profiles/noor/en.essay.json").read_text())["counts"]["texts"] == 9


def test_changed_file_keeps_a_per_file_profile(tmp_path):
    st = make_store(tmp_path)
    learn.start(st, targets=["noor"], profile="noor")
    path = sorted(v["path"] for v in learn.Run(st).state["texts"].values())[0]
    a = answers(tmp_path, "noor", "noor")
    a.write_text(a.read_text() + "  - {name: acme, subject: house, consent: self}\n"
                 f"files:\n  - {{path: {path}, profile: acme, ownership: own}}\n")
    learn.answer(st, a)
    learn.stage_texts(st)
    learn.do_measure(st)
    approve_all(st)
    f = tmp_path / "Writing" / path
    f.write_text(f.read_text().replace(" the ", " a ", 1))
    out = learn.start(st, targets=["noor"], profile="noor")
    qs = out["questions"]["undecided"]
    assert any(q["profile"] == "acme" and q.get("default") == "own" for q in qs)
    stage.discard(st)


def test_rollback_of_one_profile_leaves_a_shared_text_alone(tmp_path):
    st = make_store(tmp_path)
    learn.start(st, targets=["noor"], profile="noor")
    a = answers(tmp_path, "noor", "noor")
    a.write_text(a.read_text().replace("profiles:", "  - {path: noor, profile: acme, ownership: own, facets: {type: essay}}\nprofiles:")
                 + "  - {name: acme, subject: house, consent: self}\n")
    learn.answer(st, a)
    learn.stage_texts(st)
    learn.do_measure(st)
    approve_all(st)
    path = sorted(e["path"] for e in Store(st).manifest["texts"].values())[0]
    f = tmp_path / "Writing" / path
    f.write_text(f.read_text().replace(" the ", " a ", 1))
    learn.start(st, targets=["noor"], profile="noor")
    learn.stage_texts(st)
    learn.do_measure(st)
    approve_all(st)
    acme_fp = (st / "profiles/acme/en.essay.json").read_text()

    def acme_view(s):
        return {k: (e["status"], e["cached"], e["profiles"]["acme"]) for k, e in s.manifest["texts"].items()
                if "acme" in e["profiles"]}
    before = acme_view(Store(st))
    maintain.rollback(st, "noor")
    approve_all(st)
    s = Store(st)
    assert (st / "profiles/acme/en.essay.json").read_text() == acme_fp
    assert acme_view(s) == before
    acme_now = next(x["fingerprint"] for x in measure.fingerprints(s, "acme") if x["fingerprint"]["slot"] == "en.essay")
    assert acme_now["counts"] == json.loads(acme_fp)["counts"]
    active_at_path = [k for k, e in s.manifest["texts"].items() if e["path"] == path and e["status"] == "active"]
    assert len(active_at_path) == 1


def test_cached_never_turns_true_without_its_text(tmp_path):
    st = make_store(tmp_path)
    basic_learn(tmp_path, st)
    approve_all(st)
    s = Store(st)
    key = sorted(s.manifest["texts"])[0]
    path = s.manifest["texts"][key]["path"]
    maintain.forget(st, path)
    approve_all(st)
    src = tmp_path / "Writing" / path
    saved = src.read_text()
    src.unlink()
    first_after = maintain._snapshots(Store(st), "noor")[-1]   # taken just before the forget
    maintain.rollback(st, "noor", to=first_after)
    approve_all(st)
    e = Store(st).manifest["texts"][key]
    assert e["status"] == "unreachable" and not e["cached"]
    src.write_text(saved)
    learn.start(st, targets=["noor"], profile="noor")
    learn.stage_texts(st)
    learn.do_measure(st)              # would raise on a cached entry without text
    approve_all(st)
    e = Store(st).manifest["texts"][key]
    assert e["status"] == "active" and e["cached"] and (st / "corpus" / f"{key}.txt").exists()


def test_first_learn_can_be_rolled_back_and_forget_drops_examples(tmp_path):
    st = make_store(tmp_path)
    full_learn(tmp_path, st, "noor", "noor")
    exm = pages.parse_examples((st / "profiles/noor/en.essay.examples.md").read_text())[1]
    src = exm[0]["source"]
    path = Store(st).manifest["texts"][src]["path"]
    maintain.forget(st, path)
    approve_all(st)
    after = pages.parse_examples((st / "profiles/noor/en.essay.examples.md").read_text())[1]
    assert all(e["source"] != src for e in after)
    first = maintain._snapshots(Store(st), "noor")[0]
    maintain.rollback(st, "noor", to=first)
    approve_all(st)
    s = Store(st)
    # everything the first learn added is gone from the ledger, so a later learn sees the texts as new
    assert s.manifest["texts"] == {}
    assert not list((st / "corpus").glob("*.txt"))
    assert not (st / "profiles/noor/en.essay.json").exists()


def test_atomic_proposals_cannot_be_split(tmp_path):
    st = make_store(tmp_path)
    basic_learn(tmp_path, st)
    approve_all(st)
    path = sorted(e["path"] for e in Store(st).manifest["texts"].values())[0]
    maintain.forget(st, path)
    first = items(st)[0][0]["id"]
    stage.Pending(Store(st)).decide(reject=[first], all_decision="approved")
    assert all(i["decision"] == "rejected" for i, _ in items(st))
    stage.commit(st)
    assert all(e["status"] == "active" for e in Store(st).manifest["texts"].values())


def test_recursive_false_is_honoured(tmp_path):
    st = make_store(tmp_path)
    (tmp_path / "Writing/noor/drafts").mkdir()
    shutil.move(str(tmp_path / "Writing/noor/02-lentil-soup-on-a-tuesday.md"), tmp_path / "Writing/noor/drafts/")
    learn.start(st, targets=["noor"], profile="noor")
    a = answers(tmp_path, "noor", "noor")
    a.write_text(a.read_text().replace("facets:", "recursive: false, facets:", 1))
    out = learn.answer(st, a)
    assert any("drafts" in q["path"] for q in out["questions"]["undecided"])
    stage.discard(st)


@pytest.mark.parametrize("text", ["In 1066 AD the", "a 3000 MB disk", "2019 SP was", "the 2024 NL election",
                                  "the 2024 EU Summit", "1999 US President", "2030 UN Goals"])
def test_postcode_pattern_leaves_ordinary_text(text):
    assert redact.redact(text)[0] == text


def test_postcode_and_contacts_are_redacted():
    out, _ = redact.redact("Write to Kerkstraat 12, 1012 AB Amsterdam, a.b@example.org or +31 6 12345678.")
    assert "1012" not in out and "@" not in out and "12345678" not in out


def test_another_live_run_blocks(tmp_path):
    st = make_store(tmp_path)
    learn.start(st, targets=["noor"], profile="noor")
    lock.release(str(st))
    lock.acquire(str(st), "forget")                       # someone else, live
    with pytest.raises(lock.Locked):
        learn.Run(st)


def test_a_large_slot_is_sampled_across_its_whole_period():
    """Found learning a blog of 214 posts: the lessons sample held only the oldest 66, because it filled
    up in date order. It is now spread evenly over the dates (design: a stratified sample)."""
    dated = [(f"k{i:03d}", "text") for i in range(214)]
    picked = learn.spread(dated, 300)
    assert len(picked) == 66 and picked[0] == dated[0] and picked[-1][0] >= "k210"
    assert learn.spread(dated[:10], 300) == dated[:10]
