# Mode: guide

A voice guide for people: a document an editor, a ghostwriter or a colleague can follow to write in a
learned voice (spec §29). Read-only: writes nothing to the store and takes no lock. Run scripts from
the skill folder.

```
python3 scripts/guide.py --store S [--profile P] [--lang L] [--type T] [--examples N] [--out guide.md]
python3 scripts/guide.py --store S --profile acme --rulings-only --out style-guide.md    # the house style guide
```

- It covers one slot, resolved as for `write`. For more than one kind of text, make one guide per slot.
- A slot that belongs to a parent profile is refused unless the writer says so (`--include-parent`).
- It leaves out private vocabulary, lesson quotes and every corpus text. An example passage without a
  reviewed redaction record is left out and counted: offer to review it in the next `learn`.
- `--examples 0` leaves the passages out, for a guide that travels further.

Hand the file to the writer and say in one line what it holds and what was left out. The guide
describes the voice on the day it was made: a later `learn` changes the profile, not the file.

`export` is the other way out: one prompt for another AI tool (`export.md`).

## interactive=false

Never ask; write the file and return the JSON.
