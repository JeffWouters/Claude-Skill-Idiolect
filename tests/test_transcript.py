"""Phase 6: the transcript adapter (spec §24)."""
import adapters
import inventory
from test_learn import make_store

VTT = """WEBVTT

NOTE made by a recorder

1
00:00:01.000 --> 00:00:04.000
<v Sam>So the first thing I tell people is simple.

2
00:00:04.200 --> 00:00:07.000
<v Sam>Measure before you <i>change</i> anything.

3
00:00:10.500 --> 00:00:13.000
<v Sam>Then change one thing at a time.
"""

SRT = """1
00:00:01,000 --> 00:00:03,000
HOST: Welcome back to the show.

2
00:00:03,500 --> 00:00:06,000
SAM: Thanks. Good to be here.
"""


def test_vtt_cues_become_paragraphs_without_timing_or_tags(tmp_path):
    f = tmp_path / "talk.vtt"
    f.write_text(VTT)
    ex = adapters.extract(f)
    assert ex.blocks == ["So the first thing I tell people is simple. Measure before you change anything.",
                         "Then change one thing at a time."]
    assert ex.meta["speakers"] == ["Sam"] and not ex.flags


def test_several_speakers_are_flagged_and_reported(tmp_path):
    f = tmp_path / "show.srt"
    f.write_text(SRT)
    ex = adapters.extract(f)
    assert ex.blocks == ["Welcome back to the show.", "Thanks. Good to be here."]
    assert ex.flags and "several speakers" in ex.flags[0]
    t = tmp_path / "notes.txt"
    t.write_text("plain notes are not a transcript")
    assert adapters.extract(t) is None
    p = tmp_path / "keynote.transcript.txt"
    p.write_text("Sam: One line.\nSam: Another line.\n")
    assert adapters.extract(p).blocks == ["One line. Another line."]


def test_inventory_row_carries_the_speaker_note(tmp_path):
    st = make_store(tmp_path)
    d = tmp_path / "Writing" / "talks"
    d.mkdir()
    (d / "show.srt").write_text(SRT * 40)
    rep = inventory.inventory(__import__("store").Store(st), targets=["talks"], dry_run=True)
    row = next(r for r in rep["rows"] if r["path"].endswith("show.srt"))
    assert "several speakers" in row.get("note", "")
