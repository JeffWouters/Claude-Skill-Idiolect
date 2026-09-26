"""Phase 6 exit, first part: a publishing skill gates on check with interactive=false (spec §25)."""
import importlib.util
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("gate", ROOT / "evals" / "callers" / "publish-demo" / "scripts" / "gate.py")
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)
IDIOLECT = ROOT / "idiolect"
STORE = ROOT / "evals" / "store"
RUN6 = ROOT / "evals" / "runs" / "20260926T163530Z"


def test_the_writers_own_text_is_published_and_a_plain_draft_is_blocked(tmp_path):
    own = next(p for p in sorted((RUN6 / "passages").glob("synthetic-noor-*.md")))
    out = gate.gate(IDIOLECT, STORE, "synthetic-noor", "essay", own, tmp_path / "published")
    assert out["action"] == "published" and (tmp_path / "published" / own.name).exists()
    plain = RUN6 / "drafts" / "plain" / own.name
    out = gate.gate(IDIOLECT, STORE, "synthetic-noor", "essay", plain, tmp_path / "published2")
    assert out["action"] == "blocked" and out["status"] == "fail" and out["flagged"]
    assert not (tmp_path / "published2").exists()


def test_no_store_and_no_slot_stop_without_publishing(tmp_path):
    f = tmp_path / "post.md"
    f.write_text("A short post. " * 60)
    out = gate.gate(IDIOLECT, tmp_path / "nowhere", "sam", "essay", f, tmp_path / "pub")
    assert out["action"] == "stopped" and out["status"] in ("no_store", "error")
    out = gate.gate(IDIOLECT, STORE, "nobody", "essay", f, tmp_path / "pub")
    assert out["action"] == "stopped" and out["status"] in ("no_slot", "error") and out["message"]
    assert not (tmp_path / "pub").exists() and json.dumps(out)
