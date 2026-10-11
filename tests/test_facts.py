"""Facts and an occasion before drafting (spec §38): the kit counts the brief's specifics and says when
to ask for them; check counts placeholders and warns about one in the opening, never failing for it."""
import pytest

import check
import kit
from store import Store
from test_ai_signs import PLAIN, learned, st  # noqa: F401  (fixtures)


@pytest.mark.parametrize("brief, enough", [
    ("Write about DNS.", False),
    ("A post on Microsoft Teams, SharePoint and OneDrive for Acme. Around 600 words.", False),  # names only
    ("Around 1,050 words on why Sam moved acme.example to a new host in March 2024 after 3 outages; "
     "mention Get-DnsServerZone and the \"it was always DNS\" joke.", True),
    ("Sam's notes: the build broke twice, `make test` took 14 minutes, and Priya fixed it.", True),
])
def test_the_kit_counts_the_specifics_a_brief_gives(brief, enough):
    f = kit.brief_specifics(brief)
    assert f["enough"] is enough
    assert kit.brief_specifics("   ") is None and kit.brief_specifics(None) is None


def test_the_length_of_the_piece_is_not_a_fact():
    assert kit.brief_specifics("About 1,200 words on the kitchen tap.")["numbers"] == 0
    assert kit.brief_specifics("The tap dripped 40 times an hour.")["numbers"] == 1


def test_the_kit_asks_for_facts_only_when_the_brief_lacks_them(st):  # noqa: F811
    thin = kit.markdown(kit.build(Store(st), "noor", {"type": "essay"}, "An essay about the kitchen tap."))
    assert "## Facts for this piece" in thin and "ask the writer once" in thin
    assert "interactive=false, do not ask" in thin and "Never open the draft on a placeholder" in thin
    rich = kit.markdown(kit.build(Store(st), "noor", {"type": "essay"},
                                  "The tap at 14 Mill Lane dripped for 3 weeks; the plumber said \"it is the washer\"."))
    assert "## Facts for this piece" in rich and "ask the writer" not in rich
    assert thin.index("## Facts for this piece") < thin.index("## Example passages")
    assert "## Facts for this piece" not in kit.markdown(kit.build(Store(st), "noor", {"type": "essay"}))


def test_check_counts_placeholders_and_warns_about_one_in_the_opening(st):  # noqa: F811
    store = Store(st)
    clean = check.check(store, PLAIN, "noor", {"type": "essay"})
    assert "placeholders" not in clean
    later = PLAIN + "\nIt was [number needed: how many] years since the flood.\n"
    r = check.check(store, later, "noor", {"type": "essay"})
    assert r["placeholders"] == {"count": 1, "in_opening": False}
    assert "first paragraph has a placeholder" not in r.get("message", "")
    opening = "---\ntitle: x\n---\n\n# The river\n\n[example needed: what prompted the walk]\n\n" + later
    r = check.check(store, opening, "noor", {"type": "essay"})
    assert r["placeholders"] == {"count": 2, "in_opening": True}
    assert "first paragraph has a placeholder" in r["message"]
    assert "placeholders: 2 (one in the opening paragraph)" in check.readable(r)
    assert r["status"] == check.check(store, later, "noor", {"type": "essay"})["status"]   # never a fail by itself


def test_a_long_piece_gets_a_point_ledger_and_a_short_one_does_not(st):  # noqa: F811
    long = kit.markdown(kit.build(Store(st), "noor", {"type": "essay"}, "About 4,500 words on the kitchen tap."))
    assert "## A long piece: one place per point" in long and "About 4,500 words" in long
    assert long.index("## A long piece") < long.index("## Example passages")
    for brief in ("About 800 words on the kitchen tap.", "An essay on the kitchen tap."):
        assert "## A long piece" not in kit.markdown(kit.build(Store(st), "noor", {"type": "essay"}, brief))
    assert "## A long piece" in kit.markdown(kit.build(Store(st), "noor", {"type": "essay"}, "On the tap.", words=1500))


def test_every_voice_is_told_to_say_each_point_once(st):  # noqa: F811
    md = kit.markdown(kit.build(Store(st), "noor", {"type": "essay"}, "the kitchen tap"))
    assert "Say each point once." in md
