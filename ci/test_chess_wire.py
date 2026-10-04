"""Chess's own provider wire, `chess-1` and `chess-1-solo`, as `D-170` fixes it (`#202`).

`vectors/chess-1-wire/cases.json` holds scenarios of signed requests a Chess provider receives, each
with its answer. These tests require, without any Chess provider:

- the keys to be `provider-wire-v1`'s published test keys, reproducible from their seeds;
- every ticket to be signed over its second-version lines and to name a Chess game version;
- every message to be signed over its play lines with the session key its ticket binds;
- every step to get its published answer from the same reference check `provider-wire-v1` runs;
- every accepted answer to be a seat answer whose observation the game version's schema accepts,
  and every accepted move one its move schema accepts;
- the game in each scenario to be the moves its answers record, in order, by the right colour;
- `D-170`'s rules to be shown: a match `awaiting_seats` until both seats bind, the wrong side to
  move, an illegal move, a claim that does not hold, three moves outside the move schema, a draw
  claimed with the move that brings it about, the end it gives, and the computer's answer in
  `chess-1-solo`.

Every key here is a published test key that is valid nowhere. No ticket here is a grant (`D-101`).
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
from json_schema import valid
from provider_wire import PATH, SIGNATURE_HEADER, Provider, play_bytes, ticket_bytes

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT / "protocol" / "v1"
VECTOR = ROOT / "vectors" / "chess-1-wire" / "cases.json"
WIRE = ROOT / "vectors" / "provider-wire-v1" / "cases.json"
PAYLOADS = ROOT / "vectors" / "chess-1-payloads" / "cases.json"
GAMES = {
    "chess-1": ROOT / "games" / "chess" / "chess-1",
    "chess-1-solo": ROOT / "games" / "chess" / "chess-1-solo",
}
COLOURS = {"first": "white", "second": "black"}
KINDS = {"redemption": "redeem", "resumption": "resume", "actions": "act"}


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def vector() -> dict[str, Any]:
    return load(VECTOR)


def scenario_names() -> list[str]:
    return (
        [s["name"] for s in vector()["scenarios"]]
        if VECTOR.is_file()
        else ["<missing>"]
    )


def scenario(name: str) -> dict[str, Any]:
    (found,) = [s for s in vector()["scenarios"] if s["name"] == name]
    return found


def steps() -> list[dict[str, Any]]:
    return [step for s in vector()["scenarios"] for step in s["steps"]]


def schema(game_version: str, payload: str) -> dict[str, Any]:
    return load(GAMES[game_version] / f"{payload}.schema.json")


def limits() -> dict[str, int]:
    doc = load(PAYLOADS)
    plus = {
        "move_ceiling": doc["shared_ceilings"]["move"],
        "observation_bound": schema("chess-1", "observation")["x-agentnexus-max-bytes"],
    }
    return {
        entry["message"]: entry["fixed_bytes"]
        + (plus[entry["plus"]] if entry["plus"] else 0)
        for entry in doc["message_limits"]
    }


def run(scenario_: dict[str, Any]) -> list[tuple[int, Any]]:
    doc = vector()
    keys = {key["key_id"]: key["public_key"] for key in doc["grant_verification_keys"]}
    verifier = Provider(doc["provider_id"], keys, limits(), PROTOCOL)
    results = []
    for step in scenario_["steps"]:
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


def tickets() -> dict[tuple[str, str], dict[str, Any]]:
    return {
        (entry["ticket"]["match_id"], entry["ticket"]["seat"]): entry
        for entry in vector()["tickets"]
    }


def accepted(scenario_: dict[str, Any]) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    """Each step answered 200, with its request body."""
    return [
        (step, json.loads(step["request"]["body"]))
        for step in scenario_["steps"]
        if step["expected"]["status"] == 200
    ]


def test_the_vector_exists_and_names_both_chess_game_versions() -> None:
    doc = vector()
    assert doc["game_versions"] == ["chess-1", "chess-1-solo"]
    assert doc["body_limits_from"] == "vectors/chess-1-payloads/cases.json"
    assert "D-170" in doc["decisions"]
    assert {t["ticket"]["game_version"] for t in doc["tickets"]} == set(
        doc["game_versions"]
    )


def test_the_keys_are_provider_wire_v1s_published_test_keys() -> None:
    doc, wire = vector(), load(WIRE)
    for member in (
        "provider_id",
        "grant_verification_keys",
        "unheld_grant_key",
        "session_test_keys",
    ):
        assert doc[member] == wire[member], member
    for entry in (*doc["grant_verification_keys"], *doc["session_test_keys"]):
        assert public(private(entry)) == entry["public_key"]


def test_each_ticket_is_signed_over_its_second_version_lines() -> None:
    doc = vector()
    grant = private(doc["grant_verification_keys"][0])
    sessions = {entry["name"]: private(entry) for entry in doc["session_test_keys"]}
    for entry in doc["tickets"]:
        ticket = entry["ticket"]
        signature = base64.b64decode(ticket["signature"])
        grant.public_key().verify(signature, ticket_bytes(ticket))
        raw = base64.b64decode(public(sessions[entry["session_key"]]))
        assert ticket["session_key_fingerprint"] == hashlib.sha256(raw).hexdigest()
        assert ticket["seat"] in COLOURS
        assert ticket["provider_id"] == doc["provider_id"]


def test_each_message_is_signed_over_its_play_lines() -> None:
    sessions = {
        entry["name"]: private(entry) for entry in vector()["session_test_keys"]
    }
    for step in steps():
        request = step["request"]
        found = PATH.fullmatch(request["path"])
        assert found is not None, step["name"]
        body = request["body"].encode("utf-8")
        document = json.loads(body)
        lines = play_bytes(
            KINDS[found["kind"]],
            found["match_id"],
            found["seat"],
            document["seat_generation"],
            document["sequence"],
            body,
        )
        signature = base64.b64decode(request["headers"][SIGNATURE_HEADER])
        sessions[request["signed_by"]].public_key().verify(signature, lines)


@pytest.mark.parametrize("name", scenario_names())
def test_each_scenario_gets_its_published_answers(name: str) -> None:
    published = scenario(name)
    expected = [
        (s["expected"]["status"], s["expected"]["body"]) for s in published["steps"]
    ]
    assert run(published) == expected


def test_each_accepted_answer_carries_an_observation_its_game_version_accepts() -> None:
    seat_answer = load(PROTOCOL / "seat-answer.schema.json")
    for entry in vector()["scenarios"]:
        for step, document in accepted(entry):
            found = PATH.fullmatch(step["request"]["path"])
            assert found is not None
            ticket = tickets()[(found["match_id"], found["seat"])]["ticket"]
            answer = step["expected"]["body"]
            assert valid(answer, seat_answer), step["name"]
            assert valid(
                answer["observation"], schema(ticket["game_version"], "observation")
            )
            assert answer["observation"]["you_are"] == COLOURS[found["seat"]]
            if "move" in document:
                assert valid(document["move"], schema(ticket["game_version"], "move"))


def test_the_answers_record_the_game_that_was_played() -> None:
    """Each accepted move is the next in the game, by the side to move, in every later answer."""
    for entry in vector()["scenarios"]:
        played: list[str] = []
        for step, document in accepted(entry):
            observation = step["expected"]["body"]["observation"]
            uci = document.get("move", {}).get("uci")
            if uci is not None and step.get("provider_answer") is not None:
                assert observation["moves"][len(played)] == uci, step["name"]
                found = PATH.fullmatch(step["request"]["path"])
                assert found is not None
                assert len(played) % 2 == (0 if found["seat"] == "first" else 1)
            assert observation["moves"][: len(played)] == played, step["name"]
            played = list(observation["moves"])
            assert step["expected"]["body"]["state_version"] >= 0


def test_a_match_awaits_both_seats_and_white_moves_first() -> None:
    steps_ = {s["name"]: s for s in scenario("bind-both-and-play")["steps"]}
    assert steps_["redeem-first"]["expected"]["body"]["status"] == "awaiting_seats"
    assert steps_["a-move-before-both-seats-are-bound"]["expected"]["body"] == {
        "error": {"code": "move_not_legal"}
    }
    assert steps_["redeem-second"]["expected"]["body"]["status"] == "active"
    refused = {s["name"]: s for s in scenario("chess-refusals")["steps"]}
    assert refused["black-before-white"]["expected"]["body"] == {
        "error": {"code": "move_not_legal"}
    }


@pytest.mark.parametrize(
    ("name", "code"),
    [
        ("a-move-the-rules-refuse", "move_not_legal"),
        ("a-claim-that-does-not-hold", "move_not_legal"),
        ("a-move-outside-the-vocabulary", "malformed_body"),
        ("a-connect-four-move", "malformed_body"),
        ("an-empty-move", "malformed_body"),
    ],
)
def test_chess_refusals_are_shown(name: str, code: str) -> None:
    (step,) = [s for s in scenario("chess-refusals")["steps"] if s["name"] == name]
    assert step["expected"]["body"] == {"error": {"code": code}}
    move = json.loads(step["request"]["body"])["move"]
    assert valid(move, schema("chess-1", "move")) == (code == "move_not_legal")


def test_a_claimed_repetition_ends_the_game_drawn() -> None:
    steps_ = {s["name"]: s for s in scenario("a-claimed-repetition")["steps"]}
    claim = steps_["black-plays-f6g8-and-claims-the-repetition"]
    assert json.loads(claim["request"]["body"])["move"] == {
        "uci": "f6g8",
        "claim": "threefold_repetition",
    }
    answer = claim["expected"]["body"]
    assert answer["status"] == "ended"
    result = answer["observation"]["result"]
    assert result["outcome"] == "draw" and result["reason"] == "threefold_repetition"
    assert steps_["a-move-after-the-end"]["expected"]["body"] == {
        "error": {"code": "match_not_running"}
    }


def test_the_computer_answers_in_the_same_request_in_solo() -> None:
    steps_ = {s["name"]: s for s in scenario("solo")["steps"]}
    redeemed = steps_["redeem-the-agent"]["expected"]["body"]
    assert redeemed["status"] == "active"
    answer = steps_["white-plays-and-the-computer-answers"]["expected"]["body"]
    assert answer["observation"]["moves"][0] == "e2e4"
    assert len(answer["observation"]["moves"]) == 2
    assert answer["observation"]["to_move"] == "white"
