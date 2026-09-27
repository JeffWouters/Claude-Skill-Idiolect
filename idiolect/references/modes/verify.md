# Mode: verify

"Does this read like me?" Measures one text against the writer's own texts of a slot (spec §28).
Read-only: writes nothing and takes no lock. Run scripts from the skill folder.

```
python3 scripts/verify.py --store S --file text.md [--profile P] [--lang L] [--type T]
```

Relay the verdict, the measures furthest off and the note, in the script's words:

- **looks like the writer's texts**: closer to their typical text than most of their own texts are;
- **within the range of the writer's own texts**: further than usual, but their own texts go this far;
- **unlike the writer's texts**: further out than their own texts go.

It measures style on a handful of counts (sentence length, punctuation, hedges, contractions and the
like). Always say that one text is weak evidence: a short text, a different kind of text or a
deliberate change of style can move it. Never present the result as proof of who wrote something,
and never use it to judge a text by someone else as theirs or not.

A slot needs at least 5 texts; with fewer, say so and offer to learn more of that kind first. The
same measure runs at every `learn`, where it flags texts that do not fit their slot (`learn.md`, step 4).

## interactive=false

Never ask; return the JSON (`--json`).
