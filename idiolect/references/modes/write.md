# Modes: write, rewrite, check

Read-only: these modes never write to the store and take no lock. Run scripts from the skill folder.

## Common start

1. `scripts/check_env.py`; find the store (SKILL.md).
2. Build the kit for the requested profile and facets:

   ```
   python3 scripts/kit.py --store S [--profile P] [--lang L] [--type T] [--facet channel=x] --brief <brief or text file> [--tone T] [--words N] [--flavour off]
   ```

   - **Tone.** When the writer asks for a lean ("warmer", "firmer", "more formal", "more casual",
     "softer", "cooler"), pass `--tone warm|cool|firm|soft|formal|casual`, and pass the same `--tone`
     to `check.py`. Two may be combined in the order the writer gave them (`firm,formal`); where they
     pull a measure both ways, the first decides and the kit says so. The kit's Tone section says
     which targets moved and the writer's range: stay inside it and get the rest of the tone from word
     choice and stance, never by exaggerating. A slot with fewer than 5 texts cannot take a tone: say so
     and write without it.

   - **Language flavour.** Pass `--words N` with the piece's length (the kit also reads "N words" from
     the brief) so the kit says how many traces of the writer's flavour this piece gets. When the writer
     asks for it without ("clean English", "no accent", `flavour=off`), pass `--flavour off` to both
     `kit.py` and `check.py`.

   - `no_slot`: ask which profile or type to use (with `interactive=false`, return `status: no_slot`
     and the message). `no_store`: say nothing has been learned yet and offer `learn`.
   - Name the profile and slot you use in your answer, and repeat any warning the kit gives (a parent
     profile, a pooled slot, low confidence).
3. Read the whole kit. The **example passages** come first because they are the voice: match how they
   read, including how sparingly they use each device. Never reuse their content, facts, names or turns
   of phrase. **Rulings** always apply; **edit lessons** (the writer's own corrections) come next. The
   **targets** are set for this piece from the writer's texts and these examples, and they are what
   `check` measures: aim at them, primary metrics first. The **Never sound like AI** section is built
   into the skill and applies to every voice: none of those signs, unless the kit says the writer's own
   texts do it (then never more than the rate it gives), and follow its guidance for what no script
   can check. Never use a **never-list** phrase. A **form**
   fixes how a word is written when you use it; it never asks you to use it. The **language
   flavour**, when the writer has one, is traces of another language in their prose, at a measured
   rate: use about the number the kit gives for this piece, each where it reads naturally, spread
   over the text and never two in one paragraph. They are the writer's grammar and idiom, never
   spelling mistakes. Fewer is fine; more is a caricature, and `check` fails it.
   - The **background** at the end describes what most of the writer's texts show. It is not a
     checklist: the examples already show these habits at the right density. Never add a habit
     because it is listed, and never stack habits. A caricature (every habit, each one more often
     than in the examples) reads less like the writer than a plain draft does.

## write

4. **Facts and an occasion first** (spec §38). The kit's "Facts for this piece" says whether the brief
   gives enough specifics. When it gives few, ask the writer once, in one message, before drafting:
   what prompted the piece (what happened, who asked, what they saw), three to five specifics (names,
   numbers, commands, what was tried and what came of it) and, if they like, their own first lines
   or notes. Do not ask when the brief already has them. With `interactive=false`, never ask: draft
   with placeholders and list the missing facts in your answer, outside the draft. A real post starts
   from an occasion, so open from what prompted it, never on a placeholder.
   Draft from the brief and those facts at the requested length (about 400 words when none is given).
   - **Say each point once** (spec §39). For a piece of 1,500 words or more the kit has a section "A
     long piece: one place per point": before drafting, write a point ledger, each point once with the
     section that owns it. Another section that needs the point refers back to it in a clause and never
     explains it again. Build the piece section by section against the ledger, not each section as if
     it stood alone. The ledger also gives each pointer to another chapter or piece one place. When
     the writer is there, show them the ledger in one message and draft after their answer (a changed
     order, a cut point); with `interactive=false`, draft from it directly.
   - **What the brief rules out.** When the kit has a section "The brief rules out", nothing in it
     goes into the draft: not a source it excludes, not a claim it lists.
   - **Never invent facts.** Numbers, names, dates, incidents and anecdotes come only from the brief
     or the writer. Where the voice wants one you do not have, leave a placeholder such as
     `[example needed: a real incident]` or `[number needed: how many]`.
   - Write the way the examples read; not every habit belongs in every text.
   - **The writer's quirks.** When the kit has "The writer's quirks", use the marks the writer uses
     (an ellipsis, an exclamation, a question, an aside in brackets, an emoji) where they would, about
     as often as given and never more; never one the writer does not use.
   - **Build it the way the writer builds.** When the kit has "Shape of the piece", keep paragraph
     length, sentences per paragraph, one-sentence paragraphs, section lengths, reader address and
     quotations inside the writer's ranges, near the middle. Some paragraphs are one line, some run
     long; one section carries the weight and the others are short. Paraphrase sources and name them;
     quote only the line whose exact words matter.
   - Before checking, reread the draft beside the examples. If any device (a hedge, a rhetorical
     question, an archaic word, an exclamation, a signature phrase) appears more often per paragraph
     than in the examples, cut it back.
   - Then reread it as a stranger looking for machine text (spec §37), for what no script can check:
     a generic statement where the writer would give the specific fact; things grouped in threes for
     rhythm; telling the reader why something matters instead of showing it; a closing summary, a
     list of challenges or a look at the future the brief did not ask for; synonyms cycled to avoid
     repeating a word; headings, bullets or bold where the examples use plain paragraphs; every
     sentence about the same length; a paragraph that ends on a short moral summing itself up. Fix
     what you find.
   - Then reread the whole draft once more for repetition: a point already made (against the ledger,
     for a long piece), a sentence that restates its own paragraph, the opening story summed up again,
     and "as I said earlier" or "more on this later" holding two tellings together. Cut the second
     telling; never reword it.
   - Last, reread against every ruling in the kit and every line of "The brief rules out". `check`
     tests only the rulings that carry a test; the others are yours to check.
5. Save the draft to a file and run
   `scripts/check.py --store S --file draft.md --brief <the same brief file> [same facets] [same --tone] [same --flavour] --json`,
   so it measures against the same targets as the kit. Placeholders are not measured; write them
   plainly. A line that breaks a ruling (`lesson: r-...`) fails the draft outright: fix every one.
   So does a line with a sign of machine-written text (`lesson: a-...`, the report's `ai_signs`):
   rewrite the sentence the way the writer would say it, never by swapping in a synonym of the
   flagged word. In a slot with few texts, a sign the writer does use only warns (`ai_signs.warned`):
   rewrite those lines too when you can, but they do not fail the draft.
   Too many language-flavour traces (`lesson: f-...`, the report's `flavour`) fail it too: remove
   traces until `hits` is within `allowed`.
   When the report's `shape` is `warned` (spec §41), the piece is built unlike the writer: revise the
   build for each measure outside the range (split or join paragraphs, shorten the sections that do not
   carry the argument, paraphrase quotations, turn to the reader), and count it as one of the
   check-driven revisions. It never fails the draft.
   If it fails, a primary metric is flagged, or a habit is **bunched**, revise what the report
   names, in the direction it names (overshoot or a bunch means too much of a habit: pull back, do not
   exaggerate the voice). At most two check-driven revisions; then return the best draft with its
   report. Removing an invented fact is not a check revision: always do it, and check again.
6. Return the text. With `report=true`, also the final check report (JSON). With `explain=true`,
   annotate the choices with the lesson or ruling ids behind them, after the text. Say so when
   confidence is low.
   - **Keeping the draft.** If the store has `publish.yaml` with `keep_drafts: true`, save the returned
     draft to a file and run `python3 scripts/published.py --store S keep --file draft.md --profile P
     --slot K --mode write` (`--mode rewrite` for a rewrite), so the version the writer publishes can later
     be matched to it (`published.md`). Without `publish.yaml` skip this.

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
- Then steps 5 and 6 as for `write`, with the input text as the `--brief` for both `kit.py` and
  `check.py`.

## check

```
python3 scripts/check.py --store S --file <text> [--profile P] [--lang L] [--type T] [--json]
```

Relay the verdict in one line, then the flagged metrics in plain words (both directions), any
bunched habits (where, how many uses against the writer's rate), any never-list lines, the number of
placeholders (`placeholders`; one in the opening paragraph is warned about, never a fail), any signs of
machine-written text (`ai_signs`: which, and the lines; they fail the draft unless the writer's own
texts do the same as often; `warned` ones are a warning only), the shape measures outside the
writer's range (`shape`; a warning from `warn_at` measures, never a fail), quirks overdone or missing
(`quirks`; hints only), and the
language flavour counted against the writer's rate (more than the writer's highest rate fails; fewer never does). A single flag is a hint, not a failure. Under 150 words the metrics are hints only.

## Signs of machine-written text without a profile

`python3 scripts/aisigns.py scan --file <text> [--lang L]` lists the built-in signs a text shows with
no store and no writer (every sign counts from its first use). `aisigns.py list --lang L` shows the
signs and the guidance. A writer who really does one of them (and whose texts do not show it yet) can
switch that sign off for their profile: `aisigns.py --store S allow --profile P --sign a-009`, a ruling
proposed for approval like any other (`rules.md`). Signs of the `always` tier (a chatbot's
self-description, its citation markup, talk about its knowledge cutoff) cannot be switched off.

## interactive=false (calling skills)

Never ask, not even for the facts of step 4: draft with placeholders and name the missing facts
beside the text. Return one of: `pass`, `fail`, `low_confidence` (with the text and the report), or
`no_slot`, `no_store`, `needs_input` (with the question you would have asked), `error` (with the
message). The check report schema is `assets/schemas/check-report.schema.json`.
