"""The built-in signs of machine-written text (spec §37): sound lists, no false alarms on human text,
check failing a draft in every profile, the writer's own rate, switching a sign off, and the profile's
own starter rules deciding."""
import glob
import json
import pathlib
import re
import shutil

import pytest

import aisigns
import check
import kit
import rules
import stage
from common import StoreError, count_words, read_store_file
from store import Store
from test_learn import full_learn, make_store

ROOT = pathlib.Path(__file__).resolve().parent.parent
FIX = ROOT / "evals" / "fixtures"
HUMAN_EN = ("katharine-fullerton-gerould", "robert-cortes-holliday", "samuel-mcchord-crothers")
# signs added with the built-in list (not carried over from the starter set): held to a false-alarm bar
NEW = ("a-005", "a-009", "a-010", "a-026", "a-027", "a-028", "a-029", "a-030", "a-031")

PLAIN = """The river path was closed for most of the spring, so we walked the long way round through the
market and past the old mill. It took an hour more than it should have, and nobody minded much.

By the time we reached the bridge the light had gone soft and the water was high and brown. My
brother counted the swans. There were eleven, which he said was a record, though he had no way to
know. We stood there until the cold came up off the water and then we turned for home.
"""


def body(f):
    t = pathlib.Path(f).read_text(encoding="utf-8")
    return t.split("---", 2)[-1] if t.startswith("---") else t


def windows(text, size=500):
    out, cur, n = [], [], 0
    for p in re.split(r"\n\s*\n", text):
        cur.append(p)
        n += count_words(p)
        if n >= size:
            out.append("\n\n".join(cur))
            cur, n = [], 0
    return out


# ---------- the lists ----------

@pytest.mark.parametrize("name", ["universal", "en", "nl"])
def test_every_sign_file_is_sound(name):
    assert aisigns.problems(name) == []


def test_ids_are_shared_across_languages_and_never_clash_with_the_universal_ones():
    en = {s["id"]: s for s in aisigns._read("en")["signs"]}
    nl = {s["id"]: s for s in aisigns._read("nl")["signs"]}
    uni = {s["id"] for s in aisigns._read("universal")["signs"]}
    assert set(nl) <= set(en) and not (uni & set(en))
    for sid, s in nl.items():
        assert (s["category"], s["tier"], s.get("starter")) == (en[sid]["category"], en[sid]["tier"], en[sid].get("starter")), sid
    # every starter rule is extended by exactly one sign, so a profile's copy of it decides
    for lang, data in (("en", en), ("nl", nl)):
        starters = [s["starter"] for s in data.values() if s.get("starter")]
        assert sorted(starters) == sorted(r["id"] for r in rules.starter(lang)["rules"]), lang


def test_a_language_without_a_list_gets_the_language_independent_signs():
    d = aisigns.load("de")
    assert d["covered"] is False and {s["id"] for s in d["signs"]} == {"a-101"}
    assert aisigns.load("en-gb")["covered"] is True


# ---------- no false alarms on human text ----------

def test_the_always_tier_never_fires_on_human_text():
    always_en = [s for s in aisigns.load("en")["signs"] if s["tier"] == "always"]
    for author in HUMAN_EN:
        for f in sorted(glob.glob(str(FIX / author / "*.md"))):
            assert aisigns.flag(body(f), always_en, {}, 1000) == [], f
    uni = aisigns.load("de")["signs"]
    for f in sorted(glob.glob(str(FIX / "native-*" / "*.md"))):
        assert aisigns.flag(body(f), uni, {}, 1000) == [], f


def test_the_new_signs_rarely_fire_on_human_text_even_for_a_writer_who_never_uses_them():
    """In passages of about 500 words of public-domain essays, each sign added with the built-in list
    fires in at most 2% (measured at 0.3% or less when the list was built); a writer who never does it
    is the strictest case, since then a single use counts."""
    signs = [s for s in aisigns.load("en")["signs"] if s["id"] in NEW]
    ws = [w for a in HUMAN_EN for f in sorted(glob.glob(str(FIX / a / "*.md"))) for w in windows(body(f))]
    assert len(ws) > 200
    for s in signs:
        share = sum(bool(aisigns.flag(w, [s], {}, count_words(w))) for w in ws) / len(ws)
        assert share <= 0.02, (s["id"], share)


def test_front_matter_is_not_a_horizontal_rule():
    s = [x for x in aisigns.load("en")["signs"] if x["id"] == "a-031"]
    assert aisigns.flag("---\ntitle: x\n---\n\nText.\n", s, {}, 10) == []
    assert len(aisigns.flag("Intro\n\n---\n\nOne\n\n---\n\nTwo", s, {}, 10)) == 2


# ---------- flagging against the writer's own rate ----------

def test_the_writers_own_rate_allows_a_sign_up_to_twice_that_rate():
    dash = [x for x in aisigns.load("en")["signs"] if x["id"] == "a-006"]
    one = "It works — mostly.\n" + "word " * 199
    four = "It works — mostly — and — then — not.\n" + "word " * 195
    assert aisigns.flag(one, dash, {}, 200)                          # the writer never does it: one is enough
    assert aisigns.flag(one, dash, {"a-006": 5.0}, 200) == []        # one use: within their habit
    assert aisigns.flag(four, dash, {"a-006": 5.0}, 200)             # 20 per 1,000 words: four times theirs
    always = [x for x in aisigns.load("en")["signs"] if x["id"] == "a-001"]
    assert aisigns.flag("As an AI, I cannot say.", always, {"a-001": 50.0}, 10)   # always: rate ignored


def test_a_density_sign_needs_its_minimum():
    s = [x for x in aisigns.load("en")["signs"] if x["id"] == "a-009"]
    assert aisigns.flag("We leverage the API.", s, {}, 4) == []
    assert len(aisigns.flag("We leverage the API to enhance it.", s, {}, 7)) == 1


def test_scan_works_without_a_store(tmp_path, capsys):
    f = tmp_path / "t.md"
    f.write_text("Certainly! Here is the answer.\n\nIt shipped in 2024.:contentReference[oaicite:0]{index=0}\n")
    assert aisigns.main(["scan", "--file", str(f), "--json"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert {x["lesson"] for x in out["lines"]} == {"a-026", "a-101"}


# ---------- in check and kit, for every profile ----------

@pytest.fixture(scope="module")
def learned(tmp_path_factory):
    t = tmp_path_factory.mktemp("learned")
    st = make_store(t)
    full_learn(t, st, "noor", "noor")
    return st


@pytest.fixture
def st(learned, tmp_path):
    dst = tmp_path / "Store"
    shutil.copytree(learned, dst)
    shutil.copytree(learned.parent / "Writing", tmp_path / "Writing")
    return dst


def commit(st, reject=()):
    stage.Pending(Store(st)).decide(reject=list(reject), all_decision="approved")
    return stage.commit(st)


def run_check(st, text):
    return check.check(Store(st), text, "noor", {"type": "essay"})


def test_check_fails_machine_text_in_a_profile_with_no_rulings(st):
    assert not (st / "profiles/noor/rulings.yaml").exists()
    clean = run_check(st, PLAIN)
    assert clean["ai_signs"]["found"] == [] and clean["ai_signs"]["checked"] > 30
    r = run_check(st, PLAIN + "\nAs an AI, I cannot verify the count.\n")
    assert r["status"] == "fail" and r["ai_signs"]["found"] == ["a-001"]
    assert "machine-written" in r["message"]
    assert any(x["lesson"] == "a-001" for x in r["flagged_lines"])
    assert "sounds like AI (a-001" in check.readable(r)
    r = run_check(st, PLAIN.replace("for home.", "for home, highlighting the importance of family."))
    assert r["status"] == "fail" and "a-015" in r["ai_signs"]["found"]


def test_the_kit_carries_the_signs_and_the_guidance(st):
    k = kit.build(Store(st), "noor", {"type": "essay"}, "the kitchen tap")
    md = kit.markdown(k)
    assert "## Never sound like AI (built into Idiolect, signs 1.0)" in md
    assert "As an AI" in md and "Do not group in threes" in md
    assert k["ai_signs"]["covered"] and not k["ai_signs"]["allowed"]
    json.dumps(k)                                      # the kit stays plain data


def test_a_writer_can_switch_a_sign_off_but_never_an_always_one(st):
    with pytest.raises(StoreError, match="cannot be switched off"):
        aisigns.allow(st, "noor", "a-001")
    text = PLAIN + "\nWe leverage the bridge to enhance the walk.\n"
    assert "a-009" in run_check(st, text)["ai_signs"]["found"]
    out = aisigns.allow(st, "noor", "a-009")
    assert out["proposed"] == "r-001"
    assert "a-009" in run_check(st, text)["ai_signs"]["found"]           # nothing changes before approval
    commit(st)
    entry = read_store_file(st / "profiles/noor/rulings.yaml", "rulings")["entries"][0]
    assert entry["overrides"] == "a-009" and entry["lang"] == "en"
    r = run_check(st, text)
    assert "a-009" not in r["ai_signs"]["found"] and r["ai_signs"]["allowed"] == ["a-009"]
    k = kit.build(Store(st), "noor", {"type": "essay"})
    md = kit.markdown(k)
    assert "Switched off for this writer" in md and "a-009" in md
    assert not k["rulings"]                            # shown with the signs, not as a ruling


def test_the_profiles_own_starter_rule_decides_instead_of_the_sign(st):
    rules.defaults(st, "noor", categories=["punctuation"])
    commit(st)
    r = run_check(st, PLAIN.replace("round through the", "round — through the"))
    lessons = {x["lesson"] for x in r["flagged_lines"]}
    assert "r-001" in lessons and "a-006" not in lessons               # flagged once, by the profile's rule
    assert "a-006" not in r["ai_signs"]["found"]


def test_a_declined_starter_rule_switches_its_sign_off(st):
    rules.defaults(st, "noor", categories=["punctuation"])
    p = stage.Pending(Store(st))
    dash = [i["id"] for i in p.plan["items"] if p.payload(i["id"])["ruling"]["entry"]["starter"]["id"] == "s-001"]
    commit(st, reject=dash)
    r = run_check(st, PLAIN.replace("round through the", "round — through the"))
    assert "a-006" not in r["ai_signs"]["found"] and "a-006" in r["ai_signs"]["allowed"]
