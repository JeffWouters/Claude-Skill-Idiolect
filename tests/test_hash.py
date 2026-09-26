"""Hash test vectors for spec §4. The reference function here is what scripts/ must match.

    python3 -m pytest tests/test_hash.py -q
"""
import hashlib
import json
import pathlib
import re
import unicodedata

VEC = json.loads((pathlib.Path(__file__).parent / "hash-vectors.json").read_text())


def content_hash(text):
    text = unicodedata.normalize("NFC", text)
    text = "".join(" " if c.isspace() else c for c in text)
    text = re.sub(" +", " ", text).strip(" ")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def test_vectors():
    for v in VEC["vectors"]:
        assert content_hash(v["input"]) == v["sha256"], v["name"]


def test_equal_groups():
    by = {v["name"]: v["sha256"] for v in VEC["vectors"]}
    for group in VEC["equal_groups"]:
        assert len({by[n] for n in group}) == 1, group
    assert by["plain"] != by["case-kept"]
