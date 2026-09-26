# Mode: test

Holds one of the writer's texts out of learning and measures how close the profile, and a draft
written without seeing the text, come to it (spec §19). Store-writing: the proposal takes the lock
and changes nothing until the writer approves it. Run scripts from the skill folder.

## 1. Choose the text

The writer names a text: one already learned (by path or key) or a file under the sources root that
has not been learned. A good holdout is a recent, typical piece of the kind the profile covers.
For a file not learned yet, ask its type (`type=essay`, `post` and so on) if the request does not say.

## 2. Propose and approve

```
python3 scripts/holdout.py --store S propose --source <path or key> [--profile P] [--type T]
python3 scripts/stage.py --store S diff
```

Show the diff. For a learned text, it holds the holdout flag plus what learning without it changes:
fingerprints re-measured, examples and lesson quotes taken from it removed. Say that lessons and
phrase rates refresh at the next `learn`, and that from now on learning refuses the text (only
`rollback` or `forget` clears the flag). The proposal is approved or rejected as a whole:
`stage.py decide --approve all` (or `--reject all`), then `stage.py commit`.

## 3. The brief

A topic-only brief of at most 60 words: the subject and up to three points, plus a target length,
never the text's wording.

- **Best: the writer writes it**, from memory of the piece. Then do not open the held-out text at
  all: you never see it, and every draft below is made blind.
- Otherwise a **separate agent** that reads only the held-out text (`corpus/<key>.txt` in the store)
  writes the brief. You, and every drafting agent, never read the text or the agent's notes.

Check it, and rewrite it until it passes:

```
python3 scripts/holdout.py --store S brief-check --key K --brief brief.md
```

## 4. Drafts

Each draft is written from the brief alone, by a context that has not seen the held-out text: a
separate agent per draft where agents are available, or you, when the writer wrote the brief.

- **Idiolect**: the `write` procedure (`references/modes/write.md`) with the brief and the text's
  profile and slot.
- With `judge=true`, also:
  - **plain**: "Write a piece of about N words from this brief." Nothing else.
  - **few-shot**: the brief plus the passages from
    `python3 scripts/holdout.py --store S examples --key K --brief brief.md`, with "write in the style
    of these passages; never reuse their content".
  - All three get the same skeleton: about the brief's length, no facts, names or anecdotes beyond
    the brief (a placeholder instead).

## 5. Judge (only with `judge=true`)

```
python3 scripts/holdout.py --store S packet --key K --brief brief.md --draft plain=p.md --draft fewshot=f.md --draft idiolect=i.md
```

Show the writer the `packet` exactly as printed, labels A, B, C. Do not say, hint or guess which draft
is which, before or after they rank, and do not read `.state/test/`. Ask them to rank the three by which
reads most like them (voice, not content), best first.

## 6. Record

```
python3 scripts/holdout.py --store S record --test <id> --ranking B,A,C      # after judging
python3 scripts/holdout.py --store S record --key K --draft i.md             # without a judge
```

It appends one row to `eval/results.md`. Relay it plainly:

- **Profile drift**: how far the held-out text sits from the profile (mean of |ln ratio| over the
  metrics; 0 is identical, 0.1 is about 10% off on average) and how many metrics fall outside the
  slot's band. Several outside means the profile does not yet describe texts like this one.
- **Draft drift**: the same, for the Idiolect draft against the held-out text.
- **Blind picks** (with a judge): the writer's order, now revealed, e.g. `idiolect > fewshot > plain`.
- Never merge these into one score. One test is one text: say that a few tests over time say more.

`python3 scripts/holdout.py --store S drift --key K [--draft F]` gives the same figures without
writing a row.

## interactive=false

Never ask. Without a named text, or without a type for a new file, return `needs_input`. A proposal
waits for the writer's approval, so return `needs_input` after `propose` with the diff summary. Never
run `judge=true` unattended.
