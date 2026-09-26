"""Phase 2: a full learn with scripted model outputs, approval, commit, relearn, rejections that stay
gone, stable ids, rollback isolation, forget, prune and an interrupted commit."""
import glob
import hashlib
import json
import os
import pathlib
import shutil

import pytest

import learn
import maintain
import pages
import stage
from common import load_yaml_text
from store import Store

ROOT = pathlib.Path(__file__).resolve().parent.parent
FIX = ROOT / "evals" / "fixtures"


def make_store(tmp_path):
    src = tmp_path / "Writing"
    for author, n in (("synthetic-noor", 10), ("synthetic-idris", 8)):
        d = src / author.split("-")[1]
        d.mkdir(parents=True)
        for f in sorted(glob.glob(str(FIX / author / "[0-9]*.md")))[:n]:
            shutil.copy(f, d / pathlib.Path(f).name)
    st = tmp_path / "Store"
    st.mkdir()
    (st / "idiolect.yaml").write_text("schema_version: 1\nsources_root: ../Writing\nfacets: [lang, type]\n"
                                      "types: [essay, email]\ndefault_profile: noor\ndefaults:\n  lang: en\n")
    return st


def answers(tmp_path, prof, folder):
    f = tmp_path / f"answers-{prof}.yaml"
    f.write_text(f"folders:\n  - {{path: {folder}, profile: {prof}, ownership: own, facets: {{type: essay}}}}\n"
                 f"profiles:\n  - {{name: {prof}, subject: synthetic fixture author, consent: 'public-domain fixture, evaluation only'}}\n")
    return f


def fake_rewrites(sample):
    d = pathlib.Path(sample["rewrites_dir"])
    for p in sample["paragraphs"]:
        body = p["text"][0].lower() + p["text"][1:]
        (d / f"{p['n']}.txt").write_text(
            f"It is important to note that {body} Additionally, this highlights the overall significance of the matter.")
    return d


def lesson_file(tmp_path, run_store, prof, slot, extra=True):
    run = learn.Run(run_store)
    texts = learn.slot_texts(run, prof, slot)
    k = [k for k, _ in texts]
    first_sentence = lambda t: t.split(". ")[0].strip()  # noqa: E731
    les = [
        {"section": "Sentences", "text": "Keeps most sentences very short.", "evidence": k[:4],
         "quote": first_sentence(texts[0][1])},
        {"section": "Openings", "text": "Opens on a concrete object in the room.", "evidence": k[:2]},
        {"section": "Tone", "text": "Rarely hedges a claim.", "evidence": k[:1]},
    ]
    if extra:
        les.append({"section": "Endings", "text": "Ends on a plain statement of fact.", "evidence": k[1:3]})
    f = tmp_path / f"lessons-{prof}.yaml"
    import yaml
    f.write_text(yaml.safe_dump(les))
    return f


def full_learn(tmp_path, st, prof, folder, reject_text=None, crash_after=None):
    learn.start(st, targets=[folder], profile=prof)
    learn.answer(st, answers(tmp_path, prof, folder))
    learn.stage_texts(st)
    out = learn.do_measure(st)
    slots = [s["slot"] for s in out["slots"]]
    for slot in slots:
        cs = learn.contrast_sample(st, prof, slot)
        if not cs["reuse"]:
            learn.contrast_apply(st, prof, slot, fake_rewrites(cs))
        learn.lessons_apply(st, prof, slot, lesson_file(tmp_path, st, prof, slot))
    ex = learn.examples_sample(st, prof, "en.essay")
    import yaml
    ef = tmp_path / "examples.yaml"
    ef.write_text(yaml.safe_dump({"examples": [{"key": c["key"], "text": c["text"], "habit": "short sentences"}
                                               for c in ex["candidates"][:2]]}))
    learn.examples_apply(st, prof, "en.essay", ef)
    vf = tmp_path / "vocab.yaml"
    vf.write_text("- {text: kitchen tap, kind: term}\n")
    learn.vocab_apply(st, prof, vf)
    p = stage.Pending(Store(st))
    rej = [i["id"] for i in p.plan["items"] if reject_text and reject_text in i["summary"]]
    p.decide(reject=rej, all_decision="approved")
    if crash_after:
        os.environ["IDIOLECT_TEST_CRASH_AFTER"] = str(crash_after)
        try:
            with pytest.raises(RuntimeError):
                stage.commit(st)
        finally:
            del os.environ["IDIOLECT_TEST_CRASH_AFTER"]
        return None
    return stage.commit(st)


def tree_hash(d):
    h = hashlib.sha256()
    for f in sorted(pathlib.Path(d).rglob("*")):
        if f.is_file() and "snapshots" not in f.parts:
            h.update(str(f.relative_to(d)).encode())
            h.update(f.read_bytes())
    return h.hexdigest()


def test_full_cycle(tmp_path):
    st = make_store(tmp_path)
    full_learn(tmp_path, st, "noor", "noor", reject_text="Opens on a concrete object")
    s = Store(st)
    page = (st / "profiles" / "noor" / "en.essay.md").read_text()
    _, conf, lessons = pages.parse_slot_page(page)
    ids = {x["text"]: x["id"] for x in lessons}
    assert "Opens on a concrete object in the room." not in ids                   # rejected
    assert set(ids) == {"Keeps most sentences very short.", "Rarely hedges a claim.",
                        "Ends on a plain statement of fact."}
    assert next(x for x in lessons if x["text"] == "Rarely hedges a claim.")["section"] == "Seen once"
    assert conf.startswith(("low", "medium", "high"))
    rej = load_yaml_text((st / "profiles" / "noor" / "rejected.yaml").read_text())
    assert rej["entries"][0]["rejects"].startswith("l-") and rej["entries"][0]["kind"] == "observed"
    assert (st / "profiles" / "noor" / "en.essay.never.md").exists()
    fp = json.loads((st / "profiles" / "noor" / "en.essay.json").read_text())
    assert fp["metric_list"] == "contrast" and any(m["primary"] for m in fp["metrics"].values())
    assert (st / "profiles" / "noor" / "en._.json").exists()
    assert len([k for k, e in s.manifest["texts"].items() if e["status"] == "active"]) == 10
    assert all((st / "corpus" / f"{k}.txt").exists() for k in s.manifest["texts"])
    assert not (st / ".state" / "pending").exists() and not (st / ".state" / "lock").exists()
    assert (st / "profiles" / "noor" / "changelog.md").exists()
    assert "kitchen tap" in (st / "profiles" / "noor" / "vocabulary.yaml").read_text()

    # relearn with one more text: ids survive, the rejected lesson stays gone, a snapshot is taken
    shutil.copy(sorted(glob.glob(str(FIX / "synthetic-noor" / "[0-9]*.md")))[10], tmp_path / "Writing" / "noor")
    learn.start(st, targets=["noor"], profile="noor")
    learn.stage_texts(st)
    learn.do_measure(st)
    for slot in ("en.essay", "en._"):
        learn.lessons_apply(st, "noor", slot, lesson_file(tmp_path, st, "noor", slot))
    p = stage.Pending(Store(st))
    assert not any("Opens on a concrete object" in i["summary"] for i in p.plan["items"])
    p.decide(all_decision="approved")
    stage.commit(st)
    _, _, lessons2 = pages.parse_slot_page((st / "profiles" / "noor" / "en.essay.md").read_text())
    assert {x["text"]: x["id"] for x in lessons2} == ids
    snaps = sorted((st / "profiles" / "noor" / "snapshots").iterdir())
    assert len(snaps) == 1 and (snaps[0] / "manifest-entries.json").exists()

    # a second profile, then rollback of the first must not touch it
    full_learn(tmp_path, st, "idris", "idris")
    before = tree_hash(st / "profiles" / "idris")
    idris_entries = {k: e for k, e in Store(st).manifest["texts"].items() if "idris" in e["profiles"]}
    maintain.rollback(st, "noor")
    stage.Pending(Store(st)).decide(all_decision="approved")
    stage.commit(st)
    assert tree_hash(st / "profiles" / "idris") == before
    after = {k: e for k, e in Store(st).manifest["texts"].items() if "idris" in e["profiles"]}
    assert after == idris_entries
    noor_active = [k for k, e in Store(st).manifest["texts"].items()
                   if "noor" in e["profiles"] and e["status"] == "active"]
    assert len(noor_active) == 10    # the 11th text was added after the snapshot: forgotten again

    # forget a text: its cache is gone and a later learn skips it
    key = sorted(noor_active)[0]
    path = Store(st).manifest["texts"][key]["path"]
    maintain.forget(st, path)
    stage.Pending(Store(st)).decide(all_decision="approved")
    stage.commit(st)
    assert Store(st).manifest["texts"][key]["status"] == "forgotten"
    assert not (st / "corpus" / f"{key}.txt").exists()
    learn.start(st, targets=["noor"], profile="noor")
    run = learn.Run(st)
    assert run.state["texts"][key]["result"] == "skipped: forgotten"
    stage.discard(st)

    # prune keeps the newest snapshot only
    maintain.prune(st, "noor", keep=1)
    stage.Pending(Store(st)).decide(all_decision="approved")
    stage.commit(st)
    assert len(list((st / "profiles" / "noor" / "snapshots").iterdir())) == 1


def test_measurement_is_repeatable(tmp_path):
    st = make_store(tmp_path)
    learn.start(st, targets=["noor"], profile="noor")
    learn.answer(st, answers(tmp_path, "noor", "noor"))
    learn.stage_texts(st)
    learn.do_measure(st)
    p = stage.Pending(Store(st))
    first = [p.payload(i["id"])["fingerprint"] for i in p.plan["items"] if i["kind"] == "fingerprint"]
    learn.do_measure(st)
    second = [p.payload(i["id"])["fingerprint"] for i in p.plan["items"] if i["kind"] == "fingerprint"]
    for a, b in zip(first, second):
        a.pop("built"), b.pop("built")
    assert first == second and first


def test_interrupted_commit_resumes_to_the_same_result(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir(), b.mkdir()
    sa, sb = make_store(a), make_store(b)
    full_learn(a, sa, "noor", "noor")
    full_learn(b, sb, "noor", "noor", crash_after=3)
    status = stage.Pending(Store(sb)).plan
    assert "commit" in status and any(s["state"] == "todo" for s in status["commit"]["steps"])
    with pytest.raises(Exception):
        stage.discard(sb)                         # only resume is allowed
    stage.resume(sb)
    assert not (sb / ".state" / "pending").exists()

    def content(root):
        out = {}
        for f in sorted(root.rglob("*")):
            if f.is_file() and "snapshots" not in f.parts and f.name != "changelog.md" and f.suffix != ".json" \
                    and not f.name.endswith(".md"):
                out[str(f.relative_to(root))] = f.read_bytes()
        return out
    assert content(sa) == content(sb)
    ja = json.loads((sa / "corpus" / "manifest.json").read_text())
    jb = json.loads((sb / "corpus" / "manifest.json").read_text())
    assert ja == jb


def test_leftover_pending_blocks_a_new_run(tmp_path):
    st = make_store(tmp_path)
    learn.start(st, targets=["noor"], profile="noor")
    with pytest.raises(Exception):
        learn.start(st, targets=["noor"], profile="noor")
