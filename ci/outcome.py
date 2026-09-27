"""Reference intake of the provider's signed outcome, for `agentnexus-games-v1`.

It runs the scenario in `vectors/outcome-v1/` and nothing else: it is test code, not the API. Each
rule below is a sentence of `D-123` or `D-124` in the AgentNexus decisions:

- the provider sends one outcome per match to `POST /agentnexus-games/v1/outcomes`, at most 2048
  bytes, checked in the refusal order: size (`too_large`), schema (`malformed_body`),
  authentication against an outcome key of the provider's manifest (`unauthenticated`), and the
  bindings, where another provider's match is `outcome_provider` and another game version is
  `outcome_game`, both 403;
- the signed bytes are `agentnexus-outcome-v1` and the twelve members below, one LF between lines
  and none after; `winner_seat` is the empty line when `null`, `solo` is `true` or `false`, and an
  integer is written in decimal;
- the API answers 200 with the match and a status: `recorded` for the first outcome;
  `already_recorded` only for one whose signed lines are byte-identical to the recorded one;
  `disputed` for any other, which never overwrites the first; `evidence_only` for a match already
  aborted or cancelled.

An outcome for a match the API does not know raises `Undecided`: no decision fixes its answer, and
no case sends one.
"""

from __future__ import annotations

import base64
import binascii
import json
from pathlib import Path
from typing import Any, Final

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from json_schema import valid

VERSION: Final = "agentnexus-outcome-v1"
SIGNED_LINES: Final = (
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
LIMIT: Final = 2048
STATUS: Final = {
    "too_large": 413,
    "malformed_body": 400,
    "unauthenticated": 401,
    "outcome_provider": 403,
    "outcome_game": 403,
}


class Undecided(Exception):
    """No decision fixes the answer to this outcome, so the intake does not choose one."""


def outcome_bytes(outcome: dict[str, Any]) -> bytes:
    """The outcome's signed bytes, as `D-123` fixes them."""

    def line(name: str) -> str:
        value = outcome[name]
        if value is None:
            return ""
        if isinstance(value, bool):
            return "true" if value else "false"
        return str(value)

    return "\n".join([VERSION, *(line(name) for name in SIGNED_LINES)]).encode("utf-8")


def _verifies(public_key: str | None, signature: str, message: bytes) -> bool:
    if public_key is None:
        return False
    try:
        key = Ed25519PublicKey.from_public_bytes(
            base64.b64decode(public_key, validate=True)
        )
        key.verify(base64.b64decode(signature, validate=True), message)
    except (InvalidSignature, ValueError, binascii.Error):
        return False
    return True


class Intake:
    """The API's outcome intake, with the records `I-6` keeps, and nothing else."""

    def __init__(
        self,
        keys_by_provider: dict[str, dict[str, str]],
        matches: dict[str, dict[str, str]],
        schemas: Path,
    ) -> None:
        self.keys_by_provider = keys_by_provider
        self.matches = matches
        self.schemas = schemas
        self.recorded: dict[str, bytes] = {}

    def handle(self, body: bytes) -> tuple[int, dict[str, Any]]:
        """Return the status and body the API answers an outcome with."""
        try:
            return 200, self._handle(body)
        except _Refused as refused:
            return STATUS[refused.code], {"error": {"code": refused.code}}

    def _handle(self, body: bytes) -> dict[str, Any]:
        if len(body) > LIMIT:
            raise _Refused("too_large")
        try:
            doc = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as error:
            raise _Refused("malformed_body") from error
        schema = json.loads(
            (self.schemas / "outcome.schema.json").read_text(encoding="utf-8")
        )
        if not valid(doc, schema):
            raise _Refused("malformed_body")

        lines = outcome_bytes(doc)
        keys = self.keys_by_provider.get(doc["provider_id"], {})
        if not _verifies(keys.get(doc["key_id"]), doc["signature"], lines):
            raise _Refused("unauthenticated")

        match = self.matches.get(doc["match_id"])
        if match is None:
            raise Undecided("an outcome for a match the API does not know")
        if match["provider_id"] != doc["provider_id"]:
            raise _Refused("outcome_provider")
        if match["game_version"] != doc["game_version"]:
            raise _Refused("outcome_game")

        recorded = self.recorded.get(doc["match_id"])
        if recorded is not None:
            status = "already_recorded" if lines == recorded else "disputed"
        elif match["state"] in ("aborted", "cancelled"):
            status = "evidence_only"
        else:
            self.recorded[doc["match_id"]] = lines
            status = "recorded"
        return {"match_id": doc["match_id"], "status": status}


class _Refused(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code
