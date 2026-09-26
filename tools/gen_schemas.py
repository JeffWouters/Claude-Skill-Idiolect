#!/usr/bin/env python3
"""Generate the JSON Schemas for every Idiolect store file.

Run from the repo root:  python3 tools/gen_schemas.py
Writes idiolect/assets/schemas/*.schema.json. Edit this file, not the output.
Every schema is draft 2020-12 and describes schema_version 1, except vocabulary (2).
"""
import json
import pathlib

OUT = pathlib.Path(__file__).resolve().parent.parent / "idiolect" / "assets" / "schemas"
BASE = "https://github.com/JeffWouters/Claude-Skill-Idiolect/schemas/v1/"
DRAFT = "https://json-schema.org/draft/2020-12/schema"

C = "common.schema.json#/$defs/"


def ref(name):
    return {"$ref": C + name}


common = {
    "$schema": DRAFT,
    "$id": BASE + "common.schema.json",
    "title": "Shared definitions for Idiolect store files",
    "$defs": {
        "schemaVersion": {"const": 1, "description": "Bumped on any format change; ships with a migration."},
        "profileName": {"type": "string", "pattern": "^[a-z][a-z0-9-]{0,39}$"},
        "facetName": {"type": "string", "pattern": "^[a-z][a-z0-9_]{0,29}$"},
        "facetValue": {"type": "string", "pattern": "^(_|[a-z0-9][a-z0-9-]{0,39})$",
                        "description": "A facet value, or _ for 'any'."},
        "langValue": {"type": "string", "pattern": "^[a-z]{2,3}(-[a-z0-9]{2,8})?$",
                       "description": "A language code. Never _."},
        "slotKey": {"type": "string",
                    "pattern": "^[a-z]{2,3}(-[a-z0-9]{2,8})?(\\.(_|[a-z0-9][a-z0-9-]{0,39}))+$",
                    "description": "One value per declared facet in declared order, lang first and never _."},
        "facetValues": {"type": "object",
                        "propertyNames": {"$ref": "#/$defs/facetName"},
                        "additionalProperties": {"$ref": "#/$defs/facetValue"},
                        "properties": {"lang": {"$ref": "#/$defs/langValue"}}},
        "hash": {"type": "string", "pattern": "^[0-9a-f]{64}$",
                 "description": "SHA-256 of the text normalised to Unicode NFC with whitespace collapsed, case kept."},
        "textKey": {"type": "string", "pattern": "^[0-9a-f]{64}(#([2-9]|[1-9][0-9]+))?$",
                    "description": "A content hash, or hash#n for segment n (n >= 2) of a mixed-language file. Stored on disk as <hash>-n.txt."},
        "relPath": {"type": "string", "minLength": 1,
                    "pattern": "^(?![A-Za-z]:)(?!/)(?!~)(?!.*\\\\)(?!(.*/)?\\.\\.(/|$)).+$",
                    "description": "Relative to sources_root. Forward slashes only. No drive letter, leading slash, ~, backslash or .. segments."},
        "storePath": {"type": "string", "minLength": 1,
                      "pattern": "^(?![A-Za-z]:)(?!/)(?!~)(?!.*\\\\)(?!(.*/)?\\.\\.(/|$)).+$",
                      "description": "Relative to the store root, same rules as relPath."},
        "glob": {"type": "string", "minLength": 1},
        "date": {"type": "string", "format": "date"},
        "dateTime": {"type": "string", "format": "date-time"},
        "ownership": {"enum": ["own", "assisted", "exclude"]},
        "id": {"type": "string", "pattern": "^[a-z]{1,4}-[0-9]{3,6}$",
               "description": "Stable entry id, e.g. r-001 (ruling), v-001 (vocabulary), x-001 (rejection), e-001 (example), p-001 (edit pair)."},
        "redaction": {
            "type": "object",
            "description": "Privacy record for any item that can leave the store.",
            "required": ["redacted", "version"],
            "properties": {
                "redacted": {"type": "boolean"},
                "version": {"type": "string", "pattern": "^[0-9]+\\.[0-9]+(\\.[0-9]+)?$",
                            "description": "Version of redact.py (plus model pass) that produced this item."},
                "reviewed": {"type": "boolean", "description": "Shown to and approved by the writer in a diff."}
            },
            "additionalProperties": False
        },
        "confidenceLevel": {"enum": ["low", "medium", "high"]}
    }
}

idiolect = {
    "$schema": DRAFT, "$id": BASE + "idiolect.schema.json",
    "title": "idiolect.yaml — store marker and settings",
    "type": "object",
    "required": ["schema_version", "sources_root", "facets", "types", "default_profile"],
    "properties": {
        "schema_version": ref("schemaVersion"),
        "sources_root": {"type": "string", "minLength": 1,
                         "pattern": "^(?![A-Za-z]:)(?![/\\\\])(?!~).+$",
                         "description": "Relative to the store folder, e.g. ../Writing. May start with ../ segments."},
        "facets": {"type": "array", "minItems": 2, "uniqueItems": True,
                   "prefixItems": [{"const": "lang"}, {"const": "type"}],
                   "items": ref("facetName"),
                   "description": "Declared order. lang first, type second; new facets only appended."},
        "types": {"type": "array", "minItems": 1, "uniqueItems": True,
                  "items": {"type": "string", "pattern": "^[a-z0-9][a-z0-9-]{0,39}$"},
                  "description": "Candidate values for type; the model picks from these or proposes a new one."},
        "default_profile": ref("profileName"),
        "defaults": {"allOf": [ref("facetValues")],
                     "description": "Fallback facet values after command, ledger and detection."}
    },
    "additionalProperties": False
}

source_entry_common = {
    "profile": ref("profileName"),
    "ownership": ref("ownership"),
    "facets": ref("facetValues"),
    "exclude": {"type": "array", "items": ref("glob")},
    "decided": ref("date")
}
sources = {
    "$schema": DRAFT, "$id": BASE + "sources.schema.json",
    "title": "sources.yaml — folder, file and tag rules of the ledger",
    "type": "object",
    "required": ["schema_version", "sources"],
    "properties": {
        "schema_version": ref("schemaVersion"),
        "sources": {"type": "array", "items": {
            "oneOf": [
                {"type": "object", "title": "path rule (folder or single file)",
                 "required": ["path", "profile", "ownership"],
                 "properties": {"path": ref("relPath"),
                                "recursive": {"type": "boolean", "default": True},
                                **source_entry_common},
                 "additionalProperties": False},
                {"type": "object", "title": "tag rule",
                 "required": ["tag", "profile", "ownership"],
                 "properties": {"tag": {"type": "string", "pattern": "^[^\\s#][^\\s]*$",
                                        "description": "Frontmatter tags: value or inline #tag, without the #."},
                                **source_entry_common},
                 "additionalProperties": False}
            ]}},
        "exclude": {"type": "array", "items": ref("glob")}
    },
    "additionalProperties": False
}

manifest_entry = {
    "type": "object",
    "required": ["origin", "profiles", "facets", "holdout", "status", "cached"],
    "properties": {
        "path": {"oneOf": [ref("relPath"), {"type": "null"}],
                 "description": "null for interview answers and connector sources."},
        "date": {"oneOf": [ref("date"), {"type": "null"}]},
        "origin": {"enum": ["file", "interview", "mail", "web"]},
        "profiles": {
            "type": "object", "minProperties": 1,
            "description": "Ownership per profile (spec §7). A profile the text does not feed is absent.",
            "propertyNames": ref("profileName"),
            "additionalProperties": {
                "type": "object", "required": ["ownership", "decided", "decided_by"],
                "properties": {
                    "ownership": ref("ownership"),
                    "decided": ref("date"),
                    "decided_by": {"enum": ["path-rule", "tag-rule", "writer"],
                                   "description": "Per-file answer (writer) beats path rule beats tag rule."}
                },
                "additionalProperties": False}},
        "facets": {"allOf": [ref("facetValues"), {"required": ["lang", "type"]}]},
        "words": {"type": "integer", "minimum": 0},
        "holdout": {"type": "boolean"},
        "status": {"enum": ["active", "superseded", "unreachable", "forgotten"]},
        "superseded_by": ref("textKey"),
        "cached": {"type": "boolean",
                   "description": "true when the text is own for at least one profile and not forgotten (spec §7.4)."},
        "redaction": ref("redaction")
    },
    "additionalProperties": False,
    "allOf": [
        {"if": {"properties": {"status": {"const": "superseded"}}},
         "then": {"required": ["superseded_by"]},
         "else": {"not": {"required": ["superseded_by"]}}},
        {"if": {"properties": {"status": {"const": "forgotten"}}},
         "then": {"properties": {"cached": {"const": False}}}},
        {"if": {"properties": {"origin": {"const": "mail"}, "cached": {"const": True}}},
         "then": {"required": ["redaction"],
                  "description": "Other people's details in mail are redacted in the corpus too."}}
    ]
}

manifest = {
    "$schema": DRAFT, "$id": BASE + "manifest.schema.json",
    "title": "corpus/manifest.json — per-text ledger entries and corpus index",
    "type": "object",
    "required": ["schema_version", "texts"],
    "properties": {
        "schema_version": ref("schemaVersion"),
        "texts": {"type": "object", "propertyNames": ref("textKey"),
                  "additionalProperties": {"$ref": "#/$defs/entry"}}
    },
    "additionalProperties": False,
    "$defs": {"entry": manifest_entry}
}

manifest_entries = {
    "$schema": DRAFT, "$id": BASE + "manifest-entries.schema.json",
    "title": "snapshots/<timestamp>/manifest-entries.json — the manifest entries feeding one profile at snapshot time",
    "type": "object",
    "required": ["schema_version", "profile", "taken", "texts"],
    "properties": {
        "schema_version": ref("schemaVersion"),
        "profile": ref("profileName"),
        "taken": ref("dateTime"),
        "texts": {"type": "object", "propertyNames": ref("textKey"),
                  "additionalProperties": {"$ref": "manifest.schema.json#/$defs/entry"}}
    },
    "additionalProperties": False
}

profile = {
    "$schema": DRAFT, "$id": BASE + "profile.schema.json",
    "title": "profiles/<name>/profile.yaml",
    "type": "object",
    "required": ["schema_version", "subject", "consent"],
    "properties": {
        "schema_version": ref("schemaVersion"),
        "subject": {"type": "string", "minLength": 1, "description": "Whose voice this is."},
        "consent": {"type": "string", "minLength": 1,
                    "description": "'self' for the user's own voice; otherwise a record of the subject's consent, or 'public-domain fixture, evaluation only'."},
        "extends": {"oneOf": [ref("profileName"), {"type": "null"}]},
        "since": {"oneOf": [{"type": "integer", "minimum": 1900, "maximum": 2200}, {"type": "null"}],
                  "description": "Writing from this year onward is weighted more."},
        "description": {"type": "string"}
    },
    "additionalProperties": False
}


def entry_list(title, item_props, required, extra=None):
    s = {
        "$schema": DRAFT, "$id": BASE + title,
        "type": "object",
        "required": ["schema_version", "entries"],
        "properties": {
            "schema_version": ref("schemaVersion"),
            "last_id": {"type": "integer", "minimum": 0,
                        "description": "Highest id number ever used in this file; ids are never reused (spec §14.2)."},
            "entries": {"type": "array", "items": {
                "type": "object", "required": required,
                "properties": item_props, "additionalProperties": False}}
        },
        "additionalProperties": False
    }
    if extra:
        s.update(extra)
    return s


rulings = entry_list("rulings.schema.json", {
    "id": ref("id"),
    "text": {"type": "string", "minLength": 1},
    "slot": {"oneOf": [ref("slotKey"), {"type": "null"}], "description": "null = applies to every slot."},
    "overrides": {"oneOf": [ref("id"), {"type": "null"}], "description": "Id of a parent profile's ruling this replaces."},
    "origin": {"enum": ["stated", "promoted"]},
    "promoted_from": {"type": "string", "pattern": "^(l|d)-[0-9]{3,6}$",
                      "description": "The observed or edit lesson this ruling was promoted from."},
    "created": ref("date"),
    "personal_data": {"const": "none"}
}, ["id", "text", "origin", "created", "personal_data"], {"title": "profiles/<name>/rulings.yaml"})

vocabulary = entry_list("vocabulary.schema.json", {
    "id": ref("id"),
    "text": {"type": "string", "minLength": 1},
    "kind": {"enum": ["term", "spelling", "coinage", "phrase"],
             "description": "term, spelling and coinage are forms: written exactly this way whenever used, never "
                            "required. phrase is a favoured phrase: a habit with a measured rate, never required."},
    "note": {"type": "string"},
    "private": {"type": "boolean", "description": "Private entries are never exported."},
    "overrides": {"oneOf": [ref("id"), {"type": "null"}]},
    "created": ref("date"),
    "rate": {"type": "object", "required": ["per_1k", "texts", "of", "measured"],
             "description": "Phrases only: how often the profile's own texts use it, measured by script.",
             "properties": {"per_1k": {"type": "number", "minimum": 0},
                            "texts": {"type": "integer", "minimum": 0, "description": "Texts that use it at least once."},
                            "of": {"type": "integer", "minimum": 0, "description": "Texts measured."},
                            "measured": ref("date")},
             "additionalProperties": False}
}, ["id", "text", "kind", "private", "created"], {"title": "profiles/<name>/vocabulary.yaml"})
# version 2 (design: Schemas and migrations): keep -> phrase, phrase rates
vocabulary["properties"]["schema_version"] = {"const": 2, "description": "Version 2: kind keep became phrase, with a rate. migrate.py upgrades version 1."}

rejected = entry_list("rejected.schema.json", {
    "id": ref("id"),
    "slot": {"oneOf": [ref("slotKey"), {"type": "null"}], "description": "null for vocabulary, which is per profile."},
    "kind": {"enum": ["observed", "edit", "vocabulary", "example"]},
    "text": {"type": "string", "minLength": 1},
    "normalised": {"type": "string", "minLength": 1,
                   "description": "Lower-case, punctuation removed, stop words from references/lang/<lang>/stopwords.txt removed, single spaces."},
    "rejects": {"type": "string", "pattern": "^(l|d|v|e)-[0-9]{3,6}$",
                "description": "Id of the rejected lesson, vocabulary entry or example (spec §14.2)."},
    "rejected": ref("date")
}, ["id", "slot", "kind", "text", "normalised", "rejected"], {"title": "profiles/<name>/rejected.yaml"})

fingerprint = {
    "$schema": DRAFT, "$id": BASE + "fingerprint.schema.json",
    "title": "profiles/<name>/<slot>.json — slot fingerprint",
    "type": "object",
    "required": ["schema_version", "profile", "slot", "pooled", "metrics", "counts", "confidence",
                 "seed", "metric_list", "built", "personal_data"],
    "properties": {
        "schema_version": ref("schemaVersion"),
        "profile": ref("profileName"),
        "slot": ref("slotKey"),
        "pooled": {"type": "boolean"},
        "metrics": {
            "type": "object", "minProperties": 1,
            "propertyNames": {"pattern": "^[a-z][a-z0-9_]{0,59}$"},
            "additionalProperties": {
                "type": "object",
                "required": ["value", "overshoot", "shortfall", "primary"],
                "properties": {
                    "value": {"type": "number"},
                    "overshoot": {"type": "number", "exclusiveMinimum": 1,
                                  "description": "Flag when draft/writer ratio exceeds this, e.g. 2.0."},
                    "shortfall": {"type": "number", "exclusiveMinimum": 0, "exclusiveMaximum": 1,
                                  "description": "Flag when draft/writer ratio falls below this, e.g. 0.5."},
                    "primary": {"type": "boolean"}
                },
                "additionalProperties": False
            }
        },
        "counts": {"type": "object", "required": ["texts", "words"],
                   "properties": {"texts": {"type": "integer", "minimum": 0},
                                  "words": {"type": "integer", "minimum": 0}},
                   "additionalProperties": False},
        "confidence": {"type": "object", "required": ["level", "count_level", "stability_level"],
                       "properties": {"level": ref("confidenceLevel"),
                                      "count_level": ref("confidenceLevel"),
                                      "stability_level": ref("confidenceLevel"),
                                      "splits": {"type": "integer", "minimum": 1}},
                       "additionalProperties": False},
        "seed": {"type": "integer", "minimum": 0},
        "metric_list": {"enum": ["global", "contrast"],
                        "description": "global = no contrast pass yet; contrast = primary flags set by this slot's contrast pass. The list itself is always the applicable global metrics (spec §17.1)."},
        "contrast": {"type": "object",
                     "properties": {"sample_texts": {"type": "array", "items": ref("textKey")},
                                    "corpus_words_at_sample": {"type": "integer", "minimum": 0},
                                    "fresh_context": {"type": "boolean"}},
                     "additionalProperties": False},
        "built": ref("dateTime"),
        "personal_data": {"const": "none"}
    },
    "additionalProperties": False
}

check_report = {
    "$schema": DRAFT, "$id": BASE + "check-report.schema.json",
    "title": "Output of check (and of write/rewrite with report=true)",
    "type": "object",
    "required": ["schema_version", "status"],
    "properties": {
        "schema_version": ref("schemaVersion"),
        "status": {"enum": ["pass", "fail", "low_confidence", "no_slot", "no_store", "needs_input", "error"]},
        "message": {"type": "string"},
        "question": {"type": "string", "description": "Present when status is needs_input."},
        "profile": ref("profileName"),
        "slot": ref("slotKey"),
        "confidence": ref("confidenceLevel"),
        "flagged": {"type": "integer", "minimum": 0, "description": "Number of metrics flagged."},
        "fail_threshold": {"type": "integer", "minimum": 1,
                           "description": "The resolved fail count (spec §17.2): 4 for 11 to 14 applicable metrics. The draft fails when flagged >= fail_threshold."},
        "metrics": {"type": "array", "items": {
            "type": "object", "required": ["name", "draft", "writer", "ratio", "flag"],
            "properties": {"name": {"type": "string"}, "draft": {"type": "number"},
                           "writer": {"type": "number"},
                           "ratio": {"type": ["number", "null"],
                                     "description": "draft / writer; null when the writer's value is below the metric's floor (then judged by absolute difference, spec §17.1)."},
                           "flag": {"enum": ["ok", "overshoot", "shortfall"]},
                           "primary": {"type": "boolean"}},
            "additionalProperties": False}},
        "bunched": {"type": "array", "description": "Habits used far above the writer's rate in one paragraph "
                    "(design: Guardrails, No caricature). A revision trigger, not a fail by itself.",
                    "items": {"type": "object", "required": ["paragraph", "habit", "count", "expected"],
                              "properties": {"paragraph": {"type": "integer", "minimum": 0,
                                                           "description": "1-based; 0 means the whole text."},
                                             "habit": {"type": "string"},
                                             "count": {"type": "integer", "minimum": 0},
                                             "expected": {"type": "number", "minimum": 0}},
                              "additionalProperties": False}},
        "flagged_lines": {"type": "array", "items": {
            "type": "object", "required": ["line", "text", "reason"],
            "properties": {"line": {"type": "integer", "minimum": 1}, "text": {"type": "string"},
                           "lesson": {"type": "string", "description": "Id or slug of the lesson, ruling or never-list marker broken."},
                           "reason": {"type": "string"}},
            "additionalProperties": False}}
    },
    "additionalProperties": False,
    "allOf": [
        {"if": {"properties": {"status": {"const": "needs_input"}}}, "then": {"required": ["question"]}},
        {"if": {"properties": {"status": {"enum": ["pass", "fail", "low_confidence"]}}},
         "then": {"required": ["profile", "slot", "confidence", "metrics", "flagged", "fail_threshold"]}},
        {"if": {"properties": {"status": {"enum": ["no_slot", "no_store", "error"]}}},
         "then": {"required": ["message"]}}
    ]
}

lock = {
    "$schema": DRAFT, "$id": BASE + "lock.schema.json",
    "title": ".state/lock — held by any store-writing mode",
    "type": "object",
    "required": ["schema_version", "mode", "started", "heartbeat"],
    "properties": {
        "schema_version": ref("schemaVersion"),
        "mode": {"enum": ["learn", "learn-edit", "interview", "forget", "rollback", "prune", "test", "migrate"]},
        "profile": ref("profileName"),
        "started": ref("dateTime"),
        "heartbeat": ref("dateTime"),
        "pending": {"type": "boolean", "description": "Informational: a pending area exists. Takeover depends only on the heartbeat age (spec §10)."}
    },
    "additionalProperties": False
}

progress = {
    "$schema": DRAFT, "$id": BASE + "progress.schema.json",
    "title": ".state/progress.json — resumable batch progress",
    "type": "object",
    "required": ["schema_version", "run_id", "mode", "target", "batch_size", "batches_done", "done", "started", "updated"],
    "properties": {
        "schema_version": ref("schemaVersion"),
        "run_id": {"type": "string", "pattern": "^[0-9]{8}T[0-9]{6}Z$"},
        "mode": {"enum": ["learn", "interview"]},
        "target": {"type": "string"},
        "batch_size": {"type": "integer", "minimum": 1, "maximum": 50},
        "batches_done": {"type": "integer", "minimum": 0},
        "done": {"type": "array", "items": ref("relPath"), "description": "Source paths already through steps 1-4."},
        "started": ref("dateTime"),
        "updated": ref("dateTime")
    },
    "additionalProperties": False
}

pending = {
    "$schema": DRAFT, "$id": BASE + "pending.schema.json",
    "title": ".state/pending/plan.json — what a run proposes, awaiting approval (spec §9)",
    "type": "object",
    "required": ["schema_version", "run_id", "mode", "created", "items"],
    "properties": {
        "schema_version": ref("schemaVersion"),
        "run_id": {"type": "string", "pattern": "^[0-9]{8}T[0-9]{6}Z$"},
        "mode": {"enum": ["learn", "learn-edit", "interview", "forget", "rollback", "prune", "test"]},
        "profiles": {"type": "array", "items": ref("profileName")},
        "created": ref("dateTime"),
        "items": {"type": "array", "items": {
            "type": "object", "required": ["id", "kind", "op", "path", "summary", "decision"],
            "properties": {
                "id": {"type": "string", "pattern": "^i-[0-9]{3,6}$"},
                "kind": {"enum": ["corpus-text", "ownership", "rule", "profile", "status", "lesson", "edit-lesson",
                                  "ruling", "vocabulary", "example", "fingerprint", "never-list", "slot-page",
                                  "rejection", "holdout", "deletion", "restore", "snapshot-prune"]},
                "op": {"enum": ["add", "modify", "remove"]},
                "profile": ref("profileName"),
                "slot": ref("slotKey"),
                "ref": {"type": "string", "description": "The id or text key the item is about (l-003, a hash, ...)."},
                "path": ref("storePath"),
                "summary": {"type": "string", "minLength": 1},
                "decision": {"enum": ["pending", "approved", "rejected"]}
            },
            "additionalProperties": False}},
        "commit": {
            "type": "object", "required": ["started", "steps"],
            "description": "The journal, written before the first commit write (spec §9.4). Its presence means the store is half-written.",
            "properties": {
                "started": ref("dateTime"),
                "steps": {"type": "array", "minItems": 1, "items": {
                    "type": "object", "required": ["op", "path", "state"],
                    "properties": {
                        "op": {"enum": ["write", "delete", "snapshot", "changelog"]},
                        "path": ref("storePath"),
                        "state": {"enum": ["todo", "done"]}
                    },
                    "additionalProperties": False}}
            },
            "additionalProperties": False}
    },
    "additionalProperties": False
}

edit_pair = {
    "$schema": DRAFT, "$id": BASE + "edit-pair.schema.json",
    "title": "profiles/<name>/edits/<id>/pair.yaml — one stored edit pair",
    "type": "object",
    "required": ["schema_version", "id", "slot", "date", "redaction", "changes"],
    "properties": {
        "schema_version": ref("schemaVersion"),
        "id": ref("id"),
        "slot": ref("slotKey"),
        "date": ref("date"),
        "redaction": ref("redaction"),
        "changes": {"type": "array", "items": {
            "type": "object", "required": ["id", "before", "after"],
            "properties": {
                "id": {"type": "string", "pattern": "^c-[0-9]{3,6}$"},
                "before": {"type": "string"},
                "after": {"type": "string"},
                "kind": {"type": "string", "description": "Model-assigned category, e.g. cut-hedge, split-paragraph."}
            },
            "additionalProperties": False}}
    },
    "additionalProperties": False
}

global_metrics = {
    "$schema": DRAFT,
    "$id": BASE + "global-metrics.schema.json",
    "title": "Global metric list shipped with the skill (assets/global-metrics.json)",
    "type": "object",
    "required": ["schema_version", "source", "fail_fraction", "downgrade_fraction", "min_count", "metrics"],
    "properties": {
        "schema_version": ref("schemaVersion"),
        "source": {"type": "string"},
        "fail_fraction": {"type": "number", "exclusiveMinimum": 0, "maximum": 1},
        "downgrade_fraction": {"type": "number", "exclusiveMinimum": 0, "maximum": 1},
        "min_count": {"type": "integer", "minimum": 1},
        "note": {"type": "string"},
        "metrics": {"type": "array", "minItems": 1, "items": {
            "type": "object",
            "required": ["name", "overshoot", "shortfall", "floor", "stability_tolerance", "sparse"],
            "properties": {
                "name": {"type": "string", "pattern": "^[a-z][a-z0-9_]*$"},
                "overshoot": {"type": "number", "minimum": 1},
                "shortfall": {"type": "number", "minimum": 0, "maximum": 1},
                "floor": {"type": "number", "exclusiveMinimum": 0},
                "stability_tolerance": {"type": "number", "exclusiveMinimum": 0, "maximum": 1.5},
                "sparse": {"type": "boolean"}
            },
            "additionalProperties": False}}
    },
    "additionalProperties": False
}

RESULTS = ["unchanged", "moved", "copy", "reverted", "changed", "new",
           "skipped: not prose", "skipped: language not supported", "skipped: forgotten",
           "skipped: holdout", "skipped: earlier version", "skipped: too short", "skipped: near-duplicate"]

inventory_report = {
    "$schema": DRAFT, "$id": BASE + "inventory-report.schema.json",
    "title": "Inventory report (learn step 1, the whole output of dry-run=true); also the format of expected-inventory.json",
    "type": "object",
    "required": ["schema_version", "scope", "rows", "unreachable"],
    "properties": {
        "schema_version": ref("schemaVersion"),
        "command": {"type": "string"},
        "store": {"type": ["string", "null"], "description": "Store root used; null when a dry run runs without a store."},
        "scope": {"type": "string"},
        "not_listed": {"type": "array", "items": {"type": "string"},
                       "description": "Excluded paths or folders with the reason; informational, never compared."},
        "rows": {"type": "array", "items": {
            "type": "object", "required": ["path", "key", "result", "words", "lang", "type"],
            "properties": {
                "path": ref("relPath"),
                "key": {"oneOf": [ref("textKey"), {"type": "null"}],
                        "description": "null only for skipped: not prose. In an expected file null means 'not asserted'."},
                "result": {"enum": RESULTS},
                "words": {"type": ["integer", "null"], "minimum": 0,
                          "description": "Words of this text after cleaning (references/fingerprint.md); null when not extracted."},
                "lang": {"oneOf": [ref("langValue"), {"type": "null"}],
                         "description": "Resolved main language (spec §12.1); null for not prose."},
                "type": {"oneOf": [ref("facetValue"), {"const": "?"}, {"type": "null"}],
                         "description": "Resolved type; ? when only the model could tell (dry run); null for not prose."},
                "note": {"type": "string"}
            },
            "additionalProperties": False}},
        "unreachable": {"type": "array", "items": {
            "type": "object", "required": ["path", "key"],
            "properties": {"path": ref("relPath"), "key": ref("textKey")},
            "additionalProperties": False}},
        "notes": {"type": "array", "items": {"type": "string"}}
    },
    "additionalProperties": False
}

SCHEMAS = {
    "inventory-report": inventory_report,
    "global-metrics": global_metrics,
    "common": common, "idiolect": idiolect, "sources": sources, "manifest": manifest,
    "profile": profile, "rulings": rulings, "vocabulary": vocabulary, "rejected": rejected,
    "fingerprint": fingerprint, "manifest-entries": manifest_entries, "check-report": check_report, "lock": lock,
    "progress": progress, "pending": pending, "edit-pair": edit_pair,
}

if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    for name, s in SCHEMAS.items():
        (OUT / f"{name}.schema.json").write_text(json.dumps(s, indent=2, ensure_ascii=False) + "\n")
    print(f"wrote {len(SCHEMAS)} schemas to {OUT}")
