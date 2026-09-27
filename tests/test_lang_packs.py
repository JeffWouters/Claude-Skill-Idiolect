"""Language packs (spec §32): English repackaged unchanged, the Dutch pack end to end, the pack checker,
and the Dutch starter set."""
import glob
import hashlib
import json
import pathlib
import re
import shutil
import subprocess
import sys

import pytest
import yaml

import check
import kit
import langpack
import learn
import measure
import rules
import stage
from store import Store
from test_learn import lesson_file

ROOT = pathlib.Path(__file__).resolve().parent.parent
LANG = ROOT / "idiolect" / "references" / "lang"
SANNE = ROOT / "evals" / "fixtures" / "synthetic-sanne"

# The English lists as they were calibrated (phase 0): repackaging must not change a byte.
EN_LISTS = {
    "contractions.txt": "dd555b16af9e8743e106bf378b99401eee5a9a10fce306c00226d213410129e0",
    "hedges.txt": "1d1a548c3f95ca8414a50a13f32e642acd806a9afe6c1dc24c1117a2615ac5d0",
    "openers.txt": "ae2683868da055c0b9fd892a768a22c5410e93e94bbd215a7c0a8abcac827fa6",
    "stopwords.txt": "5124f07c383e2a05d11876d1fcd1f9137908d1fef7ccb8284b2447d6e82702d0",
}


def body(f):
    return re.sub(r"^---.*?---\n", "", pathlib.Path(f).read_text(encoding="utf-8"), flags=re.S)


def test_english_is_a_pack_with_its_lists_unchanged():
    for name, digest in EN_LISTS.items():
        assert hashlib.sha256((LANG / "en" / name).read_bytes()).hexdigest() == digest, name
    info = measure.pack_info("en")
    assert info["code"] == "en" and info["calibrated"] is True
    assert measure.pack_warning("en") is None


def test_every_shipped_pack_passes_the_checker():
    assert langpack.packs() == ["de", "en", "es", "fr", "nl"]
    for code in langpack.packs():
        assert langpack.check(code) == [], code
    listed = {p["code"]: p for p in langpack.listing()}
    assert listed["nl"]["metrics"] == 14 and listed["nl"]["calibrated"] is False
    p = subprocess.run([sys.executable, str(ROOT / "idiolect/scripts/langpack.py"), "check"], capture_output=True, text=True)
    assert p.returncode == 0 and json.loads(p.stdout)["status"] == "ok"


def test_the_checker_finds_a_broken_pack(tmp_path, monkeypatch):
    bad = tmp_path / "xx"
    bad.mkdir()
    (bad / "pack.yaml").write_text("code: yy\nname: Test\n")
    (bad / "hedges.txt").write_text("maybe\nMaybe\nmaybe\n perhaps\n")
    (bad / "contractions.txt").write_text("(unclosed\n")
    monkeypatch.setattr(langpack, "LANG_DIR", tmp_path)
    problems = langpack.check("xx")
    for part in ("says code 'yy'", "no version", "no calibrated", "not lower case", "duplicate 'maybe'",
                 "leading or trailing spaces", "not a valid pattern"):
        assert any(part in x for x in problems), part
    assert langpack.check("zz") == ["zz: no pack folder"]


def test_dutch_is_measured_on_all_fourteen_metrics():
    v = measure.metrics("Misschien was het de kou. Maar m’n band was lek, en 't regende. Zo'n dag.", "nl")
    assert len(v) == 14
    assert v["hedges_per_1k"] > 0 and v["contractions_per_1k"] > 0 and v["conjunction_opener_share"] > 0
    assert measure.pack_warning("nl") == "the thresholds were calibrated on English, not on Dutch"
    assert measure.pack_warning("pt").startswith("no language pack for 'pt': measured on the 11 metrics")
    # a pack with flavour detectors but no word lists yet says both (spec §32, §34)
    assert measure.pack_warning("de") == ("the thresholds were calibrated on English, not on German; the German "
                                          "pack has no word lists yet: measured on the 11 metrics that need none")


def test_the_dutch_starter_set_mirrors_the_english_one_and_leaves_plain_dutch_alone():
    en, nl = rules.starter("en"), rules.starter("nl")
    assert [(r["id"], r["category"], r["unless_writer_uses"]) for r in nl["rules"]] == \
        [(r["id"], r["category"], r["unless_writer_uses"]) for r in en["rules"]]
    samples = {"s-001": "Het was laat — te laat.", "s-002": "Ik hoop dat dit helpt bij je plannen.",
               "s-003": "Goede vraag, en een lastige.", "s-004": "Tot mijn laatste update was de brug dicht.",
               "s-005": "Hier is de herziene alinea.", "s-006": "Een naadloze overgang.",
               "s-007": "Een innovatieve aanpak.", "s-008": "Het speelt een cruciale rol in de stad.",
               "s-009": "Een huisje gelegen in het hart van de heuvels.", "s-010": "Experts zeggen dat het water stijgt.",
               "s-011": "De zaal dient als vergaderruimte.", "s-012": "De stad groeide, wat de noodzaak van wegen benadrukt.",
               "s-013": "Laten we erin duiken.", "s-014": "Laat dat even bezinken.",
               "s-015": "Begrijp me niet verkeerd, ik vind het mooi.",
               "s-016": "Het is niet alleen goedkoop, maar ook snel.", "s-017": "Met betrekking tot de planning.",
               "s-018": "Het regende. Bovendien sneeuwde het.", "s-019": "Het zou mogelijk kunnen regenen.",
               "s-020": "Concluderend: het regende.", "s-021": "We wonnen \U0001F389", "s-022": "- **Let op:** het pad is dicht."}
    texts = [body(f) for f in sorted(SANNE.glob("*.md"))]
    for r in nl["rules"]:
        pat = rules.compile_test(r["test"])
        assert rules.count(pat, samples[r["id"]]) >= 1, r["id"]
        assert all(rules.count(pat, t) == 0 for t in texts), r["id"]


@pytest.fixture(scope="module")
def dutch(tmp_path_factory):
    t = tmp_path_factory.mktemp("nl")
    (t / "Writing" / "sanne").mkdir(parents=True)
    for f in SANNE.glob("*.md"):
        shutil.copy(f, t / "Writing" / "sanne" / f.name)
    st = t / "Store"
    st.mkdir()
    (st / "idiolect.yaml").write_text("schema_version: 1\nsources_root: ../Writing\nfacets: [lang, type]\n"
                                      "types: [essay]\ndefault_profile: sanne\n")
    learn.start(st, targets=["sanne"], profile="sanne")
    a = t / "answers.yaml"
    a.write_text("folders:\n  - {path: sanne, profile: sanne, ownership: own, facets: {type: essay}}\n"
                 "profiles:\n  - {name: sanne, subject: synthetic Dutch fixture author, consent: 'synthetic fixture, evaluation only'}\n")
    learn.answer(st, a)
    learn.stage_texts(st)
    out = learn.do_measure(st)
    for slot in [s["slot"] for s in out["slots"]]:
        cs = learn.contrast_sample(st, "sanne", slot)
        if not cs["reuse"]:
            d = pathlib.Path(cs["rewrites_dir"])
            for p in cs["paragraphs"]:
                (d / f"{p['n']}.txt").write_text("Het is belangrijk om op te merken dat " + p["text"][0].lower()
                                                 + p["text"][1:] + " Bovendien onderstreept dit het belang ervan.")
            learn.contrast_apply(st, "sanne", slot, d)
        learn.lessons_apply(st, "sanne", slot, lesson_file(t, st, "sanne", slot))
    ex = learn.examples_sample(st, "sanne", "nl.essay")
    ef = t / "examples.yaml"
    ef.write_text(yaml.safe_dump({"examples": [{"key": c["key"], "text": c["text"], "habit": "korte zinnen"}
                                               for c in ex["candidates"][:2]]}, allow_unicode=True))
    learn.examples_apply(st, "sanne", "nl.essay", ef)
    vf = t / "vocab.yaml"
    vf.write_text("- {text: binnenband, kind: term}\n")
    learn.vocab_apply(st, "sanne", vf)
    stage.Pending(Store(st)).decide(all_decision="approved")
    stage.commit(st)
    return st, [s["slot"] for s in out["slots"]]


def test_a_dutch_writer_learns_into_a_dutch_slot_with_every_metric(dutch):
    st, slots = dutch
    assert "nl.essay" in slots
    fp = json.loads((st / "profiles/sanne/nl.essay.json").read_text())
    assert len(fp["metrics"]) == 14 and fp["metrics"]["contractions_per_1k"]["value"] > 0
    k = kit.build(Store(st), "sanne", {"lang": "nl", "type": "essay"})
    assert "the thresholds were calibrated on English, not on Dutch" in k["warnings"]
    draft = body(SANNE / "02-soep-op-maandag.md")
    r = check.check(Store(st), draft, "sanne", {"lang": "nl", "type": "essay"})
    assert "calibrated on English, not on Dutch" in r["message"]


def test_dutch_starter_rules_load_with_their_language_and_catch_a_dash(dutch, tmp_path):
    st0, _ = dutch
    st = tmp_path / "Store"
    shutil.copytree(st0, st)
    shutil.copytree(st0.parent / "Writing", tmp_path / "Writing")
    out = rules.defaults(st, "sanne", lang="nl")
    assert len(out["proposed"]) == 22
    stage.Pending(Store(st)).decide(all_decision="approved")
    stage.commit(st)
    held = yaml.safe_load((st / "profiles/sanne/rulings.yaml").read_text())["entries"]
    assert {e["lang"] for e in held} == {"nl"}
    s = Store(st)
    assert len(rules.applicable(s, "sanne", "nl.essay")) == 22
    draft = body(SANNE / "02-soep-op-maandag.md").replace("Op maandag maak ik soep.", "Op maandag maak ik soep — altijd.")
    r = check.check(s, draft, "sanne", {"lang": "nl", "type": "essay"})
    assert r["status"] == "fail" and {x["lesson"] for x in r["flagged_lines"] if x["lesson"].startswith("r-")} == {"r-001"}


def test_short_paragraphs_are_joined_into_passages_for_the_contrast_sample():
    text = "\n\n".join(["Een korte alinea van zes woorden."] * 12 + ["## Kop"] + ["Nog een alinea met precies zeven woorden."] * 3)
    ps = learn.passages(text, 60, 200)
    from common import count_words
    assert ps
    assert all(60 <= count_words(p) <= 200 for p in ps)
    assert all("## Kop" not in p for p in ps)                      # a heading ends a passage
    assert learn.paragraphs(text, 60, 200) == []                     # no paragraph is long enough by itself
