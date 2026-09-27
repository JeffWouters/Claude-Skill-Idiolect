"""Short mails are joined per thread, then per week (spec §6.4)."""
import email.message
import shutil

import inventory
import learn
import stage
from store import Store
from test_learn import make_store

WORDS = ("We keep the plan as it is and move the billing change first. The login change can wait a week "
         "because it breaks loudly and billing breaks quietly. Tell the testers to start with the old "
         "accounts. Call me if something looks odd. ").split()


def body(n, seed):
    w = [WORDS[(i + seed) % len(WORDS)] for i in range(n)]
    return " ".join(w).capitalize() + ".\n\nBest,\nSam\n"


def mail(path, subject, date, n, seed):
    m = email.message.EmailMessage()
    m["From"], m["To"], m["Subject"], m["Date"] = "Sam <sam@example.com>", "team@example.com", subject, date
    m.set_content(body(n, seed))
    path.write_bytes(bytes(m))


def setup(tmp_path):
    st = make_store(tmp_path)
    d = tmp_path / "Writing" / "mail"
    d.mkdir()
    # a thread of three short replies (about 60 words each)
    mail(d / "t1.eml", "Rollout plan", "Mon, 02 Mar 2026 09:00:00 +0100", 60, 1)
    mail(d / "t2.eml", "Re: Rollout plan", "Mon, 02 Mar 2026 11:00:00 +0100", 60, 7)
    mail(d / "t3.eml", "RE: Re: rollout plan", "Tue, 03 Mar 2026 09:00:00 +0100", 60, 13)
    # three unrelated short mails in the same ISO week
    mail(d / "w1.eml", "Lunch", "Wed, 04 Mar 2026 12:00:00 +0100", 55, 3)
    mail(d / "w2.eml", "Parking", "Thu, 05 Mar 2026 08:00:00 +0100", 55, 5)
    mail(d / "w3.eml", "Keys", "Fri, 06 Mar 2026 16:00:00 +0100", 55, 11)
    # a lonely short mail in another week stays too short
    mail(d / "lone.eml", "Hello", "Mon, 20 Apr 2026 09:00:00 +0200", 40, 2)
    return st, d


def test_short_mails_are_joined_per_thread_then_week(tmp_path):
    st, d = setup(tmp_path)
    rep = inventory.inventory(Store(st), targets=["mail"], dry_run=True)
    rows = {r["path"]: r for r in rep["rows"]}
    groups = {p: r for p, r in rows.items() if "/_joined/" in p}
    assert len(groups) == 2
    thread = next(r for p, r in groups.items() if "thread-" in p)
    week = next(r for p, r in groups.items() if "week-2026-W10" in p)
    assert thread["result"] == week["result"] == "new" and thread["words"] >= 150
    assert "t1.eml" in thread["note"] and "t3.eml" in thread["note"] and "w1.eml" in week["note"]
    assert rows["mail/t2.eml"]["result"] == "skipped: too short" and rows["mail/t2.eml"]["note"].startswith("joined into mail/_joined/thread-")
    assert rows["mail/lone.eml"]["result"] == "skipped: too short" and "note" not in rows["mail/lone.eml"]


def test_joined_mails_are_learned_and_a_new_member_changes_the_group(tmp_path):
    st, d = setup(tmp_path)
    f = tmp_path / "ans.yaml"
    f.write_text("folders:\n  - {path: mail, profile: noor, ownership: own, facets: {type: email}}\n"
                 "profiles:\n  - {name: noor, subject: synthetic fixture author, consent: 'public-domain fixture, evaluation only'}\n")
    names = tmp_path / "names.yaml"
    names.write_text("[]\n")

    def run():
        learn.start(st, targets=["mail"], profile="noor")
        if learn.questions(learn.Run(st))["undecided"] or learn.questions(learn.Run(st))["new_profiles_need"]:
            learn.answer(st, f)
        learn.mail_names(st, names)
        learn.stage_texts(st)
        learn.do_measure(st)
        stage.Pending(Store(st)).decide(all_decision="approved")
        stage.commit(st)
        return Store(st).manifest["texts"]

    texts = run()
    joined = {k: e for k, e in texts.items() if e.get("path") and "/_joined/" in e["path"]}
    assert len(joined) == 2 and all(e["origin"] == "mail" and e["redaction"]["redacted"] and e["cached"]
                                    for e in joined.values())
    week_key = next(k for k, e in joined.items() if "week-" in e["path"])
    assert "Best," not in Store(st).corpus_text(week_key)
    # a fourth short mail in the same week changes the week's text: the old one is superseded
    mail(d / "w4.eml", "Printer", "Fri, 06 Mar 2026 17:00:00 +0100", 50, 9)
    texts = run()
    assert texts[week_key]["status"] == "superseded"
    new = [e for k, e in texts.items() if e.get("path") == texts[week_key]["path"] and e["status"] == "active"]
    assert len(new) == 1
