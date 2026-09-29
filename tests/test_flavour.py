"""Language flavour (spec §34): the pack detectors, detection in every learn, the flavour file with how
each trace is recognised and how often the writer shows it, and its use in the kit and the check."""
import glob
import pathlib
import re

import pytest
import yaml

import check as checkmod
import flavour
import kit as kitmod
import langpack
import learn
import maintain
import stage
from common import count_words, load_yaml_text
from store import Store
from test_learn import FIX, answers, make_store

ROOT = pathlib.Path(__file__).resolve().parent.parent


# ---------- the packs ----------

PACKS = ("en", "nl", "de", "fr", "es") + ("it", "pt", "pl", "ru", "uk", "tr", "sv", "nb", "da")


def test_the_packs_detectors_pass_their_own_examples_and_counter_examples():
    for code in PACKS:
        assert langpack.check(code) == [], code
        assert len(flavour.detectors(code)) >= 3, code
        for d in flavour.detectors(code):
            assert d["examples"] and d["not"], d["id"]
    assert len(flavour.detectors("en")) >= 40


def test_english_detectors_cover_the_widely_spoken_first_languages():
    origins = {o for d in flavour.detectors("en") for o in d["origins"]}
    for code in ("de", "nl", "fr", "es", "it", "pt", "pl", "ru", "tr", "sv", "no", "da", "hi", "zh", "ja", "ar"):
        assert code in origins, code
    # Norwegian is the string "no", never YAML 1.1's false
    assert all(isinstance(o, str) for d in flavour.detectors("en") for o in d["origins"])


def test_word_order_traces_are_detected_without_native_inversions():
    found = {x["detector"] for x in flavour.detect_text("en", (
        "Then have we a problem. The more versions you target, the less sophisticated will your code get. "
        "I drive tomorrow to Berlin."))["found"]}
    assert found == {"verb-before-subject", "comparative-inversion", "time-before-place"}
    native = ("Often have I seen it. So do I. Only then did we notice. Now can you see it? The longer you wait, the "
              "harder it gets. He came yesterday to fix the boiler. I drive to Berlin tomorrow.")
    assert flavour.detect_text("en", native)["found"] == []


@pytest.mark.parametrize("lang,text", [
    ("it", "Questo fa senso. Ho realizzato che era sbagliato."),
    ("pt", "Realizei que estava errado. A reunião toma lugar amanhã."),
    ("pl", "To robi sens. Mieliśmy dobry czas."),
    ("ru", "Это делает смысл. Встреча берёт место завтра."),
    ("uk", "Це робить сенс. Я приймаю участь у конференції."),
    ("tr", "Bu anlam yapıyor. Hatayı sonra realize ettim."),
    ("sv", "Det gör mening. Idag jag går till jobbet."),
    ("nb", "Det gjør mening. I dag jeg går på jobb."),
    ("da", "Det gør mening. I dag jeg går på arbejde."),
    ("de", "Heute ich gehe ins Büro."),
    ("nl", "Vandaag ik ga naar kantoor."),
])
def test_every_pack_detects_traces_of_english(lang, text):
    assert flavour.detect_text(lang, text)["found"], lang


def test_german_french_and_spanish_packs_detect_english_traces():
    assert flavour.detect_text("de", "Wir müssen eine Entscheidung machen. Das ist, warum.")["found"]
    assert flavour.detect_text("fr", "Ça fait du sens. Je suis faim.")["found"]
    assert flavour.detect_text("es", "Eso hace sentido. La reunión toma lugar mañana.")["found"]
    assert {o for c in ("fr", "es") for d in flavour.detectors(c) for o in d["origins"]} == {"en"}
    assert {o for d in flavour.detectors("de") for o in d["origins"]} == {"en", "nl"}


def test_a_broken_detector_is_reported(tmp_path, monkeypatch):
    lang = tmp_path / "xx"
    lang.mkdir()
    (lang / "pack.yaml").write_text("code: xx\nname: Test\nversion: '1.0'\ncalibrated: false\n")
    (lang / "flavours.yaml").write_text(yaml.safe_dump({"version": "1.0", "detectors": [
        {"id": "a", "name": "A", "origins": ["de"], "how": "h", "pattern": r"\bfoo\b", "examples": ["bar"],
         "not": ["foo here"]},
        {"id": "a", "name": "B", "origins": ["German"], "how": "h", "pattern": "(", "examples": ["x"]}]}))
    monkeypatch.setattr(flavour, "LANG_DIR", tmp_path)
    monkeypatch.setattr(langpack, "LANG_DIR", tmp_path)
    problems = " | ".join(langpack.check("xx"))
    for part in ("misses its example 'bar'", "matches its counter-example 'foo here'", "id used twice",
                 "origin 'German'", "does not compile"):
        assert part in problems, part


@pytest.mark.parametrize("author,lang", [("katharine-fullerton-gerould", "en"), ("robert-cortes-holliday", "en"),
                                         ("samuel-mcchord-crothers", "en"), ("synthetic-noor", "en"),
                                         ("synthetic-idris", "en"), ("native-de", "de"), ("native-fr", "fr"),
                                         ("native-es", "es"), ("synthetic-sanne", "nl")]
                         + [(f"native-{c}", c) for c in ("it", "pt", "pl", "ru", "uk", "tr", "sv", "nb", "da")])
def test_native_prose_barely_triggers_the_detectors(author, lang):
    """The false-alarm test: native writers' texts (spec §34.2). Under 5 per 100,000 words."""
    words = hits = 0
    for f in glob.glob(str(FIX / author / "[0-9]*.md")):
        t = pathlib.Path(f).read_text(encoding="utf-8").split("\n---\n", 1)[-1]
        words += count_words(t)
        hits += sum(x["count"] for x in flavour.detect_text(lang, t)["found"])
    assert words > 1000 and hits * 1000 / words < 0.05, (author, hits, words)


def test_detect_names_what_it_finds_in_any_text():
    out = flavour.detect_text("en", "Else, you become an error. I know already the answer. It is on your own risk.")
    found = {x["detector"] for x in out["found"]}
    assert {"else-opener", "become-get", "adverb-before-object", "own-risk"} <= found


# ---------- learning it ----------

TRACES = {0: "Else, the drip keeps going.", 1: "I know already the answer.", 2: "Else, it waits.",
          3: "I know already the trick.", 4: "Else, nothing.", 5: "Meanwhile I am used to it."}


def flavoured_store(tmp_path):
    st = make_store(tmp_path)
    files = sorted((tmp_path / "Writing" / "noor").glob("*.md"))
    for i, f in enumerate(files):
        if i in TRACES:
            paras = f.read_text(encoding="utf-8").split("\n\n")
            paras[2] = paras[2].rstrip() + " " + TRACES[i]
            f.write_text("\n\n".join(paras), encoding="utf-8")
    return st


def start(tmp_path, st):
    learn.start(st, targets=["noor"], profile="noor")
    learn.answer(st, answers(tmp_path, "noor", "noor"))
    learn.stage_texts(st)
    learn.do_measure(st)


def key_with(st, text):
    run = learn.Run(st)
    return next(k for k, t in flavour._run_texts(run, "noor", "en") if text in t)


def proposal(tmp_path, st, extra=()):
    f = tmp_path / "flavour.yaml"
    markers = [{"detector": "else-opener", "origin": "de"}, {"detector": "adverb-before-object", "origin": "de"},
               {"name": "'Meanwhile' for 'by now'", "origin": "de",
                "how": "'Meanwhile' where English says 'by now' (German mittlerweile).",
                "examples": [{"key": key_with(st, TRACES[5]), "quote": TRACES[5]}]}] + list(extra)
    f.write_text(yaml.safe_dump({"markers": markers}))
    return f


def approve(st, reject=()):
    p = stage.Pending(Store(st))
    p.decide(reject=list(reject), all_decision="approved")
    return stage.commit(st)


def test_every_learn_asks_for_the_flavour_step_and_the_sample_finds_the_traces(tmp_path):
    st = flavoured_store(tmp_path)
    start(tmp_path, st)
    assert "flavour noor/en" in learn.next_step(st)["next"]
    s = flavour.sample(st, "noor", "en")
    det = {d["detector"]: d for d in s["detected"]}
    assert det["else-opener"]["hits"] == 3 and det["else-opener"]["texts"] == 3
    assert det["adverb-before-object"]["hits"] == 2
    assert s["origins"][0] in ("de", "nl") and pathlib.Path(s["sample"]).exists()
    assert all(m["context"] for m in det["else-opener"]["matches"])
    stage.discard(st)


def test_the_flavour_file_says_how_each_trace_is_recognised_and_how_often(tmp_path):
    st = flavoured_store(tmp_path)
    start(tmp_path, st)
    out = flavour.apply(st, "noor", "en", proposal(tmp_path, st))
    assert out["problems"] == [] and len(out["staged"]) == 3
    assert out["if_all_approved"]["strength"] == "light"
    assert learn.next_step(st)["next"].startswith("model steps left") and "flavour" not in learn.next_step(st)["next"]
    approve(st)
    fl = load_yaml_text((st / "profiles/noor/en.flavour.yaml").read_text())
    by = {m["name"]: m for m in fl["markers"]}
    els = by["'Else,' to open a sentence"]
    assert els["pattern"] and els["detector"] == "else-opener" and els["how"]
    assert els["count"] == {"hits": 3, "texts": 3, "per_1k": els["count"]["per_1k"], "measured": "pattern"}
    assert all(e.lower().startswith("else,") for e in els["examples"])
    mw = by["'Meanwhile' for 'by now'"]
    assert mw["count"]["measured"] == "examples" and mw["count"]["hits"] == 1 and "pattern" not in mw
    assert fl["origins"] == ["de"] and fl["strength"] == "light"
    assert fl["rate"]["texts"] == 6 and fl["rate"]["of"] == 10
    total = sum(m["count"]["hits"] for m in fl["markers"])
    assert fl["rate"]["per_1k"] == round(total * 1000 / fl["rate"]["words"], 2)
    assert fl["rate"]["max_per_1k"] > fl["rate"]["per_1k"]
    assert flavour.readable(fl).count("e.g.") >= 3


def test_bad_proposals_are_reported_not_learned(tmp_path):
    st = flavoured_store(tmp_path)
    start(tmp_path, st)
    k = key_with(st, TRACES[0])
    f = proposal(tmp_path, st, extra=[
        {"detector": "no-such-thing"},
        {"name": "Too broad", "origin": "de", "how": "Every 'the'.", "pattern": r"\bthe\b",
         "examples": [{"key": k, "quote": "Else, the drip keeps going."}]},
        {"name": "Misses", "origin": "de", "how": "x", "pattern": r"\bzzz\b",
         "examples": [{"key": k, "quote": "Else, the drip keeps going."}]},
        {"name": "Invented", "origin": "de", "how": "x", "examples": [{"key": k, "quote": "Words the writer never wrote."}]},
        {"name": "Bad origin", "origin": "German", "how": "x", "examples": [{"key": k, "quote": "Else, the drip keeps going."}]},
    ])
    out = flavour.apply(st, "noor", "en", f)
    msg = " | ".join(out["problems"])
    for part in ("unknown detector 'no-such-thing'", "too broad", "misses the example", "example not found",
                 "Invented: no verified example and no pattern", "not a language code"):
        assert part in msg, part
    plan = stage.Pending(Store(st)).plan
    names = [i["summary"] for i in plan["items"] if i["kind"] == "flavour"]
    assert not any("Invented" in n for n in names)
    assert any("Too broad" in n and "its examples" in n for n in names)      # kept, counted by its example
    stage.discard(st)


def test_ids_stay_rejections_stay_gone_and_unproposed_markers_are_removed(tmp_path):
    st = flavoured_store(tmp_path)
    start(tmp_path, st)
    flavour.apply(st, "noor", "en", proposal(tmp_path, st))
    p = stage.Pending(Store(st))
    adv = next(i["id"] for i in p.plan["items"] if "Adverb" in i["summary"])
    approve(st, reject=[adv])
    fl = load_yaml_text((st / "profiles/noor/en.flavour.yaml").read_text())
    assert [r["detector"] for r in fl["rejected"]] == ["adverb-before-object"]
    ids = {m["name"]: m["id"] for m in fl["markers"]}
    # relearn: the same proposal keeps ids, drops the rejected detector, and removes what is not proposed
    start(tmp_path, st)
    f = tmp_path / "again.yaml"
    f.write_text(yaml.safe_dump({"markers": [{"detector": "else-opener", "origin": "de"},
                                             {"detector": "adverb-before-object"}]}))
    out = flavour.apply(st, "noor", "en", f)
    assert out["dropped_as_rejected"] == ["Adverb between verb and object"]
    plan = stage.Pending(Store(st)).plan
    fitems = [i for i in plan["items"] if i["kind"] == "flavour"]
    assert [(i["op"], i["ref"]) for i in fitems] == [("remove", ids["'Meanwhile' for 'by now'"])]
    approve(st)
    fl2 = load_yaml_text((st / "profiles/noor/en.flavour.yaml").read_text())
    assert [m["id"] for m in fl2["markers"]] == [ids["'Else,' to open a sentence"]]
    assert fl2["last_id"] >= 3 and fl2["rejected"] == fl["rejected"]


def test_forgetting_a_text_recounts_and_drops_its_examples(tmp_path):
    st = flavoured_store(tmp_path)
    start(tmp_path, st)
    flavour.apply(st, "noor", "en", proposal(tmp_path, st))
    approve(st)
    before = load_yaml_text((st / "profiles/noor/en.flavour.yaml").read_text())
    key = key_with_store(st, TRACES[5])
    maintain.forget(st, key)
    approve(st)
    after = load_yaml_text((st / "profiles/noor/en.flavour.yaml").read_text())
    assert "'Meanwhile' for 'by now'" not in {m["name"] for m in after["markers"]}   # its only example went
    assert after["rate"]["of"] == before["rate"]["of"] - 1
    assert all(key not in m.get("sources", []) for m in after["markers"])


def key_with_store(st, text):
    s = Store(st)
    return next(k for k, e in s.manifest["texts"].items() if e.get("cached") and text in s.corpus_text(k))


def test_rollback_keeps_the_flavour_ids_and_rejections(tmp_path):
    st = flavoured_store(tmp_path)
    start(tmp_path, st)
    approve(st)                                 # a first learn without flavour: its snapshot has no file
    start(tmp_path, st)
    flavour.apply(st, "noor", "en", proposal(tmp_path, st))
    p = stage.Pending(Store(st))
    adv = next(i["id"] for i in p.plan["items"] if "Adverb" in i["summary"])
    approve(st, reject=[adv])
    snaps = sorted(p.name for p in (st / "profiles/noor/snapshots").iterdir())
    maintain.rollback(st, "noor", snaps[-1])
    approve(st)
    fl = load_yaml_text((st / "profiles/noor/en.flavour.yaml").read_text())
    assert fl["markers"] == [] and fl["strength"] == "none" and fl["last_id"] >= 3
    assert [r["detector"] for r in fl["rejected"]] == ["adverb-before-object"]


# ---------- using it ----------

@pytest.fixture
def learned(tmp_path):
    st = flavoured_store(tmp_path)
    start(tmp_path, st)
    flavour.apply(st, "noor", "en", proposal(tmp_path, st))
    approve(st)
    return st


def test_the_kit_gives_the_rate_and_a_count_for_the_piece(learned, tmp_path):
    k = kitmod.build(Store(learned), "noor", {"lang": "en", "type": "essay"}, "Write 2000 words on taps.")
    assert k["words"] == 2000
    md = kitmod.markdown(k)
    sec = md[md.index("## Language flavour"):]
    assert "## Language flavour: light (German)" in md and "never more" in sec and "never as spelling mistakes" in sec
    assert re.search(r"For this piece of about 2000 words: about \d+ \(at most \d+\)", sec)
    assert "'Else,' opens a sentence" in sec and "For example:" in sec
    off = kitmod.markdown(kitmod.build(Store(learned), "noor", {"lang": "en", "type": "essay"}, "", flavour_mode="off"))
    assert "## Language flavour: off" in off and "standard language" in off
    short = kitmod.markdown(kitmod.build(Store(learned), "noor", {"lang": "en", "type": "essay"}, "", words=150))
    assert "none, or at most one" in short
    assert "## Language flavour" in kitmod.markdown(kitmod.build(Store(learned), "noor", {"lang": "en", "type": "essay"}, ""), "none")


def _draft(n_traces, paras=8):
    para = "The tap drips. I fix it on a Sunday. The washer is old, and the seat is worn. " * 3
    out = [para.strip() + (" Else, the drip goes on." if i < n_traces else "") for i in range(paras)]
    return "\n\n".join(out)


def test_the_check_fails_a_caricature_but_never_too_little(learned):
    store = Store(learned)
    fl = flavour.read(store, "noor", "en")
    allowed = flavour.allowance(fl, count_words(_draft(0)))
    ok = checkmod.check(store, _draft(0), "noor", {"lang": "en", "type": "essay"})
    assert ok["flavour"]["hits"] == 0 and not any(x.get("lesson", "").startswith("f-") for x in ok.get("flagged_lines", []))
    over = checkmod.check(store, _draft(allowed + 2), "noor", {"lang": "en", "type": "essay"})
    assert over["status"] == "fail" and over["flavour"]["hits"] == allowed + 2
    assert "language flavour" in over["message"]
    assert any(x["reason"].startswith("language flavour") for x in over["flagged_lines"])
    one = checkmod.check(store, _draft(1), "noor", {"lang": "en", "type": "essay"}, flavour_mode="off")
    assert one["flavour"]["allowed"] == 0 and one["status"] == "fail"
    assert "without them" in one["message"]
    assert "language flavour (off)" in checkmod.readable(one)


def test_guide_and_export_carry_the_flavour(learned):
    import export
    import guide
    g = guide.build(Store(learned), "noor", {"lang": "en", "type": "essay"})["guide"]
    assert "## Language flavour" in g and "German" in g
    e = export.build(Store(learned), "noor", {"lang": "en", "type": "essay"})["prompt"]
    assert "## Language flavour" in e


def test_a_trace_never_spans_a_paragraph_break():
    """Found learning a blog: with its code blocks removed, 'as you can see' ended one paragraph and
    'Now that the ...' began the next, which read as 'see now that' (adverb before the object)."""
    assert flavour.detect_text("en", "It is added to the pull request as you can see\n\nNow that the checks pass, merge it.")["found"] == []
    assert flavour.detect_text("en", "You know already the name of the cmdlet.")["found"]
