"""A JSON Schema 2020-12 validator for exactly the keywords this repository's schemas use.

It is test code for CI, not a library. `KEYWORDS` names what it implements, and `unknown_keywords`
names anything else a schema uses, so a check refuses such a schema instead of passing an instance
by ignoring a keyword it does not know.

Two points of 2020-12 it keeps deliberately: an integer is any number with no fractional part, and
never a boolean; and `pattern` is an ECMA-262 regular expression, in which `$` matches only at the
very end of the string, never before a trailing line feed as Python's does.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Final

KEYWORDS: Final = frozenset(
    {
        "$schema",
        "$defs",
        "$ref",
        "title",
        "description",
        "type",
        "enum",
        "const",
        "minimum",
        "maximum",
        "pattern",
        "minItems",
        "maxItems",
        "items",
        "uniqueItems",
        "required",
        "properties",
        "additionalProperties",
        "anyOf",
        "not",
        "if",
        "then",
        "else",
    }
)
#: Keywords whose value is one schema, and keywords whose value is a map or a list of schemas.
_ONE: Final = ("items", "not", "if", "then", "else")
_MANY: Final = ("properties", "$defs")


def _subschemas(schema: dict[str, Any]) -> list[dict[str, Any]]:
    found = [schema[key] for key in _ONE if isinstance(schema.get(key), dict)]
    for key in _MANY:
        found.extend(schema.get(key, {}).values())
    found.extend(schema.get("anyOf", []))
    return found


def unknown_keywords(
    schema: dict[str, Any], allowed: frozenset[str] = KEYWORDS
) -> list[str]:
    """Every keyword, anywhere in `schema`, that is not in `allowed`."""
    found = sorted(set(schema) - allowed)
    for sub in _subschemas(schema):
        found.extend(unknown_keywords(sub, allowed))
    return found


def _is_type(value: Any, name: str) -> bool:
    if name == "null":
        return value is None
    if name == "boolean":
        return isinstance(value, bool)
    if name == "object":
        return isinstance(value, dict)
    if name == "array":
        return isinstance(value, list)
    if name == "string":
        return isinstance(value, str)
    number = isinstance(value, (int, float)) and not isinstance(value, bool)
    if name == "integer":
        return number and float(value).is_integer()
    if name == "number":
        return number
    raise ValueError(f"unknown type {name!r}")


def _equal(left: Any, right: Any) -> bool:
    """JSON equality: `true` is not `1`, and `1` is `1.0`."""
    if isinstance(left, bool) or isinstance(right, bool):
        return type(left) is type(right) and left == right
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return left == right
    if isinstance(left, list) and isinstance(right, list):
        return len(left) == len(right) and all(map(_equal, left, right))
    if isinstance(left, dict) and isinstance(right, dict):
        return left.keys() == right.keys() and all(
            _equal(left[key], right[key]) for key in left
        )
    return type(left) is type(right) and left == right


def _ecma(pattern: str) -> re.Pattern[str]:
    """Compile an ECMA-262 pattern: a final unescaped `$` matches only at the end."""
    if pattern.endswith("$") and not pattern.endswith("\\$"):
        pattern = pattern[:-1] + r"\Z"
    return re.compile(pattern)


def _resolve(
    ref: str, root: dict[str, Any], base: Path | None
) -> tuple[dict[str, Any], dict[str, Any], Path | None]:
    """The schema a `$ref` names, with the root and base it is read against."""
    if ref.startswith("#/"):
        target = root
        for part in ref[2:].split("/"):
            target = target[part]
        return target, root, base
    if base is None or "#" in ref or "/" in ref:
        raise ValueError(f"unsupported $ref {ref!r}")
    loaded = json.loads((base / ref).read_text(encoding="utf-8"))
    return loaded, loaded, base


def valid(
    instance: Any,
    schema: dict[str, Any],
    *,
    root: dict[str, Any] | None = None,
    base: Path | None = None,
) -> bool:
    """Whether `instance` satisfies `schema`, for the keywords in `KEYWORDS`.

    `base` is the directory a `$ref` to a sibling schema file is read from.
    """
    root = schema if root is None else root
    if "$ref" in schema:
        target, target_root, target_base = _resolve(schema["$ref"], root, base)
        if not valid(instance, target, root=target_root, base=target_base):
            return False

    def sub(value: Any, subschema: dict[str, Any]) -> bool:
        return valid(value, subschema, root=root, base=base)

    kinds = schema.get("type")
    if kinds is not None:
        kinds = kinds if isinstance(kinds, list) else [kinds]
        if not any(_is_type(instance, kind) for kind in kinds):
            return False
    if "const" in schema and not _equal(instance, schema["const"]):
        return False
    if "enum" in schema and not any(_equal(instance, item) for item in schema["enum"]):
        return False
    if _is_type(instance, "number"):
        if "minimum" in schema and instance < schema["minimum"]:
            return False
        if "maximum" in schema and instance > schema["maximum"]:
            return False
    if (
        isinstance(instance, str)
        and "pattern" in schema
        and not _ecma(schema["pattern"]).search(instance)
    ):
        return False
    if isinstance(instance, list):
        if len(instance) < schema.get("minItems", 0):
            return False
        if "maxItems" in schema and len(instance) > schema["maxItems"]:
            return False
        if schema.get("uniqueItems") and any(
            _equal(instance[i], instance[j])
            for i in range(len(instance))
            for j in range(i + 1, len(instance))
        ):
            return False
        if "items" in schema and not all(
            sub(item, schema["items"]) for item in instance
        ):
            return False
    if isinstance(instance, dict):
        if not all(name in instance for name in schema.get("required", [])):
            return False
        properties = schema.get("properties", {})
        for name, value in instance.items():
            if name in properties:
                if not sub(value, properties[name]):
                    return False
            elif schema.get("additionalProperties") is False:
                return False
    if "anyOf" in schema and not any(sub(instance, s) for s in schema["anyOf"]):
        return False
    if "not" in schema and sub(instance, schema["not"]):
        return False
    if "if" in schema:
        branch = "then" if sub(instance, schema["if"]) else "else"
        if branch in schema and not sub(instance, schema[branch]):
            return False
    return True
