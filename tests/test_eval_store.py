"""The committed evaluation store (evals/store): every fixture author has an approved profile, and the
corpus rebuilds the same fingerprints (phase 2 exit criteria)."""
import json
import pathlib

import pytest

import measure
from store import Store

ROOT = pathlib.Path(__file__).resolve().parent.parent
STORE = ROOT / "evals" / "store"
# The evaluation store holds the English evaluation authors. A pack fixture (synthetic-sanne, Dutch)
# tests its language pack end to end in tests/test_lang_packs.py and is not an evaluation author.
# The native-* folders are the language-flavour detectors' false-alarm test (tests/test_flavour.py).
PACK_FIXTURES = {"synthetic-sanne"}
AUTHORS = sorted(p.name for p in (ROOT / "evals" / "fixtures").iterdir()
                 if p.is_dir() and p.name not in PACK_FIXTURES and not p.name.startswith("native-"))


@pytest.mark.parametrize("author", AUTHORS)
def test_profile_complete(author):
    d = STORE / "profiles" / author
    for f in ("profile.yaml", "en.essay.json", "en.essay.md", "en.essay.never.md", "en.essay.examples.md",
              "en._.json", "en._.md", "changelog.md"):
        assert (d / f).exists(), f
    assert "- [l-001]" in (d / "en.essay.md").read_text()


@pytest.mark.parametrize("author", AUTHORS)
def test_corpus_rebuilds_the_same_fingerprints(author):
    store = Store(STORE)
    for x in measure.fingerprints(store, author):
        new = x["fingerprint"]
        old = json.loads((STORE / "profiles" / author / f"{new['slot']}.json").read_text())
        assert new["counts"] == old["counts"] and new["confidence"] == old["confidence"]
        assert new["seed"] == old["seed"]
        assert {m: v["value"] for m, v in new["metrics"].items()} == {m: v["value"] for m, v in old["metrics"].items()}


def test_holdouts_are_not_learned():
    holdouts = json.loads((ROOT / "evals" / "holdouts.json").read_text())["authors"]
    paths = {e["path"] for e in Store(STORE).manifest["texts"].values()}
    for author, files in holdouts.items():
        for f in files:
            assert f"{author}/{f}" not in paths


def test_every_store_file_is_valid():
    from common import read_store_file
    import pages
    s = STORE
    read_store_file(s / "idiolect.yaml", "idiolect")
    read_store_file(s / "sources.yaml", "sources")
    read_store_file(s / "corpus" / "manifest.json", "manifest")
    for prof in (s / "profiles").iterdir():
        read_store_file(prof / "profile.yaml", "profile")
        for name, schema in (("vocabulary.yaml", "vocabulary"), ("rulings.yaml", "rulings"),
                             ("rejected.yaml", "rejected")):
            if (prof / name).exists():
                read_store_file(prof / name, schema)
        for f in prof.glob("*.json"):
            read_store_file(f, "fingerprint")
        for f in prof.glob("*.md"):
            text = f.read_text(encoding="utf-8")
            if f.name.endswith(".examples.md"):
                meta, ex = pages.parse_examples(text)
                assert ex and all(e["text"] and e["redaction"]["redacted"] for e in ex)
            elif f.name.endswith(".never.md") or f.name == "changelog.md":
                pages.split_page(text)
            else:
                meta, conf, lessons = pages.parse_slot_page(text)
                assert conf and lessons and meta["last_id"] >= len(lessons)
