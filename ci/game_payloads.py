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

Instances are validated by `json_schema.py`. A game schema that uses a keyword outside `KEYWORDS`
here is refused, so no instance passes because a keyword was ignored.

It runs no request. Where a game payload is checked in the refusal order, and with which code, is
`D-123`'s, and `ci/provider_wire.py` runs it.
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
