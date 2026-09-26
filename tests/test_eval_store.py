"""The committed evaluation store (evals/store): every fixture author has an approved profile, and the
corpus rebuilds the same fingerprints (phase 2 exit criteria)."""
import json
import pathlib

import pytest

import measure
from store import Store

ROOT = pathlib.Path(__file__).resolve().parent.parent
STORE = ROOT / "evals" / "store"
AUTHORS = sorted(p.name for p in (ROOT / "evals" / "fixtures").iterdir() if p.is_dir())


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
