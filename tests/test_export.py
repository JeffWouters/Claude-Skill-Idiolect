"""Phase 6: export (spec §22)."""
import pytest
import yaml

import export
from common import StoreError, dump_yaml
from store import Store
from test_learn import full_learn, make_store


def test_export_is_one_self_contained_prompt_without_private_data(tmp_path):
    st = make_store(tmp_path)
    full_learn(tmp_path, st, "noor", "noor")
    voc = st / "profiles" / "noor" / "vocabulary.yaml"
    data = yaml.safe_load(voc.read_text())
    data["entries"].append({"id": "v-099", "text": "Secret Project Falcon", "kind": "term", "private": True,
                            "created": "2026-09-26"})
    voc.write_text(dump_yaml(data))
    out = export.build(Store(st), "noor", {"type": "essay"})
    p = out["prompt"]
    for head in ("## How to use this", "## Targets", "## Example passages", "## Forms"):
        assert head in p
    assert "kitchen tap" in p and "Secret Project Falcon" not in p and out["left_out"]["private_vocabulary"] == 1
    corpus = [f.read_text() for f in (st / "corpus").glob("*.txt")]
    assert not any(c in p for c in corpus)          # whole texts never leave the store


def test_export_refuses_an_unreviewed_example_and_a_parents_slot(tmp_path):
    st = make_store(tmp_path)
    full_learn(tmp_path, st, "noor", "noor")
    ex = st / "profiles" / "noor" / "en.essay.examples.md"
    ex.write_text(ex.read_text().replace("reviewed: true", "reviewed: false", 1))
    with pytest.raises(StoreError, match="reviewed redaction"):
        export.build(Store(st), "noor", {"type": "essay"})
    ex.write_text(ex.read_text().replace("reviewed: false", "reviewed: true", 1))
    kid = st / "profiles" / "kid"
    kid.mkdir()
    (kid / "profile.yaml").write_text(dump_yaml({"schema_version": 1, "subject": "a child profile",
                                                 "consent": "self", "extends": "noor"}))
    with pytest.raises(StoreError, match="include_parent"):
        export.build(Store(st), "kid", {"type": "essay"})
    out = export.build(Store(st), "kid", {"type": "essay"}, include_parent=True)
    assert out["profile"] == "noor" and "parent profile noor of kid" in out["prompt"]
