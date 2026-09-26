#!/usr/bin/env python3
"""Build scripted draft/final edit pairs from the synthetic author Noor Vale.

    python3 tools/build_edit_pairs.py

The final version is Noor's own text. The draft is produced by applying known,
reversible 'AI-ish' changes, so learn-edit has a known right answer:

  cut-hedge       hedges added to the draft; the writer removes them   (every pair)
  split-sentence  two short sentences merged in the draft; the writer splits them (pairs 1-5)
  numerals        one number written as a word in the draft; the writer uses digits (pair 3 only)

cut-hedge and split-sentence recur across pairs, so they must become edit lessons.
numerals appears once, so it must stay under "Seen once".
"""
import pathlib
import random
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / "evals" / "fixtures" / "synthetic-noor"
OUT = ROOT / "evals" / "edit-pairs"
HEDGES = ["Perhaps ", "It seems that ", "In some ways, ", "Arguably, "]
NUMWORDS = {"2": "two", "3": "three", "4": "four", "5": "five", "6": "six", "10": "ten", "12": "twelve",
            "20": "twenty", "30": "thirty", "40": "forty"}


def body(p):
    return p.read_text(encoding="utf-8").split("---", 2)[2].strip()


def sentences(par):
    return re.split(r"(?<=[.])\s+", par)


def main():
    rnd = random.Random(20261002)
    files = sorted(SRC.glob("*.md"))[:6]
    for n, f in enumerate(files, 1):
        paras = body(f).split("\n\n")[:7]
        final = "\n\n".join(paras)
        draft_paras, log = [], []
        hedged = merged = 0
        for par in paras:
            ss = sentences(par)
            # hedge: first sentence of up to 3 paragraphs that start with a capitalised plain word
            if hedged < 3 and len(ss[0].split()) > 3 and re.match(r"[A-Z][a-z]", ss[0]) and not ss[0].startswith("I ") \
                    and ss[0].split()[0] not in {"But", "So", "And", "Then", "At", "Not"}:
                h = HEDGES[(n + hedged) % len(HEDGES)]
                log.append(("cut-hedge", h + ss[0][0].lower() + ss[0][1:], ss[0]))
                ss[0] = h + ss[0][0].lower() + ss[0][1:]
                hedged += 1
            # merge two short sentences, pairs 1-5, up to 2 per pair
            if n <= 5 and merged < 2:
                for i in range(len(ss) - 1):
                    a, b = ss[i], ss[i + 1]
                    if a.endswith(".") and 3 <= len(a.split()) <= 9 and 3 <= len(b.split()) <= 9 and b[0].isupper() \
                            and not b.startswith("I ") and b.split()[0] not in {"And", "But", "So", "Then"} and not any(a.startswith(h) for h in HEDGES):
                        m = a[:-1] + ", and " + b[0].lower() + b[1:]
                        log.append(("split-sentence", m, a + " " + b))
                        ss[i:i + 2] = [m]
                        merged += 1
                        break
            draft_paras.append(" ".join(ss))
        draft = "\n\n".join(draft_paras)
        if n == 3:
            m = re.search(r"\b(2|3|4|5|6|10|12|20|30|40)\b", draft)
            if m:
                draft = draft[:m.start()] + NUMWORDS[m.group(1)] + draft[m.end():]
                log.append(("numerals", NUMWORDS[m.group(1)], m.group(1)))
        d = OUT / f"pair-{n:02d}"
        d.mkdir(parents=True, exist_ok=True)
        (d / "draft.md").write_text(draft + "\n", encoding="utf-8")
        (d / "final.md").write_text(final + "\n", encoding="utf-8")
        lines = ["# What the writer changed, draft -> final. Used as the expected answer in tests.",
                 f"source: synthetic-noor/{f.name}", "changes:"]
        for kind, before, after in log:
            lines.append(f"  - kind: {kind}")
            lines.append(f"    draft: {before!r}".replace("'", '"') if '"' not in before else f"    draft: '{before}'")
            lines.append(f"    final: {after!r}".replace("'", '"') if '"' not in after else f"    final: '{after}'")
        (d / "expected.yaml").write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"pair-{n:02d}: " + ", ".join(k for k, _, _ in log))
    (OUT / "expected-lessons.yaml").write_text(
        "# The right answer for learn-edit over all six pairs.\n"
        "edit_lessons:\n  - cut-hedge        # in all 6 pairs\n  - split-sentence   # in pairs 1-5\n"
        "seen_once:\n  - numerals         # pair 3 only\n", encoding="utf-8")


if __name__ == "__main__":
    main()
