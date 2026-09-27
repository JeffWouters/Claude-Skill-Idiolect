"""Phase 1 engine: adapters, language segments, globs, lock, pending area, inventory without a store,
measurement and status."""
import datetime as dt
import glob
import json
import os
import pathlib
import shutil
import sys
import zipfile

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "evals" / "spike"))

import detect  # noqa: E402
import inventory  # noqa: E402
import lock  # noqa: E402
import measure  # noqa: E402
import pending  # noqa: E402
import status as statusmod  # noqa: E402
from adapters import extract  # noqa: E402
from common import content_hash, count_words, iso, write_json  # noqa: E402
from store import Store, glob_match, resolve_facets  # noqa: E402

FX = ROOT / "tests" / "inventory-fixture" / "sources"


# ---------- adapters ----------

MD = """---
date: 2025-01-02
tags: [a, b]
lang: nl
---
# Title here

Some **bold** and `short code` and `this inline code is definitely longer than forty chars` text,
a [link](http://x), [[Note|alias]], [[Plain]] and #tag here.![[embed.png]] Footnote[^1].

> quoted stuff is someone else's

> [!note] Callout title
> Callout body text.

| a | b |
|---|---|
| 1 | 2 |
| 3 | 4 |

| name | say |
|---|---|
| x | hello there |

- item one
- item two

```python
print("code")
```

<div>html</div>

[^1]: footnote definition
"""


def test_markdown_adapter(tmp_path):
    f = tmp_path / "n.md"
    f.write_text(MD, encoding="utf-8")
    e = extract(f)
    assert e.date == "2025-01-02" and e.meta["lang"] == "nl" and e.meta["tags"] == ["a", "b"]
    assert e.blocks[0] == "Title here"
    assert "short code" in e.blocks[1] and "definitely longer" not in e.blocks[1]
    assert "alias" in e.blocks[1] and "Plain" in e.blocks[1] and "#tag" not in e.blocks[1]
    assert "embed" not in e.blocks[1] and "[^1]" not in e.blocks[1] and "**" not in e.blocks[1]
    text = e.text
    assert "quoted stuff" not in text and "Callout title" not in text and "Callout body text." in text
    assert "hello there" in text and "\n1 2" not in text
    assert "item one" in e.blocks and "item two" in e.blocks
    assert "print" not in text and "html" not in text and "footnote definition" not in text


def _docx(path, paras):
    W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
    body = "".join(f"<w:p>{p}</w:p>" for p in paras)
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("word/document.xml", f'<?xml version="1.0"?><w:document {W}><w:body>{body}</w:body></w:document>')


def test_docx_tracked_changes(tmp_path):
    f = tmp_path / "d.docx"
    _docx(f, ['<w:r><w:t>Kept words </w:t></w:r><w:ins w:id="1"><w:r><w:t>inserted words</w:t></w:r></w:ins>'
              '<w:del w:id="2"><w:r><w:delText> deleted words</w:delText></w:r></w:del>', ""])
    e = extract(f)
    assert e.blocks == ["Kept words inserted words"]


def test_fixture_pdf_and_docx_words():
    exp = json.loads((FX.parent / "expected-inventory.json").read_text())
    for name in ("essays/lecture.pdf", "essays/tracked.docx"):
        want = next(r["words"] for r in exp["rows"] if r["path"] == name)
        assert count_words(extract(FX / name).text) == want


def test_no_adapter():
    assert extract(FX / "images" / "diagram.png") is None


# ---------- language and segments ----------

def test_mixed_language_segments():
    e = extract(FX / "essays" / "mixed.md")
    parts = detect.split(e.blocks)
    assert [p.lang for p in parts] == ["en", "nl"]
    assert parts[0].key == content_hash(e.text) and parts[1].key == parts[0].key + "#2"
    assert parts[0].words + parts[1].words == count_words(e.text)


def test_set_lang_replaces_main_but_keeps_segments():
    e = extract(FX / "essays" / "mixed.md")
    parts = detect.split(e.blocks, set_lang="en-gb")
    assert parts[0].lang == "en-gb" and parts[1].lang == "nl"


def test_unsupported_language():
    e = extract(FX / "essays" / "japanese.md")
    assert detect.split(e.blocks)[0].lang in detect.UNSUPPORTED


# ---------- globs and facets ----------

@pytest.mark.parametrize("pattern,path,ok", [
    ("drafts/**", "drafts/wip.md", True), ("drafts/**", "drafts/a/b.md", True),
    ("drafts/**", "notes/drafts.md", False), ("**/_archive/**", "_archive/x.md", True),
    ("**/_archive/**", "a/b/_archive/x.md", True), ("*Accepted*", "Mail/2026 Accepted x.eml", True),
    ("*.pdf", "a/b.pdf", True), ("a/*.md", "a/b/c.md", False), ("a/?.md", "a/b.md", True),
])
def test_globs(pattern, path, ok):
    assert glob_match(pattern, path) is ok


def test_facet_order():
    r = resolve_facets(["lang", "type"], command={"type": "post"}, entry={"lang": "en", "type": "essay"},
                       rule={"type": "howto"}, front={"lang": "nl"}, detected={"lang": "de"})
    assert r == {"lang": "en", "type": "post"}
    assert resolve_facets(["lang", "type"], detected={"lang": "de"}, unknown="?") == {"lang": "de", "type": "?"}


# ---------- lock ----------

T0 = dt.datetime(2026, 10, 2, 12, 0, tzinfo=dt.timezone.utc)


def test_lock_cycle(tmp_path):
    s = str(tmp_path)
    assert lock.state(s, T0) == "free"
    got = lock.acquire(s, "learn", "sam", now=T0)
    assert not got["taken_over"] and lock.state(s, T0) == "held"
    with pytest.raises(lock.Locked):
        lock.acquire(s, "forget", now=T0 + dt.timedelta(minutes=59))
    lock.heartbeat(s, now=T0 + dt.timedelta(minutes=50))
    with pytest.raises(lock.Locked):
        lock.acquire(s, "forget", now=T0 + dt.timedelta(minutes=100))
    got = lock.acquire(s, "forget", now=T0 + dt.timedelta(minutes=111))
    assert got["taken_over"]
    lock.release(s)
    assert lock.state(s, T0) == "free"


def test_damaged_lock_uses_file_time(tmp_path):
    s = str(tmp_path)
    (tmp_path / ".state").mkdir()
    p = tmp_path / ".state" / "lock"
    p.write_text("")
    now = dt.datetime.now(dt.timezone.utc)
    assert lock.state(s, now) == "damaged"
    old = now.timestamp() - 7200
    os.utime(p, (old, old))
    assert lock.state(s, now) == "abandoned"
    assert lock.acquire(s, "learn", now=now)["taken_over"]


def test_lock_refuses_read_only_modes(tmp_path):
    with pytest.raises(Exception):
        lock.acquire(str(tmp_path), "write")


# ---------- pending area ----------

def test_pending_leftovers(tmp_path):
    s = str(tmp_path)
    assert pending.status(s)["pending"] is False
    plan = {"schema_version": 1, "run_id": "20261002T120000Z", "mode": "learn",
            "created": "2026-10-02T12:00:00Z", "items": []}
    write_json(tmp_path / ".state" / "pending" / "plan.json", plan, "pending")
    assert pending.status(s)["choices"] == ["resume", "discard"]
    plan["commit"] = {"started": "2026-10-02T12:05:00Z",
                      "steps": [{"op": "write", "path": "corpus/manifest.json", "state": "todo"}]}
    write_json(tmp_path / ".state" / "pending" / "plan.json", plan, "pending")
    assert pending.status(s)["choices"] == ["resume"]
    with pytest.raises(Exception):
        pending.discard(s)
    del plan["commit"]
    write_json(tmp_path / ".state" / "pending" / "plan.json", plan, "pending")
    assert pending.discard(s)["discarded"] and not (tmp_path / ".state" / "pending").exists()


def test_progress(tmp_path):
    s = str(tmp_path)
    pending.progress_start(s, "learn", "Published", 50)
    d = pending.progress_batch_done(s, ["Published/a.md", "Published/b.md"])
    assert d["batches_done"] == 1 and pending.progress_read(s, "Published")["done"] == ["Published/a.md", "Published/b.md"]
    assert pending.progress_read(s, "Other") is None


# ---------- inventory without a store (spec §3.4) ----------

def test_dry_run_without_store():
    rep = inventory.inventory(None, FX)
    results = {r["path"]: r["result"] for r in rep["rows"] if "#" not in (r["key"] or "")}
    assert rep["store"] is None
    assert not any(r["path"].startswith(".idiolect") for r in rep["rows"])
    assert results["essays/unchanged.md"] == "new"          # no manifest: nothing is known
    assert results["essays/near-dup-a.md"] == "skipped: near-duplicate"
    assert results["essays/short-note.md"] == "skipped: too short"
    assert results["drafts/wip.md"] == "new"                # no rules, so no excludes
    types = {r["path"]: r["type"] for r in rep["rows"]}
    assert types["essays/new-essay.md"] == "?"


def test_inventory_target_scope():
    store = Store(FX / ".idiolect")
    rep = inventory.inventory(store, targets=["howto"])
    assert [r["path"] for r in rep["rows"]] == ["howto/code-heavy.md"]
    assert rep["unreachable"] == []   # entries outside the scope are not touched


# ---------- measurement ----------

def test_counts():
    assert [measure.fail_count(n) for n in (14, 13, 12, 11)] == [4, 4, 4, 4]
    assert measure.fail_count(1) == 1 and measure.fail_count(5) == 2
    assert len(measure.applicable("en")) == 14 and len(measure.applicable("nl")) == 14   # Dutch pack (spec §32)
    assert len(measure.applicable("fr")) == 11                                            # no word lists (the French pack holds flavour detectors only)


def test_metrics_match_phase0_without_headings():
    import spike
    for f in sorted(glob.glob(str(ROOT / "evals" / "fixtures" / "synthetic-noor" / "[0-9]*.md")))[:4]:
        t = spike.strip_meta(pathlib.Path(f).read_text(encoding="utf-8"))
        a, b = spike.metrics(t), measure.metrics(t, "en")
        for k in b:
            assert b[k] == pytest.approx(a[k], rel=1e-4, abs=1e-6), k


def test_headings_are_not_measured():
    body = "It rained. We stayed in. Nobody minded the noise at all, not even the dog."
    assert measure.metrics("A heading\n\n" + body) == measure.metrics(body)


def _author_store(tmp_path, author, n=None):
    src = tmp_path / "Writing"
    store = tmp_path / "Store"
    (store / "corpus").mkdir(parents=True)
    (store / "profiles" / "fx").mkdir(parents=True)
    (store / "idiolect.yaml").write_text("schema_version: 1\nsources_root: ../Writing\nfacets: [lang, type]\n"
                                         "types: [essay]\ndefault_profile: fx\n")
    (store / "profiles" / "fx" / "profile.yaml").write_text(
        "schema_version: 1\nsubject: fixture author\nconsent: public-domain fixture, evaluation only\n")
    texts = {}
    files = sorted(glob.glob(str(ROOT / "evals" / "fixtures" / author / "[0-9]*.md")))[: n or None]
    for f in files:
        dst = src / "essays" / pathlib.Path(f).name
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(f, dst)
        t = extract(dst).text
        k = content_hash(t)
        (store / "corpus" / f"{k}.txt").write_text(t, encoding="utf-8")
        texts[k] = {"path": f"essays/{dst.name}", "origin": "file",
                    "profiles": {"fx": {"ownership": "own", "decided": "2026-10-02", "decided_by": "path-rule"}},
                    "facets": {"lang": "en", "type": "essay"}, "words": count_words(t), "holdout": False,
                    "status": "active", "cached": True}
    write_json(store / "corpus" / "manifest.json", {"schema_version": 1, "texts": texts}, "manifest")
    return Store(store)


def test_fingerprints_and_pooled_slot(tmp_path):
    store = _author_store(tmp_path, "synthetic-noor")
    fps = {x["fingerprint"]["slot"]: x["fingerprint"] for x in measure.fingerprints(store, "fx")}
    assert set(fps) == {"en.essay", "en._"}
    assert fps["en._"]["pooled"] and not fps["en.essay"]["pooled"]
    assert fps["en.essay"]["counts"]["texts"] == 12
    assert fps["en.essay"]["confidence"]["count_level"] == "medium"   # 12 texts but under 15,000 words
    again = {x["fingerprint"]["slot"]: x["fingerprint"] for x in measure.fingerprints(store, "fx")}
    for k in fps:
        a, b = dict(fps[k]), dict(again[k])
        a.pop("built"), b.pop("built")
        assert a == b     # deterministic apart from the build time


def test_high_confidence_for_a_large_consistent_corpus(tmp_path):
    store = _author_store(tmp_path, "robert-cortes-holliday")
    fp = next(x["fingerprint"] for x in measure.fingerprints(store, "fx") if x["fingerprint"]["slot"] == "en.essay")
    assert fp["confidence"]["count_level"] == "high"


def test_status_on_example_store():
    s = statusmod.status(Store(ROOT / "tests" / "example-store"))
    sam = next(p for p in s["profiles"] if p["name"] == "sam")
    acme = next(p for p in s["profiles"] if p["name"] == "acme")
    assert sam["slots"][0]["slot"] == "en.essay" and sam["rejections"] == 1
    assert acme["extends"] == ["sam"] and acme["inherited_rulings"]
    assert s["pending"]["choices"] == ["resume"]
