"""Distribution: the plugin marketplace, the plugin manifest, the changelog, the package and the
workflows agree with each other (design: Skill package)."""
import json
import pathlib
import re
import subprocess
import sys
import zipfile

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "idiolect" / ".claude-plugin" / "plugin.json"
MARKET = ROOT / ".claude-plugin" / "marketplace.json"


def manifest():
    return json.loads(PLUGIN.read_text(encoding="utf-8"))


def test_the_marketplace_lists_the_skill_folder_as_the_plugin():
    m = json.loads(MARKET.read_text(encoding="utf-8"))
    assert re.match(r"^[a-z0-9-]+$", m["name"])
    [entry] = m["plugins"]
    assert entry["name"] == manifest()["name"] == "idiolect"
    assert (ROOT / entry["source"] / ".claude-plugin" / "plugin.json").resolve() == PLUGIN.resolve()


def test_the_plugin_manifest_points_at_the_skill_and_names_no_person():
    p = manifest()
    assert re.match(r"^\d+\.\d+\.\d+$", p["version"])
    assert p["skills"] == ["./"] and (PLUGIN.parent.parent / "SKILL.md").exists()
    assert p["license"] == "MIT" and "contributors" in p["author"]["name"]      # no real people in the package


def test_the_changelog_has_an_entry_for_the_current_version():
    text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert re.search(rf"^## {re.escape(manifest()['version'])} \(\d{{4}}-\d{{2}}-\d{{2}}\)$", text, re.M)


def test_the_package_leaves_the_plugin_manifest_out(tmp_path):
    out = tmp_path / "dist"                                         # a folder that does not exist yet, as in CI
    p = subprocess.run([sys.executable, str(ROOT / "tools" / "build_package.py"), "--out", str(out)],
                       capture_output=True, text=True, check=True)
    assert f"version {manifest()['version']}" in p.stdout
    names = zipfile.ZipFile(out / "idiolect.skill").namelist()
    assert "idiolect/SKILL.md" in names and not any(".claude-plugin" in n for n in names)
    assert not any("__pycache__" in n for n in names)


def test_the_workflows_run_the_tests_and_release_on_a_version_tag():
    tests = yaml.safe_load((ROOT / ".github" / "workflows" / "tests.yml").read_text(encoding="utf-8"))
    steps = " ".join(s.get("run", "") for s in tests["jobs"]["pytest"]["steps"])
    assert "pip install -r requirements-dev.txt" in steps and "pytest tests" in steps
    rel = yaml.safe_load((ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8"))
    assert rel[True]["push"]["tags"] == ["v*.*.*"]                 # YAML reads the key `on` as True
    rsteps = " ".join(s.get("run", "") for s in rel["jobs"]["release"]["steps"])
    for part in ("plugin.json", "CHANGELOG.md", "pytest tests", "build_package.py", "gh release create"):
        assert part in rsteps, part


def test_requirements_cover_what_check_env_asks_for():
    req = (ROOT / "requirements-dev.txt").read_text(encoding="utf-8").lower()
    for pkg in ("pyyaml", "jsonschema", "markdown-it-py", "pdfminer.six", "lingua-language-detector", "pytest"):
        assert pkg in req, pkg
