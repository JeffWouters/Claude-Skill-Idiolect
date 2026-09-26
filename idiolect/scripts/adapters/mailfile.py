"""Mail adapter (spec §6.4): exported .eml files, and .msg when the optional extract-msg package is
installed. Only what the writer wrote is kept: quoted replies and signatures are removed."""
import email
import email.policy
import email.utils
import html
import re

from . import Extract

QUOTE_HEAD = re.compile(r"^(On .{3,200} wrote:|Op .{3,200} schreef .{0,80}:|-{2,}\s*Original Message\s*-{2,}|"
                        r"_{5,}|From:\s.+)$", re.I)
OUTLOOK_FIELD = re.compile(r"^(Sent|Date|To|Cc|Subject|Verzonden|Aan|Onderwerp):\s", re.I)
SIGNOFF = re.compile(r"^[A-Za-zÀ-ÿ' ]{2,40},\s*$")
SIGNOFF_WORDS = 4
SIGNOFF_WINDOW = 8


def _html_to_text(h):
    h = re.sub(r"(?is)<(script|style).*?</\1>", "", h)
    h = re.sub(r"(?i)<br\s*/?>", "\n", h)
    h = re.sub(r"(?i)</(p|div|li|h[1-6]|tr)>", "\n\n", h)
    return html.unescape(re.sub(r"<[^>]+>", "", h))


def strip_mail(body):
    """The writer's own part of a mail body: quotes and signature removed (spec §6.4)."""
    lines = body.replace("\r\n", "\n").split("\n")
    out = []
    for i, ln in enumerate(lines):
        s = ln.strip()
        if s.startswith(">"):
            continue
        if QUOTE_HEAD.match(s):
            # an Outlook header block: "From:" followed by Sent/To/Subject lines, or a plain marker
            if not s.lower().startswith("from:") or any(OUTLOOK_FIELD.match(x.strip()) for x in lines[i + 1:i + 4]):
                break
        if s == "--" and ln.rstrip("\n") in ("-- ", "--"):
            break
        out.append(ln)
    # a sign-off line ("Best,", "Kind regards,") in the last lines ends the prose
    tail_from = max(0, len(out) - SIGNOFF_WINDOW)
    for i in range(len(out) - 1, tail_from - 1, -1):
        s = out[i].strip()
        if SIGNOFF.match(s) and len(s.rstrip(",").split()) <= SIGNOFF_WORDS:
            out = out[:i]
            break
    text = "\n".join(out)
    return [re.sub(r"[ \t]*\n[ \t]*", " ", b).strip() for b in re.split(r"\n\s*\n", text) if b.strip()]


def _date(value):
    try:
        return email.utils.parsedate_to_datetime(value).isoformat() if value else None
    except (TypeError, ValueError):
        return None


def extract_eml(path):
    msg = email.message_from_bytes(path.read_bytes(), policy=email.policy.default)
    part = msg.get_body(preferencelist=("plain",))
    if part is not None:
        body = part.get_content()
    else:
        part = msg.get_body(preferencelist=("html",))
        body = _html_to_text(part.get_content()) if part is not None else ""
    return Extract(blocks=strip_mail(body), date=_date(msg["Date"]), meta={"origin": "mail"})


def extract_msg(path):
    try:
        import extract_msg as em
    except ImportError:
        return None
    m = em.Message(str(path))
    try:
        body = m.body or (_html_to_text(m.htmlBody.decode("utf-8", "replace")) if m.htmlBody else "")
        date = m.date.isoformat() if hasattr(m.date, "isoformat") else _date(m.date)
    finally:
        m.close()
    return Extract(blocks=strip_mail(body or ""), date=date, meta={"origin": "mail"})
