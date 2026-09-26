# Modes: forget, rollback, prune

The only modes that delete. Each builds a proposal that is approved or rejected **as a whole**;
nothing changes until the writer approves the diff (`stage.py diff`, `decide --approve all` or
`--reject all`, `commit`). Where the environment needs permission to delete, ask for it at commit
time and say why.

## forget

```
python3 scripts/maintain.py --store S forget --source <path or key> [--profile P] [--ownership own|assisted|exclude]
```

- Without `--ownership`: removes the text from `--profile` (or from every profile). When no profile
  owns it any more, its cached text is deleted; with no profile left it becomes `forgotten`, and
  later learns skip it.
- With `--ownership`: reclassifies it. `own` extracts and caches it again, also for a forgotten text,
  as long as the file still gives the same text.
- `--source` by path matches the current version of that file and its segments (earlier,
  superseded versions are history and stay as they are); by key, exactly one text.
- Examples taken from the text are removed and affected slots are re-measured in the same proposal.
  Lessons are refreshed at the next `learn`; say so.

## rollback

```
python3 scripts/maintain.py --store S rollback --profile P [--to <snapshot name>]
```

Restores the profile's files from the snapshot (latest by default), removes files created after it,
and restores that profile's ownership records, statuses and holdout flags. Other profiles are never
touched: a text that another profile also uses keeps its status, and only this profile's record
changes (this profile may then lack that text until the next learn; say so). The commit takes a new
snapshot first, so a rollback can itself be rolled back: a plain `rollback` straight after a rollback
undoes it. A profile's first learn has an empty snapshot, so rolling back to it removes everything
that learn added, including the profile itself; a later `learn` asks for the profile again and sees
the texts as new. Rejections are never rolled back, and lesson and example ids are never reused.

## prune

```
python3 scripts/maintain.py --store S prune --profile P [--keep 10]
```

Removes all but the newest `keep` snapshots. Pruning takes no snapshot of its own.
