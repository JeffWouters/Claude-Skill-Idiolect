# Modes: forget, rollback, prune, delete, remove, lift

The only modes that delete (`remove` and `lift` delete no files, only entries). Each builds a proposal that is approved or rejected **as a whole**;
nothing changes until the writer approves the diff (`stage.py diff`, `decide --approve all` or
`--reject all`, `commit`). Where the environment needs permission to delete, ask for it at commit
time and say why.

## forget

```
python3 scripts/maintain.py --store S forget --source <path or key> [--profile P] [--ownership own|assisted|exclude]
```

- Without `--ownership`: removes the text from `--profile` (recorded as `exclude` for that profile, so
  its folder rule does not give it back) or from every profile. When no profile
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
changes (the next learn gives this profile the current version again, through its rule; say so). The commit takes a new
snapshot first, so a rollback can itself be rolled back: a plain `rollback` straight after a rollback
undoes it. A profile's first learn has an empty snapshot, so rolling back to it removes everything
that learn added, including the profile itself; a later `learn` asks for the profile again and sees
the texts as new. Rejections are never rolled back, and lesson and example ids are never reused.

## prune

```
python3 scripts/maintain.py --store S prune --profile P [--keep 10]
```

Removes all but the newest `keep` snapshots. Pruning takes no snapshot of its own.

## delete

```
python3 scripts/maintain.py --store S delete --profile P
```

Deletes a whole profile (spec §35): its folder with every slot, ruling, vocabulary, flavour file,
rejection, changelog and snapshot; its ledger records (a text only this profile used leaves the
ledger and its cached text is deleted; a text another profile uses stays for that profile); its
source rules, kept drafts, queued edits and published sources. Refused for the store's default
profile and for a profile another profile extends. Show the diff and say plainly that deleting cannot
be rolled back; only the writer approves it. Ask for delete permission at commit time where needed.

## remove

```
python3 scripts/maintain.py --store S remove --profile P --id l-004 [--id v-002 ...] [--slot en.essay]
```

Removes learned items by id (spec §36): lessons `l-`, edit lessons `d-`, examples `e-`, vocabulary
items `v-`, rulings `r-` and flavour markers `f-`. Find the ids with `status` or on the profile's
pages. Each removal is recorded as the writer's rejection, so a later learn does not propose it
again; a starter rule is declined; a ruling the writer stated simply goes. A lesson id on several
slot pages with the same text goes from all of them; if the texts differ, the script asks for
`--slot`. The commit takes a snapshot, so it can be rolled back. Say that the item stays out until
the writer lifts the rejection.

## lift

```
python3 scripts/maintain.py --store S lift --profile P --id x-003 [--id f-002 --id s-011 ...]
```

Lifts rejections (`status.py --profile P` lists them with their ids): `x-` entries in `rejected.yaml`, rejected flavour markers `f-` (in the flavour
file's `rejected` list) and declined starter rules `s-`. Nothing comes back by itself: say that the
next learn, flavour step or `rules defaults` may propose the item again, for approval as always.
Never edit `rejected.yaml` by hand for this.
