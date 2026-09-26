"""The inventory fixture is internally consistent, and the comparator behaves as spec §5 says.

When the phase 1 engine exists, test_dry_run_matches_expected runs it; until then it is skipped.
"""
import copy
import json
import pathlib
import subprocess
import sys

import pytest

from inventory_compare import compare
from test_hash import content_hash
from test_schemas import validator

ROOT = pathlib.Path(__file__).resolve().parent.parent
FX = ROOT / "tests" / "inventory-fixture"
STORE = FX / "sources" / ".idiolect"
EXPECTED = json.loads((FX / "expected-inventory.json").read_text(encoding="utf-8"))
MANIFEST = json.loads((STORE / "corpus" / "manifest.json").read_text(encoding="utf-8"))


def test_expected_report_validates():
    errors = list(validator("inventory-report").iter_errors(EXPECTED))
    assert not errors, "\n".join(e.message for e in errors)


def test_cached_entries_have_their_text():
    for key, e in MANIFEST["texts"].items():
        path = STORE / "corpus" / f"{key.replace('#', '-')}.txt"
        if e["cached"]:
            assert path.exists(), f"cached entry without text: {key}"
            assert content_hash(path.read_text(encoding="utf-8")) == key.split("#")[0]
        else:
            assert not path.exists(), f"uncached entry with text: {key}"
    for f in (STORE / "corpus").glob("*.txt"):
        assert f.stem.replace("-", "#") in MANIFEST["texts"], f"orphan corpus text: {f.name}"


def test_every_result_row_type_is_covered():
    results = {r["result"] for r in EXPECTED["rows"]}
    for needed in ("unchanged", "moved", "copy", "reverted", "changed", "new", "skipped: not prose",
                   "skipped: language not supported", "skipped: forgotten", "skipped: holdout",
                   "skipped: too short", "skipped: near-duplicate"):
        assert needed in results, needed
    assert EXPECTED["unreachable"], "no unreachable case"


def test_comparator_accepts_itself_and_catches_changes():
    assert compare(EXPECTED, EXPECTED) == []
    bad = copy.deepcopy(EXPECTED)
    bad["rows"][0]["result"] = "new"
    bad["unreachable"] = []
    d = compare(bad, EXPECTED)
    assert any("result" in x for x in d) and any("unreachable" in x for x in d)
    # an expected null key accepts any actual key
    pdf = next(r for r in EXPECTED["rows"] if r["path"].endswith(".pdf"))
    act = copy.deepcopy(EXPECTED)
    next(r for r in act["rows"] if r["path"] == pdf["path"])["key"] = "0" * 64
    assert compare(act, EXPECTED) == []


ENGINE = ROOT / "idiolect" / "scripts" / "inventory.py"


@pytest.mark.skipif(not ENGINE.exists(), reason="phase 1 engine not built yet")
def test_dry_run_matches_expected():
    out = subprocess.run([sys.executable, str(ENGINE), "--store", str(STORE), "--dry-run", "--json"],
                         capture_output=True, text=True, check=True).stdout
    actual = json.loads(out)
    assert not list(validator("inventory-report").iter_errors(actual))
    diffs = compare(actual, EXPECTED)
    assert not diffs, "\n".join(diffs)
