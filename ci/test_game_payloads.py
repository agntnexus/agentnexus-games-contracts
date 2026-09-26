"""Connect Four's own payloads, `connect-four-1`, and the size limits, as D-118 fixes them.

The schemas in `games/connect-four/connect-four-1/` and the cases in
`vectors/connect-four-1-payloads/cases.json` are checked here against the values `D-118` accepted:
the move and the observation, the data class and retained flag of every observation field, the
game bounds, the shared ceilings and the body limit of every message. Every positive case has to
pass and every negative one has to fail, and every rule is broken once in a copy of a schema and
has to be refused, for its own reason.
"""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any

import pytest
from game_payloads import (
    BOUND_KEY,
    CLASS_KEY,
    RETAINED_KEY,
    message_limit,
    message_verdict,
    payload_verdict,
    schema_refusals,
    valid,
)

ROOT = Path(__file__).resolve().parents[1]
GAME_VERSION = "connect-four-1"
GAME = ROOT / "games" / "connect-four" / GAME_VERSION
VECTOR = ROOT / "vectors" / "connect-four-1-payloads" / "cases.json"

#: What `D-118` accepted, restated here so that neither the schemas nor the vector can drift from it.
ACCEPTED_MOVE = {"column": {"type": "integer", "minimum": 0, "maximum": 6}}
ACCEPTED_RETAINED = {
    "board": True,
    "you_are": False,
    "to_move": True,
    "legal_columns": False,
    "move_count": True,
    "last_move": True,
    "result": True,
}
ACCEPTED_BOUNDS = {"move": 64, "observation": 2048}
ACCEPTED_CEILINGS = {"move": 4096, "observation": 65536}
ACCEPTED_LIMITS = {
    "redemption": (4096, "too_large"),
    "resumption": (1024, "too_large"),
    "action": (1024 + 4096, "too_large"),
    "resignation_instruction": (2048, "too_large"),
    "resignation_acknowledgement": (1024, None),
    "seat_answer": (1024 + 2048, None),
    "refusal": (1024, None),
}


def schema(payload: str) -> dict[str, Any]:
    return json.loads((GAME / f"{payload}.schema.json").read_text(encoding="utf-8"))


def vector() -> dict[str, Any]:
    return json.loads(VECTOR.read_text(encoding="utf-8"))


def plus() -> dict[str, int]:
    return {
        "move_ceiling": vector()["shared_ceilings"]["move"],
        "observation_bound": schema("observation")[BOUND_KEY],
    }


def names(kind: str) -> list[str]:
    return [case["name"] for case in json.loads(VECTOR.read_text("utf-8"))[kind]]


def case(kind: str, name: str) -> dict[str, Any]:
    (found,) = [c for c in vector()[kind] if c["name"] == name]
    return found


def padded(value: Any, length: int) -> str:
    text = json.dumps(value, separators=(",", ":"))
    assert len(text) <= length, "the case pads to less than its compact value"
    return text + " " * (length - len(text))


# Where the schemas are, and what they hold.


def test_the_schemas_are_in_the_game_versions_own_directory() -> None:
    """One directory per game version, named by the game version the ticket carries (D-118)."""
    assert re.fullmatch(r"[A-Za-z0-9._-]{1,64}", GAME.name)
    assert sorted(path.name for path in GAME.glob("*.schema.json")) == [
        "move.schema.json",
        "observation.schema.json",
    ]
    assert vector()["game_version"] == GAME_VERSION
    assert vector()["schemas"] == {
        payload: f"games/connect-four/{GAME_VERSION}/{payload}.schema.json"
        for payload in ("move", "observation")
    }


@pytest.mark.parametrize("payload", ["move", "observation"])
def test_each_schema_keeps_every_rule(payload: str) -> None:
    assert schema_refusals(schema(payload), payload, ACCEPTED_CEILINGS) == []


def test_the_move_is_what_d118_accepted() -> None:
    move = schema("move")
    assert move["properties"] == ACCEPTED_MOVE
    assert move["required"] == ["column"]
    assert move[BOUND_KEY] == ACCEPTED_BOUNDS["move"]


def test_the_observation_is_what_d118_accepted() -> None:
    observation = schema("observation")
    fields = observation["properties"]
    assert set(fields) == set(ACCEPTED_RETAINED)
    assert observation["required"] == list(ACCEPTED_RETAINED)
    assert {name: field[CLASS_KEY] for name, field in fields.items()} == dict.fromkeys(
        ACCEPTED_RETAINED, "public"
    )
    assert {
        name: field[RETAINED_KEY] for name, field in fields.items()
    } == ACCEPTED_RETAINED
    assert observation[BOUND_KEY] == ACCEPTED_BOUNDS["observation"]


def test_the_ceilings_and_body_limits_are_what_d118_accepted() -> None:
    doc = vector()
    assert doc["shared_ceilings"] == ACCEPTED_CEILINGS
    limits = {
        entry["message"]: (message_limit(entry, plus()), entry["over_limit_code"])
        for entry in doc["message_limits"]
    }
    assert limits == ACCEPTED_LIMITS


# The cases as published.


@pytest.mark.parametrize("name", names("move_cases"))
def test_each_move_case_gets_its_published_verdict(name: str) -> None:
    c = case("move_cases", name)
    assert ("valid" if valid(c["move"], schema("move")) else "invalid") == c["expected"]


@pytest.mark.parametrize("name", names("observation_cases"))
def test_each_observation_case_gets_its_published_verdict(name: str) -> None:
    c = case("observation_cases", name)
    verdict = valid(c["observation"], schema("observation"))
    assert ("valid" if verdict else "invalid") == c["expected"]


@pytest.mark.parametrize("kind", ["move_cases", "observation_cases"])
def test_each_payload_has_positive_and_negative_cases(kind: str) -> None:
    assert {c["expected"] for c in vector()[kind]} == {"valid", "invalid"}


@pytest.mark.parametrize("name", names("payload_size_cases"))
def test_each_payload_size_case_gets_its_published_verdict(name: str) -> None:
    c = case("payload_size_cases", name)
    text = padded(c["value"], c["pad_to_bytes"])
    assert valid(json.loads(text), schema(c["payload"])), (
        "a size case must be a valid payload"
    )
    assert payload_verdict(text, schema(c["payload"])[BOUND_KEY]) == c["expected"]


def test_each_game_bound_is_proven_at_its_edge() -> None:
    """For each payload, one case exactly at its bound and one a byte over it."""
    edges = {
        (
            c["payload"],
            c["pad_to_bytes"] - schema(c["payload"])[BOUND_KEY],
            c["expected"],
        )
        for c in vector()["payload_size_cases"]
    }
    for payload in ("move", "observation"):
        assert (payload, 0, "within_bound") in edges
        assert (payload, 1, "over_bound") in edges


@pytest.mark.parametrize("name", names("message_size_cases"))
def test_each_message_size_case_gets_its_published_verdict(name: str) -> None:
    c = case("message_size_cases", name)
    (entry,) = [e for e in vector()["message_limits"] if e["message"] == c["message"]]
    assert message_verdict(c["length"], entry, plus()) == (c["expected"], c["code"])


def test_each_message_limit_is_proven_at_its_edge() -> None:
    cases = vector()["message_size_cases"]
    for entry in vector()["message_limits"]:
        limit = message_limit(entry, plus())
        lengths = {c["length"] for c in cases if c["message"] == entry["message"]}
        assert {limit, limit + 1} <= lengths, entry["message"]


# Every rule, broken once.


def observation_with(change: Any) -> dict[str, Any]:
    broken = copy.deepcopy(schema("observation"))
    change(broken)
    return broken


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        (lambda s: s["properties"]["board"].pop(CLASS_KEY), "carries no data class"),
        (
            lambda s: s["properties"]["you_are"].update({CLASS_KEY: "secret"}),
            "carries no data class",
        ),
        (lambda s: s["properties"]["result"].pop(RETAINED_KEY), "no retained flag"),
        (
            lambda s: s["properties"]["to_move"].update({RETAINED_KEY: "yes"}),
            "no retained flag",
        ),
        (
            lambda s: s["properties"]["board"]["items"].update({CLASS_KEY: "public"}),
            "is not a keyword this contract uses here",
        ),
        (lambda s: s.update({BOUND_KEY: 65537}), "not within the shared ceiling"),
        (lambda s: s.pop(BOUND_KEY), "not within the shared ceiling"),
        (lambda s: s.update({"additionalProperties": True}), "is not a strict object"),
        (
            lambda s: s.update({"$schema": "http://json-schema.org/draft-07/schema#"}),
            "is not JSON Schema 2020-12",
        ),
        (
            lambda s: s["properties"]["you_are"].update({"pattern": "^f"}),
            "is not a keyword this contract uses here",
        ),
    ],
    ids=[
        "no class",
        "unknown class",
        "no retained flag",
        "retained not boolean",
        "nested class",
        "bound over ceiling",
        "no bound",
        "not strict",
        "other dialect",
        "unimplemented keyword",
    ],
)
def test_a_broken_observation_schema_is_refused(change: Any, reason: str) -> None:
    refusals = schema_refusals(
        observation_with(change), "observation", ACCEPTED_CEILINGS
    )
    assert any(reason in refusal for refusal in refusals), refusals


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        (
            lambda s: s["properties"]["column"].update({CLASS_KEY: "public"}),
            "is not a keyword this contract uses here",
        ),
        (lambda s: s.update({BOUND_KEY: 4097}), "not within the shared ceiling"),
        (lambda s: s.update({BOUND_KEY: True}), "not within the shared ceiling"),
    ],
    ids=["annotated move field", "bound over ceiling", "bound not an integer"],
)
def test_a_broken_move_schema_is_refused(change: Any, reason: str) -> None:
    broken = copy.deepcopy(schema("move"))
    change(broken)
    refusals = schema_refusals(broken, "move", ACCEPTED_CEILINGS)
    assert any(reason in refusal for refusal in refusals), refusals


def test_a_payload_one_byte_over_its_bound_is_over() -> None:
    bound = schema("move")[BOUND_KEY]
    assert payload_verdict(padded({"column": 6}, bound), bound) == "within_bound"
    assert payload_verdict(padded({"column": 6}, bound + 1), bound) == "over_bound"


# The validator keeps JSON Schema 2020-12's meaning.


@pytest.mark.parametrize(
    ("instance", "expected"),
    [(3, True), (3.0, True), (3.5, False), (True, False), ("3", False), (None, False)],
)
def test_an_integer_is_what_2020_12_calls_one(instance: Any, expected: bool) -> None:
    assert valid(instance, {"type": "integer"}) is expected


def test_unique_items_compares_as_json() -> None:
    assert not valid([1, 1.0], {"type": "array", "uniqueItems": True})
    assert valid([1, True], {"type": "array", "uniqueItems": True})
