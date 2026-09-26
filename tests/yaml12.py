"""YAML loader with the behaviour spec §1.2 requires, on top of PyYAML (which is YAML 1.1).

- Only true/false (any case YAML 1.2 core allows) are booleans: yes, no, on, off, y, n stay strings,
  so `lang: no` (Norwegian) is the string "no".
- Dates and times are never resolved: `created: 2026-10-02` is the string "2026-10-02".
- Everything else is PyYAML's safe loader.
"""
import re

import yaml


class Yaml12Loader(yaml.SafeLoader):
    pass


Yaml12Loader.yaml_implicit_resolvers = {
    first: [(tag, rx) for tag, rx in resolvers
            if tag not in ("tag:yaml.org,2002:bool", "tag:yaml.org,2002:timestamp")]
    for first, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
}
Yaml12Loader.add_implicit_resolver(
    "tag:yaml.org,2002:bool", re.compile(r"^(?:true|True|TRUE|false|False|FALSE)$"), list("tTfF"))


def load(text):
    return yaml.load(text, Loader=Yaml12Loader)
