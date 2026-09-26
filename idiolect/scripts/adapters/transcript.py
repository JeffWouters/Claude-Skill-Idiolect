"""Transcript adapter (spec §24): .vtt, .srt and *.transcript.txt, for a spoken-voice slot."""
import re

from . import Extract

TIME = re.compile(r"^(?:(\d+):)?(\d{1,2}):(\d{2})[.,](\d{1,3})\s*-->\s*(?:(\d+):)?(\d{1,2}):(\d{2})[.,](\d{1,3})")
VOICE = re.compile(r"<v(?:\.[^ >]*)?\s+([^>]+)>")
LABEL = re.compile(r"^([A-Z][\w .'-]{0,40}):\s+")
TAG = re.compile(r"</?[^>]+>")
PAUSE = 2.0


def _sec(h, m, s, ms):
    return int(h or 0) * 3600 + int(m) * 60 + int(s) + int(ms.ljust(3, "0")) / 1000


def cues(text):
    """[(start, end, speaker or None, text)] from a .vtt or .srt body; plain text gives one cue per line."""
    out = []
    blocks = re.split(r"\n\s*\n", text.replace("\r\n", "\n").strip())
    timed = any(TIME.search(ln) for b in blocks for ln in b.split("\n"))
    if not timed:
        for ln in text.splitlines():
            if ln.strip():
                m = LABEL.match(ln.strip())
                out.append((None, None, m.group(1).strip() if m else None, ln.strip()[m.end():] if m else ln.strip()))
        return out
    for b in blocks:
        lines = [ln for ln in b.split("\n") if ln.strip()]
        if not lines or lines[0].startswith(("WEBVTT", "NOTE", "STYLE", "REGION")):
            continue
        i = next((k for k, ln in enumerate(lines) if TIME.search(ln)), None)
        if i is None:
            continue
        t = TIME.search(lines[i])
        start, end = _sec(*t.groups()[:4]), _sec(*t.groups()[4:])
        body = " ".join(lines[i + 1:])
        speaker = None
        v = VOICE.search(body)
        if v:
            speaker = v.group(1).strip()
        body = TAG.sub("", body).strip()
        m = LABEL.match(body)
        if m and not speaker:
            speaker, body = m.group(1).strip(), body[m.end():]
        if body:
            out.append((start, end, speaker, body))
    return out


def extract(path):
    raw = path.read_text(encoding="utf-8", errors="replace")
    cs = cues(raw)
    paras, cur, last_end, last_spk = [], [], None, None
    for start, end, spk, body in cs:
        new = cur and ((spk and spk != last_spk) or (start is not None and last_end is not None and start - last_end >= PAUSE))
        if new:
            paras.append(" ".join(cur))
            cur = []
        cur.append(body)
        last_end, last_spk = end, spk or last_spk
    if cur:
        paras.append(" ".join(cur))
    speakers = sorted({s for _, _, s, _ in cs if s})
    flags = [f"several speakers ({', '.join(speakers)}): learn only a transcript of the writer alone"] if len(speakers) > 1 else []
    return Extract(blocks=paras, meta={"speakers": speakers}, flags=flags)
