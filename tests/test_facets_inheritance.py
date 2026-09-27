"""Phase 5 exit, second half: a store migrated with a new facet resolves correctly (spec §12.7)."""
import json

import pytest
import yaml

import check
import kit
import learn
import maintain
import migrate
import resolve
import stage
from common import StoreError
from store import Store
from test_learn import full_learn, make_store
from test_learn_edit import run_pair


def test_a_new_facet_is_appended_everywhere_and_the_store_still_resolves(tmp_path):
    st = make_store(tmp_path)
    full_learn(tmp_path, st, "noor", "noor", reject_text="Opens on a concrete object")
    run_pair(tmp_path, st, 1)
    run_pair(tmp_path, st, 2)
    before_fp = json.loads((st / "profiles" / "noor" / "en.essay.json").read_text())
    dry = migrate.add_facet(st, "channel", dry_run=True)
    assert "profiles/noor/en.essay.json" in dry["would_change"]
    assert (st / "profiles" / "noor" / "en.essay.json").exists()          # a dry run writes nothing
    out = migrate.add_facet(st, "channel")
    s = Store(st)
    assert s.facets == ["lang", "type", "channel"]
    assert all(e["facets"]["channel"] == "_" for e in s.manifest["texts"].values())
    pdir = st / "profiles" / "noor"
    names = {f.name for f in pdir.iterdir() if f.is_file()}
    assert {"en.essay._.json", "en.essay._.md", "en.essay._.examples.md", "en.essay._.never.md",
            "en.essay._.edits.md", "en._._.json"} <= names
    assert not {"en.essay.json", "en.essay.md", "en.essay.edits.md"} & names
    fp = json.loads((pdir / "en.essay._.json").read_text())
    assert fp["slot"] == "en.essay._" and fp["metrics"] == before_fp["metrics"]
    assert "slot: en.essay._\n" in (pdir / "en.essay._.edits.md").read_text()
    pair = yaml.safe_load((pdir / "edits" / "p-001" / "pair.yaml").read_text())
    assert pair["slot"] == "en.essay._"
    rej = yaml.safe_load((pdir / "rejected.yaml").read_text())
    assert all(e["slot"] in (None, "en.essay._", "en._._") for e in rej["entries"])
    assert "new facet channel" in (pdir / "changelog.md").read_text()
    assert (st / out["backup"] / "profiles" / "noor" / "en.essay.json").exists()
    # resolution: a request with the new facet generalises to the old texts' slot
    assert resolve.resolve(s, "noor", {"type": "essay", "channel": "linkedin"})[:2] == ("noor", "en.essay._")
    assert resolve.resolve(s, "noor", {"type": "essay"})[:2] == ("noor", "en.essay._")
    assert resolve.resolve(s, "noor", {"type": "email", "channel": "x"})[:2] == ("noor", "en._._")
    k = kit.build(s, "noor", {"type": "essay", "channel": "linkedin"}, "An essay about a kitchen")
    assert k["slot"] == "en.essay._" and k["edit_lessons"] and k["targets"]
    r = check.check(s, (st.parent / "Writing" / "noor" / sorted(p.name for p in (st.parent / "Writing" / "noor").iterdir())[0]).read_text(),
                    "noor", {"type": "essay", "channel": "linkedin"})
    assert r["slot"] == "en.essay._" and r["status"] in ("pass", "low_confidence", "fail")
    # snapshots were upgraded too: rolling back restores files the migrated store can read
    snap = sorted((pdir / "snapshots").iterdir())[-1]
    assert (snap / "en.essay._.json").exists() and not (snap / "en.essay.json").exists()
    ents = json.loads((snap / "manifest-entries.json").read_text())["texts"]
    assert all(e["facets"]["channel"] == "_" for e in ents.values())
    maintain.rollback(st, "noor")
    stage.Pending(Store(st)).decide(all_decision="approved")
    stage.commit(st)
    assert resolve.resolve(Store(st), "noor", {"type": "essay"})[:2] == ("noor", "en.essay._")
    # later learns work on the new key; a second run of the same facet is refused
    learn.start(st, targets=["noor"], profile="noor")
    stage.discard(st)
    with pytest.raises(StoreError, match="already"):
        migrate.add_facet(st, "channel")


def test_adding_a_facet_waits_for_a_pending_run(tmp_path):
    st = make_store(tmp_path)
    full_learn(tmp_path, st, "noor", "noor")
    learn.start(st, targets=["noor"], profile="noor")
    with pytest.raises(StoreError):
        migrate.add_facet(st, "channel")
    stage.discard(st)
    with pytest.raises(StoreError, match="facet name"):
        migrate.add_facet(st, "Channel!")


def test_rulings_inherited_from_a_profile_not_the_writers_own_are_marked(tmp_path):
    import status
    from common import dump_yaml
    st = make_store(tmp_path)
    full_learn(tmp_path, st, "noor", "noor")
    house = st / "profiles" / "house"
    house.mkdir()
    (house / "profile.yaml").write_text(dump_yaml({"schema_version": 1, "subject": "Acme house style",
                                                   "consent": "authorised by Acme on 2026-10-02"}))
    (house / "rulings.yaml").write_text(dump_yaml({"schema_version": 2, "last_id": 1, "entries": [
        {"id": "r-001", "text": "Never use exclamation marks.", "slot": None, "origin": "stated",
         "created": "2026-10-02", "personal_data": "none"}]}))
    py = st / "profiles" / "noor" / "profile.yaml"
    data = yaml.safe_load(py.read_text())
    data["consent"] = "self"
    data["extends"] = "house"
    py.write_text(dump_yaml(data))
    s = Store(st)
    assert resolve.foreign_rulings(s, "noor") == [{"profile": "house", "id": "r-001", "text": "Never use exclamation marks."}]
    p = next(x for x in status.status(s)["profiles"] if x["name"] == "noor")
    assert p["inherited_rulings"] == ["house:r-001 Never use exclamation marks. [from a profile that is not the writer's own]"]
    learn.start(st, targets=["noor"], profile="noor")
    d = stage.diff(Store(st), stage.Pending(Store(st)))
    assert "inherits ruling house:r-001" in d and "not the writer's own profile" in d
    stage.discard(st)
    # once house's consent says self (the writer's own house style), nothing is marked
    hp = yaml.safe_load((house / "profile.yaml").read_text())
    hp["consent"] = "self"
    (house / "profile.yaml").write_text(dump_yaml(hp))
    assert resolve.foreign_rulings(Store(st), "noor") == []
