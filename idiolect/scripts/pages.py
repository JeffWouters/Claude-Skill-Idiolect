"""Markdown store pages (assets/schemas/markdown-contracts.md): parse and render the slot page, the
examples page, the never-list and the changelog. Scripts parse by heading; the headings are fixed."""
import re

from common import dump_yaml, load_yaml_text

SLOT_SECTIONS = ["Stance", "Openings", "Structure", "Endings", "Sentences", "Tone", "Recurring devices",
                 "Seen once"]
LESSON_LINE = re.compile(r"^- \[(?P<id>[a-z]-\d{3,6})\] (?P<text>.*?)(?: _\((?P<ev>.*)\)_)?\s*$")
NONE_YET = "_None yet._"


def split_page(text):
    """(frontmatter dict, {heading: [lines]}) for a page with '---' frontmatter and '## ' headings."""
    meta, body = {}, text
    m = re.match(r"\A---\n(.*?)\n---\n?", text, re.S)
    if m:
        meta = load_yaml_text(m.group(1)) or {}
        body = text[m.end():]
    sections, current = {}, None
    for line in body.splitlines():
        if line.startswith("## "):
            current = line[3:].strip()
            sections[current] = []
        elif current is not None:
            sections[current].append(line)
    return meta, sections


def join_page(meta, sections):
    out = ["---", dump_yaml(meta).rstrip(), "---"]
    for head, lines in sections:
        out.append(f"## {head}")
        body = [ln for ln in lines if ln.strip()]
        out.extend(body or [NONE_YET])
        out.append("")
    return "\n".join(out).rstrip() + "\n"


# ---------- slot page ----------

def evidence_text(lesson):
    ev = lesson.get("evidence") or {}
    n = ev.get("count", 1)
    unit = lesson.get("unit", "text")
    part = f"{n} {unit}{'' if n == 1 else 's'}"
    if ev.get("quote"):
        q = ev["quote"].replace('"', "'")
        part += f'; "{q}"'
    return part


def parse_slot_page(text):
    """Returns (meta, confidence_line, lessons) with lessons as dicts {id, section, text, evidence_raw}."""
    meta, sections = split_page(text)
    conf = next((ln.strip() for ln in sections.get("Confidence", []) if ln.strip() and ln.strip() != NONE_YET), "")
    lessons = []
    for sec in SLOT_SECTIONS:
        for ln in sections.get(sec, []):
            m = LESSON_LINE.match(ln.strip())
            if m:
                lessons.append({"id": m.group("id"), "section": sec, "text": m.group("text"),
                                "evidence_raw": m.group("ev") or ""})
    return meta, conf, lessons


def render_slot_page(meta, confidence_line, lessons):
    by = {s: [] for s in SLOT_SECTIONS}
    for les in sorted(lessons, key=lambda x: x["id"]):
        sec = "Seen once" if les.get("seen_once") else les.get("section", "Recurring devices")
        ev = les.get("evidence_raw") if "evidence" not in les else evidence_text(les)
        by[sec if sec in by else "Recurring devices"].append(
            f"- [{les['id']}] {les['text']}" + (f" _({ev})_" if ev else ""))
    sections = [("Confidence", [confidence_line] if confidence_line else [])]
    sections += [(s, by[s]) for s in SLOT_SECTIONS]
    return join_page(meta, sections)


def confidence_line(conf):
    return f"{conf['level']} (count: {conf['count_level']}, stability: {conf['stability_level']})"


# ---------- examples page ----------

def parse_examples(text):
    meta, sections = split_page(text)
    passages = {k: "\n".join(v).strip() for k, v in sections.items()}
    out = []
    for e in meta.get("examples", []) or []:
        out.append({**e, "text": passages.get(e["id"], "")})
    return meta, out


def render_examples(meta, examples):
    meta = dict(meta)
    keep = ("id", "source", "habit", "redaction")      # markdown-contracts.md
    meta["examples"] = [{k: e[k] for k in keep if k in e} for e in sorted(examples, key=lambda e: e["id"])]
    sections = [(e["id"], [e["text"]]) for e in sorted(examples, key=lambda e: e["id"])]
    if not sections:
        return join_page(meta, [])
    return join_page(meta, sections)


# ---------- never-list ----------

def render_never(meta, markers):
    lines = [f'- "{m["marker"]}" _(AI {m["ai_per_1k"]:.1f} per 1k words, writer {m["writer_per_1k"]:.1f})_'
             for m in markers]
    return join_page(meta, [("Never does", lines)])


def parse_never(text):
    meta, sections = split_page(text)
    out = []
    for ln in sections.get("Never does", []):
        m = re.match(r'^- "(.*)" _\(AI ([\d.]+) per 1k words, writer ([\d.]+)\)_', ln.strip())
        if m:
            out.append({"marker": m.group(1), "ai_per_1k": float(m.group(2)), "writer_per_1k": float(m.group(3))})
    return meta, out


# ---------- changelog ----------

def changelog_append(existing, profile, when, mode, run_id, slots, summary, snapshot):
    head = existing if existing else f"---\nschema_version: 1\nprofile: {profile}\n---\n"
    entry = [f"## {when} · {mode} · run {run_id}"]
    if slots:
        entry.append("- Slots: " + ", ".join(slots))
    entry.append(f"- Summary: {summary}")
    if snapshot:
        entry.append(f"- Snapshot: {snapshot}/")
    return head.rstrip() + "\n\n" + "\n".join(entry) + "\n"


# ---------- ids ----------

def next_id(prefix, used_max, existing_ids=()):
    nums = [int(i.split("-")[1]) for i in existing_ids if i.startswith(prefix + "-")]
    n = max([used_max or 0] + nums) + 1
    return f"{prefix}-{n:03d}", n
