"""The Games provider wire, version 1, and the reference check that runs its vector.

`vectors/provider-wire-v1/` holds the common schemas `D-114` accepted and `cases.json`: scenarios
of requests a provider receives, each with the answer `D-114` fixes for it. These tests require:

- the schemas to be `D-114`'s, byte for byte in their meaning;
- the vector to be reproducible from its published test seeds;
- every step to get its published answer from the reference check;
- every accepted answer to be a seat answer whose observation `D-118`'s schema accepts;
- every refusal `D-114` decides that the vector can show to be shown, and every refusal before
  authentication to name nothing;
- what `D-114` leaves open to stay open: the reference check refuses to choose.

Every key here is a published test key that is valid nowhere. No ticket here is a grant (`D-101`).
"""

from __future__ import annotations

import base64
import copy
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from json_schema import unknown_keywords, valid
from provider_wire import (
    KINDS,
    PATH,
    SIGNATURE_HEADER,
    NotRun,
    Provider,
    Undecided,
    play_bytes,
    ticket_bytes,
)

ROOT = Path(__file__).resolve().parents[1]
WIRE = ROOT / "vectors" / "provider-wire-v1"
VECTOR = WIRE / "cases.json"
PAYLOADS = ROOT / "vectors" / "connect-four-1-payloads" / "cases.json"
GAME = ROOT / "games" / "connect-four" / "connect-four-1"
DIALECT = "https://json-schema.org/draft/2020-12/schema"

#: The eight common schemas of `D-114`'s W-7, pinned by the SHA-256 of their canonical JSON (sorted
#: keys, no whitespace), so that neither a member nor a pattern can change unnoticed.
SCHEMA_SHA256 = {
    "ticket-v2.schema.json": (
        "e31324a19fb71185a0444dcffcd46e0ebddf75c9104c2afca4a4336f532b9d70"
    ),
    "redemption.schema.json": (
        "137529430dfa0e881e76a47430e4ce9c7ac3603eff2135ae3ea5c7762ba96b5f"
    ),
    "resumption.schema.json": (
        "b0e786902ef30a80757a32db85a3a712f03c5df653c53c84e51f551bb35d3f0a"
    ),
    "action.schema.json": (
        "abdefd772bfc1b392f0e472846ea5d5d06337bc34c5c09856e60a4065fefb3b7"
    ),
    "seat-answer.schema.json": (
        "7abae53e1f77be46b5f6fbb71d7200ee7c43d163fa4d9df09b49a7813980b3ef"
    ),
    "resignation-instruction.schema.json": (
        "e24e71491b9bc8cbff52106b955f99db7eb12b4ffcae37deb34c1f4b9afc1491"
    ),
    "resignation-acknowledgement.schema.json": (
        "7c28c0ec1d6c38071d53410dda3da69935ca916d44ddddf6773f922092b10d3b"
    ),
    "refusal.schema.json": (
        "eebc9a3bbf962145f6168e431a178df8ac4d3baff67e8b7417eb6581a5627d1b"
    ),
}

#: The refusals `D-114` decides that this vector shows, with the 404 of an unserved path.
SHOWN = {
    "too_large",
    "malformed_body",
    "unauthenticated",
    "ticket_clock",
    "ticket_match",
    "generation_stale",
    "sequence_conflict",
    "sequence_stale",
    "sequence_gap",
    "state_version_stale",
    "idempotency_conflict",
}


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def vector() -> dict[str, Any]:
    return load(VECTOR)


def scenario_names() -> list[str]:
    return [s["name"] for s in load(VECTOR)["scenarios"]]


def scenario(name: str) -> dict[str, Any]:
    (found,) = [s for s in vector()["scenarios"] if s["name"] == name]
    return found


def steps() -> list[dict[str, Any]]:
    return [step for s in vector()["scenarios"] for step in s["steps"]]


def limits() -> dict[str, int]:
    doc = load(PAYLOADS)
    plus = {
        "move_ceiling": doc["shared_ceilings"]["move"],
        "observation_bound": load(GAME / "observation.schema.json")[
            "x-agentnexus-max-bytes"
        ],
    }
    return {
        entry["message"]: entry["fixed_bytes"]
        + (plus[entry["plus"]] if entry["plus"] else 0)
        for entry in doc["message_limits"]
    }


def provider(doc: dict[str, Any]) -> Provider:
    keys = {key["key_id"]: key["public_key"] for key in doc["grant_verification_keys"]}
    return Provider(doc["provider_id"], keys, limits(), WIRE)


def run(steps_: list[dict[str, Any]], doc: dict[str, Any]) -> list[tuple[int, Any]]:
    verifier = provider(doc)
    results = []
    for step in steps_:
        request = step["request"]
        results.append(
            verifier.handle(
                request["method"],
                request["path"],
                request["headers"],
                request["body"].encode("utf-8"),
                step["now"],
                step.get("provider_answer"),
            )
        )
    return results


def private(entry: dict[str, Any]) -> Ed25519PrivateKey:
    seed = hashlib.sha256(entry["seed_is_sha256_of"].encode("utf-8")).digest()
    return Ed25519PrivateKey.from_private_bytes(seed)


def public(key: Ed25519PrivateKey) -> str:
    raw = key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    return base64.b64encode(raw).decode("ascii")


def signature(key: Ed25519PrivateKey, message: bytes) -> str:
    return base64.b64encode(key.sign(message)).decode("ascii")


# The schemas.


def test_the_schemas_are_d114s_eight() -> None:
    assert sorted(path.name for path in WIRE.glob("*.schema.json")) == sorted(
        SCHEMA_SHA256
    )
    for name, digest in SCHEMA_SHA256.items():
        canonical = json.dumps(load(WIRE / name), sort_keys=True, separators=(",", ":"))
        assert hashlib.sha256(canonical.encode("utf-8")).hexdigest() == digest, name


@pytest.mark.parametrize("name", sorted(SCHEMA_SHA256))
def test_each_schema_is_strict_2020_12_in_keywords_the_check_knows(name: str) -> None:
    schema = load(WIRE / name)
    assert schema["$schema"] == DIALECT
    assert schema["additionalProperties"] is False
    assert unknown_keywords(schema) == []


def test_an_action_carries_a_move_exactly_when_it_moves() -> None:
    action = load(WIRE / "action.schema.json")
    base = {
        "seat_generation": 1,
        "sequence": 2,
        "idempotency_key": "0" * 8 + "-0000-4000-8000-" + "0" * 12,
        "expected_state_version": 0,
    }
    assert valid(
        {**base, "operation": "move", "move": {"column": 3}}, action, base=WIRE
    )
    assert not valid({**base, "operation": "move"}, action, base=WIRE)
    assert valid({**base, "operation": "resign"}, action, base=WIRE)
    assert not valid(
        {**base, "operation": "resign", "move": {"column": 3}}, action, base=WIRE
    )


def test_a_pattern_does_not_end_before_a_trailing_line_feed() -> None:
    """ECMA-262's `$` is the end of the string; Python's would also accept a final LF."""
    ticket = load(WIRE / "ticket-v2.schema.json")
    fingerprint = ticket["properties"]["session_key_fingerprint"]
    assert valid("a" * 64, fingerprint)
    assert not valid("a" * 64 + "\n", fingerprint)


# The vector is reproducible.


def test_the_keys_are_what_their_published_seeds_produce() -> None:
    doc = vector()
    for entry in [*doc["grant_verification_keys"], doc["unheld_grant_key"]]:
        assert public(private(entry)) == entry["public_key"]
        assert (
            private(entry).private_bytes_raw().hex() == entry["test_private_seed_hex"]
        )
    for entry in doc["session_test_keys"]:
        assert public(private(entry)) == entry["public_key"]


def test_each_ticket_is_signed_over_its_second_version_lines() -> None:
    doc = vector()
    signers = {
        entry["key_id"]: private(entry)
        for entry in [*doc["grant_verification_keys"], doc["unheld_grant_key"]]
    }
    sessions = {
        entry["name"]: entry["public_key"] for entry in doc["session_test_keys"]
    }
    for entry in doc["tickets"]:
        ticket = entry["ticket"]
        assert ticket["version"] == "agentnexus-grant-v2"
        assert ticket["operations"] == ["move", "resign"]
        assert ticket["signature"] == signature(
            signers[ticket["key_id"]], ticket_bytes(ticket)
        )
        raw = base64.b64decode(sessions[entry["session_key"]])
        assert ticket["session_key_fingerprint"] == hashlib.sha256(raw).hexdigest()


def test_each_message_is_signed_over_its_play_lines() -> None:
    sessions = {
        entry["name"]: private(entry) for entry in vector()["session_test_keys"]
    }
    for step in steps():
        request = step["request"]
        if request["signed_by"] is None:
            assert SIGNATURE_HEADER not in request["headers"]
            continue
        match = PATH.fullmatch(request["path"])
        body = request["body"].encode("utf-8")
        doc = json.loads(body)
        lines = play_bytes(
            KINDS[match["kind"]][0],
            match["match_id"],
            match["seat"],
            doc["seat_generation"],
            doc["sequence"],
            body,
        )
        assert request["headers"][SIGNATURE_HEADER] == signature(
            sessions[request["signed_by"]], lines
        ), step["name"]


# Every step gets its published answer.


@pytest.mark.parametrize("name", scenario_names())
def test_each_scenario_gets_its_published_answers(name: str) -> None:
    doc = vector()
    found = run(scenario(name)["steps"], doc)
    expected = [
        (step["expected"]["status"], step["expected"]["body"])
        for step in scenario(name)["steps"]
    ]
    assert found == expected


def test_each_accepted_answer_is_a_seat_answer_with_a_d118_observation() -> None:
    answer = load(WIRE / "seat-answer.schema.json")
    observation = load(GAME / "observation.schema.json")
    accepted = [step for step in steps() if step["expected"]["status"] == 200]
    assert accepted
    for step in accepted:
        body = step["expected"]["body"]
        assert valid(body, answer, base=WIRE), step["name"]
        assert valid(body["observation"], observation), step["name"]


def test_the_legal_action_is_a_d118_move() -> None:
    move = load(GAME / "move.schema.json")
    played = [
        json.loads(step["request"]["body"])
        for step in steps()
        if step["expected"]["status"] == 200
        and step["request"]["path"].endswith("/actions")
    ]
    assert played
    for action in played:
        assert action["operation"] == "move"
        assert valid(action["move"], move)


def test_an_identical_repetition_returns_the_stored_answer() -> None:
    golden = scenario("redeem-and-play")["steps"]
    first, again = golden[1], golden[2]
    assert first["request"] == again["request"]
    assert again["provider_answer"] is None
    assert again["expected"] == first["expected"]


def test_every_refusal_d114_decides_here_is_shown() -> None:
    codes = {
        step["expected"]["body"]["error"]["code"]
        for step in steps()
        if step["expected"]["status"] not in (200, 404)
    }
    assert codes == SHOWN
    assert any(step["expected"]["status"] == 404 for step in steps())


def test_a_refusal_names_nothing_but_its_code() -> None:
    for step in steps():
        if step["expected"]["status"] in (200, 404):
            continue
        assert step["expected"]["body"] == {
            "error": {"code": step["expected"]["body"]["error"]["code"]}
        }
        assert valid(step["expected"]["body"], load(WIRE / "refusal.schema.json"))


# A break the vector does not publish is refused all the same.


def test_a_ticket_whose_signature_breaks_is_unauthenticated() -> None:
    doc = vector()
    step = copy.deepcopy(scenario("redeem-and-play")["steps"][0])
    body = json.loads(step["request"]["body"])
    body["ticket"]["seat"] = "seat-b"
    step["request"]["body"] = json.dumps(body, separators=(",", ":"))
    sessions = {entry["name"]: private(entry) for entry in doc["session_test_keys"]}
    raw = step["request"]["body"].encode("utf-8")
    match = PATH.fullmatch(step["request"]["path"])
    step["request"]["headers"][SIGNATURE_HEADER] = signature(
        sessions[step["request"]["signed_by"]],
        play_bytes("redeem", match["match_id"], match["seat"], 1, 1, raw),
    )
    assert run([step], doc) == [(401, {"error": {"code": "unauthenticated"}})]


def test_a_body_changed_after_signing_is_unauthenticated() -> None:
    doc = vector()
    steps_ = copy.deepcopy(scenario("redeem-and-play")["steps"][:2])
    steps_[1]["request"]["body"] = steps_[1]["request"]["body"].replace(
        '"column":3', '"column":4'
    )
    assert run(steps_, doc)[1] == (401, {"error": {"code": "unauthenticated"}})


# What D-114 leaves open stays open.


def test_a_repeated_redemption_is_not_decided() -> None:
    """W-3 would return the stored answer, W-8 lists `ticket_spent`; D-114 orders neither."""
    doc = vector()
    redeem = scenario("redeem-and-play")["steps"][0]
    with pytest.raises(Undecided):
        run([redeem, {**redeem, "provider_answer": None}], doc)


def test_another_method_on_a_served_path_is_not_decided() -> None:
    doc = vector()
    redeem = copy.deepcopy(scenario("redeem-and-play")["steps"][0])
    redeem["request"]["method"] = "GET"
    with pytest.raises(Undecided):
        run([redeem], doc)


@pytest.mark.parametrize("tail", ["seats/seat-a/resignation-instructions", "spectator"])
def test_the_paths_this_check_does_not_run_are_not_answered(tail: str) -> None:
    doc = vector()
    match_id = PATH.fullmatch(
        scenario("redeem-and-play")["steps"][0]["request"]["path"]
    )["match_id"]
    with pytest.raises(NotRun):
        provider(doc).handle(
            "POST", f"/agentnexus-games/v1/matches/{match_id}/{tail}", {}, b"{}", ""
        )
