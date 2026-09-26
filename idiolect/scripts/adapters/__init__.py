"""Source adapters: one kind of source in, cleaned blocks plus metadata out (spec §6).

extract(path) returns an Extract, or None when no adapter handles the extension (spec §5 row 2).
Adapters never decide ownership and never write to the source.
"""
import dataclasses
import pathlib


@dataclasses.dataclass
class Extract:
    blocks: list            # cleaned blocks (paragraphs, headings, list items), in order
    date: str = None        # document date (spec §5, near-duplicates), ISO date or date-time
    meta: dict = dataclasses.field(default_factory=dict)   # frontmatter lang/type/tags
    flags: list = dataclasses.field(default_factory=list)  # e.g. "page 3 has no text layer"

    @property
    def text(self):
        return "\n\n".join(self.blocks)


def extract(path):
    path = pathlib.Path(path)
    ext = path.suffix.lower()
    if ext in (".md", ".markdown"):
        from . import markdown
        return markdown.extract(path)
    if ext == ".docx":
        from . import docx
        return docx.extract(path)
    if ext == ".pdf":
        from . import pdf
        return pdf.extract(path)
    return None


HANDLED = (".md", ".markdown", ".docx", ".pdf")
