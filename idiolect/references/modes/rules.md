# Mode: rules

Rulings are the writer's absolute instructions ("never use semicolons"). A ruling may carry a test, and
then `check` enforces it: any broken ruling fails a draft (spec §27). This mode adds rulings, loads the
optional starter set, and shows what applies. Store-writing: nothing changes until the writer approves
the diff. Run scripts from the skill folder.

## The starter set

`assets/starter-rules/en.yaml` holds common signs of machine-written text (em dashes, chatbot talk,
"delve", "a testament to", stacked hedges, filler, stock openers and conclusions, emojis, bold labels),
each as a ruling with a test and a category. It is **never applied by itself**. The writer loads it,
whole or by category, and approves each rule; from then on the rules are theirs, to edit or remove.

Two kinds:

- **Applies whatever the writer does** (`unless_writer_uses: false`): chatbot leftovers, praise for
  the question, knowledge-limit disclaimers, talk about the draft itself.
- **Applies unless the writer does it** (`unless_writer_uses: true`, everything else): if the writer's
  own texts of the slot use the thing (dashes, say), a draft may too, up to twice their rate; if they
  never do, neither may a draft.

## 1. Load the starter set

When the writer asks for default, standard or starter rules ("add the default rules", "stop the AI
tells", "no em dashes unless I use them"):

```
python3 scripts/rules.py starter [--lang en]                    # show the set, if they want to see it first
python3 scripts/rules.py --store S defaults [--profile P] [--lang en] [--category C ...]
```

Categories: `punctuation`, `chatbot`, `vocabulary`, `inflation`, `structure`, `framing`, `filler`,
`decoration`. It prints what it proposed and what it skipped (held unchanged, declined before, edited
by the writer). If it says nothing to propose, say so and stop.

## 2. Add one

When the writer states a rule, give it a test whenever a script can check it, and ask whether their
own habit should count (`--unless-writer-uses`) only when the rule is about something they might do
themselves:

```
python3 scripts/rules.py --store S add --profile P --text "Never use 'utilise'." --words utilise utilised utilising
python3 scripts/rules.py --store S add --profile P --text "No exclamation marks." --chars "!"
python3 scripts/rules.py --store S add --profile P --text "Never open with 'So,'." --pattern "^\s*so,"
```

One form per ruling: `--chars`, `--words` (whole words), `--phrases` (whole phrases) or `--pattern`
(a regular expression, case insensitive, per line). A rule no script can test ("keep a warm tone")
is added without a test: the kit carries it, the check cannot. `--slot K` or `--lang L` narrow it.
During a `learn` run, a lesson the writer calls "always" or "never" is promoted with `learn.py rule`
instead (`learn.md`, step 8).

## 3. Diff, approve, commit

`stage.py diff`, the writer's decisions, `stage.py commit`, as in `learn`. The proposals join a learn
run already waiting for approval, if there is one. A starter rule the writer rejects is remembered and
not proposed again for that version of the set. Say that rulings apply in every draft from then on,
and that a later version of the set never overwrites a rule the writer has edited.

## 4. Show what applies

```
python3 scripts/rules.py --store S show [--profile P] [--lang L] [--type T]
```

Lists the rulings that apply to the slot (inherited ones included) with, for those that apply unless
the writer does it, the writer's own rate per 1,000 words.

## Editing and removing

`profiles/<name>/rulings.yaml` is the writer's own file: edit or delete a ruling there (a text editor
is fine). The next run validates it; a malformed test stops with a message naming the ruling.

## interactive=false

Never ask. A proposal waits for the writer's approval, so return `needs_input` after `defaults` or
`add` with the diff summary.
