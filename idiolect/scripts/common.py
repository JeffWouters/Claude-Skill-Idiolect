"""Shared helpers for Idiolect scripts: loading and validating store files, atomic writes,
hashing, paths and time. Spec references are to docs/spec.md in the source repository."""
import datetime as _dt
import hashlib
import json
import os
import pathlib
import re
import unicodedata

import yaml

SKILL = pathlib.Path(__file__).resolve().parent.parent
SCHEMAS = SKILL / "assets" / "schemas"
GLOBAL_METRICS = SKILL / "assets" / "global-metrics.json"
LANG_DIR = SKILL / "references" / "lang"


class StoreError(Exception):
    """A problem that stops a run with status: error (spec §1.3)."""


# ---------- YAML 1.2 core loader (spec §1.2) ----------

class Yaml12Loader(yaml.SafeLoader):
    pass


Yaml12Loader.yaml_implicit_resolvers = {
    first: [(tag, rx) for tag, rx in resolvers
            if tag not in ("tag:yaml.org,2002:bool", "tag:yaml.org,2002:timestamp")]
    for first, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
}
Yaml12Loader.add_implicit_resolver(
    "tag:yaml.org,2002:bool", re.compile(r"^(?:true|True|TRUE|false|False|FALSE)$"), list("tTfF"))


def load_yaml_text(text):
    return yaml.load(text, Loader=Yaml12Loader)


def dump_yaml(data):
    return yaml.safe_dump(data, sort_keys=False, allow_unicode=True, default_flow_style=False)


# ---------- schemas ----------

_VALIDATORS = {}


def validator(name):
    if name not in _VALIDATORS:
        from jsonschema import Draft202012Validator, FormatChecker
        from referencing import Registry, Resource
        reg = Registry()
        for f in SCHEMAS.glob("*.schema.json"):
            s = json.loads(f.read_text(encoding="utf-8"))
            res = Resource.from_contents(s)
            reg = reg.with_resource(s["$id"], res).with_resource(f.name, res)
        s = json.loads((SCHEMAS / f"{name}.schema.json").read_text(encoding="utf-8"))
        _VALIDATORS[name] = Draft202012Validator(s, registry=reg, format_checker=FormatChecker())
    return _VALIDATORS[name]


def check_schema(name, data, where="data"):
    errors = sorted(validator(name).iter_errors(data), key=lambda e: list(e.path))
    if errors:
        e = errors[0]
        loc = "/".join(str(p) for p in e.path) or "(root)"
        raise StoreError(f"{where} does not match {name}.schema.json at {loc}: {e.message}")
    return data


# Current schema_version per store file (design: Schemas and migrations); anything not listed is 1.
VERSIONS = {"vocabulary": 2, "rulings": 2, "manifest": 2, "manifest-entries": 2}


def version_of(schema):
    return VERSIONS.get(schema, 1)


def read_store_file(path, schema):
    """Read a JSON or YAML store file and validate it (spec §1.3). An older schema_version stops with a
    message naming migrate.py: files are never upgraded silently."""
    path = pathlib.Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise StoreError(f"missing store file: {path}")
    try:
        data = json.loads(text) if path.suffix == ".json" or path.name == "lock" else load_yaml_text(text)
    except Exception as exc:  # noqa: BLE001 - any parse error stops the run
        raise StoreError(f"cannot parse {path}: {exc}")
    have = data.get("schema_version") if isinstance(data, dict) else None
    if isinstance(have, int) and have < version_of(schema):
        raise StoreError(f"{path} is schema version {have}, this engine needs {version_of(schema)}: "
                         f"run scripts/migrate.py --store <store> first")
    return check_schema(schema, data, str(path))


# ---------- writing ----------

def atomic_write(path, text):
    """Write to <file>.tmp in the same folder, then rename over the target (spec §1.4)."""
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


def write_json(path, data, schema=None):
    if schema:
        check_schema(schema, data, str(path))
    atomic_write(path, json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def write_yaml(path, data, schema=None):
    if schema:
        check_schema(schema, data, str(path))
    atomic_write(path, dump_yaml(data))


# ---------- hashing (spec §4) ----------

def normalise(text):
    text = unicodedata.normalize("NFC", text)
    text = "".join(" " if c.isspace() else c for c in text)
    return re.sub(" +", " ", text).strip(" ")


def content_hash(text):
    return hashlib.sha256(normalise(text).encode("utf-8")).hexdigest()


# ---------- words (references/fingerprint.md) ----------

WORD_RE = re.compile(r"[^\W\d_](?:[^\W\d_]|['-])*")


def words(text):
    return WORD_RE.findall(text.replace("’", "'").replace("‘", "'"))


def count_words(text):
    return len(words(text))


# ---------- time ----------

def utcnow():
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0)


def iso(dt):
    return dt.astimezone(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(s):
    return _dt.datetime.fromisoformat(s.replace("Z", "+00:00"))


def run_id(dt=None):
    return (dt or utcnow()).strftime("%Y%m%dT%H%M%SZ")


# ---------- paths (spec §2) ----------

def case_insensitive(root):
    """Probe whether the file system under root compares names case-insensitively (spec §2.3)."""
    root = pathlib.Path(root)
    try:
        probe = next(p for p in root.iterdir() if p.name.lower() != p.name.upper())
    except (StopIteration, OSError):
        return os.name == "nt"
    other = probe.with_name(probe.name.swapcase())
    return other.exists() and os.path.samefile(probe, other)


def rel(path, root):
    return pathlib.PurePath(os.path.relpath(path, root)).as_posix()
