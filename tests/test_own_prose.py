"""Only the writer's own prose is measured (spec §40): a reference list, tables, block quotes and long
quotations are left out of the metrics, the rulings and the signs a writer may use; remeasure brings a
profile's fingerprints up to date."""
import json
import shutil

import pytest

import check
import maintain
import measure
import stage
from store import Store
from test_ai_signs import PLAIN, learned  # noqa: F401  (fixture)

QUOTE = ('As the report put it, "organisations often respond to problems with more heavyweight approvals and '
         'longer review queues that nobody measures"; we did the same.')
EXTRA = ("\n\n| Question | Score |\n|---|---|\n| Wait; how long? | 2 |\n\n"
         "> A block quote, with its own; punctuation, which is somebody else's.\n\n"
         "## Sources\n\n- Smith, J. (2019). Organization behavior; a review. https://example.com/a\n"
         "- Doe, A. (2020). Analyzing color. https://example.com/b\n")


@pytest.fixture
def st(learned, tmp_path):  # noqa: F811
    dst = tmp_path / "Store"
    shutil.copytree(learned, dst)
    shutil.copytree(learned.parent / "Writing", tmp_path / "Writing")
    return dst


def test_the_reference_list_tables_and_block_quotes_are_not_measured():
    assert measure.metrics(PLAIN + EXTRA, "en") == measure.metrics(PLAIN, "en")


def test_a_long_quotation_is_left_out_and_a_scare_quote_stays():
    long = PLAIN + "\n" + QUOTE + "\n"
    cut = PLAIN + "\nAs the report put it, ; we did the same.\n"
    assert measure.metrics(long, "en") == measure.metrics(cut, "en")
    assert "'checked'" not in measure._unquote('It was "checked" twice.') and \
        measure._unquote('It was "checked" twice.') == 'It was "checked" twice.'


def test_the_mask_keeps_line_numbers():
    text = "One line.\n" + QUOTE + "\n| a | b |\n> quoted\n## Sources\n- a source; here"
    masked = measure.prose_mask(text)
    assert masked.count("\n") == text.count("\n")
    lines = masked.split("\n")
    assert lines[0] == "One line." and lines[2:] == ["", "", "", ""]
    assert "heavyweight" not in lines[1] and lines[1].startswith("As the report put it,")


def test_rulings_and_signs_ignore_quotations_and_sources_but_leftovers_still_fail(st):
    from test_ai_signs import commit
    import rules
    rules.add(st, "noor", "Spell in UK English.", test={"words": ["organization", "behavior", "color"]})
    rules.add(st, "noor", "No semicolons.", test={"chars": [";"]})
    commit(st)
    r = check.check(Store(st), PLAIN + EXTRA, "noor", {"type": "essay"})
    assert not [x for x in r.get("flagged_lines", []) if x["lesson"].startswith("r-")]
    r = check.check(Store(st), PLAIN + "\nWe organize; then we go.\n" + EXTRA, "noor", {"type": "essay"})
    assert {x["lesson"] for x in r["flagged_lines"] if x["lesson"].startswith("r-")} == {"r-002"}
    leftover = PLAIN + "\n## Sources\n\n- It shipped.:contentReference[oaicite:0]{index=0}\n"
    assert "a-101" in check.check(Store(st), leftover, "noor", {"type": "essay"})["ai_signs"]["found"]


def test_remeasure_proposes_the_fingerprints_again_and_changes_nothing_else(st):
    before = {f.name: f.read_text() for f in (st / "profiles/noor").glob("*.md")}
    out = maintain.remeasure(st, "noor")
    p = stage.Pending(Store(st))
    kinds = {i["kind"] for i in p.plan["items"]}
    assert out["proposed"] == len(p.plan["items"]) and kinds == {"fingerprint"}
    p.decide(all_decision="approved")
    stage.commit(st)
    fp = json.loads((st / "profiles/noor/en.essay.json").read_text())
    assert fp["counts"]["texts"] > 0
    def learned_lines(t):                       # lessons and examples, not dates or confidence
        return [ln for ln in t.splitlines() if ln.startswith(("- [", "### e-"))]
    after = {f.name: f.read_text() for f in (st / "profiles/noor").glob("*.md") if f.name in before}
    assert all(learned_lines(before[n]) == learned_lines(after[n]) for n in before if n != "changelog.md")
    assert after["changelog.md"].rstrip().split("## ")[-1].count("fingerprint approved") == 1
    with pytest.raises(Exception, match="no profile"):
        maintain.remeasure(st, "nobody")
