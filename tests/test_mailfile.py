"""Phase 5: the mail adapter (spec §6.4) and mail texts in learn (origin mail, redacted cache)."""
import email.message

import adapters
import learn
import stage
from adapters import mailfile
from store import Store
from test_learn import make_store

BODY = """Hi team,

I read the rollout plan twice. The dates hold, but the order does not. We should move the billing
change before the login change, because billing breaks quietly and login breaks loudly. Loud is fine.
Quiet is what costs us a weekend. Call me on +31 6 1234 5678 if you disagree before Friday.

The rest can stay as it is. Nobody reads step nine anyway, and that is its own problem, which we can
fix another week. For now: billing first, then login, then the rest, in that order and no other.

One more thing about the testers. They should start with the old accounts, not the new ones. The new
accounts were made last month by people who knew the plan, so they follow it. The old accounts were
made years ago by people who never read a plan in their lives, and they are the ones that will break.
If the old accounts pass, the new ones will. The other way round tells us nothing at all, and we would
learn that on the Monday after, when it is too late to do anything but apologise to the customers.

Kind regards,
Sam
Acme Ltd | sam@example.com

On Tue, 3 Mar 2026 at 09:12, Jane Doe <jane@example.com> wrote:
> Here is the rollout plan for March.
> Let me know what you think.
"""


def eml(path, body=BODY, html=False):
    m = email.message.EmailMessage()
    m["From"] = "Sam <sam@example.com>"
    m["To"] = "team@example.com"
    m["Subject"] = "Re: rollout plan"
    m["Date"] = "Wed, 04 Mar 2026 10:00:00 +0100"
    if html:
        m.set_content("<p>" + body.replace("\n\n", "</p><p>") + "</p>", subtype="html")
    else:
        m.set_content(body)
    path.write_bytes(bytes(m))
    return path


def test_quotes_and_signature_are_removed(tmp_path):
    ex = adapters.extract(eml(tmp_path / "a.eml"))
    text = ex.text
    assert ex.meta["origin"] == "mail" and ex.date.startswith("2026-03-04")
    assert text.startswith("Hi team,") and "billing first" in text
    assert "Kind regards" not in text and "Jane" not in text and "rollout plan for March" not in text
    assert "Subject" not in text and "Re: rollout" not in text
    outlook = "My answer is no.\n\nIt is still no.\n\n-----Original Message-----\nFrom: X\nSent: today\n\nold text"
    assert mailfile.strip_mail(outlook) == ["My answer is no.", "It is still no."]
    block = "Fine by me.\n\nFrom: Jane Doe\nSent: Monday\nTo: Sam\nSubject: plan\n\nold"
    assert mailfile.strip_mail(block) == ["Fine by me."]
    sig = "Short and plain.\n\n-- \nSam\nAcme"
    assert mailfile.strip_mail(sig) == ["Short and plain."]
    assert "billing first" in adapters.extract(eml(tmp_path / "b.eml", html=True)).text


def test_msg_without_the_package_is_reported(tmp_path, monkeypatch):
    import builtins
    real = builtins.__import__

    def fake(name, *a, **k):
        if name == "extract_msg":
            raise ImportError
        return real(name, *a, **k)
    monkeypatch.setattr(builtins, "__import__", fake)
    (tmp_path / "x.msg").write_bytes(b"not really outlook")
    assert adapters.extract(tmp_path / "x.msg") is None


def test_mail_texts_are_learned_redacted_with_origin_mail(tmp_path):
    st = make_store(tmp_path)
    mail = tmp_path / "Writing" / "mail"
    mail.mkdir()
    for i in range(2):          # the second is a near-duplicate of the first: one is learned
        eml(mail / f"m{i}.eml", BODY.replace("twice", "twice" + " again" * i))
    (tmp_path / "Writing" / "mail" / "note.msg").write_bytes(b"x")
    learn.start(st, targets=["mail"], profile="noor")
    run = learn.Run(st)
    assert {i["origin"] for i in run.state["texts"].values() if i["path"].endswith(".eml")} == {"mail"}
    # no rule covers them: ownership is asked
    q = learn.questions(run)
    assert q["undecided"]
    f = tmp_path / "ans.yaml"
    f.write_text("folders:\n  - {path: mail, profile: noor, ownership: own, facets: {type: email}}\n"
                 "profiles:\n  - {name: noor, subject: synthetic fixture author, consent: 'public-domain fixture, evaluation only'}\n")
    learn.answer(st, f)
    names = tmp_path / "names.yaml"
    names.write_text("- {name: Jane Doe, placeholder: '[person]'}\n")
    learn.mail_names(st, names)
    learn.stage_texts(st)
    learn.do_measure(st)
    stage.Pending(Store(st)).decide(all_decision="approved")
    stage.commit(st)
    s = Store(st)
    mails = {k: e for k, e in s.manifest["texts"].items() if e["origin"] == "mail"}
    assert len(mails) == 1 and all(e["redaction"]["redacted"] and e["redaction"]["reviewed"] for e in mails.values())
    text = s.corpus_text(next(iter(mails)))
    assert "[phone]" in text and "+31 6" not in text
