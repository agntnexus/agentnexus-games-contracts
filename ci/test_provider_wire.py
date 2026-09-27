"""The Games provider wire of `agentnexus-games-v1`, and the reference check that runs its vector.

`protocol/v1/` holds the common schemas: `D-114`'s, with the counters' maximum `D-123` adds.
`vectors/provider-wire-v1/cases.json` holds scenarios of requests a provider receives, each with
the answer `D-114` and `D-123` fix for it. These tests require:

- the schemas to be `D-114`'s, byte for byte in their meaning, but for `D-123`'s maxima;
- the vector to be reproducible from its published test seeds;
- every step to get its published answer from the reference check;
- every accepted answer to be a seat answer whose observation `D-118`'s schema accepts;
- every refusal the vector can show to be shown, and every refusal to name nothing but its code;
- `D-123`'s rules: an identical redemption retry is no second redemption, a move the rules refuse
  consumes its sequence, a game payload is checked after the bindings and before the state, and a
  retried move returns its stored answer;
- what stays open to stay open: the reference check refuses to choose.

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
PROTOCOL = ROOT / "protocol" / "v1"
VECTOR = ROOT / "vectors" / "provider-wire-v1" / "cases.json"
PAYLOADS = ROOT / "vectors" / "connect-four-1-payloads" / "cases.json"
GAME = ROOT / "games" / "connect-four" / "connect-four-1"
DIALECT = "https://json-schema.org/draft/2020-12/schema"

#: The counters `D-123` bounds, per schema, and the maximum it gives them.
COUNTERS = {
    "resumption.schema.json": ("sequence",),
    "action.schema.json": ("sequence", "expected_state_version"),
    "seat-answer.schema.json": ("sequence", "state_version"),
}
COUNTER_MAXIMUM = 9007199254740991

#: The eight common schemas of `D-114`'s W-7, as `D-114` accepted them, pinned by the SHA-256 of
#: their canonical JSON (sorted keys, no whitespace).
D114_SHA256 = {
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
#: The same eight schemas as `protocol/v1/` holds them, with `D-123`'s maxima.
SCHEMA_SHA256 = {
    "ticket-v2.schema.json": (
        "e31324a19fb71185a0444dcffcd46e0ebddf75c9104c2afca4a4336f532b9d70"
    ),
    "redemption.schema.json": (
        "137529430dfa0e881e76a47430e4ce9c7ac3603eff2135ae3ea5c7762ba96b5f"
    ),
    "resumption.schema.json": (
        "27f510fce714b184c77f9555e51d9d6abf758d8db2a2cc2fd35e50e6afa1f7a7"
    ),
    "action.schema.json": (
        "b20c94bf2c957b959c336cd1c70f49f58b1bf3ca09ec377de231b55c39642aa7"
    ),
    "seat-answer.schema.json": (
        "cb626077ff811c6c6135684ca3d17c9c8bb7482b3ed62a9bcfbc6e63b922b3d4"
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
    "ticket_spent",
    "move_not_legal",
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
    return Provider(doc["provider_id"], keys, limits(), PROTOCOL)


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
                step.get("game_refuses", False),
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


def canonical_sha256(schema: dict[str, Any]) -> str:
    text = json.dumps(schema, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def test_the_counters_carry_d123s_maximum_and_nothing_else_changed() -> None:
    """Without `D-123`'s maxima, every schema is exactly the one `D-114` accepted."""
    for name, digest in D114_SHA256.items():
        schema = load(PROTOCOL / name)
        for member in COUNTERS.get(name, ()):
            assert schema["properties"][member]["maximum"] == COUNTER_MAXIMUM, (
                name,
                member,
            )
            del schema["properties"][member]["maximum"]
        assert canonical_sha256(schema) == digest, name


def test_a_counter_over_its_maximum_is_malformed() -> None:
    answer = load(PROTOCOL / "seat-answer.schema.json")
    body = {
        "seat_generation": 1,
        "sequence": COUNTER_MAXIMUM,
        "state_version": COUNTER_MAXIMUM,
        "status": "active",
        "observation": {},
    }
    assert valid(body, answer, base=PROTOCOL)
    assert not valid({**body, "sequence": COUNTER_MAXIMUM + 1}, answer, base=PROTOCOL)
    assert not valid(
        {**body, "state_version": COUNTER_MAXIMUM + 1}, answer, base=PROTOCOL
    )


def test_the_schemas_are_d114s_eight() -> None:
    assert sorted(path.name for path in PROTOCOL.glob("*.schema.json")) == sorted(
        SCHEMA_SHA256
    )
    for name, digest in SCHEMA_SHA256.items():
        canonical = json.dumps(
            load(PROTOCOL / name), sort_keys=True, separators=(",", ":")
        )
        assert hashlib.sha256(canonical.encode("utf-8")).hexdigest() == digest, name


@pytest.mark.parametrize("name", sorted(SCHEMA_SHA256))
def test_each_schema_is_strict_2020_12_in_keywords_the_check_knows(name: str) -> None:
    schema = load(PROTOCOL / name)
    assert schema["$schema"] == DIALECT
    assert schema["additionalProperties"] is False
    assert unknown_keywords(schema) == []


def test_an_action_carries_a_move_exactly_when_it_moves() -> None:
    action = load(PROTOCOL / "action.schema.json")
    base = {
        "seat_generation": 1,
        "sequence": 2,
        "idempotency_key": "0" * 8 + "-0000-4000-8000-" + "0" * 12,
        "expected_state_version": 0,
    }
    assert valid(
        {**base, "operation": "move", "move": {"column": 3}}, action, base=PROTOCOL
    )
    assert not valid({**base, "operation": "move"}, action, base=PROTOCOL)
    assert valid({**base, "operation": "resign"}, action, base=PROTOCOL)
    assert not valid(
        {**base, "operation": "resign", "move": {"column": 3}}, action, base=PROTOCOL
    )


def test_a_pattern_does_not_end_before_a_trailing_line_feed() -> None:
    """ECMA-262's `$` is the end of the string; Python's would also accept a final LF."""
    ticket = load(PROTOCOL / "ticket-v2.schema.json")
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
    answer = load(PROTOCOL / "seat-answer.schema.json")
    observation = load(GAME / "observation.schema.json")
    accepted = [step for step in steps() if step["expected"]["status"] == 200]
    assert accepted
    for step in accepted:
        body = step["expected"]["body"]
        assert valid(body, answer, base=PROTOCOL), step["name"]
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
        assert valid(step["expected"]["body"], load(PROTOCOL / "refusal.schema.json"))


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


def test_an_identical_redemption_retry_is_no_second_redemption() -> None:
    """`D-123`: it gets the existing binding's answer, and the ticket is not redeemed again."""
    doc = vector()
    redeem = scenario("redeem-and-play")["steps"][0]
    verifier = provider(doc)
    body = redeem["request"]["body"].encode("utf-8")
    args = (
        redeem["request"]["method"],
        redeem["request"]["path"],
        redeem["request"]["headers"],
    )
    first = verifier.handle(*args, body, redeem["now"], redeem["provider_answer"])
    spent = set(verifier.spent)
    again = verifier.handle(*args, body, redeem["now"])
    assert again == first
    assert verifier.spent == spent


def test_a_game_payload_is_checked_after_authentication_and_before_the_state() -> None:
    """A move `D-118`'s schema refuses is `malformed_body`, but only once the seat is known."""
    doc = vector()
    sessions = {entry["name"]: private(entry) for entry in doc["session_test_keys"]}
    redeem = scenario("redeem-and-play")["steps"][0]
    path = redeem["request"]["path"].replace("/redemption", "/actions")
    match = PATH.fullmatch(path)

    def action(sequence: int, key: str) -> dict[str, Any]:
        body = json.dumps(
            {
                "seat_generation": 1,
                "sequence": sequence,
                "operation": "move",
                "idempotency_key": "6b5a4c3d-2e1f-4a0b-9c8d-7e6f5a4b3c2d",
                "expected_state_version": 0,
                "move": {"column": 7},
            },
            separators=(",", ":"),
        )
        lines = play_bytes(
            "act", match["match_id"], match["seat"], 1, sequence, body.encode()
        )
        return {
            "name": "invalid-move",
            "now": redeem["now"],
            "provider_answer": None,
            "request": {
                "method": "POST",
                "path": path,
                "signed_by": key,
                "headers": {SIGNATURE_HEADER: signature(sessions[key], lines)},
                "body": body,
            },
        }

    malformed = (400, {"error": {"code": "malformed_body"}})
    unauthenticated = (401, {"error": {"code": "unauthenticated"}})
    assert run([redeem, action(2, "session-2")], doc)[1] == unauthenticated
    assert run([redeem, action(9, "session-1")], doc)[1] == malformed
    assert run([redeem, action(2, "session-1")], doc)[1] == malformed


def test_a_retry_with_the_same_key_and_move_but_another_state_version_is_not_decided() -> (
    None
):
    doc = vector()
    (found,) = [s for s in doc["scenarios"] if s["name"] == "d123-wire-rules"]
    steps_ = copy.deepcopy(found["steps"])
    (index,) = [
        i for i, s in enumerate(steps_) if s["name"] == "the-move-retried-with-its-key"
    ]
    retry = steps_[index]
    body = json.loads(retry["request"]["body"])
    body["expected_state_version"] = 1
    retry["request"]["body"] = json.dumps(body, separators=(",", ":"))
    sessions = {entry["name"]: private(entry) for entry in doc["session_test_keys"]}
    match = PATH.fullmatch(retry["request"]["path"])
    retry["request"]["headers"][SIGNATURE_HEADER] = signature(
        sessions[retry["request"]["signed_by"]],
        play_bytes(
            "act",
            match["match_id"],
            match["seat"],
            body["seat_generation"],
            body["sequence"],
            retry["request"]["body"].encode(),
        ),
    )
    with pytest.raises(Undecided):
        run(steps_[: index + 1], doc)


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
