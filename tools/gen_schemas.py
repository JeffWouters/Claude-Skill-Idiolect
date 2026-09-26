#!/usr/bin/env python3
"""Generate the JSON Schemas for every Idiolect store file.

Run from the repo root:  python3 tools/gen_schemas.py
Writes idiolect/assets/schemas/*.schema.json. Edit this file, not the output.
Every schema is draft 2020-12 and describes schema_version 1.
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
                    "pattern": "^(?![A-Za-z]:)(?![/\\\\])(?!~)(?!.*(^|[/\\\\])\\.\\.([/\\\\]|$)).+$",
                    "description": "Relative to sources_root. Forward slashes. No drive letter, leading slash, ~ or .. segments."},
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

manifest = {
    "$schema": DRAFT, "$id": BASE + "manifest.schema.json",
    "title": "corpus/manifest.json — per-text ledger entries and corpus index",
    "type": "object",
    "required": ["schema_version", "texts"],
    "properties": {
        "schema_version": ref("schemaVersion"),
        "texts": {
            "type": "object",
            "propertyNames": ref("textKey"),
            "additionalProperties": {
                "type": "object",
                "required": ["origin", "ownership", "profiles", "facets", "holdout", "decided", "status"],
                "properties": {
                    "path": {"oneOf": [ref("relPath"), {"type": "null"}],
                             "description": "null for interview answers and connector sources."},
                    "date": {"oneOf": [ref("date"), {"type": "null"}]},
                    "origin": {"enum": ["file", "interview", "mail", "web"]},
                    "ownership": ref("ownership"),
                    "profiles": {"type": "array", "minItems": 1, "uniqueItems": True, "items": ref("profileName")},
                    "facets": {"allOf": [ref("facetValues"), {"required": ["lang", "type"]}]},
                    "words": {"type": "integer", "minimum": 0},
                    "holdout": {"type": "boolean"},
                    "decided": ref("date"),
                    "decided_by": {"enum": ["file", "folder-rule", "tag-rule", "writer"],
                                   "description": "Which ledger layer decided ownership: per-file answer beats folder or tag rule."},
                    "status": {"enum": ["active", "superseded", "unreachable", "forgotten"]},
                    "superseded_by": ref("textKey"),
                    "cached": {"type": "boolean",
                               "description": "true only for own texts; assisted and exclude keep hash and decision, no text."},
                    "redaction": ref("redaction")
                },
                "additionalProperties": False,
                "allOf": [
                    {"if": {"properties": {"ownership": {"const": "own"}, "status": {"const": "active"}}},
                     "then": {"properties": {"cached": {"const": True}}}},
                    {"if": {"properties": {"ownership": {"enum": ["assisted", "exclude"]}}},
                     "then": {"properties": {"cached": {"const": False}}}},
                    {"if": {"properties": {"status": {"const": "superseded"}}},
                     "then": {"required": ["superseded_by"]}},
                    {"if": {"properties": {"origin": {"const": "mail"}, "ownership": {"const": "own"}}},
                     "then": {"required": ["redaction"],
                              "description": "Other people's details in mail are redacted in the corpus too."}}
                ]
            }
        }
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
    "created": ref("date"),
    "personal_data": {"const": "none"}
}, ["id", "text", "origin", "created", "personal_data"], {"title": "profiles/<name>/rulings.yaml"})

vocabulary = entry_list("vocabulary.schema.json", {
    "id": ref("id"),
    "text": {"type": "string", "minLength": 1},
    "kind": {"enum": ["term", "spelling", "coinage", "keep"]},
    "note": {"type": "string"},
    "private": {"type": "boolean", "description": "Private entries are never exported."},
    "overrides": {"oneOf": [ref("id"), {"type": "null"}]},
    "created": ref("date")
}, ["id", "text", "kind", "private", "created"], {"title": "profiles/<name>/vocabulary.yaml"})

rejected = entry_list("rejected.schema.json", {
    "id": ref("id"),
    "slot": ref("slotKey"),
    "kind": {"enum": ["observed", "edit", "vocabulary", "example"]},
    "text": {"type": "string", "minLength": 1},
    "normalised": {"type": "string", "minLength": 1,
                   "description": "Lower-case, punctuation removed, stop words from references/lang/<lang>/stopwords.txt removed, single spaces."},
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
                        "description": "global = phase-0 list; contrast = narrowed by this slot's contrast pass."},
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
                           "description": "The resolved count: max(min_count, ceil(fail_fraction x metrics in the list)); 4 for the 14 global metrics. The draft fails when flagged >= fail_threshold."},
        "metrics": {"type": "array", "items": {
            "type": "object", "required": ["name", "draft", "writer", "ratio", "flag"],
            "properties": {"name": {"type": "string"}, "draft": {"type": "number"},
                           "writer": {"type": "number"}, "ratio": {"type": "number"},
                           "flag": {"enum": ["ok", "overshoot", "shortfall"]},
                           "primary": {"type": "boolean"}},
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
         "then": {"required": ["profile", "slot", "confidence", "metrics"]}},
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
        "mode": {"enum": ["learn", "learn-edit", "interview", "forget", "rollback", "prune", "test"]},
        "profile": ref("profileName"),
        "started": ref("dateTime"),
        "heartbeat": ref("dateTime"),
        "pending": {"type": "boolean", "description": "A pending area exists; the lock is not stale while true."}
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
    "title": ".state/pending/plan.json — what a run proposes, awaiting approval",
    "type": "object",
    "required": ["schema_version", "run_id", "mode", "created", "changes"],
    "properties": {
        "schema_version": ref("schemaVersion"),
        "run_id": {"type": "string", "pattern": "^[0-9]{8}T[0-9]{6}Z$"},
        "mode": {"enum": ["learn", "learn-edit", "interview", "forget", "rollback", "prune", "test"]},
        "profiles": {"type": "array", "items": ref("profileName")},
        "created": ref("dateTime"),
        "changes": {"type": "array", "items": {
            "type": "object", "required": ["op", "path"],
            "properties": {
                "op": {"enum": ["add", "modify", "remove"]},
                "path": {"type": "string", "description": "Store-relative path; the proposed file lives at .state/pending/<path>."},
                "summary": {"type": "string"},
                "decision": {"enum": ["pending", "approved", "rejected"], "default": "pending"}
            },
            "additionalProperties": False}}
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

SCHEMAS = {
    "global-metrics": global_metrics,
    "common": common, "idiolect": idiolect, "sources": sources, "manifest": manifest,
    "profile": profile, "rulings": rulings, "vocabulary": vocabulary, "rejected": rejected,
    "fingerprint": fingerprint, "check-report": check_report, "lock": lock,
    "progress": progress, "pending": pending, "edit-pair": edit_pair,
}

if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    for name, s in SCHEMAS.items():
        (OUT / f"{name}.schema.json").write_text(json.dumps(s, indent=2, ensure_ascii=False) + "\n")
    print(f"wrote {len(SCHEMAS)} schemas to {OUT}")
