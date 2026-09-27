"""Rulings with tests and the optional starter set (spec §27): loading through an approved diff,
declined rules remembered, the writer's edits never overwritten, check failing a draft that breaks a
ruling, unless_writer_uses following the writer's own texts, the kit's note and the migration."""
import shutil

import pytest
import yaml

import check
import export
import kit
import migrate
import rules
import stage
from common import StoreError, check_schema, read_store_file
from store import Store
from test_learn import full_learn, make_store

PLAIN = """The river path was closed for most of the spring, so we walked the long way round through the
market and past the old mill. It took an hour more than it should have, and nobody minded much.

By the time we reached the bridge the light had gone soft and the water was high and brown. My
brother counted the swans. There were eleven, which he said was a record, though he had no way to
know. We stood there until the cold came up off the water and then we turned for home.

I have walked that path a hundred times since. It is open again now, and shorter, and I take it
most mornings before work. But I still think of the long way round as the right way, and of the
evening when we had nowhere to be and the swans were eleven. Some walks are for getting somewhere.
That one was not, and I am glad of it, and I would do it again tomorrow if the path closed.
"""


@pytest.fixture(scope="module")
def learned(tmp_path_factory):
    t = tmp_path_factory.mktemp("learned")
    st = make_store(t)
    full_learn(t, st, "noor", "noor")
    full_learn(t, st, "idris", "idris")
    return st


@pytest.fixture
def st(learned, tmp_path):
    dst = tmp_path / "Store"
    shutil.copytree(learned, dst)
    shutil.copytree(learned.parent / "Writing", tmp_path / "Writing")
    return dst


def items(st):
    p = stage.Pending(Store(st))
    return [(i, p.payload(i["id"])) for i in p.plan["items"]]


def commit(st, reject=()):
    stage.Pending(Store(st)).decide(reject=list(reject), all_decision="approved")
    return stage.commit(st)


def rulings(st, prof):
    return read_store_file(st / "profiles" / prof / "rulings.yaml", "rulings")


def run_check(st, prof, text):
    return check.check(Store(st), text, prof, {"type": "essay"})


def ruling_lines(report):
    return [x for x in report.get("flagged_lines", []) if x["lesson"].startswith("r-")]


def by_starter(st, prof):
    return {e["starter"]["id"]: e for e in rulings(st, prof)["entries"] if e.get("starter")}


def test_the_starter_set_is_valid_and_every_rule_is_a_valid_ruling():
    data = rules.starter("en")
    ids = [r["id"] for r in data["rules"]]
    assert ids == [f"s-{n:03d}" for n in range(1, len(ids) + 1)]
    entries = [{"id": f"r-{n:03d}", "text": r["text"], "slot": None, "lang": "en", "origin": "starter",
                "created": "2026-10-03", "personal_data": "none", "test": r["test"],
                "unless_writer_uses": r["unless_writer_uses"], "starter": {"id": r["id"], "version": data["version"]}}
               for n, r in enumerate(data["rules"], 1)]
    check_schema("rulings", {"schema_version": 2, "entries": entries})
    hard = {r["id"] for r in data["rules"] if not r["unless_writer_uses"]}
    assert hard == {"s-002", "s-003", "s-004", "s-005"}          # chatbot leftovers only
    with pytest.raises(StoreError, match="no starter set"):
        rules.starter("xx")


def test_each_starter_test_catches_its_example_and_leaves_plain_text_alone():
    samples = {"s-001": "It was late — too late.", "s-002": "I hope this helps with your plans.",
               "s-003": "Great question, and a hard one.", "s-004": "As of my last update the bridge was shut.",
               "s-005": "Here is the revised paragraph.", "s-006": "We delve into the record.",
               "s-007": "A robust plan.", "s-008": "It stands as a testament to her work.",
               "s-009": "A cottage nestled in the hills.", "s-010": "Experts say the river is rising.",
               "s-011": "The hall serves as a meeting place.", "s-012": "The town grew, highlighting the need for roads.",
               "s-013": "Let's dive in.", "s-014": "Let that sink in.", "s-015": "Don’t get me wrong, I like it.",
               "s-016": "It isn't about the money, it's about the time.", "s-017": "We left early in order to see it.",
               "s-018": "It rained. Moreover, it snowed.", "s-019": "It could potentially rain.",
               "s-020": "In conclusion, it rained.", "s-021": "We won \U0001F389",
               "s-022": "- **Note:** the path is shut."}
    data = rules.starter("en")
    assert set(samples) == {r["id"] for r in data["rules"]}
    for r in data["rules"]:
        pat = rules.compile_test(r["test"])
        assert rules.count(pat, samples[r["id"]]) >= 1, r["id"]
        assert rules.count(pat, PLAIN) == 0, r["id"]
    en_dash = rules.compile_test(data["rules"][0]["test"])
    assert rules.count(en_dash, "From 2019–2021 we lived there.") == 0      # a number range is fine
    assert rules.count(en_dash, "We lived there – for a while.") == 1


def test_defaults_are_proposed_approved_and_then_fail_a_draft_with_a_dash(st):
    assert run_check(st, "noor", PLAIN).get("flagged_lines") is None
    out = rules.defaults(st, "noor")
    assert len(out["proposed"]) == 22 and all(p["op"] == "add" for p in out["proposed"])
    assert all(i["decision"] == "pending" for i, _ in items(st))     # nothing changes before approval
    assert not (st / "profiles/noor/rulings.yaml").exists()
    commit(st)
    held = by_starter(st, "noor")
    assert len(held) == 22 and held["s-001"]["id"] == "r-001" and held["s-001"]["origin"] == "starter"
    assert run_check(st, "noor", PLAIN).get("flagged_lines") is None
    r = run_check(st, "noor", PLAIN.replace("round through the", "round — through the"))
    assert r["status"] == "fail"
    assert [x["lesson"] for x in ruling_lines(r)] == ["r-001"]
    assert "breaks 1 ruling (r-001)" in r["message"]
    assert "line 1: breaks ruling r-001" in check.readable(r)


def test_a_writer_who_uses_dashes_keeps_them_up_to_twice_their_rate(st):
    rules.defaults(st, "idris", categories=["punctuation"])
    commit(st)
    s = Store(st)
    rid = by_starter(st, "idris")["s-001"]["id"]
    rate = rules.writer_rates(s, "idris", "en.essay", rules.applicable(s, "idris", "en.essay"))[rid]
    assert rate > 0
    one = PLAIN.replace("round through the", "round — through the")
    assert ruling_lines(run_check(st, "idris", one)) == []                    # one dash: within their habit
    many = PLAIN.replace(",", " —")
    r = run_check(st, "idris", many)
    assert r["status"] == "fail" and {x["lesson"] for x in ruling_lines(r)} == {rid}
    assert "the writer's texts about" in ruling_lines(r)[0]["reason"]
    md = kit.markdown(kit.build(s, "idris", {"type": "essay"}))
    assert f"your texts do this about {rate:g} times per 1,000 words: never more" in md


def test_a_hard_rule_applies_whatever_the_writer_does(st):
    rules.defaults(st, "idris")
    commit(st)
    r = run_check(st, "idris", PLAIN + "\nI hope this helps.\n")
    assert r["status"] == "fail"
    assert [x["text"] for x in ruling_lines(r)] == ["I hope this helps."]


def test_a_rejected_starter_rule_is_remembered_and_a_rerun_proposes_nothing(st):
    rules.defaults(st, "noor")
    dash = [i["id"] for i, pl in items(st) if pl["ruling"]["entry"]["starter"]["id"] == "s-001"]
    commit(st, reject=dash)
    data = rulings(st, "noor")
    assert [d["starter"] for d in data["declined"]] == ["s-001"]
    assert "s-001" not in by_starter(st, "noor")
    assert data["last_id"] == 22                         # the declined rule's id is never reused
    assert ruling_lines(run_check(st, "noor", PLAIN.replace("round through", "round — through"))) == []
    out = rules.defaults(st, "noor")
    assert out["proposed"] == [] and not stage.Pending(Store(st)).exists()
    assert {s["why"] for s in out["skipped"]} == {"held unchanged", "declined (set version 1.0); unchanged since"}


def test_the_writers_edit_is_kept_and_a_changed_rule_in_a_new_set_version_is_a_modify(st, monkeypatch):
    rules.defaults(st, "noor")
    commit(st)
    f = st / "profiles/noor/rulings.yaml"
    data = yaml.safe_load(f.read_text())
    for e in data["entries"]:
        if e["starter"]["id"] == "s-006":
            e["text"] = "Never use delve."                   # the writer's own edit
            e["test"] = {"words": ["delve"]}
    f.write_text(yaml.safe_dump(data, allow_unicode=True))
    new = rules.starter("en")
    new["version"] = "1.1"
    for r in new["rules"]:
        if r["id"] in ("s-006", "s-007"):         # the set changes both; the writer had edited s-006
            r["test"] = {"words": r["test"]["words"] + ["paradigm"]}
    monkeypatch.setattr(rules, "starter", lambda lang="en": new)
    out = rules.defaults(st, "noor")
    held = by_starter(st, "noor")
    assert out["proposed"] == [{"id": held["s-007"]["id"], "starter": "s-007", "category": "vocabulary", "op": "modify"}]
    why = {s["starter"]: s["why"] for s in out["skipped"]}
    assert why["s-006"].startswith("edited by the writer")
    commit(st)
    held = by_starter(st, "noor")
    assert "paradigm" in held["s-007"]["test"]["words"] and held["s-007"]["starter"]["version"] == "1.1"
    assert held["s-006"]["text"] == "Never use delve."


def test_add_a_ruling_with_a_test_and_refuse_a_malformed_one(st):
    with pytest.raises(StoreError, match="not a valid regular expression"):
        rules.add(st, "noor", "Never write (", {"pattern": "("})
    assert not stage.Pending(Store(st)).exists()
    with pytest.raises(StoreError, match="needs a test"):
        rules.add(st, "noor", "Never use swans.", None, unless_writer_uses=True)
    out = rules.add(st, "noor", "Never write about swans.", {"words": ["swan", "swans"]})
    commit(st)
    assert out["proposed"] == "r-001"
    r = run_check(st, "noor", PLAIN)
    assert r["status"] == "fail" and len(ruling_lines(r)) == 2        # two lines mention swans
    # a ruling added by hand with a broken pattern stops the next run with a message
    data = yaml.safe_load((st / "profiles/noor/rulings.yaml").read_text())
    data["entries"][0]["test"] = {"pattern": "[unclosed"}
    (st / "profiles/noor/rulings.yaml").write_text(yaml.safe_dump(data))
    with pytest.raises(StoreError, match="fix or remove it in rulings.yaml"):
        run_check(st, "noor", PLAIN)


def test_lang_and_slot_limit_where_a_ruling_applies_and_rulings_are_inherited(st):
    base = {"origin": "stated", "created": "2026-10-03", "personal_data": "none", "test": {"words": ["swans"]}}
    (st / "profiles/noor/rulings.yaml").write_text(yaml.safe_dump({"schema_version": 2, "entries": [
        {"id": "r-001", "text": "Nooit zwanen.", "slot": None, "lang": "nl", **base},
        {"id": "r-002", "text": "No swans in mail.", "slot": "en.email", **base},
        {"id": "r-003", "text": "No swans.", "slot": None, **base}]}))
    s = Store(st)
    assert [r["id"] for r in rules.applicable(s, "noor", "en.essay")] == ["r-003"]
    child = st / "profiles/kid"
    child.mkdir()
    (child / "profile.yaml").write_text("schema_version: 1\nsubject: c\nconsent: self\nextends: noor\n")
    shutil.copy(st / "profiles/noor/en.essay.json", child / "en.essay.json")
    fp = read_store_file(child / "en.essay.json", "fingerprint")
    import json
    fp["profile"] = "kid"
    (child / "en.essay.json").write_text(json.dumps(fp))
    r = check.check(Store(st), PLAIN, "kid", {"type": "essay"})
    assert r["profile"] == "kid" and {x["lesson"] for x in ruling_lines(r)} == {"r-003"}


def test_export_carries_the_rulings_with_the_writers_rate(st):
    rules.defaults(st, "idris", categories=["punctuation"])
    commit(st)
    prompt = export.build(Store(st), "idris", {"type": "essay"})["prompt"]
    assert "Never use an em dash" in prompt and "the writer's texts do this about" in prompt


def test_migrate_upgrades_a_version_1_rulings_file_and_keeps_the_original(st):
    f = st / "profiles/noor/rulings.yaml"
    f.write_text("schema_version: 1\nentries:\n  - {id: r-001, text: Never use semicolons., slot: null, "
                 "origin: stated, created: '2026-10-02', personal_data: none}\n")
    with pytest.raises(StoreError, match="migrate.py"):
        read_store_file(f, "rulings")
    out = migrate.migrate(st)
    assert "profiles/noor/rulings.yaml" in out["upgraded"]
    assert rulings(st, "noor")["schema_version"] == 2
    assert "schema_version: 1" in (st / out["backup"] / "profiles/noor/rulings.yaml").read_text()


def test_a_declined_rule_returns_only_when_a_later_set_changes_it(st, monkeypatch):
    rules.defaults(st, "noor", categories=["punctuation", "decoration"])
    commit(st, reject=[i["id"] for i, pl in items(st) if pl["ruling"]["entry"]["starter"]["id"] == "s-001"])
    assert rulings(st, "noor")["declined"][0]["digest"] == rules.digest(rules.starter("en")["rules"][0])
    new = rules.starter("en")
    new["version"] = "1.1"
    monkeypatch.setattr(rules, "starter", lambda lang="en": new)
    assert rules.defaults(st, "noor", categories=["punctuation"])["proposed"] == []   # a new version alone: no
    new["rules"][0]["text"] += " Brackets are fine."
    out = rules.defaults(st, "noor", categories=["punctuation"])
    assert [p["starter"] for p in out["proposed"]] == ["s-001"] and out["proposed"][0]["op"] == "add"
    assert out["proposed"][0]["id"] == "r-004"          # r-001 was the declined one; ids are never reused
