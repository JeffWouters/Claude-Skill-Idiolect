# Recognition study (after runs 5 and 6)

Why the recognition check changed from run 7 (design: decision log; `evals/eval-protocol.md`,
"Recognition (runs 7 on)"). Everything here was produced in one session; the prompts name the
temporary folder the agents worked in (`/tmp/claude-0/recog-exp/`), which is this folder.

## Material

- `key.json`: the 16 study passages. `p01`..`p16` map to a run (run 5 is `20260926T163528Z`, run 6
  is `20260926T163530Z`), the passage id, the run's original recognition answer and the anonymous
  judge id. 12 are real-author passages (Gerould, Holliday, Crothers), 4 synthetic (Noor, Idris).
- `pNN.md`: the passage as the judges saw it. `rNN.md`: the same passage with names, titles, places and
  dates removed by an agent (checked with a word diff).
- `prompts/`: every prompt, one fresh agent each.
- `out/`: the answers.
  - `rep-NN`: the old question again (name and confidence), to see how stable it is.
  - `prob-NN`, `probred-NN`: open question, top three authors with probabilities; original and redacted.
  - `fc-NN`, `fcred-NN`: forced choice, ten candidates and "none"; original and redacted.
- `judge/`: the sensitivity test. `blind-NN` is the packet judged again blind, `named-NN` judged
  again with the author named (`prompts/jblind-NN.txt`, `prompts/jnamed-NN.txt`).
- `label-reanalysis.json`: all 128 real-author recognition answers of runs 1, 4, 5 and 6, with whether
  the name was right and whether Idiolect beat few-shot (`wf`) and plain (`wp`) on that brief.

Two answers (`out/prob-10.json`, `out/probred-05.json`) gave the tester's own name for a synthetic
passage: the session's memory of the person running it had reached the agents. The name is replaced by
"[the tester (name removed)]" here.

## Findings

| Question | Result |
| --- | --- |
| Does the confidence label measure familiarity? | No. Across runs 1, 4, 5 and 6 agents named the right author at "low" confidence 59 times; "low" meant "I am guessing well", not "I do not know" |
| Does forced choice? | Yes. It put the true author first for all 12 real passages, with 44 to 85% on the true author (mean 62%). The 4 synthetic passages got 89 to 98% on "none" |
| Does removing names and dates help? | No. Mean on the true author 62% with names, 62% without; the model knows these writers by their prose |
| Does excluding recognised briefs help? | It biases the result. Idiolect beat few-shot on 11 of 40 briefs recognised at medium or high and 43 of 88 of the rest (`label-reanalysis.json`): the passages the model knew best favoured few-shot, so leaving them out moved the real-author rate for a reason unrelated to the design |
| Does naming the author change the judge? | Somewhat. Over the 12 real packets, agreement with the original judgment was 0.93 blind and 0.86 named; Idiolect's wins over few-shot were 8 (original), 7 (blind) and 6 (named) |

## What changed

Forced choice replaces the label; no brief is excluded and win rates are shown by familiarity; a
positive control and the synthetic passages as negative controls in every run; a sensitivity test
every run; new authors screened by forced choice on redacted passages (under 30% to be used); the real
authors are the known-author group; recognition and judging agents run with memory off. Name
redaction is not used as a fix.
