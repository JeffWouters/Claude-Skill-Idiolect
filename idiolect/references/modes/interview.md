# Mode: interview

Builds or extends a slot from the writer's answers to open questions, for a kind of text they have
little written material for (spec §21). Store-writing: nothing is learned until the writer approves
the diff.

## 1. Start

The writer names the profile and the slot: language and type (`lang=nl type=post`), plus any further
facet. The type must be one of the store's `types`.

```
python3 scripts/interview.py --store S start --profile P --lang L --type T [--facet channel=x]
```

## 2. Ask

Ask one open question at a time that makes the writer write the kind of text the slot is for: an
opinion they hold ("What do most people get wrong about X?"), an explanation ("How would you explain Y
to a new colleague?"), a story from their work ("Tell me about a project that went differently than
planned"). Never ask about their private life, health, finances or other people's details; if an
answer names other people, say they will be kept as written in the store, which only the writer sees.

- Ask for at least 150 words per answer, in their own words, typed or dictated, and not to polish
  it: the aim is how they write when they are not trying.
- Save each answer as they gave it (a dictated answer as transcribed) and add it:

```
python3 scripts/interview.py --store S add --file answer.md
```

A shorter answer is refused; offer to join it with the next one. Three to five answers make a slot
worth measuring; say that fewer give `low` confidence.

## 3. Learn and approve

Then continue with `references/modes/learn.md` from **measurement** (`learn.py measure`) through
contrast, lessons, vocabulary, examples, the language flavour, the diff and the commit: the answers are ordinary texts of
the slot with `origin: interview`.

## interactive=false

Not available: an interview needs the writer. Return `needs_input`.
