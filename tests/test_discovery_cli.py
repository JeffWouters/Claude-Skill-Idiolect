"""Gaps found by coverage (2026-09-27): finding the store, broken inheritance, rules joining or refusing a
waiting run, `status` wording, and the scripts' command lines end to end, which is how Claude drives
the skill (JSON out, exit codes)."""
import json
import pathlib
import shutil
import subprocess
import sys

import pytest
import yaml

import resolve
import rules
import stage
import status
from common import StoreError
from store import Store, discover
from test_learn import full_learn, make_store
from test_rules import PLAIN

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent / "idiolect" / "scripts"
EXAMPLE = pathlib.Path(__file__).resolve().parent / "example-store"
MARKER = "schema_version: 1\nsources_root: ../Writing\nfacets: [lang, type]\ntypes: [essay]\ndefault_profile: sam\n"


def run(script, *args, cwd=None):
    p = subprocess.run([sys.executable, str(SCRIPTS / script), *map(str, args)], capture_output=True,
                       text=True, cwd=cwd, timeout=120)
    return p.returncode, p.stdout, p.stderr


def as_json(out):
    return json.loads(out)


# ---------- finding the store ----------

def tree(root, rel, marker=MARKER):
    d = root / rel
    d.mkdir(parents=True)
    (d / "idiolect.yaml").write_text(marker)
    return d


def test_discover_finds_valid_stores_three_levels_deep_and_skips_the_rest(tmp_path):
    good = tree(tmp_path, "Idiolect")
    deep_ok = tree(tmp_path, "a/b/store")                   # level 3: found
    tree(tmp_path, "a/b/c/too-deep")                        # level 4: not searched
    tree(tmp_path, ".hidden/store")
    tree(tmp_path, "node_modules/pkg")
    tree(tmp_path, "_to_delete/old-store")
    tree(tmp_path, "broken", marker="not: [a valid marker")
    tree(tmp_path, "wrong", marker="schema_version: 1\nfacets: [type]\n")
    found = sorted(str(p.relative_to(tmp_path)) for p in discover([tmp_path]))
    assert found == sorted([str(good.relative_to(tmp_path)), str(deep_ok.relative_to(tmp_path))])
    assert [p.name for p in discover([tmp_path], depth=1)] == ["Idiolect"]


def test_discover_on_the_command_line_and_with_no_store(tmp_path):
    tree(tmp_path, "one")
    tree(tmp_path, "two/inner")
    code, out, _ = run("store.py", "discover", tmp_path)
    assert code == 0 and as_json(out)["count"] == 2           # several: the procedure lists them and asks
    empty = tmp_path / "empty"
    empty.mkdir()
    code, out, _ = run("store.py", "discover", cwd=empty)     # no roots: the current folder
    assert code == 0 and as_json(out) == {"stores": [], "count": 0}


def test_a_store_is_never_found_through_a_link_loop(tmp_path):
    tree(tmp_path, "s")
    (tmp_path / "s" / "loop").symlink_to(tmp_path, target_is_directory=True)
    assert [p.name for p in discover([tmp_path])] == ["s"]


# ---------- broken inheritance ----------

def profile(st, name, extends=None):
    d = st / "profiles" / name
    d.mkdir(parents=True, exist_ok=True)
    body = {"schema_version": 1, "subject": name, "consent": "self"}
    if extends:
        body["extends"] = extends
    (d / "profile.yaml").write_text(yaml.safe_dump(body))


def test_profiles_that_extend_each_other_or_a_missing_parent_stop_with_a_message(tmp_path):
    st = tmp_path / "s"
    shutil.copytree(EXAMPLE, st)
    profile(st, "a", "b")
    profile(st, "b", "a")
    profile(st, "c", "ghost")
    s = Store(st)
    with pytest.raises(StoreError, match="extend each other in a cycle: a > b > a"):
        resolve.chain(s, "a")
    with pytest.raises(StoreError, match="profile c extends ghost, which does not exist"):
        resolve.chain(s, "c")
    with pytest.raises(StoreError, match="no profile nobody"):
        resolve.chain(s, "nobody")
    code, out, _ = run("status.py", "--store", st)
    assert code == 2 and "cycle" in as_json(out)["message"]   # a message, never a hang


# ---------- rules and a waiting run ----------

def clean_copy(dst):
    """The example store without its sample lock and pending area (they are schema fixtures)."""
    shutil.copytree(EXAMPLE, dst)
    shutil.rmtree(dst / ".state" / "pending")
    (dst / ".state" / "lock").unlink()
    return dst


@pytest.fixture
def example(tmp_path):
    return clean_copy(tmp_path / "s")


def test_rules_join_a_waiting_learn_run_and_refuse_another_kind(example, tmp_path):
    stage.begin(example, "learn", ["sam"])
    out = rules.add(example, "sam", "Never write 'utilise'.", {"words": ["utilise"]})
    assert out["proposed"] == "r-003"                              # sam holds r-001 and r-002
    assert rules.add(example, "sam", "No exclamation marks.", {"chars": ["!"]})["proposed"] == "r-004"
    plan = stage.Pending(Store(example)).plan
    assert plan["mode"] == "learn" and [i["ref"] for i in plan["items"]] == ["r-003", "r-004"]
    stage.discard(example)
    other = clean_copy(tmp_path / "t")
    stage.begin(other, "learn-edit", ["sam"])
    with pytest.raises(StoreError, match="pending area is waiting"):
        rules.add(other, "sam", "No exclamation marks.", {"chars": ["!"]})
    with pytest.raises(StoreError, match="no profile nobody"):
        rules.defaults(example, "nobody")
    with pytest.raises(StoreError, match="unknown categories: vibes"):
        rules.defaults(example, "sam", categories=["vibes"])


def test_show_lists_what_applies(example):
    out = rules.show(Store(example), "sam", {"type": "essay"})
    assert out["slot"] == "en.essay"
    assert [(r["id"], r["starter"]) for r in out["rulings"]] == [("r-001", None), ("r-002", "s-001")]
    assert out["rulings"][0]["test"] == {"chars": [";"]}


# ---------- status wording ----------

def test_status_says_what_the_store_holds_and_what_waits(example):
    s = Store(example)
    text = status.readable(status.status(s))
    assert text.startswith(f"Store: {s.root}")
    assert "Profile sam (" in text and "consent: self" in text
    assert "en.essay: " in text and " texts, " in text and " words, confidence " in text
    assert "rejected proposals" in text
    assert "a pending area is waiting" not in text
    rules.add(example, "sam", "No exclamation marks.", {"chars": ["!"]})
    text = status.readable(status.status(Store(example)))
    assert "a pending area is waiting: " in text and "resume" in text and "discard" in text


# ---------- the command lines end to end ----------

@pytest.fixture(scope="module")
def learned(tmp_path_factory):
    t = tmp_path_factory.mktemp("cli")
    st = make_store(t)
    full_learn(t, st, "noor", "noor")
    return st


def test_the_rules_stage_check_status_export_round_trip_on_the_command_line(learned, tmp_path):
    st = tmp_path / "Store"
    shutil.copytree(learned, st)
    shutil.copytree(learned.parent / "Writing", tmp_path / "Writing")
    code, out, _ = run("rules.py", "--store", st, "defaults", "--profile", "noor", "--category", "punctuation",
                       "--category", "chatbot")
    assert code == 0 and [p["starter"] for p in as_json(out)["proposed"]] == ["s-001", "s-002", "s-003", "s-004", "s-005"]
    code, out, _ = run("stage.py", "--store", st, "diff")
    assert code == 0 and "ruling" in out and "[s-001 punctuation]" in out
    code, out, _ = run("stage.py", "--store", st, "decide", "--reject", "i-002")
    code, out, _ = run("stage.py", "--store", st, "decide", "--approve", "all")
    assert code == 0 and as_json(out) == {"approved": 4, "rejected": 1}
    code, out, _ = run("stage.py", "--store", st, "commit")
    assert code == 0
    code, out, _ = run("rules.py", "--store", st, "show", "--profile", "noor", "--type", "essay")
    shown = as_json(out)["rulings"]
    assert code == 0 and [r["starter"] for r in shown] == ["s-001", "s-003", "s-004", "s-005"]

    clean, dashed = tmp_path / "clean.md", tmp_path / "dashed.md"
    clean.write_text(PLAIN)
    dashed.write_text(PLAIN.replace("round through the", "round — through the"))
    code, out, _ = run("check.py", "--store", st, "--file", clean, "--profile", "noor", "--type", "essay", "--json")
    assert "flagged_lines" not in as_json(out)          # no ruling broken (the metrics may still differ)
    code, out, _ = run("check.py", "--store", st, "--file", dashed, "--profile", "noor", "--type", "essay", "--json")
    rep = as_json(out)
    assert code == 1 and rep["status"] == "fail" and rep["flagged_lines"][0]["lesson"] == "r-001"
    code, out, _ = run("check.py", "--store", st, "--file", dashed, "--profile", "noor", "--type", "essay")
    assert code == 1 and out.startswith("FAIL against noor / en.essay") and "breaks ruling r-001" in out

    code, out, _ = run("status.py", "--store", st)
    assert code == 0 and "Profile noor" in out and "en.essay" in out
    code, out, _ = run("status.py", "--store", st, "--json")
    assert code == 0 and as_json(out)["profiles"][0]["name"] == "noor"
    code, out, _ = run("export.py", "--store", st, "--profile", "noor", "--type", "essay", "--out", tmp_path / "voice.md")
    assert code == 0 and "## Rulings (always obey)" in (tmp_path / "voice.md").read_text()
    code, out, _ = run("rules.py", "--store", st, "defaults", "--profile", "noor", "--category", "chatbot")
    assert code == 0 and as_json(out)["proposed"] == []           # s-002 declined, the rest held


def test_command_lines_fail_with_a_json_message_and_a_nonzero_exit(tmp_path):
    missing = tmp_path / "nowhere"
    for script, args in (("rules.py", ["--store", missing, "defaults"]),
                         ("rules.py", ["--store", missing, "add", "--text", "x", "--words", "y", "--chars", "z"]),
                         ("stage.py", ["--store", missing, "commit"]),
                         ("status.py", ["--store", missing]),
                         ("export.py", ["--store", missing]),
                         ("learn.py", ["--store", missing, "next"])):
        code, out, err = run(script, *args)
        assert code != 0, script
        assert as_json(out)["status"] in ("error", "no_store"), script
    code, out, _ = run("check.py", "--file", __file__)                 # no store given
    assert code == 1 and out.startswith("no_store")
    code, out, _ = run("rules.py", "starter", "--lang", "xx")
    assert code == 1 and "no starter set for 'xx'" in as_json(out)["message"]


def test_a_learn_starts_and_answers_on_the_command_line(tmp_path):
    from test_learn import answers
    st = make_store(tmp_path)
    code, out, _ = run("learn.py", "--store", st, "start", "--target", "noor", "--profile", "noor")
    assert code == 0, out
    code, out, _ = run("learn.py", "--store", st, "answer", "--file", answers(tmp_path, "noor", "noor"))
    assert code == 0, out
    code, out, _ = run("learn.py", "--store", st, "next")
    assert code == 0 and as_json(out)                        # what the procedure does next
    code, out, _ = run("learn.py", "--store", st, "start", "--target", "noor")
    assert code == 2 and "store is locked by learn" in as_json(out)["message"]   # the first run holds it
    code, out, _ = run("stage.py", "--store", st, "discard")
    assert code == 0 and not (st / ".state" / "pending" / "plan.json").exists()
