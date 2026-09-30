"""A web text keeps its address and can be forgotten by it; the ledger's version 2 and its migration
(spec §36.7)."""
import json

import pytest

import connector
import maintain
import migrate
import stage
from common import StoreError, read_store_file
from store import Store
from test_learn import full_learn, make_store
from test_web_connector import essays


def commit(st):
    stage.Pending(Store(st)).decide(all_decision="approved")
    return stage.commit(st)


def texts(st):
    return Store(st).manifest["texts"]


@pytest.fixture
def web_store(tmp_path):
    st = make_store(tmp_path)
    connector.start(st, "guest", "en", "essay", subject="A guest writer", consent="agreed by mail on 2026-09-27")
    for i, text in enumerate(essays(3, start=0)):
        f = tmp_path / f"p{i}.txt"
        f.write_text(text)
        if i == 0:
            connector.add(st, f, "web", "own", url="https://www.example.com/posts/first/")
        else:
            connector.add(st, f, "web", "own", note=f"https://example.com/posts/{i}")   # a note that is an address
    commit(st)
    return st


def test_web_texts_keep_their_address(web_store):
    urls = sorted(e.get("url") for e in texts(web_store).values())
    assert urls == ["https://example.com/posts/1", "https://example.com/posts/2",
                    "https://www.example.com/posts/first/"]
    assert json.loads((web_store / "corpus/manifest.json").read_text())["schema_version"] == 2


@pytest.mark.parametrize("address", ["https://www.example.com/posts/first/", "http://example.com/posts/first",
                                     "https://EXAMPLE.com/posts/first#top"])
def test_forget_by_address_finds_the_page_however_it_is_written(web_store, address):
    key = next(k for k, e in texts(web_store).items() if e["url"].endswith("first/"))
    maintain.forget(web_store, address)
    commit(web_store)
    e = texts(web_store)[key]
    assert e["status"] == "forgotten" and not e["cached"]
    assert not (web_store / "corpus" / f"{key}.txt").exists()
    assert sum(1 for e in texts(web_store).values() if e["status"] == "active") == 2


def test_an_unknown_address_is_refused(web_store):
    with pytest.raises(StoreError, match="no manifest entry for https://example.com/nothing"):
        maintain.forget(web_store, "https://example.com/nothing")
    assert not (web_store / ".state" / "pending").exists()


def test_only_a_web_text_has_an_address(tmp_path):
    st = make_store(tmp_path)
    connector.start(st, "guest", "en", "essay", subject="A guest writer", consent="agreed by mail")
    f = tmp_path / "p.txt"
    f.write_text(essays(1, start=0)[0])
    with pytest.raises(StoreError, match="only a web text"):
        connector.add(st, f, "mail", "own", url="https://example.com/x")
    with pytest.raises(StoreError, match="not a web address"):
        connector.add(st, f, "web", "own", url="example.com/x")
    out = connector.add(st, f, "mail", "own", note="https://example.com/x")        # a mail's note stays a note
    stage.Pending(Store(st)).decide(all_decision="approved")
    stage.commit(st)
    assert "url" not in texts(st)[out["key"]]


def test_migrate_upgrades_the_ledger_and_its_snapshot_copies(tmp_path):
    st = make_store(tmp_path)
    full_learn(tmp_path, st, "noor", "noor")
    mp = st / "corpus/manifest.json"
    snap = sorted((st / "profiles/noor/snapshots").iterdir())[0] / "manifest-entries.json"
    for f in (mp, snap):
        data = json.loads(f.read_text())
        data["schema_version"] = 1
        f.write_text(json.dumps(data, indent=2) + "\n")
    v1 = mp.read_text()
    with pytest.raises(StoreError, match="migrate.py"):
        Store(st)
    assert migrate.migrate(st, dry_run=True)["would_upgrade"] == [
        "corpus/manifest.json", str(snap.relative_to(st))]
    out = migrate.migrate(st)
    assert read_store_file(mp, "manifest")["schema_version"] == 2
    assert read_store_file(snap, "manifest-entries")["schema_version"] == 2
    assert (st / out["backup"] / "corpus/manifest.json").read_text() == v1
    assert json.loads(mp.read_text())["texts"] == json.loads(v1)["texts"]
    assert migrate.migrate(st) == {"upgraded": []}
    Store(st)
