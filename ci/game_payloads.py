"""Reference check for a game version's own payloads, as D-118 fixes them for `connect-four-1`.

It runs the schemas in `games/connect-four/connect-four-1/` and the cases in
`vectors/connect-four-1-payloads/`, and nothing else: it is test code, not a provider, and nothing
here plays, relays or stores a move. Each rule below is one sentence of `D-118` in the AgentNexus
decisions:

- a game version's move and observation schemas are JSON Schema 2020-12, strict: an unknown member
  is refused;
- each schema declares its bound as `x-agentnexus-max-bytes` at its root, within the shared ceiling
  for its payload;
- every top-level field of an observation carries `x-agentnexus-data-class`, one of `public`,
  `opponent_visible` and `seat_private`, and `x-agentnexus-retained`, `true` or `false`; nested
  values take the class of their top-level field, so no nested value carries either annotation;
- each message has its body limit; a message the provider receives over its limit is refused
  `too_large`, and an answer over its limit is not refused with a code.

The validator implements the 2020-12 keywords these schemas use, and refuses a schema that uses any
other, so it never passes an instance by ignoring a keyword it does not know.

What it does not check, because `D-118` leaves it open: at which stage of the refusal order a game
payload is validated and which code refuses it, a code for a move the rules refuse, and a maximum
for the protocol's counters.
"""

from __future__ import annotations

from typing import Any, Final

DIALECT: Final = "https://json-schema.org/draft/2020-12/schema"
CLASS_KEY: Final = "x-agentnexus-data-class"
RETAINED_KEY: Final = "x-agentnexus-retained"
BOUND_KEY: Final = "x-agentnexus-max-bytes"
CLASSES: Final = frozenset({"public", "opponent_visible", "seat_private"})

#: The keywords the validator implements. A schema that uses another one is refused.
KEYWORDS: Final = frozenset(
    {
        "$schema",
        "title",
        "description",
        "type",
        "enum",
        "const",
        "minimum",
        "maximum",
        "minItems",
        "maxItems",
        "items",
        "uniqueItems",
        "required",
        "properties",
        "additionalProperties",
        "anyOf",
    }
)
ROOT_ONLY: Final = frozenset({BOUND_KEY})
FIELD_ONLY: Final = frozenset({CLASS_KEY, RETAINED_KEY})


def _subschemas(schema: dict[str, Any]) -> list[dict[str, Any]]:
    found = list(schema.get("properties", {}).values())
    if isinstance(schema.get("items"), dict):
        found.append(schema["items"])
    found.extend(schema.get("anyOf", []))
    return found


def _keyword_refusals(
    schema: dict[str, Any], where: str, depth: int, annotated: bool
) -> list[str]:
    """Refuse a keyword the validator does not implement, or an annotation out of its place.

    The bound belongs to the root only; the field annotations belong to an observation's top-level
    fields only. On a move, and on anything nested, they are refused like any unknown keyword.
    """
    allowed = set(KEYWORDS)
    if depth == 0:
        allowed |= ROOT_ONLY
    if depth == 1 and annotated:
        allowed |= FIELD_ONLY
    refusals = [
        f"{where}: `{key}` is not a keyword this contract uses here"
        for key in sorted(set(schema) - allowed)
    ]
    for index, sub in enumerate(_subschemas(schema)):
        refusals.extend(
            _keyword_refusals(sub, f"{where}/{index}", depth + 1, annotated)
        )
    return refusals


def schema_refusals(
    schema: dict[str, Any], payload: str, ceilings: dict[str, int]
) -> list[str]:
    """Return every rule of `D-118` the schema of a `move` or `observation` breaks."""
    refusals: list[str] = []
    if schema.get("$schema") != DIALECT:
        refusals.append(f"{payload}: is not JSON Schema 2020-12")
    if (
        schema.get("type") != "object"
        or schema.get("additionalProperties") is not False
    ):
        refusals.append(
            f"{payload}: is not a strict object; an unknown member must fail"
        )
    bound = schema.get(BOUND_KEY)
    if not (
        isinstance(bound, int)
        and not isinstance(bound, bool)
        and 0 < bound <= ceilings[payload]
    ):
        refusals.append(
            f"{payload}: `{BOUND_KEY}` is missing, or not within the shared ceiling of "
            f"{ceilings[payload]} bytes"
        )
    refusals.extend(
        _keyword_refusals(schema, payload, 0, annotated=payload == "observation")
    )
    if payload == "observation":
        for name, field in schema.get("properties", {}).items():
            if field.get(CLASS_KEY) not in CLASSES:
                refusals.append(
                    f"observation.{name}: carries no data class from "
                    f"{', '.join(sorted(CLASSES))}"
                )
            if not isinstance(field.get(RETAINED_KEY), bool):
                refusals.append(f"observation.{name}: carries no retained flag")
    return refusals


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


def valid(instance: Any, schema: dict[str, Any]) -> bool:
    """Whether `instance` satisfies `schema`, for the keywords in `KEYWORDS`."""
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
            valid(item, schema["items"]) for item in instance
        ):
            return False
    if isinstance(instance, dict):
        if not all(name in instance for name in schema.get("required", [])):
            return False
        properties = schema.get("properties", {})
        for name, value in instance.items():
            if name in properties:
                if not valid(value, properties[name]):
                    return False
            elif schema.get("additionalProperties") is False:
                return False
    return "anyOf" not in schema or any(valid(instance, sub) for sub in schema["anyOf"])


def payload_verdict(text: str, bound: int) -> str:
    """A payload, as JSON text, is within its game bound or over it, by its UTF-8 bytes."""
    return "within_bound" if len(text.encode("utf-8")) <= bound else "over_bound"


def message_limit(entry: dict[str, Any], plus: dict[str, int]) -> int:
    """A message's body limit: its fixed bytes, plus a payload bound where it carries one."""
    return entry["fixed_bytes"] + (plus[entry["plus"]] if entry["plus"] else 0)


def message_verdict(
    length: int, entry: dict[str, Any], plus: dict[str, int]
) -> tuple[str, Any]:
    """("within_limit", None), or ("over_limit", the refusal code, or None for an answer)."""
    if length <= message_limit(entry, plus):
        return "within_limit", None
    return "over_limit", entry["over_limit_code"]
