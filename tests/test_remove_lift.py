"""Removing a learned item by id and lifting a rejection (spec §36)."""
import shutil

import pytest

import learn
import maintain
import pages
import rules
import stage
from common import StoreError, load_yaml_text, read_store_file
from store import Store
from test_flavour import approve, flavoured_store, proposal, start
from test_learn import full_learn, lesson_file, make_store, tree_hash


@pytest.fixture(scope="module")
def learned(tmp_path_factory):
    t = tmp_path_factory.mktemp("learned")
    st = make_store(t)
    full_learn(t, st, "noor", "noor")
    return st


@pytest.fixture
def st(learned, tmp_path):
    dst = tmp_path / "Store"
    shutil.copytree(learned, dst)
    shutil.copytree(learned.parent / "Writing", tmp_path / "Writing")
    return dst


def commit(st, reject=()):
    stage.Pending(Store(st)).decide(reject=list(reject), all_decision="approved")
    return stage.commit(st)


def lessons(st, slot="en.essay"):
    return {x["id"]: x for x in pages.parse_slot_page((st / "profiles/noor" / f"{slot}.md").read_text())[2]}


def rejected(st):
    f = st / "profiles/noor/rejected.yaml"
    return load_yaml_text(f.read_text())["entries"] if f.exists() else []


def snapshots(st):
    d = st / "profiles/noor/snapshots"
    return sorted(d.iterdir()) if d.exists() else []


def test_a_removed_lesson_is_gone_recorded_and_not_proposed_again(st, tmp_path):
    lid = next(i for i, x in lessons(st).items() if x["text"] == "Rarely hedges a claim.")
    n_snaps = len(snapshots(st))
    out = maintain.remove(st, "noor", [lid], slot="en.essay")
    assert out["proposed"] == 1
    assert lid in lessons(st)                                   # nothing changes before approval
    commit(st)
    assert lid not in lessons(st)
    rej = [e for e in rejected(st) if e.get("rejects") == lid]
    assert len(rej) == 1 and rej[0]["kind"] == "observed" and rej[0]["slot"] == "en.essay"
    assert len(snapshots(st)) == n_snaps + 1                    # it can be rolled back
    # a relearn with the same lessons does not bring it back
    learn.start(st, targets=["noor"], profile="noor")
    learn.stage_texts(st)
    learn.do_measure(st)
    learn.lessons_apply(st, "noor", "en.essay", lesson_file(tmp_path, st, "noor", "en.essay"))
    plan = stage.Pending(Store(st)).plan
    assert not any("Rarely hedges" in i["summary"] for i in plan["items"])
    stage.discard(st)


def test_rejecting_the_removal_changes_nothing(st):
    lid = next(iter(lessons(st)))
    before = tree_hash(st)
    maintain.remove(st, "noor", [lid], slot="en.essay")
    stage.Pending(Store(st)).decide(all_decision="rejected")
    stage.commit(st)
    assert tree_hash(st) == before


def test_examples_and_vocabulary_are_removed_and_recorded(st):
    _, exs = pages.parse_examples((st / "profiles/noor/en.essay.examples.md").read_text())
    eid = exs[0]["id"]
    vocab = read_store_file(st / "profiles/noor/vocabulary.yaml", "vocabulary")["entries"]
    vid = next(v["id"] for v in vocab if v["text"] == "kitchen tap")
    maintain.remove(st, "noor", [eid, vid])
    commit(st)
    _, exs2 = pages.parse_examples((st / "profiles/noor/en.essay.examples.md").read_text())
    assert eid not in {x["id"] for x in exs2}
    assert "kitchen tap" not in (st / "profiles/noor/vocabulary.yaml").read_text()
    kinds = {e["kind"]: e for e in rejected(st)}
    assert kinds["example"]["normalised"].startswith("sha256:")        # the passage itself is not kept
    assert kinds["vocabulary"]["rejects"] == vid and kinds["vocabulary"]["slot"] is None


def test_a_starter_rule_is_declined_and_a_writers_ruling_simply_goes(st):
    rules.defaults(st, "noor", categories=["punctuation"])
    commit(st)
    rules.add(st, "noor", "Never write about swans.", {"words": ["swan", "swans"]})
    commit(st)
    entries = read_store_file(st / "profiles/noor/rulings.yaml", "rulings")["entries"]
    starter = next(e for e in entries if (e.get("starter") or {}).get("id") == "s-001")
    own = next(e for e in entries if e["text"] == "Never write about swans.")
    maintain.remove(st, "noor", [starter["id"], own["id"]])
    commit(st)
    data = read_store_file(st / "profiles/noor/rulings.yaml", "rulings")
    assert {starter["id"], own["id"]}.isdisjoint({e["id"] for e in data["entries"]})
    assert [d["starter"] for d in data["declined"]] == ["s-001"]
    assert not any(e.get("rejects") in (starter["id"], own["id"]) for e in rejected(st))
    out = rules.defaults(st, "noor", categories=["punctuation"])
    assert "s-001" not in {p.get("starter") for p in out["proposed"]}
    if stage.Pending(Store(st)).exists():
        stage.discard(st)

    # and lifting the decline lets the starter set offer it again
    maintain.lift(st, "noor", ["s-001"])
    commit(st)
    assert "declined" not in read_store_file(st / "profiles/noor/rulings.yaml", "rulings")
    out = rules.defaults(st, "noor", categories=["punctuation"])
    assert len(out["proposed"]) >= 1
    stage.discard(st)


def test_lifting_a_rejected_lesson_lets_a_relearn_propose_it(st, tmp_path):
    lid = next(i for i, x in lessons(st).items() if x["text"] == "Rarely hedges a claim.")
    maintain.remove(st, "noor", [lid], slot="en.essay")
    commit(st)
    xid = next(e["id"] for e in rejected(st) if e.get("rejects") == lid)
    maintain.lift(st, "noor", [xid])
    commit(st)
    assert xid not in {e["id"] for e in rejected(st)}
    data = load_yaml_text((st / "profiles/noor/rejected.yaml").read_text())
    assert data["last_id"] >= int(xid.split("-")[1])                # x- ids are never reused
    learn.start(st, targets=["noor"], profile="noor")
    learn.stage_texts(st)
    learn.do_measure(st)
    learn.lessons_apply(st, "noor", "en.essay", lesson_file(tmp_path, st, "noor", "en.essay"))
    plan = stage.Pending(Store(st)).plan
    assert any("Rarely hedges" in i["summary"] and i["op"] == "add" for i in plan["items"])
    stage.discard(st)


def test_bad_ids_are_refused_and_leave_no_proposal(st):
    with pytest.raises(StoreError, match="not an id"):
        maintain.remove(st, "noor", ["x-001"])
    with pytest.raises(StoreError, match="has no lesson l-999"):
        maintain.remove(st, "noor", ["l-999"])
    with pytest.raises(StoreError, match="no profile"):
        maintain.remove(st, "nobody", ["l-001"])
    with pytest.raises(StoreError, match="not a rejection id"):
        maintain.lift(st, "noor", ["l-001"])
    with pytest.raises(StoreError, match="has no rejection x-999"):
        maintain.lift(st, "noor", ["x-999"])
    with pytest.raises(StoreError, match="has not declined"):
        maintain.lift(st, "noor", ["s-005"])
    assert not (st / ".state" / "pending").exists() and not (st / ".state" / "lock").exists()


def test_an_id_on_two_slot_pages_goes_from_both_unless_they_differ(st):
    a = lessons(st, "en.essay")
    same = next(i for i, x in a.items() if x["text"] == "Keeps most sentences very short.")
    assert lessons(st, "en._")[same]["text"] == a[same]["text"]
    diff = next(i for i, x in a.items() if x["text"] == "Rarely hedges a claim.")
    pooled = st / "profiles/noor/en._.md"
    pooled.write_text(pooled.read_text().replace("Rarely hedges a claim.", "Hedges almost nothing."))
    with pytest.raises(StoreError, match="--slot"):
        maintain.remove(st, "noor", [diff])
    assert not (st / ".state" / "pending").exists()
    maintain.remove(st, "noor", [same, diff], slot="en.essay")
    commit(st)
    assert same not in lessons(st, "en.essay") and diff not in lessons(st, "en.essay")
    assert same in lessons(st, "en._") and diff in lessons(st, "en._")      # --slot keeps it to one page
    maintain.remove(st, "noor", [same])                                        # no --slot: every page
    commit(st)
    assert same not in lessons(st, "en._")


def test_a_removed_flavour_marker_is_rejected_and_can_be_lifted(tmp_path):
    st = flavoured_store(tmp_path)
    start(tmp_path, st)
    flavour_file = proposal(tmp_path, st)
    import flavour
    flavour.apply(st, "noor", "en", flavour_file)
    approve(st)
    fl = load_yaml_text((st / "profiles/noor/en.flavour.yaml").read_text())
    fid = next(m["id"] for m in fl["markers"] if m.get("detector") == "else-opener")
    maintain.remove(st, "noor", [fid])
    approve(st)
    fl = load_yaml_text((st / "profiles/noor/en.flavour.yaml").read_text())
    assert fid not in {m["id"] for m in fl["markers"]}
    assert [(r["id"], r["detector"]) for r in fl["rejected"]] == [(fid, "else-opener")]
    # a relearn drops it as rejected
    start(tmp_path, st)
    out = flavour.apply(st, "noor", "en", flavour_file)
    assert "'Else,' to open a sentence" in out["dropped_as_rejected"]
    stage.discard(st)
    # lifted, it may come back
    maintain.lift(st, "noor", [fid])
    approve(st)
    assert load_yaml_text((st / "profiles/noor/en.flavour.yaml").read_text()).get("rejected", []) == []
    start(tmp_path, st)
    out = flavour.apply(st, "noor", "en", flavour_file)
    assert out["dropped_as_rejected"] == []
    stage.discard(st)


def test_the_cli_takes_repeated_ids(st, capsys):
    lid = next(iter(lessons(st)))
    maintain.main(["--store", str(st), "remove", "--profile", "noor", "--id", lid, "--slot", "en.essay"])
    assert stage.Pending(Store(st)).exists()
    stage.discard(st)


def test_status_for_one_profile_lists_the_rejections_with_their_ids(st):
    import status
    lid = next(iter(lessons(st)))
    maintain.remove(st, "noor", [lid], slot="en.essay")
    commit(st)
    xid = next(e["id"] for e in rejected(st) if e.get("rejects") == lid)
    s = status.status(Store(st), "noor")
    assert any(r.startswith(f"{xid} observed in en.essay") for r in s["profiles"][0]["rejected"])
    assert xid in status.readable(s)
