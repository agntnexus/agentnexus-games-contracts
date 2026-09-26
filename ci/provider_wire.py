"""Reference check for the Games provider wire, version 1, as D-114 fixes it.

It runs the vectors in `vectors/provider-wire-v1/` and nothing else: it is test code, not a
provider. It does not play a game. Where a request passes every check, the vector supplies the
answer the provider's game gives, and this check stores it and returns it on an identical
repetition. Each rule below is a sentence of `D-114` (W-1 to W-8), with the grant ticket's times
and keys from `D-100` and the body limits from `D-118`:

- a request is checked in this order, and the first stage that fails answers: size, schema,
  authentication, freshness, bindings, state; before authentication only `too_large`,
  `malformed_body` and `unauthenticated` are returned, and they name no match or seat;
- the ticket's second version signs its lines under `agentnexus-grant-v2`; its operations are
  exactly `move,resign`; its span is at most 120 seconds and the clock may be 30 seconds outside it;
- every Connector message is signed with the seat's session key over the `agentnexus-play-v1`
  lines, and the signature travels in the header `AgentNexus-Play-Signature`; in a redemption the
  session public key's SHA-256 is the ticket's fingerprint;
- a binding starts at sequence 1; after full verification, the next number is applied, the last
  number with the same complete signed lines returns the stored answer, the last number with other
  lines is `sequence_conflict`, a lower number `sequence_stale`, a higher one `sequence_gap`;
- a ticket of a higher generation rebinds the seat, and the earlier key no longer authenticates; a
  ticket of a generation not higher than the one held is `generation_stale`;
- a path the provider does not serve answers 404 with no body.

Where `D-114` does not fix the outcome, this check raises `Undecided` instead of choosing one, and
no vector sends such a request. The resignation instruction, the spectator path and the outcome
interface are not run here.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Final

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from json_schema import valid

TICKET_VERSION: Final = "agentnexus-grant-v2"
TICKET_LINES: Final = (
    "key_id",
    "ticket_id",
    "match_id",
    "seat",
    "seat_generation",
    "provider_id",
    "game_version",
    "operations",
    "session_key_fingerprint",
    "not_before",
    "not_after",
)
PLAY_VERSION: Final = "agentnexus-play-v1"
SIGNATURE_HEADER: Final = "AgentNexus-Play-Signature"
#: Every grant of this first protocol version binds both operations, sorted.
OPERATIONS: Final = ["move", "resign"]
MAX_LIFETIME: Final = timedelta(seconds=120)
SKEW: Final = timedelta(seconds=30)

PATH: Final = re.compile(
    r"/agentnexus-games/v1/matches/(?P<match_id>[^/]+)/seats/(?P<seat>[^/]+)"
    r"/(?P<kind>redemption|resumption|actions)"
)
#: Paths W-6 serves that this check does not run: the owner's resignation, and watching, whose
#: capability `#85` defines.
NOT_RUN: Final = re.compile(
    r"/agentnexus-games/v1/matches/[^/]+"
    r"(?:/seats/[^/]+/resignation-instructions|/spectator)"
)
#: Each path: its purpose in the signed lines, its schema file and its body limit's message.
KINDS: Final = {
    "redemption": ("redeem", "redemption.schema.json", "redemption"),
    "resumption": ("resume", "resumption.schema.json", "resumption"),
    "actions": ("act", "action.schema.json", "action"),
}
STATUS: Final = {
    "too_large": 413,
    "malformed_body": 400,
    "unauthenticated": 401,
    "ticket_lifetime": 401,
    "ticket_clock": 401,
    "ticket_provider": 403,
    "ticket_match": 403,
    "ticket_seat": 403,
    "operation_not_granted": 403,
    "ticket_spent": 409,
    "generation_stale": 409,
    "sequence_conflict": 409,
    "sequence_stale": 409,
    "sequence_gap": 409,
    "state_version_stale": 409,
    "idempotency_conflict": 409,
    "match_not_running": 409,
}


class Undecided(Exception):
    """`D-114` does not fix the outcome of this request, so the check does not choose one."""


class NotRun(Exception):
    """A path `D-114` serves that this check does not run."""


class _Refused(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def ticket_bytes(ticket: dict[str, Any]) -> bytes:
    """The ticket's signed bytes: its version line and each field, in order, joined by LF."""

    def line(name: str) -> str:
        value = ticket[name]
        if name == "operations":
            return ",".join(value)
        return str(value)

    return "\n".join([TICKET_VERSION, *(line(name) for name in TICKET_LINES)]).encode(
        "utf-8"
    )


def play_bytes(
    purpose: str, match_id: str, seat: str, generation: int, sequence: int, body: bytes
) -> bytes:
    """A Connector message's signed bytes: purpose, match, seat, generation, sequence, digest."""
    lines = [
        PLAY_VERSION,
        purpose,
        match_id,
        seat,
        str(generation),
        str(sequence),
        hashlib.sha256(body).hexdigest(),
    ]
    return "\n".join(lines).encode("utf-8")


def _verifies(public_key: str, signature: str | None, message: bytes) -> bool:
    if signature is None:
        return False
    try:
        key = Ed25519PublicKey.from_public_bytes(
            base64.b64decode(public_key, validate=True)
        )
        key.verify(base64.b64decode(signature, validate=True), message)
    except (InvalidSignature, ValueError, binascii.Error):
        return False
    return True


def _time(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)


@dataclass
class _Binding:
    generation: int
    session_key: str
    operations: list[str]
    lines: bytes
    answer: dict[str, Any]
    sequence: int
    state_version: int
    status: str
    moves: dict[str, Any] = field(default_factory=dict)


class Provider:
    """One provider's verifier, with the state W-3 and W-4 keep, and nothing else."""

    def __init__(
        self,
        provider_id: str,
        grant_keys: dict[str, str],
        limits: dict[str, int],
        schemas: Path,
    ) -> None:
        self.provider_id = provider_id
        self.grant_keys = grant_keys
        self.limits = limits
        self.schemas = schemas
        self.spent: set[str] = set()
        self.bindings: dict[tuple[str, str], _Binding] = {}

    def handle(
        self,
        method: str,
        path: str,
        headers: dict[str, str],
        body: bytes,
        now: str,
        answer: dict[str, Any] | None = None,
    ) -> tuple[int, dict[str, Any] | None]:
        """Return the status and body the provider answers; `answer` is the game's, if accepted."""
        if NOT_RUN.fullmatch(path):
            raise NotRun(f"{path} is served under W-6 but not run by this check")
        match = PATH.fullmatch(path)
        if match is None:
            return 404, None
        if method != "POST":
            raise Undecided("another method on a path W-6 serves with POST")
        try:
            return 200, self._handle(match, headers, body, now, answer)
        except _Refused as refused:
            return STATUS[refused.code], {"error": {"code": refused.code}}

    def _handle(
        self,
        match: re.Match[str],
        headers: dict[str, str],
        body: bytes,
        now: str,
        answer: dict[str, Any] | None,
    ) -> dict[str, Any]:
        match_id, seat, kind = match["match_id"], match["seat"], match["kind"]
        purpose, schema_file, message = KINDS[kind]

        # 1. Size, before the body is parsed.
        if len(body) > self.limits[message]:
            raise _Refused("too_large")

        # 2. Schema.
        try:
            doc = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as error:
            raise _Refused("malformed_body") from error
        schema = json.loads((self.schemas / schema_file).read_text(encoding="utf-8"))
        if not valid(doc, schema, base=self.schemas):
            raise _Refused("malformed_body")

        lines = play_bytes(
            purpose, match_id, seat, doc["seat_generation"], doc["sequence"], body
        )
        signature = headers.get(SIGNATURE_HEADER)
        if kind == "redemption":
            return self._redeem(doc, lines, signature, match_id, seat, now, answer)
        return self._play(kind, doc, lines, signature, match_id, seat, answer)

    def _redeem(
        self,
        doc: dict[str, Any],
        lines: bytes,
        signature: str | None,
        match_id: str,
        seat: str,
        now: str,
        answer: dict[str, Any] | None,
    ) -> dict[str, Any]:
        ticket = doc["ticket"]

        # 3. Authentication: the ticket, then the possession proof.
        if ticket["operations"] != OPERATIONS:
            raise _Refused("unauthenticated")
        try:
            start, end = _time(ticket["not_before"]), _time(ticket["not_after"])
        except ValueError as error:
            raise _Refused("unauthenticated") from error
        grant_key = self.grant_keys.get(ticket["key_id"])
        if grant_key is None or not _verifies(
            grant_key, ticket["signature"], ticket_bytes(ticket)
        ):
            raise _Refused("unauthenticated")
        session_key = doc["session_public_key"]
        fingerprint = hashlib.sha256(base64.b64decode(session_key)).hexdigest()
        if fingerprint != ticket["session_key_fingerprint"]:
            raise _Refused("unauthenticated")
        if not _verifies(session_key, signature, lines):
            raise _Refused("unauthenticated")
        if doc["seat_generation"] != ticket["seat_generation"]:
            raise Undecided("a redemption whose generation differs from its ticket's")

        # 4. Freshness.
        if not timedelta(0) <= end - start <= MAX_LIFETIME:
            raise _Refused("ticket_lifetime")
        if not start - SKEW <= _time(now) <= end + SKEW:
            raise _Refused("ticket_clock")

        # 5. Bindings.
        if ticket["provider_id"] != self.provider_id:
            raise _Refused("ticket_provider")
        if ticket["match_id"] != match_id:
            raise _Refused("ticket_match")
        if ticket["seat"] != seat:
            raise _Refused("ticket_seat")

        # 6. State.
        held = self.bindings.get((match_id, seat))
        spent = ticket["ticket_id"] in self.spent
        if held is None and spent:
            raise _Refused("ticket_spent")
        if held is not None and ticket["seat_generation"] <= held.generation:
            if spent or lines == held.lines:
                # W-3 would return the stored answer, W-8 lists `ticket_spent` and W-4
                # `generation_stale`; D-114 orders none of them within the state stage.
                raise Undecided(
                    "a spent ticket, or the repeated redemption, for a bound seat"
                )
            raise _Refused("generation_stale")
        if answer is None:
            raise ValueError("the vector gives no answer for an accepted redemption")
        self.spent.add(ticket["ticket_id"])
        self.bindings[(match_id, seat)] = _Binding(
            generation=ticket["seat_generation"],
            session_key=session_key,
            operations=list(ticket["operations"]),
            lines=lines,
            answer=answer,
            sequence=1,
            state_version=answer["state_version"],
            status=answer["status"],
        )
        return answer

    def _play(
        self,
        kind: str,
        doc: dict[str, Any],
        lines: bytes,
        signature: str | None,
        match_id: str,
        seat: str,
        answer: dict[str, Any] | None,
    ) -> dict[str, Any]:
        # 3. Authentication, by the key bound to the path's seat now.
        binding = self.bindings.get((match_id, seat))
        if binding is None or not _verifies(binding.session_key, signature, lines):
            raise _Refused("unauthenticated")
        if doc["seat_generation"] != binding.generation:
            raise Undecided("a message whose generation is not the binding's")

        # 5. Bindings: the operation against the ticket.
        if kind == "actions" and doc["operation"] not in binding.operations:
            raise _Refused("operation_not_granted")

        # 6. State: the sequence first, since an identical repetition is not applied again.
        sequence = doc["sequence"]
        if sequence == binding.sequence:
            if lines == binding.lines:
                return binding.answer
            raise _Refused("sequence_conflict")
        if sequence < binding.sequence:
            raise _Refused("sequence_stale")
        if sequence > binding.sequence + 1:
            raise _Refused("sequence_gap")

        failures = []
        if kind == "actions":
            if binding.status in ("ended", "aborted"):
                failures.append("match_not_running")
            if doc["expected_state_version"] != binding.state_version:
                failures.append("state_version_stale")
            key = doc["idempotency_key"]
            if key in binding.moves:
                if binding.moves[key] == doc.get("move"):
                    raise Undecided("an idempotency key reused with the same move")
                failures.append("idempotency_conflict")
        if len(failures) > 1:
            raise Undecided(f"more than one state refusal: {', '.join(failures)}")
        if failures:
            raise _Refused(failures[0])

        if answer is None:
            raise ValueError("the vector gives no answer for an accepted message")
        binding.sequence, binding.lines, binding.answer = sequence, lines, answer
        binding.state_version, binding.status = (
            answer["state_version"],
            answer["status"],
        )
        if kind == "actions":
            binding.moves[doc["idempotency_key"]] = doc.get("move")
        return answer
