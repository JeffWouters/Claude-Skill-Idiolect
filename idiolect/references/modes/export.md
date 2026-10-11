# Mode: export

One self-contained prompt that carries the voice into another tool: another AI assistant, a custom
GPT, a writing app (spec §22). Read-only: nothing in the store changes.

```
python3 scripts/export.py --store S [--profile P] [--lang L] [--type T] [--facet k=v] [--include-parent] --out <file>.md
```

- The slot resolves as for `write`. If it would come from a parent profile, the script refuses; offer
  `include_parent=true` only when the writer is entitled to share the parent's voice (their own house
  style, say), and name the parent.
- It refuses the whole export if one example lacks a reviewed redaction record, and names it: those
  examples need reviewing in a `learn` first.
- The prompt holds rulings, the built-in signs of machine-written text (spec §37, with the writer's
  own rate where their texts show one), edit lessons, targets, the never-list, forms and non-private favoured
  phrases, the habits most texts show, and the example passages. It never holds the corpus, lesson
  quotes, edit pairs, rejections or private vocabulary.
- The other tool has no `check`: the prompt tells it to avoid the signs and reread for them, but
  nothing tests it. Say so, and suggest running `check` (or `aisigns.py scan`) on what it writes.

Hand the file to the writer and say:

- it describes one slot (name it); another type of text needs its own export;
- it is a snapshot: after the next `learn` it is out of date;
- the example passages are the writer's own text, redacted, so anyone who gets the file reads them;
- in the other tool, paste the file first and the brief after it.
