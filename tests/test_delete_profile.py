"""Deleting a whole profile (spec §35)."""
import json

import pytest

import maintain
import stage
from common import StoreError, load_yaml_text
from store import Store
from test_learn import full_learn, make_store, tree_hash


@pytest.fixture
def two(tmp_path):
    st = make_store(tmp_path)
    full_learn(tmp_path, st, "noor", "noor")
    full_learn(tmp_path, st, "idris", "idris")
    return st


def records(st, prof):
    texts = json.loads((st / "corpus" / "manifest.json").read_text())["texts"]
    return {k: e for k, e in texts.items() if prof in e["profiles"]}


def commit_all(st):
    stage.Pending(Store(st)).decide(all_decision="approved")
    return stage.commit(st)


def test_delete_removes_the_profile_and_only_its_texts(two):
    st = two
    noor_before = tree_hash(st / "profiles" / "noor")
    idris_keys = list(records(st, "idris"))
    assert idris_keys
    out = maintain.delete(st, "idris")
    assert out["texts_removed"] == len(idris_keys) and out["texts_shared"] == 0
    commit_all(st)
    assert not (st / "profiles" / "idris").exists()
    assert records(st, "idris") == {}
    texts = json.loads((st / "corpus" / "manifest.json").read_text())["texts"]
    assert not any(k in texts for k in idris_keys)          # removed from the ledger, not forgotten
    for k in idris_keys:
        assert not (st / "corpus" / f"{k.replace('#', '-')}.txt").exists()
    rules = load_yaml_text((st / "sources.yaml").read_text())["sources"]
    assert rules and all(r["profile"] != "idris" for r in rules)
    assert tree_hash(st / "profiles" / "noor") == noor_before     # no snapshot or changelog for noor
    assert not (st / ".state" / "pending").exists()


def test_a_text_another_profile_owns_is_kept(two):
    st = two
    key = next(iter(records(st, "idris")))
    maintain.forget(st, key, profile="noor", ownership="own")
    commit_all(st)
    out = maintain.delete(st, "idris")
    assert out["texts_shared"] == 1
    commit_all(st)
    e = json.loads((st / "corpus" / "manifest.json").read_text())["texts"][key]
    assert list(e["profiles"]) == ["noor"] and e["cached"]
    assert (st / "corpus" / f"{key.replace('#', '-')}.txt").exists()


def test_the_default_profile_and_a_parent_are_refused(two):
    st = two
    with pytest.raises(StoreError, match="default_profile"):
        maintain.delete(st, "noor")
    py = st / "profiles" / "noor" / "profile.yaml"
    py.write_text(py.read_text() + "extends: idris\n")
    with pytest.raises(StoreError, match="extend"):
        maintain.delete(st, "idris")
    with pytest.raises(StoreError, match="no profile"):
        maintain.delete(st, "nobody")
    assert not (st / ".state" / "pending").exists()        # a refusal leaves no proposal behind


def test_rejecting_the_proposal_changes_nothing(two):
    st = two
    before = tree_hash(st)
    maintain.delete(st, "idris")
    stage.Pending(Store(st)).decide(all_decision="rejected")
    stage.commit(st)
    assert (st / "profiles" / "idris" / "profile.yaml").exists()
    after = tree_hash(st)
    assert after == before


def test_kept_drafts_and_published_sources_go_with_the_profile(two, tmp_path):
    import published
    st = two
    published.keep_drafts(st, True)
    for prof in ("noor", "idris"):
        d = tmp_path / f"draft-{prof}.md"
        d.write_text(f"A kept draft for {prof}, long enough to be a draft of some kind.\n")
        published.keep(st, d, prof, "en.essay", "write")
        folder = tmp_path / f"pub-{prof}"
        folder.mkdir()
        published.add_source(st, prof, folder=str(folder))
    idris_draft = [e["file"] for e in json.loads((st / "drafts" / "index.json").read_text())["entries"]
                   if e["profile"] == "idris"]
    maintain.delete(st, "idris")
    commit_all(st)
    idx = json.loads((st / "drafts" / "index.json").read_text())
    assert [e["profile"] for e in idx["entries"]] == ["noor"]
    assert not (st / "drafts" / idris_draft[0]).exists()
    pub = load_yaml_text((st / "publish.yaml").read_text())
    assert [s["profile"] for s in pub["sources"]] == ["noor"]
