# Style judge

Instructions for the blind judge in `eval-protocol.md`, step 4. They follow the blind-comparator rules
from skill-creator (the judge never learns which method made which draft, ranks without ties and gives
its reasons), with a style rubric in place of a task rubric.

## What you get

A packet with one passage by an author and three drafts, A, B and C. All three drafts were written
from the same short brief of that passage's content, so they cover roughly the same ground. You do
not know who the author is and you are not told how the drafts were made. Do not try to find out:
read only the packet you were given.

## The question

**Which draft reads most as if the author of the passage wrote it?** Rank all three, best first. No
ties: if two feel equal, decide on the rubric's first line where they differ.

## Judge voice, not content

The drafts share their content by design, so content says nothing. Ignore:

- which facts, events or images a draft includes, and whether it follows the passage closely;
- placeholders such as `[example needed]` or `[number needed]` (every method was told to use them);
- length, within the ±15% every draft was held to;
- spacing and typography (runs of spaces have been normalised);
- quality as such: a better essay is not a better match.

Do not reward a draft for reusing the passage's own words or phrases. Borrowed phrasing is copying,
not voice; judge what the draft does with its own sentences.

## Rubric, in order of weight

1. **Sentence movement.** Length and its variation, how sentences open, how clauses are joined,
   rhythm across a paragraph.
2. **Stance and tone.** How the writer stands towards the reader and the subject: confiding, arguing,
   ironic, earnest, plain; how much they hedge or assert.
3. **Diction.** Register, word length, period feel, recurring kinds of word, contractions or none.
4. **Punctuation habits.** Semicolons, dashes, colons, exclamations, questions, parentheses: how often
   and to what end.
5. **Structure.** How the piece opens, turns and ends; paragraph size.
6. **Caricature.** A draft that piles on the author's habits more thickly than the passage does reads
   as imitation, not as the author. Count it against the draft.

## Output

Write `judge-out/<id>.json` (the id is the packet's) and nothing else:

```json
{
  "ranking": ["B", "A", "C"],
  "reasons": {
    "A": "one line on why A sits where it does",
    "B": "one line",
    "C": "one line"
  }
}
```

`ranking` holds A, B and C once each, best match first. Reasons are about voice, one line each.
