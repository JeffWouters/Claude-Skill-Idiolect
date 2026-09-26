# Run 20260926T133739Z: notes

**Outcome: the few-shot bar is missed in both groups, so phase 3 is not done and the design changes
before more is built (eval-protocol.md, The bar).** Idiolect beats plain clearly (all briefs: 53 of
57) but loses to few-shot (all briefs: 24 of 57, 42%).

## What the judges say

In 33 of the 57 packets, few-shot outranked Idiolect. The judges' reasons for those 33 agree closely:
the Idiolect draft **reads as a thicker imitation of the author than the author is**. Typical lines:

- "stacks hedges ('It seems to me', 'arguably', 'in some sense', a triple-semicolon series, question
  opener) more thickly than the passage does" (synthetic-idris-02);
- "'Nay', the dashes and the final exclamation pile on Victorian mannerism that the calm, unexclaiming
  passage never uses" (alexander-smith-02);
- "long, smoothly subordinated sentences … lack the passage's abrupt short-sentence jolts"
  (alice-meynell-02), and the same point for most real authors.

`check` did not catch this: over all 57 briefs Idiolect drafts average 0.8 flagged metrics and none
fails, against 2.7 and 14 fails for few-shot and 6.0 and 48 fails for plain. The metrics are met on average while the habits are over-applied.

## Why, as far as the kit shows

The kit that `write` loads (for example `kit.py --profile synthetic-idris`) presents the writer as a
recipe:

- **Every lesson reads as a rule for every piece.** The slot page records how many texts show each
  habit ("2 texts", "3 texts" of 7), but the kit drops those counts. A draft then opens with a
  question, ends the first paragraph on "I suspect", has a "Consider …" paragraph, a "There is also …"
  paragraph, an "It seems to me that …" turn and a "Perhaps …" close, which no single text of the
  writer does.
- **Habit phrases sit in the vocabulary under "use exactly as written".** "I suspect", "arguably" and
  "in some sense" are listed next to spellings such as "organisation", so they are treated as
  required.
- **Examples come last.** The few-shot baseline sees the same passages (the same `pick_examples`), with
  nothing to over-apply.
- **The metric that would catch it is averaged over the draft**: stacking is local (three hedges in a
  paragraph), while `hedges_per_1k` and the sentence-length metrics look at the whole draft.

## Recognition

The recognition agent (passage only) named the author with medium or high confidence for 27 of 37
real-author passages (Alice Meynell 7 of 7, Arthur Christopher Benson 9 of 10, Alexander Smith 9 of
10, Samuel McChord Crothers 2 of 10), so the real group has 10 counted briefs, not 37. The phase 0
recognition check was done per author on a single passage; per passage, most of these authors are
known. The informational "all briefs" column in `results.md` shows the same picture as the counted
one.

## Process caveats (from the generator logs)

- The Idiolect generators shared one scratchpad. Kit outputs were overwritten between runs; the w5
  generator briefly saw part of the w2 kit and rebuilt its kits privately; the w3 generator ran one
  check against the wrong profile and redid it; the w4 generator rebuilt its kits in a subfolder.
  All drafts used their own profile's kit in the end, per the logs.
- The w4 generator kept its first draft of w4-07 (arthur-christopher-benson-07) because both
  revisions got worse, as `write.md` allows.
- The w1 generator left a folder `scratch-w1/` in the scratch area; it is not part of the run.
- Many drafts in all three arms contain placeholders (`[number needed]`, `[example needed]`) as the
  shared instruction required; they cause digit-shortfall flags and judges were told to ignore them.
- The source editions use two spaces after a full stop and few-shot drafts copied it; judge packets
  normalise runs of spaces so spacing cannot identify a draft.
- Judges saw anonymous ids (w1 to w6), never author names; each packet had its own fresh judge, and
  each passage its own fresh recognition agent.

## Spot-check

Not yet done: a person must review a random 10% of judgments (at least one per author) before the
run counts either way.
