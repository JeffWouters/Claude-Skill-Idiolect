"""Changes after evaluation run 1 (design: decision log): favoured phrases with measured rates,
vocabulary schema v2 with migrate.py, the kit's counts and order, and bunched habits in check."""
import pathlib
import shutil

import pytest

import check
import learn
import lock
import migrate
from common import StoreError, load_yaml_text, read_store_file
from store import Store
from test_learn import answers, make_store
from test_learn_edges import approve_all, items

ROOT = pathlib.Path(__file__).resolve().parent.parent
EXAMPLE = ROOT / "tests" / "example-store"

V1 = """schema_version: 1
entries:
  - {id: v-001, text: slow tools, kind: coinage, private: false, created: "2026-10-02"}
  - {id: v-002, text: to be fair, kind: keep, private: false, created: "2026-10-02"}
last_id: 2
"""


def learned_noor(tmp_path):
    st = make_store(tmp_path)
    learn.start(st, targets=["noor"], profile="noor")
    learn.answer(st, answers(tmp_path, "noor", "noor"))
    learn.stage_texts(st)
    learn.do_measure(st)
    return st


def test_an_older_file_stops_with_a_pointer_to_migrate(tmp_path):
    f = tmp_path / "vocabulary.yaml"
    f.write_text(V1)
    with pytest.raises(StoreError, match="migrate.py"):
        read_store_file(f, "vocabulary")


def test_migrate_upgrades_live_and_snapshot_copies_and_keeps_the_originals(tmp_path):
    st = learned_noor(tmp_path)
    approve_all(st)
    pdir = st / "profiles" / "noor"
    (pdir / "vocabulary.yaml").write_text(V1)
    snap = sorted((pdir / "snapshots").iterdir())[0]
    (snap / "vocabulary.yaml").write_text(V1)
    assert migrate.migrate(st, dry_run=True)["would_upgrade"] == [
        "profiles/noor/snapshots/" + snap.name + "/vocabulary.yaml", "profiles/noor/vocabulary.yaml"]
    out = migrate.migrate(st)
    live = read_store_file(pdir / "vocabulary.yaml", "vocabulary")
    phrase = [e for e in live["entries"] if e["text"] == "to be fair"][0]
    assert live["schema_version"] == 2 and phrase["kind"] == "phrase"
    assert set(phrase["rate"]) == {"per_1k", "texts", "of", "measured"} and phrase["rate"]["of"] > 0
    old_snap = read_store_file(snap / "vocabulary.yaml", "vocabulary")
    assert "rate" not in [e for e in old_snap["entries"] if e["text"] == "to be fair"][0]
    assert (st / out["backup"] / "profiles/noor/vocabulary.yaml").read_text() == V1
    assert "migrate" in (pdir / "changelog.md").read_text()
    assert not lock.read(str(st))[0]
    assert migrate.migrate(st) == {"upgraded": []}


def test_migrate_refuses_while_a_run_waits(tmp_path):
    st = learned_noor(tmp_path)
    approve_all(st)
    (st / "profiles/noor/vocabulary.yaml").write_text(V1)
    learn.start(st, targets=["noor"], profile="noor")
    lock.release(str(st))
    with pytest.raises(StoreError, match="pending"):
        migrate.migrate(st)
    assert not lock.read(str(st))[0]


def test_vocab_apply_measures_phrases_and_keeps_forms_unrated(tmp_path):
    st = learned_noor(tmp_path)
    v = tmp_path / "v.yaml"
    v.write_text("- {text: kitchen tap, kind: term}\n- {text: I think, kind: keep}\n")
    learn.vocab_apply(st, "noor", v)
    entries = {i["summary"].split(": ", 1)[1]: p["vocab"]["entry"] for i, p in items(st) if i["kind"] == "vocabulary"}
    assert "rate" not in entries["kitchen tap"]
    assert entries["I think"]["kind"] == "phrase" and entries["I think"]["rate"]["of"] >= 8
    approve_all(st)
    # a later learn re-measures an approved phrase whose rate changed
    vf = st / "profiles/noor/vocabulary.yaml"
    data = load_yaml_text(vf.read_text())
    for e in data["entries"]:
        if e["kind"] == "phrase":
            e["rate"]["per_1k"] = 99.0
    import yaml
    vf.write_text(yaml.safe_dump(data, sort_keys=False))
    learn.start(st, targets=["noor"], profile="noor")
    learn.stage_texts(st)
    learn.do_measure(st)
    empty = tmp_path / "none.yaml"
    empty.write_text("[]\n")
    learn.vocab_apply(st, "noor", empty)
    ups = [(i, p) for i, p in items(st) if i["kind"] == "vocabulary" and i["op"] == "modify"]
    assert len(ups) == 1 and ups[0][1]["vocab"]["entry"]["rate"]["per_1k"] != 99.0


def test_bunched_hedges_in_one_paragraph_are_flagged_and_an_even_spread_is_not():
    fp = {"hedges_per_1k": {"value": 4.0}, "semicolons_per_1k": {"value": 2.0}}
    stacked = ("Perhaps the meeting was, I think, rather long; it might have been shorter, and possibly it "
               "should have been, though perhaps nobody could quite say so, and it may well be that nobody "
               "wanted to. Arguably it did no harm.")
    b = check.bunched(stacked, "en", fp)
    assert b and b[0]["paragraph"] == 1 and b[0]["habit"] == "hedges_per_1k" and b[0]["count"] >= 3
    plain = ("The meeting ran for an hour. We covered the budget, the plan for spring and the new rota. "
             "Nobody raised anything else, so we stopped early and went back to work. It was, I think, "
             "a useful hour.")
    assert check.bunched(plain, "en", fp) == []


def test_favoured_phrases_over_the_whole_text():
    fp = {}
    phrases = [{"text": "to be fair", "kind": "phrase", "rate": {"per_1k": 0.5, "texts": 3, "of": 10, "measured": "x"}}]
    para = ("To be fair, the plan was sound. The team kept to it for most of the year and the work came in "
            "on time, which nobody had expected when the year began. ")
    text = para + "\n\n" + para.replace("To be fair", "And to be fair") + "\n\n" + para
    b = check.bunched(text, "en", fp, phrases)
    assert [x for x in b if x["paragraph"] == 0 and x["habit"] == "favoured phrases"]
    unrated = [{"text": "to be fair", "kind": "phrase"}]
    assert check.bunched(text, "en", fp, unrated) == []


def test_example_store_is_version_2():
    data = read_store_file(EXAMPLE / "profiles/sam/vocabulary.yaml", "vocabulary")
    assert data["schema_version"] == 2 and {e["kind"] for e in data["entries"]} == {"coinage", "term", "phrase"}


def test_lesson_evidence_says_out_of_how_many_sampled_texts(tmp_path):
    import kit
    from test_learn import lesson_file
    st = learned_noor(tmp_path)
    learn.lessons_sample(st, "noor", "en.essay")
    learn.lessons_apply(st, "noor", "en.essay", lesson_file(tmp_path, st, "noor", "en.essay"))
    summaries = [i["summary"] for i, _ in items(st) if i["kind"] == "lesson"]
    assert summaries and all(" of " in s.split("_(")[1] for s in summaries)
    x = kit.with_share({"section": "Tone", "evidence_raw": '3 of 12 texts; "q"'}, 40)
    assert (x["texts"], x["of"], x["default"]) == (3, 12, False)
    old = kit.with_share({"section": "Tone", "evidence_raw": '7 texts; "q"'}, 8)
    assert (old["texts"], old["of"], old["default"]) == (7, 8, True)


# ---------- fixes from the independent review of the run-1 changes ----------

def test_phrase_rates_count_only_approved_texts(tmp_path):
    st = learned_noor(tmp_path)
    v = tmp_path / "v.yaml"
    v.write_text("- {text: the, kind: phrase}\n")
    learn.vocab_apply(st, "noor", v)
    texts = [i["id"] for i, _ in items(st) if i["kind"] == "corpus-text"]
    approve_all(st, texts[:2])
    rate = [e for e in read_store_file(st / "profiles/noor/vocabulary.yaml", "vocabulary")["entries"]
            if e["text"] == "the"][0]["rate"]
    assert rate["of"] == len(texts) - 2


def test_curly_apostrophes_match_straight_ones():
    import measure
    rate = measure.phrase_rate("don't think", ["I don’t think so, and I don't think it matters. " * 20])
    assert rate["texts"] == 1 and rate["per_1k"] > 0
    assert len(measure.phrases_pattern(["don’t think"]).findall(measure.normalise_quotes("I don't think"))) == 1


def test_no_texts_means_no_rate_and_no_flag():
    import measure
    assert measure.phrase_rate("to be fair", []) is None
    zero = [{"text": "to be fair", "kind": "phrase", "rate": {"per_1k": 0.0, "texts": 0, "of": 0, "measured": "x"}}]
    para = "To be fair, the plan was sound and the work came in on time, which nobody had expected. "
    assert check.bunched(para + "\n\n" + para, "en", {}, zero) == []


def test_overlapping_phrases_count_once():
    phrases = [{"text": t, "kind": "phrase", "rate": {"per_1k": 0.01, "texts": 1, "of": 10, "measured": "x"}}
               for t in ("I think", "I think that")]
    b = check.bunched("I think that the plan was sound and we should keep it. " * 1, "en", {}, phrases)
    assert b == []


def test_bunches_are_numbered_as_the_reader_sees_them():
    fp = {"hedges_per_1k": {"value": 4.0}}
    stacked = ("Perhaps the meeting was, I think, rather long; it might have been shorter, and possibly it "
               "should have been, though perhaps nobody could quite say so, and it may well be that nobody "
               "wanted to. Arguably it did no harm.")
    b = check.bunched("# A heading\n\n" + stacked, "en", fp)
    assert b and b[0]["paragraph"] == 2


def test_the_same_hedges_spread_over_paragraphs_are_not_a_bunch():
    fp = {"hedges_per_1k": {"value": 4.0}}
    para = ("The meeting ran for an hour and perhaps that was right. We covered the budget, the plan for "
            "spring, the new rota and the question of who would open the building on the first Monday.")
    assert check.bunched("\n\n".join([para] * 4), "en", fp) == []


def test_poisson_tail_holds_for_large_expectations():
    assert check.poisson_tail(2000, 800) < 1e-6
    assert abs(check.poisson_tail(1, 2.0) - (1 - 2.718281828 ** -2)) < 1e-6


def test_a_failed_migration_writes_nothing(tmp_path):
    st = learned_noor(tmp_path)
    approve_all(st)
    pdir = st / "profiles" / "noor"
    (pdir / "vocabulary.yaml").write_text(V1)
    snap = sorted((pdir / "snapshots").iterdir())[0]
    (snap / "vocabulary.yaml").write_text(V1)
    cached = sorted((st / "corpus").glob("*.txt"))[0]
    cached.rename(cached.with_suffix(".gone"))
    before = (pdir / "changelog.md").read_text()
    with pytest.raises(StoreError):
        migrate.migrate(st)
    assert (snap / "vocabulary.yaml").read_text() == V1 and (pdir / "vocabulary.yaml").read_text() == V1
    assert (pdir / "changelog.md").read_text() == before and not lock.read(str(st))[0]


def test_migration_refuses_a_malformed_version_1_file(tmp_path):
    st = learned_noor(tmp_path)
    approve_all(st)
    (st / "profiles/noor/vocabulary.yaml").write_text("schema_version: 1\nentries:\n  - {id: v-001, kind: odd}\n")
    with pytest.raises(StoreError, match="not a valid version 1"):
        migrate.migrate(st)


def test_a_mirror_slot_counts_lessons_out_of_the_same_sample(tmp_path, monkeypatch):
    import kit
    import pages
    from test_learn import lesson_file
    monkeypatch.setattr(learn, "QUAL_CAP", 300)          # a sample smaller than the slot
    st = learned_noor(tmp_path)
    learn.lessons_sample(st, "noor", "en.essay")
    learn.lessons_apply(st, "noor", "en.essay", lesson_file(tmp_path, st, "noor", "en.essay"))
    approve_all(st)
    base = st / "profiles/noor"
    shares = {}
    for slot in ("en.essay", "en._"):
        _, _, lessons = pages.parse_slot_page((base / f"{slot}.md").read_text())
        shares[slot] = sorted((x["text"], kit.with_share(x, 10)["of"]) for x in lessons)
    assert shares["en.essay"] == shares["en._"]
    assert all(of < 10 for _, of in shares["en.essay"])


def test_a_lesson_seen_once_is_never_a_default():
    import kit
    x = kit.with_share({"section": "Seen once", "evidence_raw": "1 of 2 texts"}, 2)
    assert x["default"] is False


def test_check_report_carries_bunches_end_to_end(tmp_path):
    import shutil as sh
    st = tmp_path / "s"
    sh.copytree(EXAMPLE, st)
    stacked = ("Perhaps the meeting was, I think, rather long; it might have been shorter, and possibly it "
               "should have been, though perhaps nobody could quite say so, and it may well be that nobody "
               "wanted to. Arguably it did no harm, perhaps. ") * 3
    r = check.check(Store(st), stacked, "sam", {"type": "essay"})
    from common import check_schema
    check_schema("check-report", r)
    assert r.get("bunched") and "bunched:" in check.readable(r)
