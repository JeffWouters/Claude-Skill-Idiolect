"""The shape of a piece (spec §41): paragraph and section variation, reader address and quotations, measured
per text against the writer's own range; the kit gives the ranges, check warns and never fails."""
import json
import random

import pytest

import check
import export
import kit
import shape
from common import count_words
from store import Store
from test_ai_signs import learned, st  # noqa: F401  (fixtures)


def para(n_sent, words=12, seed=0, you=False):
    rnd = random.Random(seed)
    vocab = "the river path market mill water light bridge swans brother cold home road stone field".split()
    out = []
    for i in range(n_sent):
        w = [rnd.choice(vocab) for _ in range(words - 1)]
        if you and i == 0:
            w[0] = "you"
        out.append(" ".join(w).capitalize() + ".")
    return " ".join(out)


def even_text():
    """Machine-like build: five sections of three paragraphs, each four sentences long, no reader address."""
    secs = []
    for s in range(5):
        secs.append(f"## Part {s + 1}\n\n" + "\n\n".join(para(4, seed=s * 10 + p) for p in range(3)))
    return "\n\n".join(secs)


def varied_text():
    """A writer's build: paragraphs from one line to six sentences, sections of different lengths, you."""
    sizes = [[1, 5, 2], [6, 1, 3, 1, 4, 2], [2], [1, 3, 6, 1]]
    secs = []
    for s, ps in enumerate(sizes):
        secs.append(f"## Part {s + 1}\n\n" + "\n\n".join(para(n, seed=s * 10 + i, you=i % 2 == 0)
                                                           for i, n in enumerate(ps)))
    return "\n\n".join(secs)


def test_an_even_build_and_a_varied_build_measure_apart():
    e, v = shape.measures(even_text()), shape.measures(varied_text())
    assert e["paragraph_length_cv"] == 0 and v["paragraph_length_cv"] > 0.5
    assert e["paragraph_sentences"] == 4 and e["one_sentence_paragraphs"] == 0
    assert v["one_sentence_paragraphs"] > 0.2
    assert e["section_length_cv"] == 0 and v["section_length_cv"] > 0.3
    assert e["reader_address_per_1k"] == 0 and v["reader_address_per_1k"] > 0


def test_a_short_text_has_no_shape_and_a_language_without_a_list_no_reader_address():
    assert shape.measures(para(5)) == {}
    assert "reader_address_per_1k" not in shape.measures(varied_text(), "de")
    assert shape.address_words("en")[0] == "you" and "jij" in shape.address_words("nl")


def test_quotations_count_in_the_text_and_as_block_quotes_but_not_in_the_sources():
    body = varied_text()
    quoted = body + '\n\nAs the report said, "teams that review everything ship nothing at all".\n\n> A block quote of someone else.\n'
    m = shape.measures(quoted)
    assert m["long_quotes_per_1k"] == round(2 * 1000 / count_words(quoted.replace("## ", "")), 4) or m["long_quotes_per_1k"] > 0
    assert shape.measures(body)["long_quotes_per_1k"] == 0
    with_sources = body + '\n\n## Sources\n\n- "A long title of somebody else\'s paper here", 2020.\n'
    assert shape.measures(with_sources)["long_quotes_per_1k"] == 0


def test_the_range_needs_five_texts_and_the_quote_measures_only_warn_upwards():
    texts = [varied_text()] * 4
    assert shape.ranges(texts)["features"] == {}
    w = shape.ranges([varied_text(), even_text(), varied_text(), even_text(), varied_text()])
    assert w["texts"] == 5 and set(w["features"]) >= {"paragraph_length_cv", "long_quotes_per_1k"}
    w = {"texts": 5, "features": {"long_quotes_per_1k": {"low": 2.0, "mid": 4.0, "high": 8.0, "texts": 5},
                                  "paragraph_length_cv": {"low": 0.5, "mid": 0.7, "high": 1.0, "texts": 5}}}
    rows = {r["feature"]: r["flag"] for r in shape.compare({"long_quotes_per_1k": 0.0, "paragraph_length_cv": 0.2}, w)}
    assert rows == {"long_quotes_per_1k": "ok", "paragraph_length_cv": "low"}
    rows = {r["feature"]: r["flag"] for r in shape.compare({"long_quotes_per_1k": 12.0}, w)}
    assert rows == {"long_quotes_per_1k": "high"}


def test_the_kit_and_the_export_give_the_writers_ranges(st):  # noqa: F811
    k = kit.build(Store(st), "noor", {"type": "essay"}, "the kitchen tap")
    assert k["shape"]["texts"] >= shape.MIN_TEXTS and k["shape"]["features"]
    md = kit.markdown(k)
    assert "## Shape of the piece (from the writer's own texts)" in md and "`check` warns" in md
    assert "variation in paragraph length" in md
    out = export.build(Store(st), "noor", {"type": "essay"})["prompt"]
    assert "## Shape of the piece" in out and "`check`" not in out.split("## Shape of the piece")[1].split("\n## ")[0]


def test_check_reports_the_shape_and_warns_without_failing(st):  # noqa: F811
    store = Store(st)
    r = check.check(store, even_text(), "noor", {"type": "essay"})
    sh = r["shape"]
    assert sh["compared"] >= shape.WARN_AT and sh["warn_at"] == shape.WARN_AT
    assert sh["outside"] == sum(x["flag"] != "ok" for x in sh["features"])
    assert any(x["feature"] == "paragraph_length_cv" and x["flag"] == "low" for x in sh["features"])
    if sh["warned"]:
        assert "built unlike the writer's texts" in r["message"]
    assert "- shape:" in check.readable(r)
    # the shape never decides the status on its own
    assert not any(x["lesson"].startswith("shape") for x in r.get("flagged_lines", []))
    short = check.check(store, para(5), "noor", {"type": "essay"})
    assert "shape" not in short


def test_the_kit_keeps_the_label_of_a_ruled_out_line():
    lines = kit.exclusion_lines(["- **Do not use:** the 2019 survey's wording.", "* Avoid the 2024 text."])
    assert "- **Do not use:** the 2019 survey's wording." in lines and "- Avoid the 2024 text." in lines


# ---------- the writer's quirks (spec §41.6) ----------

def quirky(n_bang=1, n_dots=1, seed=0):
    t = varied_text()
    return t.replace(".", "!", n_bang).replace("Part 2\n\n", "Part 2\n\nWell… " * n_dots, 1)


def test_quirks_are_counted_in_prose_and_not_in_code():
    counts, n = shape.quirk_counts("It works for the whole team on most days of the week! Or does it? (Mostly.) "
                                   "Then… and... `a != b` and a smile 🙂 at the end of it all.\n")
    assert counts == {"ellipses": 2, "exclamations": 1, "questions": 1, "asides": 1, "emoji": 1}
    assert shape.quirk_counts("See [the docs](https://x.example).")[0]["asides"] == 0


def test_the_quirk_allowance_follows_the_writers_rate():
    texts = [quirky(1, 1, i) for i in range(4)] + [varied_text()]
    q = shape.quirk_ranges(texts)
    assert q["exclamations"]["share"] == 0.8 and q["emoji"]["share"] == 0
    assert shape.quirk_ranges(texts[:4]) == {}
    r = q["exclamations"]
    expected, allowed = shape.quirk_allowance(r, 1000)
    assert allowed >= 1 and expected <= allowed
    assert shape.quirk_allowance(q["emoji"], 1000) == (0, 0)
    lines = "\n".join(shape.quirk_lines({"quirks": q}, 1000))
    assert "## The writer's quirks (at their rate, never more)" in lines and "- emoji: none in the writer's texts" in lines


def test_check_names_an_overdone_quirk_and_one_the_writer_never_uses():
    q = {"exclamations": {"rate": 1.0, "high": 2.0, "share": 0.6}, "emoji": {"rate": 0.0, "high": 0.0, "share": 0.0},
         "questions": {"rate": 5.0, "high": 8.0, "share": 0.9}}
    draft = varied_text().replace(".", "!", 12) + "\n\nAnd that was the end of the long walk home for all of us 🙂.\n"
    rows = {x["quirk"]: x for x in shape.compare_quirks(draft, q)}
    assert rows["exclamations"]["flag"] == "high" and rows["emoji"]["flag"] == "high"
    assert rows["questions"]["flag"] == "low"          # none, where most texts have them
    assert "never uses them" in shape.quirk_advice(rows["emoji"])
    assert shape.compare_quirks(para(5), q) == []      # too short


def test_the_kit_and_check_carry_the_quirks(st):  # noqa: F811
    k = kit.build(Store(st), "noor", {"type": "essay"}, "About 1,200 words on the kitchen tap.")
    md = kit.markdown(k)
    assert "## The writer's quirks" in md and "- exclamation marks: none in the writer's texts" in md
    q = {"questions": {"rate": 5.0, "high": 8.0, "share": 0.9}}
    assert "- questions: about 6 in a piece of 1,200 words, at most 10 (in 90% of their texts)" in \
        shape.quirk_lines({"quirks": q}, 1200)
    r = check.check(Store(st), varied_text() + "\n\nIt broke!!!! Again!!!\n", "noor", {"type": "essay"})
    assert {x["quirk"] for x in r["quirks"]} == set(shape.QUIRKS)
    assert r["status"] == check.check(Store(st), varied_text(), "noor", {"type": "essay"})["status"]

