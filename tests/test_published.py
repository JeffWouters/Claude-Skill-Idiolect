"""Learning from what the writer publishes (spec §33): settings, kept drafts, the scan that matches
published texts to them, the edit queue feeding learn-edit, expiry, and the scan's refusal while a run
holds the lock."""
import datetime as dt
import glob
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import time

import pytest
import yaml

import learn_edit
import lock
import published
import stage
from common import StoreError, read_store_file, utcnow
from store import Store
from test_learn import FIX, full_learn, make_store

ROOT = pathlib.Path(__file__).resolve().parent.parent
PAIRS = ROOT / "evals" / "edit-pairs"


def body(f):
    return re.sub(r"^---.*?---\n", "", pathlib.Path(f).read_text(encoding="utf-8"), flags=re.S)


@pytest.fixture(scope="module")
def learned(tmp_path_factory):
    t = tmp_path_factory.mktemp("pub")
    st = make_store(t)
    full_learn(t, st, "noor", "noor")
    return st


@pytest.fixture
def st(learned, tmp_path):
    dst = tmp_path / "Store"
    shutil.copytree(learned, dst)
    shutil.copytree(learned.parent / "Writing", tmp_path / "Writing")
    return dst


def keep_pair_draft(st, tmp_path, n=1, when=None):
    f = tmp_path / f"draft-{n}.md"
    f.write_text((PAIRS / f"pair-{n:02d}" / "draft.md").read_text())
    return published.keep(st, f, "noor", "en.essay", "write", now=when)


def test_settings_add_and_remove_sources_and_refuse_bad_ones(st, tmp_path):
    pubdir = tmp_path / "Published"
    pubdir.mkdir()
    assert published.show(st)["sources"] == []
    out = published.add_source(st, "noor", folder=str(pubdir), type_="essay")
    assert out["added"] == "pub-001"
    assert published.add_source(st, "noor", feed="https://example.com/feed.xml")["added"] == "pub-002"
    assert published.add_source(st, "noor", folder=str(pubdir))["added"] is None          # already there
    for kwargs, msg in (({"folder": str(pubdir), "feed": "https://x.org/f"}, "either --folder or --feed"),
                        ({}, "either --folder or --feed"),
                        ({"folder": str(tmp_path / "nowhere")}, "no folder"),
                        ({"folder": str(st / "profiles")}, "cannot be inside the store")):
        with pytest.raises(StoreError, match=msg):
            published.add_source(st, "noor", **kwargs)
    with pytest.raises(StoreError, match="no profile ghost"):
        published.add_source(st, "ghost", folder=str(pubdir))
    published.remove_source(st, "pub-002")
    assert [s["id"] for s in read_store_file(st / "publish.yaml", "publish")["sources"]] == ["pub-001"]
    with pytest.raises(StoreError, match="no source pub-009"):
        published.remove_source(st, "pub-009")


def test_drafts_are_kept_only_when_asked(st, tmp_path):
    assert keep_pair_draft(st, tmp_path)["kept"] is None
    assert not (st / "drafts").exists()
    published.keep_drafts(st, True)
    assert keep_pair_draft(st, tmp_path)["kept"] == "dr-001"
    assert keep_pair_draft(st, tmp_path, 2)["kept"] == "dr-002"
    idx = read_store_file(st / "drafts" / "index.json", "drafts")
    assert [(e["id"], e["status"], e["slot"]) for e in idx["entries"]] == [("dr-001", "open", "en.essay"),
                                                                           ("dr-002", "open", "en.essay")]
    assert (st / "drafts" / "dr-001.md").read_text().startswith((PAIRS / "pair-01" / "draft.md").read_text()[:40])


def test_a_published_edit_of_a_kept_draft_is_queued_and_other_texts_are_listed(st, tmp_path):
    pubdir = tmp_path / "Published"
    pubdir.mkdir()
    published.add_source(st, "noor", folder=str(pubdir), type_="essay")
    published.keep_drafts(st, True)
    keep_pair_draft(st, tmp_path, 1)
    keep_pair_draft(st, tmp_path, 2)
    (pubdir / "2026-10-04-final.md").write_text("---\ntitle: The final\n---\n\n" + (PAIRS / "pair-01" / "final.md").read_text())
    (pubdir / "unrelated.md").write_text(body(sorted(glob.glob(str(FIX / "synthetic-noor" / "[0-9]*.md")))[11]))
    (pubdir / "short.md").write_text("A short note. Nothing more to say here.\n")
    (pubdir / ".obsidian").mkdir()
    (pubdir / ".obsidian" / "workspace.md").write_text("ignored " * 200)
    out = published.scan(st)
    assert [(m["queue"], m["draft"]) for m in out["matched"]] == [("q-001", "dr-001")]
    assert out["matched"][0]["share"] >= 0.9
    assert [pathlib.Path(u["source"]).name for u in out["unmatched"]] == ["unrelated.md"]
    assert out["unmatched"][0]["best_share"] < published.MATCH
    assert [pathlib.Path(s["source"]).name for s in out["skipped"]] == ["short.md"]
    assert out["queue"] == 1 and "learn-edit" in out["next"]
    idx = {e["id"]: e for e in read_store_file(st / "drafts" / "index.json", "drafts")["entries"]}
    assert idx["dr-001"]["status"] == "matched" and idx["dr-001"]["matched"] == "q-001"
    assert idx["dr-002"]["status"] == "open"
    item = published.queue(st)["waiting"][0]
    assert item["draft_file"] == "drafts/dr-001.md" and (st / item["final_file"]).exists()
    # a second scan looks only at files changed since the last one
    again = published.scan(st, now=utcnow() + dt.timedelta(minutes=1))
    assert again["matched"] == [] and again["unmatched"] == [] and again["queue"] == 1


def test_the_queue_feeds_learn_edit_and_is_then_moved_to_done(st, tmp_path):
    pubdir = tmp_path / "Published"
    pubdir.mkdir()
    published.add_source(st, "noor", folder=str(pubdir), type_="essay")
    published.keep_drafts(st, True)
    keep_pair_draft(st, tmp_path, 1)
    (pubdir / "final.md").write_text((PAIRS / "pair-01" / "final.md").read_text())
    published.scan(st)
    item = published.queue(st)["waiting"][0]
    out = learn_edit.start(st, st / item["draft_file"], st / item["final_file"], profile="noor", type_="essay")
    assert out["slot"] == "en.essay" and out["changes"]
    kinds = tmp_path / "kinds.yaml"
    kinds.write_text(yaml.safe_dump({"changes": {c["id"]: "other" for c in out["changes"]}}))
    learn_edit.kinds(st, kinds)
    stage.Pending(Store(st)).decide(all_decision="approved")
    stage.commit(st)
    assert published.done(st, item["id"]) == {"id": "q-001", "status": "done"}
    assert published.queue(st)["waiting"] == []
    done = st / ".state" / "edit-queue" / "done"
    assert (done / "q-001.json").exists() and (done / "q-001.final.md").exists()
    assert read_store_file(done / "q-001.json", "edit-queue")["status"] == "done"
    with pytest.raises(StoreError, match="no queue item q-001"):
        published.done(st, "q-001")


def test_a_feed_is_read_through_the_web_fetcher(st, tmp_path):
    published.add_source(st, "noor", feed="https://example.com/feed.xml", type_="essay")
    published.keep_drafts(st, True)
    keep_pair_draft(st, tmp_path, 3)

    def fake_fetch(url, max_pages, out):
        out = pathlib.Path(out)
        (out / "001.txt").write_text((PAIRS / "pair-03" / "final.md").read_text())
        (out / "index.json").write_text(json.dumps([
            {"url": "https://example.com/p/1", "date": "2026-10-01", "words": 260, "file": str(out / "001.txt")},
            {"url": "https://example.com/p/2", "date": "2026-10-01", "words": 40, "skipped": "only 40 words"}]))
    out = published.scan(st, fetch=fake_fetch)
    assert [(m["source"], m["draft"]) for m in out["matched"]] == [("https://example.com/p/1", "dr-001")]


def test_old_drafts_expire_and_a_held_lock_stops_the_scan(st, tmp_path):
    pubdir = tmp_path / "Published"
    pubdir.mkdir()
    published.add_source(st, "noor", folder=str(pubdir))
    published.keep_drafts(st, True)
    keep_pair_draft(st, tmp_path, 1, when=utcnow() - dt.timedelta(days=published.EXPIRE_DAYS + 1))
    (pubdir / "final.md").write_text((PAIRS / "pair-01" / "final.md").read_text())
    out = published.scan(st)
    assert out["expired"] == ["dr-001"] and out["matched"] == [] and len(out["unmatched"]) == 1
    lock.acquire(str(st), "learn")
    try:
        with pytest.raises(StoreError, match="another run holds the lock"):
            published.scan(st)
    finally:
        lock.release(str(st))
    with pytest.raises(StoreError, match="no published sources"):
        published.remove_source(st, "pub-001")
        published.scan(st)


def test_the_command_line(st, tmp_path):
    pubdir = tmp_path / "Published"
    pubdir.mkdir()
    script = ROOT / "idiolect" / "scripts" / "published.py"

    def run(*args):
        p = subprocess.run([sys.executable, str(script), "--store", str(st), *map(str, args)],
                           capture_output=True, text=True, timeout=120)
        return p.returncode, json.loads(p.stdout)
    assert run("keep-drafts", "on") == (0, {"keep_drafts": True})
    code, out = run("add-source", "--folder", pubdir, "--profile", "noor", "--type", "essay")
    assert code == 0 and out["added"] == "pub-001"
    draft = tmp_path / "d.md"
    draft.write_text((PAIRS / "pair-02" / "draft.md").read_text())
    assert run("keep", "--file", draft, "--profile", "noor", "--slot", "en.essay")[1] == {"kept": "dr-001"}
    (pubdir / "f.md").write_text((PAIRS / "pair-02" / "final.md").read_text())
    code, out = run("scan")
    assert code == 0 and out["queue"] == 1
    code, out = run("show")
    assert out["drafts"] == {"matched": 1} and out["queue"] == 1
    code, out = run("done", "--id", "q-001", "--skipped")
    assert code == 0 and out["status"] == "skipped"
    code, out = run("keep-drafts", "maybe")
    assert code == 1 and "on or off" in out["message"]
