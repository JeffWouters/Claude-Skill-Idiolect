"""Phase 5: interview (spec §21). Answers become interview texts of the slot through a learn run."""
import glob
import json

import pytest

import interview
import learn
import stage
from common import StoreError
from store import Store
from test_learn import FIX, full_learn, lesson_file, make_store


def test_answers_become_interview_texts_after_approval(tmp_path):
    st = make_store(tmp_path)
    full_learn(tmp_path, st, "noor", "noor")
    fp0 = json.loads((st / "profiles" / "noor" / "en.essay.json").read_text())
    out = interview.start(st, "noor", "en", "essay")
    assert out["slot"] == "en.essay"
    with pytest.raises(StoreError, match="at least 150"):
        short = tmp_path / "short.md"
        short.write_text("I like short sentences. They land.")
        interview.add(st, short)
    extra = sorted(glob.glob(str(FIX / "synthetic-noor" / "[0-9]*.md")))[10:12]
    for i, f in enumerate(extra):
        body = open(f).read().split("---", 2)[-1] if open(f).read().startswith("---") else open(f).read()
        a = tmp_path / f"answer-{i}.md"
        a.write_text(body)
        interview.add(st, a)
    with pytest.raises(StoreError, match="already"):
        interview.add(st, a)
    assert len(interview.answers(st)["answers"]) == 2
    learn.do_measure(st)
    for slot in ("en.essay", "en._"):
        learn.lessons_apply(st, "noor", slot, lesson_file(tmp_path, st, "noor", slot))
    stage.Pending(Store(st)).decide(all_decision="approved")
    stage.commit(st)
    s = Store(st)
    iv = {k: e for k, e in s.manifest["texts"].items() if e["origin"] == "interview"}
    assert len(iv) == 2 and all(e["path"] is None and e["cached"] and e["facets"]["type"] == "essay"
                                and e["profiles"]["noor"]["ownership"] == "own" for e in iv.values())
    fp1 = json.loads((st / "profiles" / "noor" / "en.essay.json").read_text())
    assert fp1["counts"]["texts"] == fp0["counts"]["texts"] + 2
    assert "interview" in (st / "profiles" / "noor" / "changelog.md").read_text()
    # a later learn neither loses them nor reports them unreachable
    learn.start(st, targets=["noor"], profile="noor")
    assert not learn.Run(st).state["unreachable"]
    stage.discard(st)


def test_interview_needs_a_known_profile_and_type(tmp_path):
    st = make_store(tmp_path)
    full_learn(tmp_path, st, "noor", "noor")
    with pytest.raises(StoreError, match="no profile"):
        interview.start(st, "nobody", "en", "essay")
    with pytest.raises(StoreError, match="types"):
        interview.start(st, "noor", "en", "sonnet")
    assert not (st / ".state" / "lock").exists()
