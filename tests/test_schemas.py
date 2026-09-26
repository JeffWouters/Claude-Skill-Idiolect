"""Validate the example store and the invalid cases against the schemas.

    python3 -m pytest tests/test_schemas.py -q
"""
import json
import pathlib

import pytest
import yaml

from yaml12 import load as yaml12_load
from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCHEMAS = ROOT / "idiolect" / "assets" / "schemas"
STORE = ROOT / "tests" / "example-store"


def _registry():
    reg = Registry()
    for f in SCHEMAS.glob("*.schema.json"):
        s = json.loads(f.read_text())
        res = Resource.from_contents(s)
        reg = reg.with_resource(s["$id"], res).with_resource(f.name, res)
    return reg


REG = _registry()


def validator(name):
    s = json.loads((SCHEMAS / f"{name}.schema.json").read_text())
    return Draft202012Validator(s, registry=REG, format_checker=FormatChecker())


def load(path):
    text = path.read_text()
    if path.suffix in (".yaml", ".yml"):
        return yaml12_load(text)
    return json.loads(text)


VALID = [
    ("idiolect", STORE / "idiolect.yaml"),
    ("sources", STORE / "sources.yaml"),
    ("manifest", STORE / "corpus" / "manifest.json"),
    ("profile", STORE / "profiles" / "sam" / "profile.yaml"),
    ("profile", STORE / "profiles" / "acme" / "profile.yaml"),
    ("rulings", STORE / "profiles" / "sam" / "rulings.yaml"),
    ("vocabulary", STORE / "profiles" / "sam" / "vocabulary.yaml"),
    ("rejected", STORE / "profiles" / "sam" / "rejected.yaml"),
    ("fingerprint", STORE / "profiles" / "sam" / "en.essay.json"),
    ("edit-pair", STORE / "profiles" / "sam" / "edits" / "p-001" / "pair.yaml"),
    ("manifest-entries", STORE / "profiles" / "sam" / "snapshots" / "2026-10-02T2141" / "manifest-entries.json"),
    ("lock", STORE / ".state" / "lock"),
    ("progress", STORE / ".state" / "progress.json"),
    ("pending", STORE / ".state" / "pending" / "plan.json"),
    ("check-report", ROOT / "tests" / "reports" / "pass.json"),
    ("global-metrics", ROOT / "idiolect" / "assets" / "global-metrics.json"),
    ("idiolect", ROOT / "tests" / "inventory-fixture" / "sources" / ".idiolect" / "idiolect.yaml"),
    ("sources", ROOT / "tests" / "inventory-fixture" / "sources" / ".idiolect" / "sources.yaml"),
    ("manifest", ROOT / "tests" / "inventory-fixture" / "sources" / ".idiolect" / "corpus" / "manifest.json"),
    ("check-report", ROOT / "tests" / "reports" / "needs_input.json"),
    ("check-report", ROOT / "tests" / "reports" / "no_slot.json"),
]


def _lock_load(p):
    return json.loads(p.read_text())


@pytest.mark.parametrize("schema,path", VALID, ids=[f"{s}:{p.name}" for s, p in VALID])
def test_valid_examples(schema, path):
    data = _lock_load(path) if path.name == "lock" else load(path)
    errors = list(validator(schema).iter_errors(data))
    assert not errors, "\n".join(e.message for e in errors)


INVALID = sorted((ROOT / "tests" / "invalid").iterdir())


@pytest.mark.parametrize("path", INVALID, ids=[p.name for p in INVALID])
def test_invalid_examples_fail(path):
    schema = path.name.split(".")[0]
    errors = list(validator(schema).iter_errors(load(path)))
    assert errors, f"{path.name} should be rejected by {schema}.schema.json"


def test_every_schema_is_exercised():
    covered = {s for s, _ in VALID} | {"common"}
    all_names = {f.name.replace(".schema.json", "") for f in SCHEMAS.glob("*.schema.json")}
    assert all_names <= covered, f"schemas without a valid example: {all_names - covered}"


YAML_CASES = sorted((ROOT / "tests" / "yaml-cases").iterdir())


@pytest.mark.parametrize("path", YAML_CASES, ids=[p.name for p in YAML_CASES])
def test_yaml12_cases_validate(path):
    """Spec §1.2: unquoted dates stay strings and `no` stays a string, so these files are valid."""
    schema = path.name.split(".")[0]
    errors = list(validator(schema).iter_errors(load(path)))
    assert not errors, "\n".join(e.message for e in errors)


@pytest.mark.parametrize("path", YAML_CASES, ids=[p.name for p in YAML_CASES])
def test_yaml11_loader_would_break_them(path):
    """The same files fail under plain PyYAML (YAML 1.1), which is why the loader matters."""
    schema = path.name.split(".")[0]
    assert list(validator(schema).iter_errors(yaml.safe_load(path.read_text())))
