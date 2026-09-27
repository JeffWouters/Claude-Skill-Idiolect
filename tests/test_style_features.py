"""Outliers and verify (spec §28), the voice guide (§29), importing a style guide (§30) and tone (§31)."""
import glob
import json
import pathlib
import re
import shutil
import subprocess
import sys

import pytest
import yaml

import check
import guide
import kit
import learn
import rules
import stage
import verify
from common import StoreError, read_store_file
from store import Store
from test_learn import FIX, answers, full_learn, make_store
from test_rules import PLAIN

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent / "idiolect" / "scripts"


def fixture_text(author, n):
    f = sorted(glob.glob(str(FIX / author / "[0-9]*.md")))[n]
    return re.sub(r"^---.*?---\n", "", pathlib.Path(f).read_text(encoding="utf-8"), flags=re.S)


def run(script, *args):
    p = subprocess.run([sys.executable, str(SCRIPTS / script), *map(str, args)], capture_output=True, text=True,
                       timeout=120)
    return p.returncode, p.stdout


def commit(st, reject=()):
    stage.Pending(Store(st)).decide(reject=list(reject), all_decision="approved")
    return stage.commit(st)


@pytest.fixture(scope="module")
def learned(tmp_path_factory):
    t = tmp_path_factory.mktemp("style")
    st = make_store(t)
    full_learn(t, st, "noor", "noor")
    full_learn(t, st, "idris", "idris")
    return st


@pytest.fixture
def st(learned, tmp_path):
    dst = tmp_path / "Store"
    shutil.copytree(learned, dst)
    shutil.copytree(learned.parent / "Writing", tmp_path / "Writing")
    return dst


# ---------- outliers and verify ----------

def test_the_threshold_follows_the_spread_and_small_slots_are_left_alone():
    assert verify.threshold([0.2] * 6) == pytest.approx(0.3)             # no spread: 1.5 x the median
    assert verify.threshold([0.1, 0.2, 0.2, 0.3, 0.2, 0.2]) == pytest.approx(0.3)
    assert verify.slot_outliers([("a", PLAIN)] * 4, "en") == []            # under 5 texts: no picture
    assert verify.distance({"hedges_per_1k": 0.0}, {"hedges_per_1k": 0.1}) == 0.0   # both under the floor


def test_learn_flags_a_planted_guest_text_and_the_writer_can_set_it_aside(tmp_path):
    st = make_store(tmp_path)
    shutil.copy(sorted(glob.glob(str(FIX / "synthetic-idris" / "[0-9]*.md")))[-1],
                tmp_path / "Writing" / "noor" / "zz-guest.md")
    learn.start(st, targets=["noor"], profile="noor")
    learn.answer(st, answers(tmp_path, "noor", "noor"))
    learn.stage_texts(st)
    out = learn.do_measure(st)
    assert [(o["path"], o["slot"], o["new"]) for o in out["outliers"]] == [("noor/zz-guest.md", "en.essay", True)]
    o = out["outliers"][0]
    assert o["distance"] > o["threshold"] and o["off"] and "typically" in o["off"][0]
    aside = tmp_path / "aside.yaml"
    aside.write_text("files:\n  - {path: noor/zz-guest.md, profile: noor, ownership: assisted}\n")
    learn.answer(st, aside)
    learn.stage_texts(st)
    out = learn.do_measure(st)
    assert "outliers" not in out
    assert {s["slot"]: s["texts"] for s in out["slots"]}["en.essay"] == 10


def test_the_fixture_authors_learn_without_false_flags(st):
    for prof in ("noor", "idris"):
        s = Store(st)
        texts = [(k, t) for k, t, _ in
                 __import__("measure").slot_texts(s.manifest["texts"], s.corpus_text, s.facets, prof)["en.essay"]["texts"]]
        assert verify.slot_outliers(texts, "en") == [], prof


def test_verify_tells_an_unseen_text_of_the_writer_from_another_writers(st, tmp_path):
    s = Store(st)
    own = verify.verify(s, fixture_text("synthetic-noor", 11), "noor", {"type": "essay"})   # not learned
    other = verify.verify(s, fixture_text("synthetic-idris", 11), "noor", {"type": "essay"})
    assert not own["verdict"].startswith("unlike") and other["verdict"].startswith("unlike")
    assert other["distance"] > other["threshold"] > other["own_median"]
    assert other["off"] and "weak evidence" in other["notes"][0]
    assert own["texts_compared"] == 10
    f = tmp_path / "t.md"
    f.write_text(fixture_text("synthetic-idris", 11))
    code, out = run("verify.py", "--store", st, "--file", f, "--profile", "noor", "--type", "essay")
    assert code == 0 and out.startswith("Unlike the writer's texts") and "Note: one text is weak evidence" in out


def test_verify_needs_five_texts(st, monkeypatch):
    import measure
    real = measure.slot_texts
    monkeypatch.setattr(measure, "slot_texts", lambda *a: {k: {**v, "texts": v["texts"][:4]} for k, v in real(*a).items()})
    with pytest.raises(StoreError, match="verify needs at least 5"):
        verify.verify(Store(st), PLAIN, "noor", {"type": "essay"})


# ---------- the voice guide ----------

def test_the_voice_guide_has_the_rules_the_shape_and_leaves_private_things_out(st, monkeypatch):
    rules.defaults(st, "idris", categories=["punctuation", "chatbot"])
    commit(st)
    vf = st / "profiles/idris/vocabulary.yaml"
    voc = yaml.safe_load(vf.read_text())
    voc["entries"].append({"id": "v-099", "text": "secretword", "kind": "term", "private": True, "created": "2026-09-27"})
    voc["last_id"] = 99
    vf.write_text(yaml.safe_dump(voc, allow_unicode=True))
    g = guide.build(Store(st), "idris", {"type": "essay"})
    text = g["guide"]
    assert text.startswith("# Voice guide: synthetic fixture author") and "essays in English" in text
    for head in ("## Always and never", "## The shape of the writing", "## Example passages"):
        assert head in text
    assert "(checked)" in text and "this writer's own texts do this about" in text and "never more" not in text
    assert "secretword" not in text and g["left_out"]["private_vocabulary"] == 1
    available = len(kit.slot_examples(Store(st), "idris", "en.essay"))
    assert available >= 2 and g["examples"] == min(3, available)
    real = kit.build

    def unreviewed(*a, **k):
        out = real(*a, **k)
        out["examples"][0] = {**out["examples"][0], "redaction": {"redacted": True, "version": "1.0", "reviewed": False}}
        return out
    monkeypatch.setattr(kit, "build", unreviewed)
    g = guide.build(Store(st), "idris", {"type": "essay"})
    assert g["examples"] == min(3, available) - 1 and g["left_out"]["unreviewed_examples"] == 1


def test_the_house_style_guide_and_a_parents_slot(st, tmp_path):
    rules.add(st, "noor", "Never write about swans.", {"words": ["swans"]})
    commit(st)
    g = guide.build(Store(st), "noor", {"type": "essay"}, rulings_only=True)["guide"]
    assert g.startswith("# Style guide: noor") and "- Never write about swans. (checked)" in g
    assert "## The shape" not in g
    kid = st / "profiles/kid"
    kid.mkdir()
    (kid / "profile.yaml").write_text("schema_version: 1\nsubject: c\nconsent: self\nextends: noor\n")
    with pytest.raises(StoreError, match="a parent profile's"):
        guide.build(Store(st), "kid", {"type": "essay"})
    assert guide.build(Store(st), "kid", {"type": "essay"}, include_parent=True)["profile"] == "noor"
    code, out = run("guide.py", "--store", st, "--profile", "noor", "--type", "essay", "--examples", "0",
                    "--out", tmp_path / "g.md")
    assert code == 0 and json.loads(out)["examples"] == 0
    assert "## Example passages" not in (tmp_path / "g.md").read_text()


# ---------- importing a style guide ----------

GUIDE = """# Acme house style

## Numbers
Spell out numbers one to nine; use digits from 10.

## Words
- Use *use*, not **utilise**.
- Say "for example", never "e.g.".
- Know your audience.
"""


def proposals(tmp_path, rows):
    f = tmp_path / "p.yaml"
    f.write_text(yaml.safe_dump({"rules": rows}, allow_unicode=True))
    return f


def test_a_style_guide_is_imported_only_with_quotes_it_contains(st, tmp_path):
    g = tmp_path / "house.md"
    g.write_text(GUIDE)
    lines = rules.guide_text(g)
    assert any("Spell out numbers one to nine" in x for x in lines)
    good = [{"text": "Write numbers one to nine as words.", "quote": "Spell out numbers one to nine"},
            {"text": "Never use 'utilise'.", "quote": "use, not utilise", "test": {"words": ["utilise", "utilised"]}},
            {"text": "Never write 'e.g.'.", "quote": "Say “for example”, never “e.g.”", "test": {"phrases": ["e.g."]}}]
    bad = good + [{"text": "Never start with So.", "quote": "Do not start a sentence with So"}]
    with pytest.raises(StoreError, match=r"nothing was staged: rule 4 .*its quote is not in house.md"):
        rules.import_guide(st, "noor", g, proposals(tmp_path, bad))
    assert not stage.Pending(Store(st)).exists()
    with pytest.raises(StoreError, match="not a valid regular expression"):
        rules.import_guide(st, "noor", g, proposals(tmp_path, [{"text": "x", "quote": "Know your audience",
                                                                "test": {"pattern": "("}}]))
    out = rules.import_guide(st, "noor", g, proposals(tmp_path, good + [good[0]]))
    assert [p["id"] for p in out["proposed"]] == ["r-001", "r-002", "r-003"]
    assert [p["checked"] for p in out["proposed"]] == [False, True, True]
    assert out["skipped"][0]["why"] == "the profile already holds this rule"
    summary = stage.Pending(Store(st)).plan["items"][0]["summary"]
    assert "from house.md: \"Spell out numbers one to nine\"" in summary
    commit(st)
    held = read_store_file(st / "profiles/noor/rulings.yaml", "rulings")["entries"]
    assert [e["origin"] for e in held] == ["stated"] * 3
    r = check.check(Store(st), PLAIN + "\nWe utilised the bridge, e.g. at night.\n", "noor", {"type": "essay"})
    assert {x["lesson"] for x in r["flagged_lines"] if x["lesson"].startswith("r-")} == {"r-002", "r-003"}
    again = rules.import_guide(st, "noor", g, proposals(tmp_path, good))
    assert again["proposed"] == [] and not stage.Pending(Store(st)).exists()


def test_guide_text_on_the_command_line_numbers_lines_and_reads_plain_text(tmp_path):
    g = tmp_path / "rules.txt"
    g.write_text("No exclamation marks.\nKeep it short.\n")
    code, out = run("rules.py", "guide-text", "--source", g)
    assert code == 0 and json.loads(out)["lines"] == ["1: No exclamation marks.", "2: Keep it short."]
    code, out = run("rules.py", "guide-text", "--source", tmp_path / "missing.md")
    assert code == 1 and "no file" in json.loads(out)["message"]


# ---------- tone ----------

def test_tones_parse_combine_and_refuse_conflicts():
    assert kit.parse_tone(None) == [] and kit.parse_tone("Warm, firm") == ["warm", "firm"]
    with pytest.raises(StoreError, match="firm and formal pull average sentence length both ways"):
        kit.parse_tone("firm,formal")
    with pytest.raises(StoreError, match="unknown tone loud"):
        kit.parse_tone("loud")
    with pytest.raises(StoreError, match="pull contractions per 1,000 words both ways"):
        kit.parse_tone("warm,formal")
    with pytest.raises(StoreError, match="both ways"):
        kit.parse_tone("firm,soft")


def test_a_tone_moves_targets_to_the_writers_own_quartile_never_beyond(st):
    import measure
    s = Store(st)
    base = kit.build(s, "idris", {"type": "essay"}, PLAIN)
    for tone in ("firm", "soft", "casual", "formal", "warm", "cool"):
        k = kit.build(s, "idris", {"type": "essay"}, PLAIN, tone=tone)
        texts = [t for _, t, _ in measure.slot_texts(s.manifest["texts"], s.corpus_text, s.facets, "idris")["en.essay"]["texts"]]
        vals = [measure.metrics(t, "en") for t in texts]
        before = {t["metric"]: t["value"] for t in base["targets"]}
        after = {t["metric"]: t["value"] for t in k["targets"]}
        for m in k["tone"]["moved"]:
            d = kit.TONES[tone][m["metric"]]
            xs = [v[m["metric"]] for v in vals]
            assert min(xs) <= after[m["metric"]] <= max(xs)                       # inside the writer's range
            assert (after[m["metric"]] - before[m["metric"]]) * d > 0              # in the asked direction
        untouched = set(before) - {m["metric"] for m in k["tone"]["moved"]}
        assert all(after[x] == before[x] for x in untouched)
    k = kit.build(s, "idris", {"type": "essay"}, PLAIN, tone="firm")
    assert "## Tone: firmer, more direct" in kit.markdown(k)


def test_check_measures_against_the_same_toned_targets_as_the_kit(st):
    s = Store(st)
    k = kit.build(s, "idris", {"type": "essay"}, PLAIN, tone="casual")
    r = check.check(s, PLAIN, "idris", {"type": "essay"}, PLAIN, tone="casual")
    assert r["targets"]["tone"] == ["casual"]
    kt = {t["metric"]: t["value"] for t in k["targets"]}
    assert all(m["writer"] == pytest.approx(kt[m["name"]], abs=1e-4) for m in r["metrics"])
    assert "tone" not in check.check(s, PLAIN, "idris", {"type": "essay"}, PLAIN)["targets"]


def test_a_tone_needs_five_texts_and_works_on_the_command_line(st, tmp_path, monkeypatch):
    brief, draft = tmp_path / "b.md", tmp_path / "d.md"
    brief.write_text(PLAIN)
    draft.write_text(PLAIN)
    code, out = run("kit.py", "--store", st, "--profile", "idris", "--type", "essay", "--brief", brief, "--tone", "firm")
    assert code == 0 and "## Tone: firmer" in out
    code, out = run("check.py", "--store", st, "--file", draft, "--brief", brief, "--profile", "idris", "--type", "essay",
                    "--tone", "firm", "--json")
    assert json.loads(out)["targets"]["tone"] == ["firm"]
    code, out = run("check.py", "--store", st, "--file", draft, "--profile", "idris", "--type", "essay", "--tone", "loud",
                    "--json")
    assert code == 1 and "unknown tone" in json.loads(out)["message"]
    import measure
    real = measure.slot_texts
    monkeypatch.setattr(measure, "slot_texts", lambda *a: {k: {**v, "texts": v["texts"][:3]} for k, v in real(*a).items()})
    with pytest.raises(StoreError, match="a tone needs at least 5 texts"):
        kit.build(Store(st), "idris", {"type": "essay"}, PLAIN, tone="firm")
