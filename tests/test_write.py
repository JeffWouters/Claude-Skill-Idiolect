"""Phase 3: resolution, the writing kit and check."""
import json
import pathlib
import shutil

import pytest

import check
import kit
import resolve
from common import check_schema
from store import Store

ROOT = pathlib.Path(__file__).resolve().parent.parent
STORE = ROOT / "evals" / "store"
FIX = ROOT / "evals" / "fixtures"
HOLD = json.loads((ROOT / "evals" / "holdouts.json").read_text())["authors"]


def test_resolution_order():
    s = Store(STORE)
    assert resolve.resolve(s, "synthetic-noor", {"type": "essay"})[:2] == ("synthetic-noor", "en.essay")
    assert resolve.resolve(s, "synthetic-noor", {"type": "post"})[:2] == ("synthetic-noor", "en._")
    with pytest.raises(resolve.NoSlot):
        resolve.resolve(s, "synthetic-noor", {"lang": "nl"})


def test_inheritance_prefers_own_general_slot_over_parent(tmp_path):
    st = tmp_path / "store"
    shutil.copytree(STORE, st, ignore=shutil.ignore_patterns("corpus"))
    (st / "profiles/child").mkdir()
    (st / "profiles/child/profile.yaml").write_text("schema_version: 1\nsubject: c\nconsent: self\nextends: synthetic-noor\n")
    (st / "profiles/child/rulings.yaml").write_text(
        "schema_version: 1\nentries:\n  - {id: r-001, text: Never use the word very., origin: stated, created: '2026-10-01', personal_data: none}\n")
    s = Store(st)
    assert resolve.resolve(s, "child", {"type": "essay"})[:2] == ("synthetic-noor", "en.essay")
    shutil.copy(st / "profiles/synthetic-noor/en._.json", st / "profiles/child/en._.json")
    fp = json.loads((st / "profiles/child/en._.json").read_text())
    fp["profile"] = "child"
    (st / "profiles/child/en._.json").write_text(json.dumps(fp))
    assert resolve.resolve(s, "child", {"type": "essay"})[:2] == ("child", "en._")   # own voice first
    k = kit.build(s, "child", {"type": "essay"})
    assert any(r["text"].startswith("Never use the word") for r in k["rulings"])


def test_kit_contents():
    k = kit.build(Store(STORE), "synthetic-noor", {"type": "essay"}, "repainting a garden bench", 3)
    assert k["slot"] == "en.essay" and k["lessons"] and len(k["examples"]) == 3
    assert k["targets"][0]["primary"]
    md = kit.markdown(k)
    # examples lead; every lesson carries how many texts show it (decision log, run 1)
    assert md.index("## Example passages") < md.index("## Habits the writer usually shows")
    assert all(x["texts"] and x["of"] and x["texts"] <= x["of"] <= k["counts"]["texts"] for x in k["lessons"])
    assert "seen in " in md and "## Observed lessons" not in md


@pytest.mark.parametrize("author", sorted(HOLD))
def test_check_passes_the_authors_own_holdout_and_fails_the_wrong_author(author):
    s = Store(STORE)
    text = (FIX / author / HOLD[author][0]).read_text()
    own = check.check(s, text, author, {"type": "essay"})
    assert own["status"] in ("pass", "low_confidence"), own["flagged"]
    other = "synthetic-idris" if author == "synthetic-noor" else "synthetic-noor"
    wrong = check.check(s, text, other, {"type": "essay"})
    assert wrong["status"] == "fail"


def test_check_fails_a_neutral_rewrite_and_reports_both_directions():
    s = Store(STORE)
    r = check.check(s, (ROOT / "evals/spike/rewrites/synthetic-noor/1.md").read_text(), "synthetic-noor", {"type": "essay"})
    assert r["status"] == "fail" and {m["flag"] for m in r["metrics"]} >= {"overshoot", "shortfall"}
    check_schema("check-report", r)


def test_check_refuses_another_language():
    nl = ("Vandaag heb ik de hele middag in de tuin gewerkt, omdat het eindelijk droog was en de grond niet meer zo "
          "zwaar aan mijn laarzen bleef plakken. Ik heb de bonen opgebonden en het onkruid tussen de uien weggehaald.")
    r = check.check(Store(STORE), nl, "synthetic-noor", {"type": "essay"})
    assert r["status"] == "error" and "never carried across languages" in r["message"]


def test_short_drafts_never_fail():
    r = check.check(Store(STORE), "It is important to note that, in many ways, this might perhaps be rather complex. "
                                  "Moreover, it is worth considering the broader implications carefully.",
                    "synthetic-noor", {"type": "essay"})
    assert r["status"] == "pass" and "hints" in r["message"]


def test_no_slot_status():
    r = check.check(Store(STORE), "text", "synthetic-noor", {"lang": "de"})
    assert r["status"] == "no_slot"
