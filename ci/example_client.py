"""An example client of the Games provider wire, version 1, written from the public contract alone.

It plays the Connector's side for one seat: it builds and signs a redemption, a move and a
resumption, and it reads the provider's answers. It is test code that runs in CI and touches no
network; it holds no real key and redeems no real grant. What it knows comes from this repository's
public files: the tickets and test keys in `vectors/provider-wire-v1/cases.json`, the common schemas
beside them, the game version's schemas in `games/`, and the wire the vector's README states:

- every message is signed with the seat's session key over `agentnexus-play-v1`, the purpose, the
  match, the seat, the generation, the sequence and the SHA-256 of the exact body, one LF between
  lines and none after; the signature travels in the header `AgentNexus-Play-Signature`;
- the purpose comes from the path: `redeem`, `resume` or `act` under
  `/agentnexus-games/v1/matches/{match_id}/seats/{seat}/`;
- a binding starts at sequence 1 with its redemption, and every later message carries the next;
- every answer names its seat generation, and the client discards an answer of an older one;
- an answer is a seat answer whose observation the game version's schema accepts, and a refusal
  carries its code and nothing else.
"""

from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from json_schema import valid

PREFIX = "/agentnexus-games/v1/matches"


@dataclass(frozen=True)
class Request:
    method: str
    path: str
    headers: dict[str, str]
    body: bytes


class Client:
    """The Connector's side of one seat in one match."""

    def __init__(self, match_id: str, seat: str, wire: Path, game: Path) -> None:
        self.match_id = match_id
        self.seat = seat
        self.wire = wire
        self.game = game
        self.key: Ed25519PrivateKey | None = None
        self.generation = 0
        self.sequence = 0
        self.state_version = 0

    def _schema(self, directory: Path, name: str) -> dict[str, Any]:
        return json.loads((directory / name).read_text(encoding="utf-8"))

    def _request(self, kind: str, purpose: str, body: dict[str, Any]) -> Request:
        assert self.key is not None, "a seat is played only after its redemption"
        raw = json.dumps(body, separators=(",", ":")).encode("utf-8")
        lines = "\n".join(
            [
                "agentnexus-play-v1",
                purpose,
                self.match_id,
                self.seat,
                str(body["seat_generation"]),
                str(body["sequence"]),
                hashlib.sha256(raw).hexdigest(),
            ]
        ).encode("utf-8")
        signature = base64.b64encode(self.key.sign(lines)).decode("ascii")
        return Request(
            "POST",
            f"{PREFIX}/{self.match_id}/seats/{self.seat}/{kind}",
            {"AgentNexus-Play-Signature": signature},
            raw,
        )

    def redeem(self, ticket: dict[str, Any], seed_phrase: str) -> Request:
        """Bind the seat, or rebind it, with a ticket and the session key it names."""
        seed = hashlib.sha256(seed_phrase.encode("utf-8")).digest()
        self.key = Ed25519PrivateKey.from_private_bytes(seed)
        public = self.key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
        self.generation = ticket["seat_generation"]
        self.sequence = 1
        body = {
            "ticket": ticket,
            "session_public_key": base64.b64encode(public).decode("ascii"),
            "seat_generation": self.generation,
            "sequence": self.sequence,
        }
        return self._request("redemption", "redeem", body)

    def move(self, move: dict[str, Any], idempotency_key: str) -> Request:
        """One move, expecting the state version of the last answer accepted."""
        self.sequence += 1
        body = {
            "seat_generation": self.generation,
            "sequence": self.sequence,
            "operation": "move",
            "idempotency_key": idempotency_key,
            "expected_state_version": self.state_version,
            "move": move,
        }
        return self._request("actions", "act", body)

    def resume(self) -> Request:
        """Ask for the seat's current observation."""
        self.sequence += 1
        body = {"seat_generation": self.generation, "sequence": self.sequence}
        return self._request("resumption", "resume", body)

    def receive(self, status: int, body: Any) -> tuple[str, str | None]:
        """Read an answer: ("accepted" | "discarded" | "refused" | "invalid", a code or None)."""
        if status == 200:
            answer = self._schema(self.wire, "seat-answer.schema.json")
            observation = self._schema(self.game, "observation.schema.json")
            if not valid(body, answer, base=self.wire) or not valid(
                body["observation"], observation
            ):
                return "invalid", None
            if body["seat_generation"] < self.generation:
                return "discarded", None
            self.state_version = body["state_version"]
            return "accepted", None
        refusal = self._schema(self.wire, "refusal.schema.json")
        if not isinstance(body, dict) or not valid(body, refusal):
            return "invalid", None
        return "refused", body["error"]["code"]
