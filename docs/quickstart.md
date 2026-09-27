# Idiolect quickstart

From nothing to a first draft in your own voice, in about half an hour. You talk to Claude in plain
language; Claude runs the scripts. The examples use Sam, a fictional writer with essays in
`~/Writing/Published`.

## 1. Install

- **Claude Code on your computer:** copy the `idiolect` folder to `~/.claude/skills/idiolect`.
- **The Claude app:** add `idiolect.skill` as a skill in your account. A cloud session reaches the
  files on your computer only when it is linked to that computer ([runtime](../idiolect/references/runtime.md)).

The scripts need Python 3.10 or later and five packages:

```
python3 -m pip install PyYAML jsonschema markdown-it-py pdfminer.six lingua-language-detector
```

You do not have to run anything yourself: Claude runs `check_env.py` first and names what is missing.

**Say "Idiolect" in your requests.** "Rewrite this in my voice" on its own is left to other skills on
purpose; "rewrite this with Idiolect" or `/idiolect rewrite ...` uses this one.

## 2. Look before you learn

> /idiolect learn ~/Writing/Published dry-run=true

A dry run writes nothing. It lists what it found: how many texts, their language, and what it skips
and why (under 150 words of prose, near-duplicates, unreadable files). Use it to check that the
folder holds what you think it holds.

## 3. The first learn

> /idiolect learn ~/Writing/Published

Claude will ask three things:

1. **Where to keep the store**, the folder that holds everything learned. Pick one outside your
   writing folder, such as `~/Idiolect`. Your source files are only ever read, never changed.
2. **Which texts are yours.** Answer in plain words: "all mine except the two guest posts". Only
   texts you mark as your own are learned from; co-written ones can be kept aside as `assisted`.
3. **What kind of texts they are** (essay, post, email), when it cannot tell.

It then measures your texts, compares them with neutral AI rewrites of the same paragraphs, and
English and Dutch are fully supported; other languages that separate words with spaces are measured
on 11 of the 14 measures, and Claude says so.
writes down what sets you apart.

If a text measures unlike the rest (a guest post, a ghostwritten piece, or just an unusual one of
yours), Claude shows it with what is different and asks whether it is yours. Keep it, or set it aside
as `assisted` so it does not colour the profile.

## 4. Approve the diff

Nothing is saved until you approve. The diff lists every proposal as its own item:

- **Lessons**, such as "Opens with a short concrete scene", with how many of your texts show it.
- **Vocabulary**: words you always spell one way, and phrases you favour.
- **Example passages**, with names and organisations replaced by placeholders such as `[client]`.
- **The fingerprint and its confidence** for each slot, such as `en.essay`.

Reject anything that is not you ("reject l-004"). A rejection is remembered and not proposed again.
If a lesson is something you always or never do, say so and it becomes a **ruling**, which every
draft obeys. Then approve the rest.

**Confidence** is `low` below 3 texts or 3,000 words, and `high` from about 8 texts and 15,000 words
whose measurements agree. Low confidence works, but drafts are rougher: learn more texts of that kind.

## 5. Use it

| You say | What happens |
| --- | --- |
| "Write 400 words with Idiolect on why we stopped using spreadsheets for planning." | A draft in your voice, checked against your profile. Facts it does not have become placeholders such as `[example needed: a real incident]`, never inventions. |
| "Rewrite draft.md with Idiolect, depth=edit." | Your meaning and facts kept; sentences (and with `edit`, trimming) in your voice. |
| "Check this post against my Idiolect profile." | Pass or fail, with what is off: too many dashes, sentences too long, a phrase you never use. |
| "Here is the draft Idiolect wrote and the version I published. Learn from my edits." | Your corrections become edit lessons, which outrank everything learned from your texts. |
| "Write it with Idiolect, a bit firmer." | The same voice leaning one way: `warm`, `cool`, `firm`, `soft`, `formal` or `casual`. It moves only as far as your own texts go, never into a caricature. You can combine two, such as "firm and formal": where they pull something in opposite directions, the one you name first decides. Firm wants shorter sentences and formal longer ones, so "firm and formal" gives shorter sentences and "formal and firm" longer ones. |
| "Does this read like me? Check it with Idiolect." | How close the text measures to your own texts, and what differs most. A measure of style, not proof of who wrote it. |
| "Make an Idiolect voice guide for my editor." | A document a person can follow: your rules, the shape of your sentences, your habits and words, and a few example passages with names removed. `rulings-only=true` gives just the rules, as a house style guide. |
| "Import our house style guide into my Idiolect profile." | Claude reads the guide and proposes each rule it states, quoting the line it came from; you approve each one. Rules a script can test are checked in every draft. |
| "Load the Idiolect starter rules into my profile." | Optional rules against common signs of AI writing (em dashes, "delve", chatbot phrases, filler). Rules about habits apply only if your own texts don't have that habit, so if you use dashes, you keep them. You approve each rule. For Dutch, ask for the Dutch starter rules. |
| "Learn from what I publish with Idiolect: my posts end up in ~/Vault/Published." | Idiolect keeps the drafts it writes. A scan (by hand, or as a weekly scheduled task) finds the version you published, pairs it with its draft and queues the pair. When you say "process my Idiolect edit queue", your edits become edit lessons, after your approval as always. Published texts that match no draft are listed, so you can learn them too. A folder, a vault folder or an RSS feed all work. |

## 6. When something is off

- **Wrong lesson, or a text that should not have counted:**
  "Forget drafts/old-rant.md from my Idiolect store."
- **A whole learn you regret:** "Roll my Idiolect profile back to before yesterday's learn."
  A snapshot is taken before every approved change.
- **Where things stand:** "Show my Idiolect status": profiles, slots, confidence, anything waiting.
- **A session ended before you approved:** the next run offers to resume or discard it.

## Going deeper

| To learn about | Read |
| --- | --- |
| Every mode, step by step (what Claude does) | [`idiolect/references/modes/`](../idiolect/references/modes/) |
| Profiles, slots, facets such as `channel`, and inheritance | [design: Facets, resolution and inheritance](design.md#facets-resolution-and-inheritance) |
| What the store holds and how to back it up | [design: The store](design.md#the-store) |
| Testing your profile against a text it has not seen | [`modes/test.md`](../idiolect/references/modes/test.md) |
| Interviews, mail, web pages and talk transcripts | [`modes/interview.md`](../idiolect/references/modes/interview.md), [`modes/connector.md`](../idiolect/references/modes/connector.md) |
| Outliers at learn, and "does this read like me" | [`modes/verify.md`](../idiolect/references/modes/verify.md), [spec §28](spec.md#28-outliers-and-verify) |
| Voice guides and house style guides | [`modes/guide.md`](../idiolect/references/modes/guide.md), [spec §29](spec.md#29-voice-guide) |
| Tone within your voice | [`modes/write.md`](../idiolect/references/modes/write.md), [spec §31](spec.md#31-tone) |
| Learning from what you publish, and the scheduled scan | [`modes/published.md`](../idiolect/references/modes/published.md), [spec §33](spec.md#33-learning-from-what-the-writer-publishes) |
| Languages: English, Dutch, adding another | [`references/fingerprint.md`](../idiolect/references/fingerprint.md) (Language applicability), [spec §32](spec.md#32-language-packs) |
| Rulings, tests, the starter set and importing a style guide | [`modes/rules.md`](../idiolect/references/modes/rules.md), [spec §27](spec.md#27-rulings-with-tests-and-the-starter-set) |
| Exporting your voice as one prompt for another tool | [`modes/export.md`](../idiolect/references/modes/export.md) |
| What the metrics measure, and which languages are supported | [`references/fingerprint.md`](../idiolect/references/fingerprint.md) |
| Running from a cloud session on files on your computer | [`references/runtime.md`](../idiolect/references/runtime.md) |
| Why it works this way, and how well it does | [design](design.md): the worked example, quality plan and decision log |
| Exact file formats and rules | [spec](spec.md) and [`assets/schemas/`](../idiolect/assets/schemas/) |
