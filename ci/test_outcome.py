"""The provider's signed outcome of `agentnexus-games-v1`, and the API's reference intake.

`protocol/v1/outcome.schema.json` and `outcome-answer.schema.json` are the forms `D-123` and
`D-124` fix; `vectors/outcome-v1/cases.json` holds a published test replay record, published test
outcome keys that are valid nowhere, and a scenario of outcomes the API receives, each with its
answer. These tests require the signed bytes to be exactly `D-123`'s, the replay digest to be the
SHA-256 of the exact test bytes, every step to get its published answer, every status and refusal
to be shown, and every member of the outcome to carry its data class.
"""

from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from json_schema import KEYWORDS, unknown_keywords, valid
from outcome import SIGNED_LINES, Intake, outcome_bytes

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT / "protocol" / "v1"
VECTOR = ROOT / "vectors" / "outcome-v1" / "cases.json"
DIALECT = "https://json-schema.org/draft/2020-12/schema"
ANNOTATIONS = frozenset({"x-agentnexus-data-class", "x-agentnexus-retained"})

#: `D-123`'s signed lines, in their order.
D123_LINES = (
    "agentnexus-outcome-v1",
    "key_id",
    "match_id",
    "provider_id",
    "game_version",
    "result",
    "reason",
    "winner_seat",
    "solo",
    "final_state_version",
    "replay_digest",
    "replay_reference",
    "reported_at",
)
#: `D-123`'s published test replay record.
D123_TEST_RECORD = "agentnexus-games-contracts test replay record 1, valid nowhere"
STATUSES = {"recorded", "already_recorded", "disputed", "evidence_only"}
REFUSALS = {
    "too_large": 413,
    "malformed_body": 400,
    "unauthenticated": 401,
    "outcome_provider": 403,
    "outcome_game": 403,
}


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def vector() -> dict[str, Any]:
    return load(VECTOR)


def steps() -> list[dict[str, Any]]:
    return vector()["steps"]


def private(entry: dict[str, Any]) -> Ed25519PrivateKey:
    seed = hashlib.sha256(entry["seed_is_sha256_of"].encode("utf-8")).digest()
    return Ed25519PrivateKey.from_private_bytes(seed)


def intake() -> Intake:
    doc = vector()
    keys = {
        provider: {key["key_id"]: key["public_key"] for key in entries}
        for provider, entries in doc["outcome_keys_by_provider"].items()
    }
    return Intake(keys, doc["matches"], PROTOCOL)


def test_the_signed_lines_are_d123s() -> None:
    assert ("agentnexus-outcome-v1", *SIGNED_LINES) == D123_LINES


def test_the_signed_bytes_follow_d123() -> None:
    """LF between lines and none after; `winner_seat` empty when null; `solo` as true or false."""
    outcome = {
        "key_id": "k",
        "match_id": "m",
        "provider_id": "p",
        "game_version": "g",
        "result": "draw",
        "reason": "rules",
        "winner_seat": None,
        "solo": False,
        "final_state_version": 42,
        "replay_digest": "d",
        "replay_reference": "r",
        "reported_at": "t",
    }
    expected = "agentnexus-outcome-v1\nk\nm\np\ng\ndraw\nrules\n\nfalse\n42\nd\nr\nt"
    assert outcome_bytes(outcome) == expected.encode("utf-8")


def test_the_test_replay_record_is_d123s_and_its_digest_is_its_sha256() -> None:
    doc = vector()
    record = doc["test_replay_record_utf8"]
    assert record == D123_TEST_RECORD
    assert not record.endswith("\n")
    assert (
        doc["test_replay_digest"] == hashlib.sha256(record.encode("utf-8")).hexdigest()
    )


def test_each_outcome_key_is_what_its_published_seed_produces() -> None:
    for entries in vector()["outcome_keys_by_provider"].values():
        for entry in entries:
            raw = (
                private(entry).public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
            )
            assert base64.b64encode(raw).decode("ascii") == entry["public_key"]


def test_the_schemas_are_strict_2020_12_with_every_member_classified() -> None:
    outcome = load(PROTOCOL / "outcome.schema.json")
    answer = load(PROTOCOL / "outcome-answer.schema.json")
    for schema in (outcome, answer):
        assert schema["$schema"] == DIALECT
        assert schema["additionalProperties"] is False
    assert unknown_keywords(answer) == []
    assert unknown_keywords(outcome, KEYWORDS | ANNOTATIONS) == []
    assert outcome["properties"]["version"]["const"] == "agentnexus-outcome-v1"
    assert set(outcome["required"]) == set(SIGNED_LINES) | {"version", "signature"}
    for name, member in outcome["properties"].items():
        assert member["x-agentnexus-data-class"] == "public", name
        assert member["x-agentnexus-retained"] is True, name
    assert answer["properties"]["status"] == {"enum": sorted(STATUSES)}


def test_a_win_names_its_seat_and_nothing_else_does() -> None:
    outcome = load(PROTOCOL / "outcome.schema.json")
    (first,) = [s for s in steps() if s["name"] == "a-win"]
    body = json.loads(first["body"])
    assert valid(body, outcome)
    assert not valid({**body, "winner_seat": None}, outcome)
    assert not valid({**body, "result": "draw"}, outcome)
    assert valid({**body, "result": "draw", "winner_seat": None}, outcome)


@pytest.mark.parametrize(
    "index", range(len(json.loads(VECTOR.read_text("utf-8"))["steps"]))
)
def test_the_scenario_gets_its_published_answers(index: int) -> None:
    api = intake()
    for step in steps()[: index + 1]:
        found = api.handle(step["body"].encode("utf-8"))
    step = steps()[index]
    assert found == (step["expected"]["status"], step["expected"]["body"]), step["name"]


def test_each_signature_is_over_the_d123_lines() -> None:
    signers = {
        entry["key_id"]: private(entry)
        for entries in vector()["outcome_keys_by_provider"].values()
        for entry in entries
    }
    signers.update(
        {entry["key_id"]: private(entry) for entry in vector()["unheld_keys"]}
    )
    for step in steps():
        if not step.get("signed_as_published", True):
            continue
        body = json.loads(step["body"])
        signature = base64.b64encode(signers[body["key_id"]].sign(outcome_bytes(body)))
        assert body["signature"] == signature.decode("ascii"), step["name"]


def test_every_status_and_refusal_is_shown() -> None:
    answers = [step["expected"] for step in steps()]
    statuses = {a["body"]["status"] for a in answers if a["status"] == 200}
    refusals = {
        a["body"]["error"]["code"]: a["status"] for a in answers if a["status"] != 200
    }
    assert statuses == STATUSES
    assert refusals == REFUSALS


def test_already_recorded_needs_byte_identical_lines_not_an_identical_body() -> None:
    """`D-124`: the same 13 lines in another body are `already_recorded`."""
    (first,) = [s for s in steps() if s["name"] == "a-win"]
    (again,) = [s for s in steps() if s["name"] == "the-same-lines-in-another-body"]
    assert first["body"] != again["body"]
    assert outcome_bytes(json.loads(first["body"])) == outcome_bytes(
        json.loads(again["body"])
    )
    assert again["expected"]["body"]["status"] == "already_recorded"


def test_every_answer_has_its_published_form() -> None:
    answer = load(PROTOCOL / "outcome-answer.schema.json")
    refusal = load(PROTOCOL / "refusal.schema.json")
    for step in steps():
        body = step["expected"]["body"]
        schema = answer if step["expected"]["status"] == 200 else refusal
        assert valid(body, schema), step["name"]
