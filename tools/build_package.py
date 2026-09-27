#!/usr/bin/env python3
"""Build idiolect.skill (a zip of the idiolect/ folder) for delivery. Never installs anything.

    python3 tools/build_package.py [--out DIR]
"""
import argparse
import json
import pathlib
import re
import zipfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
SKILL = ROOT / "idiolect"
SKIP = {"__pycache__", ".pytest_cache", ".claude-plugin"}   # the plugin manifest is for Claude Code only


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT))
    a = ap.parse_args()
    text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    desc = re.search(r"^description: (.*)$", text, re.M).group(1)
    assert len(desc) < 1024 and "<" not in desc and ">" not in desc, "description breaks the frontmatter rules"
    version = json.loads((SKILL / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))["version"]
    assert re.match(r"^\d+\.\d+\.\d+$", version), f"plugin.json version {version!r} is not x.y.z"
    pathlib.Path(a.out).mkdir(parents=True, exist_ok=True)
    out = pathlib.Path(a.out) / "idiolect.skill"
    files = sorted(p for p in SKILL.rglob("*") if p.is_file() and not (set(p.parts) & SKIP)
                   and not p.name.endswith((".pyc", ".tmp")))
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for f in files:
            z.write(f, pathlib.Path("idiolect") / f.relative_to(SKILL))
    print(f"{out} ({len(files)} files, version {version})")


if __name__ == "__main__":
    main()
