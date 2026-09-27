# Trigger tests (phase 4, carried over from phase 3)

Does Idiolect's description make Claude reach for the skill when it should, and leave general
writing requests to other skills (design: Triggering)? `trigger-eval.json` holds 24 queries: 12 that
should trigger (learn, dry run, profile questions, check, write and rewrite with an explicit profile or
slot, test, forget, rollback, and from phase 5 learn-edit and interview) and 12 near misses that should
not (general "in my voice" or editing requests, the linguistics term, style analysis of someone else,
brand guidelines, notes, and from phase 5 a plain two-version comparison and an interview for a bio).

Run with skill-creator's `run_eval.py` (it installs the description as a command and runs `claude -p`
three times per query), from a scratch folder, never from this repository:

```
cd <scratch> && mkdir -p .claude
PYTHONPATH=<skill-creator> python3 -m scripts.run_eval --eval-set <repo>/evals/triggers/trigger-eval.json \
    --skill-path <repo>/idiolect --runs-per-query 3 --num-workers 1 --timeout 90 --model <session model> --verbose > results.json
```

**Always `--num-workers 1`.** Each run installs its own uniquely named copy of the description in the
same `.claude/commands/` folder, and a run only counts a trigger of its own copy. With parallel
workers Claude sees several identical copies, picks another run's, and the run is scored as a miss:
the first run (`runs/2026-09-26-parallel-invalid.json`, 10 workers) scored 10 of 20 with every
should-trigger query missed; the same set run serially scored 20 of 20.

**Bar, set before the first run:** at least 90% of the queries on the right side of a 50% trigger
rate (18 of 20; 22 of 24 from phase 5; 27 of 30 from phase 6; 31 of 34 with the rules mode; 37 of 41 with verify, guide, import and tone), and no general "in my voice" or editing request triggering at
all.
Results of each run go in `runs/<date>.json`.

| Run | Model | Correct | Should trigger | Should not |
| --- | --- | --- | --- | --- |
| 2026-09-26 | claude-opus-5-5 | 20 of 20 | 10 of 10 at 3/3 | 10 of 10 at 0/3 |
| 2026-09-26 (phase 5: 24 queries, description names learn-edit and interview) | claude-opus-5-5 | 24 of 24 | 12 of 12 at 3/3 | 12 of 12 at 0/3 |
| 2026-09-27 (phase 6: 30 queries, adds export, web feeds and transcripts, with near misses for exporting a document, transcribing a meeting and summarising a blog) | claude-opus-5-5 | 30 of 30 | 15 of 15 at 3/3 | 15 of 15 at 0/3 |
| 2026-09-27 (rules: 34 queries, adds loading the starter rules and adding a ruling, with near misses for humanizing a paragraph and a dash question) | claude-opus-5-5 | 34 of 34 | 17 of 17 at 3/3 | 17 of 17 at 0/3 |
| 2026-09-27 (style features: 41 queries, adds verify, a voice guide, a style-guide import and a warmer draft, with near misses for "does this sound like AI", a company style guide and "make this email warmer") | claude-opus-5-5 | 40 of 41 | 20 of 21 at 3/3 | 20 of 20 at 0/3 |

The one miss in the style-features run is the first query, `/idiolect learn ...`, at 0 of 3 (0 of 5 on a
recheck), which passed in every earlier run. Idiolect was installed in the account at 08:27 that day,
between the two runs, so a typed `/idiolect` most likely now calls the installed skill instead of the
copy under test, which the harness cannot count. The description is not the cause; run the trigger
tests where Idiolect is not installed, or read that query's result with this in mind.
