"""Phase 3: resolution, the writing kit and check."""
import json
import pathlib
import shutil

import pytest

import check
import kit
import measure
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
    assert all(x["texts"] and x["of"] and x["texts"] <= x["of"] <= k["counts"]["texts"] for x in k["lessons"])
    md = kit.markdown(k)
    # examples lead, then targets; lessons follow as background, usual habits only (decision log, run 4)
    assert md.index("## Example passages") < md.index("## Measurable targets") < md.index("## Background")
    defaults = [x for x in k["lessons"] if x["default"]]
    optional = [x for x in k["lessons"] if not x["default"]]
    assert all(x["text"] in md for x in defaults) and "seen in " in md
    assert not any(x["text"] in md for x in optional if not any(x["text"] in d["text"] for d in defaults))
    assert "Favoured phrases" not in md and "## Observed lessons" not in md


def test_kit_notes_levels():
    k = kit.build(Store(STORE), "synthetic-noor", {"type": "essay"}, "repainting a garden bench", 3)
    full, none = kit.markdown(k, "full"), kit.markdown(k, "none")
    assert all(x["text"] in full for x in k["lessons"]) and "Habits the writer sometimes shows" in full
    assert "## Background" not in none and not any(x["text"] in none for x in k["lessons"])
    assert "## Measurable targets" in none and "## Example passages" in none


def test_targets_blend_the_slot_with_the_chosen_examples():
    s = Store(STORE)
    k = kit.build(s, "robert-cortes-holliday", {"type": "essay"}, "a bookshop clerk and a famous customer", 3)
    ex = measure.metrics("\n\n".join(e["text"] for e in k["examples"]), "en")
    w = k["blend"]["weight"]
    assert k["blend"]["words"] > 0 and abs(w - k["blend"]["words"] / (k["blend"]["words"] + kit.BLEND_WORDS)) < 1e-3
    for t in k["targets"]:
        if t["metric"] in ex:
            assert abs(t["value"] - (w * ex[t["metric"]] + (1 - w) * t["slot_value"])) < 1e-3
    # check measures against the same targets when given the same brief
    text = (FIX / "robert-cortes-holliday" / HOLD["robert-cortes-holliday"][0]).read_text()
    r = check.check(s, text, "robert-cortes-holliday", {"type": "essay"}, "a bookshop clerk and a famous customer")
    assert r["targets"]["examples"] == k["blend"]["examples"]
    by = {t["metric"]: t["value"] for t in k["targets"]}
    assert all(abs(m["writer"] - by[m["name"]]) < 1e-3 for m in r["metrics"])
    check_schema("check-report", r)


def test_blend_without_examples_is_the_slot():
    fp = {"semicolons_per_1k": {"value": 4.0}}
    assert kit.blend(fp, [], "en") == ({"semicolons_per_1k": 4.0}, 0, 0.0)


def test_a_metric_inside_the_slot_band_is_not_flagged(monkeypatch):
    """Flagged only outside the band around both the target for the piece and the slot's value."""
    s = Store(STORE)
    text = (FIX / "robert-cortes-holliday" / HOLD["robert-cortes-holliday"][0]).read_text()
    monkeypatch.setattr(kit, "blend", lambda fp, ex, lang: ({m: v["value"] for m, v in fp.items()}, 0, 0.0))
    slot_only = check.check(s, text, "robert-cortes-holliday", {"type": "essay"})
    far = {m: v * 10 + 5 for m, v in measure.metrics(text, "en").items()}
    monkeypatch.setattr(kit, "blend", lambda fp, ex, lang: (far, 900, 0.75))
    r = check.check(s, text, "robert-cortes-holliday", {"type": "essay"})
    # every target is far off, so only the slot band can clear a metric
    # (the direction follows the target for the piece, which the kit told the writer to aim at)
    assert [m["flag"] == "ok" for m in r["metrics"]] == [m["flag"] == "ok" for m in slot_only["metrics"]]
    assert all(m["writer"] != m["slot"] for m in r["metrics"])


def test_placeholders_are_not_measured():
    s = Store(STORE)
    text = (FIX / "synthetic-noor" / HOLD["synthetic-noor"][0]).read_text()
    paras = text.split("\n\n")
    marked = "\n\n".join(paras[:6] + ["[example needed: a real incident: what went wrong]"] + paras[6:])
    marked = marked.replace(paras[8], paras[8] + " [number needed: how many]", 1)
    a = check.check(s, text, "synthetic-noor", {"type": "essay"}, "the kitchen tap")
    b = check.check(s, marked, "synthetic-noor", {"type": "essay"}, "the kitchen tap")
    assert [m["draft"] for m in a["metrics"]] == [m["draft"] for m in b["metrics"]]
    assert check.strip_placeholders("A [example needed: x] b.\n\n[number needed: n]\n\nC.") == "A b.\n\nplaceholder\n\nC."


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
