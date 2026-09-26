"""An independent example client of the Games provider wire, played against the reference check.

`ci/example_client.py` is written from the public contract alone: the published tickets, test keys
and schemas, and the lines, header and paths the wire vector's README states. It does not import
the reference check and takes no verdict from it. Here the reference check only stands in for a
provider, and the answers its game would give are the ones the wire vector publishes.

These tests require the client to play a valid game that the reference provider accepts step by
step, and to reject what `D-114` and `D-118` make invalid on its side: an answer of an older seat
generation (W-4), an observation the game's schema refuses, and a refusal that carries more than
its code (W-8).
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

from example_client import Client
from provider_wire import Provider

ROOT = Path(__file__).resolve().parents[1]
WIRE = ROOT / "vectors" / "provider-wire-v1"
PAYLOADS = ROOT / "vectors" / "connect-four-1-payloads" / "cases.json"
GAME = ROOT / "games" / "connect-four" / "connect-four-1"
OTHER_MATCH = "7e6d5c4b-3a29-4180-9f7e-6d5c4b3a2918"


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def vector() -> dict[str, Any]:
    return load(WIRE / "cases.json")


def ticket(name: str) -> dict[str, Any]:
    (found,) = [t for t in vector()["tickets"] if t["name"] == name]
    return found["ticket"]


def phrase(session: str) -> str:
    (found,) = [k for k in vector()["session_test_keys"] if k["name"] == session]
    return found["seed_is_sha256_of"]


def game_answers(scenario: str) -> list[dict[str, Any]]:
    """The answers the provider's game gives in a published scenario, in order."""
    (found,) = [s for s in vector()["scenarios"] if s["name"] == scenario]
    return [s["provider_answer"] for s in found["steps"] if s["provider_answer"]]


def provider() -> Provider:
    doc = vector()
    payloads = load(PAYLOADS)
    plus = {
        "move_ceiling": payloads["shared_ceilings"]["move"],
        "observation_bound": load(GAME / "observation.schema.json")[
            "x-agentnexus-max-bytes"
        ],
    }
    limits = {
        e["message"]: e["fixed_bytes"] + (plus[e["plus"]] if e["plus"] else 0)
        for e in payloads["message_limits"]
    }
    keys = {k["key_id"]: k["public_key"] for k in doc["grant_verification_keys"]}
    return Provider(doc["provider_id"], keys, limits, WIRE)


def send(
    target: Provider, request: Any, now: str, answer: dict[str, Any] | None = None
) -> tuple[int, Any]:
    return target.handle(
        request.method, request.path, request.headers, request.body, now, answer
    )


def client(match_id: str | None = None) -> Client:
    first = ticket("gen-1")
    return Client(match_id or first["match_id"], first["seat"], WIRE, GAME)


def test_the_client_imports_no_reference_check() -> None:
    tree = ast.parse((ROOT / "ci" / "example_client.py").read_text(encoding="utf-8"))
    imported = {
        node.module if isinstance(node, ast.ImportFrom) else alias.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    assert not imported & {"provider_wire", "grant_ticket", "game_payloads"}


def test_the_client_plays_a_valid_game_the_provider_accepts() -> None:
    target, player = provider(), client()
    opening, after_move, resumed = game_answers("redeem-and-play")

    status, body = send(
        target,
        player.redeem(ticket("gen-1"), phrase("session-1")),
        "2026-09-26T08:00:30Z",
        opening,
    )
    assert status == 200
    assert player.receive(status, body) == ("accepted", None)

    move = player.move({"column": 3}, "9a8b7c6d-5e4f-4a3b-8c2d-1e0f9a8b7c6d")
    status, body = send(target, move, "2026-09-26T08:00:40Z", after_move)
    assert (status, player.receive(status, body)) == (200, ("accepted", None))

    status, body = send(target, player.resume(), "2026-09-26T08:00:50Z", resumed)
    assert (status, player.receive(status, body)) == (200, ("accepted", None))


def test_the_client_reads_a_refusal_the_provider_decides() -> None:
    """The ticket for one match, sent by a client in another, is refused `ticket_match`."""
    target, player = provider(), client(OTHER_MATCH)
    request = player.redeem(ticket("gen-1"), phrase("session-1"))
    status, body = send(target, request, "2026-09-26T08:00:30Z")
    assert status == 403
    assert player.receive(status, body) == ("refused", "ticket_match")


def test_the_client_discards_an_answer_of_an_older_generation() -> None:
    """W-4: every answer names its seat generation, and the Connector discards an older one."""
    target, player = provider(), client()
    opening, after_move, rebound, _ = game_answers("rebinding")

    send(
        target,
        player.redeem(ticket("gen-1"), phrase("session-1")),
        "2026-09-26T08:00:30Z",
        opening,
    )
    status, body = send(
        target,
        player.redeem(ticket("gen-2"), phrase("session-2")),
        "2026-09-26T08:05:30Z",
        rebound,
    )
    assert player.receive(status, body) == ("accepted", None)
    assert after_move["seat_generation"] < rebound["seat_generation"]
    assert player.receive(200, after_move) == ("discarded", None)


def test_the_client_rejects_an_observation_the_game_refuses() -> None:
    player = client()
    player.redeem(ticket("gen-1"), phrase("session-1"))
    (unknown,) = [
        c["observation"]
        for c in load(PAYLOADS)["observation_cases"]
        if c["name"] == "unknown-field"
    ]
    answer = {**game_answers("redeem-and-play")[0], "observation": unknown}
    assert player.receive(200, answer) == ("invalid", None)


def test_the_client_rejects_a_refusal_with_a_message_text() -> None:
    player = client()
    body = {"error": {"code": "ticket_match", "message": "wrong match"}}
    assert player.receive(403, body) == ("invalid", None)
