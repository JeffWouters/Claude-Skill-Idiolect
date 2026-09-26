# Modes: write, rewrite, check

Read-only: these modes never write to the store and take no lock. Run scripts from the skill folder.

## Common start

1. `scripts/check_env.py`; find the store (SKILL.md).
2. Build the kit for the requested profile and facets:

   ```
   python3 scripts/kit.py --store S [--profile P] [--lang L] [--type T] [--facet channel=x] --brief <brief or text file>
   ```

   - `no_slot`: ask which profile or type to use (with `interactive=false`, return `status: no_slot`
     and the message). `no_store`: say nothing has been learned yet and offer `learn`.
   - Name the profile and slot you use in your answer, and repeat any warning the kit gives (a parent
     profile, a pooled slot, low confidence).
3. Read the whole kit. The **example passages** come first because they are the voice: match how they
   read, including how sparingly they use each device. Never reuse their content, facts, names or turns
   of phrase. Precedence among the notes: **rulings** always; then **edit lessons**; then **observed
   lessons**. A **form** fixes how a word is written when you use it; it never asks you to use it.
   Never use a **never-list** phrase. The **targets** are what `check` measures; aim at them, primary
   metrics first.
   - **Sample habits, do not stack them.** Each lesson says how many of the writer's texts show it.
     "Usually shows" habits are the default; "sometimes shows" habits are optional and usually left
     out. No text of the writer uses every habit, so no piece does. A caricature (every habit, each
     one more often than in the examples) reads less like the writer than a plain draft does.
   - **Favoured phrases** are never required. Use one only where it falls naturally, and all of them
     together no more often than their rates (per 1,000 words) allow: in 400 words, a phrase at 2 per
     1,000 appears about once, or not at all.

## write

4. Draft from the brief at the requested length (about 400 words when none is given).
   - **Never invent facts.** Numbers, names, dates, incidents and anecdotes come only from the brief
     or the writer. Where the voice wants one you do not have, leave a placeholder such as
     `[example needed: a real incident]` or `[number needed: how many]`.
   - Follow the habits that fit this piece; not every habit belongs in every text. A lesson under
     "Seen once" is weak evidence: use it only if it fits naturally.
   - Before checking, reread the draft beside the examples. If any device (a hedge, a rhetorical
     question, an archaic word, an exclamation, a signature phrase) appears more often per paragraph
     than in the examples, cut it back.
5. Save the draft to a file and run `scripts/check.py --store S --file draft.md [same facets] --json`.
   If it fails, a primary metric is flagged, or a habit is **bunched**, revise what the report names,
   in the direction it names (overshoot or a bunch means too much of a habit: pull back, do not
   exaggerate the voice). At most two revisions; then return the best draft with its report.
6. Return the text. With `report=true`, also the final check report (JSON). With `explain=true`,
   annotate the choices with the lesson or ruling ids behind them, after the text. Say so when
   confidence is low.

## rewrite

The input is the writer's (or someone's) text. Keep its meaning, facts and quotes.

- **Language.** A rewrite never changes language. If `check.py` reports the text is in another
  language than the slot, refuse and say which slot would be needed.
- **depth** (default `voice`):
  - `voice`: change sentences only. Keep every paragraph, its order and its content; keep headings.
    List any structural suggestion separately after the text.
  - `edit`: as `voice`, and also trim redundancy, merge or split sentences and paragraphs. Do not
    reorder sections.
  - `full`: may restructure: reorder, rewrite openings and endings, cut sections. Still no new facts.
- Quoted or forwarded words of other people stay untouched.
- Then steps 5 and 6 as for `write`.

## check

```
python3 scripts/check.py --store S --file <text> [--profile P] [--lang L] [--type T] [--json]
```

Relay the verdict in one line, then the flagged metrics in plain words (both directions), any
bunched habits (where, how many uses against the writer's rate) and any never-list lines. A single flag is a hint, not a failure. Under 150 words the metrics are hints only.

## interactive=false (calling skills)

Never ask. Return one of: `pass`, `fail`, `low_confidence` (with the text and the report), or
`no_slot`, `no_store`, `needs_input` (with the question you would have asked), `error` (with the
message). The check report schema is `assets/schemas/check-report.schema.json`.
