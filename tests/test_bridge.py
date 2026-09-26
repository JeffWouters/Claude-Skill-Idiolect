"""Phase 6: file-bridge helpers (spec §26.2)."""
import stage
import bridge
import maintain
from store import Store
from test_learn import full_learn, make_store


def listing(n, changed=None):
    ents = [{"name": f"noor/{i:02d}.md", "type": "file", "size": 1000 + i, "mtimeMs": 1.7e12 + i} for i in range(n)]
    ents += [{"name": "noor/photo.jpg", "type": "file", "size": 5, "mtimeMs": 1},
             {"name": ".obsidian/workspace.md", "type": "file", "size": 5, "mtimeMs": 1},
             {"name": "noor", "type": "dir"}]
    if changed is not None:
        ents[changed]["size"] += 1
    return {"root": "C:/Users/sam/Writing", "entries": ents}


def test_plan_batches_new_files_and_skips_what_was_copied(tmp_path):
    st = make_store(tmp_path)
    s = Store(st)
    p = bridge.plan(s, listing(120))
    assert p["to_copy"] == 120 and [len(b) for b in p["batches"]] == [50, 50, 20]
    assert p["batches"][0][0] == "C:/Users/sam/Writing/noor/00.md"
    bridge.record(s, listing(120))
    assert bridge.plan(s, listing(120))["to_copy"] == 0
    again = bridge.plan(s, listing(120, changed=7))
    assert again["to_copy"] == 1 and again["unchanged"] == 119


def test_changed_lists_what_a_run_wrote_and_removed(tmp_path):
    st = make_store(tmp_path)
    full_learn(tmp_path, st, "noor", "noor")
    s = Store(st)
    before = bridge.snapshot(s)
    assert "profiles/noor/en.essay.json" in before and not any(k.startswith(".state") for k in before)
    key = sorted(k for k, e in s.manifest["texts"].items() if "noor" in e["profiles"])[0]
    maintain.forget(st, key)
    stage.Pending(Store(st)).decide(all_decision="approved")
    stage.commit(st)
    out = bridge.changed(Store(st), before)
    flat = [p for b in out["write_batches"] for p in b]
    assert "corpus/manifest.json" in flat and f"corpus/{key}.txt" in [p for b in out["delete_batches"] for p in b]
    assert out["note"]
