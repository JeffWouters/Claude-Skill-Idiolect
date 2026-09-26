#!/usr/bin/env python3
"""Build tests/inventory-fixture/: a source folder that exercises every row of spec §5, a store
inside it with a prior manifest, and the expected inventory report.

    python3 tools/build_inventory_fixture.py

Deterministic (fixed seed). The texts are generated word salad: the inventory only needs lengths,
languages and hashes, not meaning. Hashes use the reference function in tests/test_hash.py.
Phase 1 is done when `learn dry-run=true` over this store reproduces expected-inventory.json.
"""
import hashlib
import io
import json
import pathlib
import random
import re
import sys
import unicodedata
import zipfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
FX = ROOT / "tests" / "inventory-fixture"
SRC = FX / "sources"
STORE = SRC / ".idiolect"
rnd = random.Random(20261003)

EN = ("morning river table window garden letter quiet reason simple answer market evening "
      "winter summer village teacher careful narrow bright heavy slowly often never always "
      "because although before after while under over between through against around "
      "people house water paper stone field road story question habit custom friend neighbour "
      "patience weather kitchen library railway harbour lantern orchard meadow chapel bridge "
      "carries finds keeps leaves makes holds brings turns follows reaches opens closes watches "
      "remembers forgets explains wonders gathers mends plants builds walks waits listens "
      "old small certain plain early late green grey warm cold honest ordinary patient strange "
      "the a an this that every some many few our their his her its and but or so yet").split()
NL = ("de het een en maar of dus toch omdat terwijl voordat nadat onder boven tussen door tegen "
      "rond mensen huis water papier steen veld weg verhaal vraag gewoonte vriend buurman geduld "
      "weer keuken bibliotheek spoorweg haven lantaarn boomgaard weide kapel brug draagt vindt "
      "houdt laat maakt brengt draait volgt bereikt opent sluit kijkt herinnert vergeet legt "
      "verzamelt herstelt plant bouwt loopt wacht luistert oud klein zeker eenvoudig vroeg laat "
      "groen grijs warm koud eerlijk gewoon geduldig vreemd ochtend rivier tafel raam tuin brief "
      "stil reden antwoord markt avond winter zomer dorp leraar voorzichtig smal helder zwaar "
      "langzaam vaak nooit altijd wij zij hij onze hun zijn haar ook nog al wel niet").split()


def content_hash(text):
    text = unicodedata.normalize("NFC", text)
    text = "".join(" " if c.isspace() else c for c in text)
    text = re.sub(" +", " ", text).strip(" ")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sentence(vocab):
    n = rnd.randint(6, 22)
    w = [rnd.choice(vocab) for _ in range(n)]
    w[0] = w[0].capitalize()
    return " ".join(w) + "."


def paragraph(vocab, words):
    out, count = [], 0
    while count < words:
        s = sentence(vocab)
        out.append(s)
        count += len(s.split())
    return " ".join(out)


def prose(vocab, words, paras=3):
    per = max(40, words // paras)
    ps, total = [], 0
    while total < words:
        p = paragraph(vocab, per)
        ps.append(p)
        total += len(p.split())
    return "\n\n".join(ps)


def nwords(t):
    return len(re.findall(r"[^\W\d_][\w'-]*", t))


def write(rel, text, date=None):
    p = SRC / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    body = text if date is None else f"---\ndate: \"{date}\"\n---\n\n{text}"
    p.write_text(body + "\n", encoding="utf-8")


def make_pdf(rel, text):
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate
    p = SRC / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(str(p), pagesize=A4, invariant=1)
    st = getSampleStyleSheet()["BodyText"]
    doc.build([Paragraph(x, st) for x in text.split("\n\n")])


def make_docx(rel, runs):
    """runs: list of paragraphs; each paragraph a list of (kind, text), kind in keep/ins/del."""
    W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
    ps = []
    rid = 1
    for para in runs:
        parts = []
        for kind, t in para:
            t = t.replace("&", "&amp;").replace("<", "&lt;")
            if kind == "keep":
                parts.append(f'<w:r><w:t xml:space="preserve">{t}</w:t></w:r>')
            elif kind == "ins":
                parts.append(f'<w:ins w:id="{rid}" w:author="Editor" w:date="2026-01-01T00:00:00Z">'
                             f'<w:r><w:t xml:space="preserve">{t}</w:t></w:r></w:ins>')
                rid += 1
            else:
                parts.append(f'<w:del w:id="{rid}" w:author="Editor" w:date="2026-01-01T00:00:00Z">'
                             f'<w:r><w:delText xml:space="preserve">{t}</w:delText></w:r></w:del>')
                rid += 1
        ps.append("<w:p>" + "".join(parts) + "</w:p>")
    document = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<w:document {W}><w:body>'
                + "".join(ps) + "</w:body></w:document>")
    ct = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
          '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
          '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
          '<Default Extension="xml" ContentType="application/xml"/>'
          '<Override PartName="/word/document.xml" '
          'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
          '</Types>')
    rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/'
            'relationships/officeDocument" Target="word/document.xml"/></Relationships>')
    p = SRC / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in (("[Content_Types].xml", ct), ("_rels/.rels", rels), ("word/document.xml", document)):
            zi = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            z.writestr(zi, data)
    p.write_bytes(buf.getvalue())


def main():
    if FX.exists() and any(FX.iterdir()):
        sys.exit(f"{FX} exists; move it to _to_delete/ first (never deleted automatically)")
    rows, manifest = [], {}

    def entry(path, status="active", holdout=False, **extra):
        e = {"path": path, "date": None, "origin": "file",
             "profiles": {"sam": {"ownership": "own", "decided": "2026-09-01", "decided_by": "folder-rule"}},
             "facets": {"lang": "en", "type": "essay"}, "words": 0, "holdout": holdout,
             "status": status, "cached": status != "forgotten"}
        e.update(extra)
        return e

    def row(path, result, text=None, key=None, lang="en", type_="essay", note=None):
        r = {"path": path, "result": result,
             "key": key if key is not None else (content_hash(text) if text is not None else None),
             "words": nwords(text) if text is not None else None, "lang": lang, "type": type_}
        if note:
            r["note"] = note
        rows.append(r)

    # 6. unchanged
    t = prose(EN, 220); write("essays/unchanged.md", t)
    manifest[content_hash(t)] = entry("essays/unchanged.md", words=nwords(t))
    row("essays/unchanged.md", "unchanged", t)
    # 6. unreachable returns
    t = prose(EN, 200); write("essays/back.md", t)
    manifest[content_hash(t)] = entry("essays/back.md", status="unreachable", words=nwords(t))
    row("essays/back.md", "unchanged", t, note="unreachable entry returns to active")
    # 7. moved
    t = prose(EN, 210); write("essays/renamed.md", t)
    manifest[content_hash(t)] = entry("essays/old-name.md", words=nwords(t))
    row("essays/renamed.md", "moved", t, note="manifest path essays/old-name.md becomes essays/renamed.md")
    # 6 + 8. copy
    t = prose(EN, 230); write("essays/original.md", t); write("archive/original-copy.md", t)
    manifest[content_hash(t)] = entry("essays/original.md", words=nwords(t))
    row("essays/original.md", "unchanged", t)
    row("archive/original-copy.md", "copy", t, type_="?", note="same text as essays/original.md; not learned twice")
    # 9. reverted
    old = prose(EN, 240)
    newer = old.replace(".", ", and then it rained.", 1)
    write("essays/reverted.md", old)
    manifest[content_hash(old)] = entry("essays/reverted.md", status="superseded",
                                        superseded_by=content_hash(newer), words=nwords(old))
    manifest[content_hash(newer)] = entry("essays/reverted.md", words=nwords(newer))
    row("essays/reverted.md", "reverted", old,
        note="superseded entry returns to active; the current one becomes superseded")
    # 11. changed (an edit of the old text: would be a near-duplicate of itself, must not be)
    old = prose(EN, 250)
    new = old.replace(".", ". It was late.", 1)
    write("essays/changed.md", new)
    manifest[content_hash(old)] = entry("essays/changed.md", words=nwords(old))
    row("essays/changed.md", "changed", new, note="old entry will be superseded; never a near-duplicate of itself")
    # 4. forgotten
    t = prose(EN, 180); write("essays/forgotten.md", t)
    manifest[content_hash(t)] = entry("essays/forgotten.md", status="forgotten", words=nwords(t))
    row("essays/forgotten.md", "skipped: forgotten", t)
    # 5. holdout
    t = prose(EN, 190); write("essays/holdout.md", t)
    manifest[content_hash(t)] = entry("essays/holdout.md", holdout=True, words=nwords(t))
    row("essays/holdout.md", "skipped: holdout", t)
    # unreachable (in scope, not found anywhere)
    t = prose(EN, 205)
    manifest[content_hash(t)] = entry("essays/deleted.md", words=nwords(t))
    unreachable = [{"path": "essays/deleted.md", "key": content_hash(t)}]
    # 10. too short
    t = prose(EN, 80, paras=1); write("essays/short-note.md", t)
    row("essays/short-note.md", "skipped: too short", t)
    # 10. code-heavy how-to: code stripped, prose under 150 words
    p1, p2 = paragraph(EN, 50), paragraph(EN, 40)
    code = "\n".join(f"    step_{i} = run('task-{i}', retries={i % 3})" for i in range(40))
    write("howto/code-heavy.md", f"# Setting it up\n\n{p1}\n\n```python\n{code}\n```\n\n{p2}", date="2025-06-01")
    row("howto/code-heavy.md", "skipped: too short", f"Setting it up\n\n{p1}\n\n{p2}", type_="?",
        note="heading kept as a plain line, code block removed")
    # 12. near-duplicates: b is newer and kept
    t = prose(EN, 260)
    tb = t.replace(" river ", " harbour ", 1) if " river " in t else t + " Then it rained."
    write("essays/near-dup-a.md", t, date="2024-01-10")
    write("essays/near-dup-b.md", tb, date="2025-02-01")
    row("essays/near-dup-a.md", "skipped: near-duplicate", t, note="of essays/near-dup-b.md, which is newer")
    row("essays/near-dup-b.md", "new", tb)
    # 13. new
    t = prose(EN, 300); write("essays/new-essay.md", t)
    row("essays/new-essay.md", "new", t)
    # mixed language: whole-file hash for English, #2 for the Dutch segment
    en1, nl, en2 = prose(EN, 120, 2), prose(NL, 170, 3), prose(EN, 90, 2)
    whole = f"{en1}\n\n{nl}\n\n{en2}"
    write("essays/mixed.md", whole)
    h = content_hash(whole)
    rows.append({"path": "essays/mixed.md", "result": "new", "key": h, "words": nwords(en1) + nwords(en2),
                 "lang": "en", "type": "essay", "note": "main language; key is the whole-file hash"})
    rows.append({"path": "essays/mixed.md", "result": "new", "key": h + "#2", "words": nwords(nl),
                 "lang": "nl", "type": "essay", "note": "segment 2, cached as <hash>-2.txt"})
    # 3. unsupported language
    ja = "\n\n".join(["今日は朝から雨が降っていた。駅まで歩く道はいつもより静かで、傘の音だけが聞こえた。"
                      "私は古い本を一冊持って、窓の近くの席に座った。"] * 6)
    write("essays/japanese.md", ja)
    rows.append({"path": "essays/japanese.md", "result": "skipped: language not supported", "key": None,
                 "words": None, "lang": "ja", "type": "essay"})
    # PDF and DOCX (keys depend on the extractor; words and result are asserted)
    t = prose(EN, 220); make_pdf("essays/lecture.pdf", t)
    rows.append({"path": "essays/lecture.pdf", "result": "new", "key": None, "words": nwords(t),
                 "lang": "en", "type": "essay", "note": "text layer only"})
    keep = [paragraph(EN, 60) for _ in range(3)]
    ins, dele = paragraph(EN, 30), paragraph(EN, 25)
    make_docx("essays/tracked.docx", [[("keep", keep[0])], [("keep", keep[1] + " "), ("ins", ins), ("del", " " + dele)],
                                      [("keep", keep[2])]])
    rows.append({"path": "essays/tracked.docx", "result": "new", "key": None,
                 "words": sum(nwords(k) for k in keep) + nwords(ins), "lang": "en", "type": "essay",
                 "note": "insertions kept, deletions dropped"})
    # 2. no adapter
    png = SRC / "images" / "diagram.png"
    png.parent.mkdir(parents=True, exist_ok=True)
    png.write_bytes(bytes.fromhex("89504e470d0a1a0a0000000d4948445200000001000000010806000000"
                                  "1f15c4890000000d49444154789c6360000002000154a24f5d0000000049454e44ae426082"))
    rows.append({"path": "images/diagram.png", "result": "skipped: not prose", "key": None, "words": None,
                 "lang": None, "type": None})
    # 1. excluded: not listed
    write("drafts/wip.md", prose(EN, 200))

    # the store, inside the sources
    STORE.mkdir(parents=True, exist_ok=True)
    (STORE / "idiolect.yaml").write_text(
        "schema_version: 1\nsources_root: ..\nfacets: [lang, type]\ntypes: [essay, howto]\n"
        "default_profile: sam\ndefaults:\n  lang: en\n", encoding="utf-8")
    (STORE / "sources.yaml").write_text(
        "schema_version: 1\nsources:\n  - path: .\n    profile: sam\n    ownership: own\n"
        "    decided: \"2026-09-01\"\n  - path: essays\n    profile: sam\n    ownership: own\n"
        "    facets: { type: essay }\n    decided: \"2026-09-01\"\nexclude:\n  - \"drafts/**\"\n",
        encoding="utf-8")
    (STORE / "corpus").mkdir(exist_ok=True)
    lines = ["{", '  "schema_version": 1,', '  "texts": {']
    items = sorted(manifest.items(), key=lambda kv: kv[1]["path"])
    for i, (k, e) in enumerate(items):
        lines.append(f'    "{k}": ' + json.dumps(e) + ("," if i < len(items) - 1 else ""))
    lines += ["  }", "}"]
    (STORE / "corpus" / "manifest.json").write_text("\n".join(lines) + "\n", encoding="utf-8")

    rows.sort(key=lambda r: (r["path"], r["key"] or ""))
    expected = {
        "command": "learn dry-run=true store=tests/inventory-fixture/sources/.idiolect",
        "scope": "all registered sources",
        "not_listed": [".idiolect/** (the store itself)", "drafts/wip.md (excluded glob)"],
        "rows": rows,
        "unreachable": unreachable,
        "notes": ["key null: not asserted (depends on the PDF/DOCX extractor or not computed)",
                  "words: words of prose after cleaning, as defined in idiolect/references/fingerprint.md",
                  "type '?': not set by a rule, frontmatter or the command; a dry run does not detect it"],
    }
    (FX / "expected-inventory.json").write_text(json.dumps(expected, indent=2, ensure_ascii=False) + "\n",
                                                encoding="utf-8")
    print(f"wrote {len(rows)} expected rows, {len(manifest)} manifest entries")


if __name__ == "__main__":
    main()
