"""Reference check for a match grant ticket's verification, as the AgentNexus grant format fixes it.

It runs the vectors in `vectors/grant-ticket-v1/` and nothing else: it is test code, not a
provider, and nothing here issues, redeems or stores a ticket. Each rule below is one sentence of
the grant ticket format (`D-100` in the AgentNexus decisions):

- the signature is Ed25519 over the UTF-8 bytes of the signed lines, joined by a single LF with no
  trailing LF, carried as standard base64, and verified only over bytes rebuilt from the fields;
- the ticket holds exactly the fields of those lines; an unknown or missing field is refused;
- the key, ticket and match IDs are lowercase hyphenated UUIDs; the seat is 1 to 64 letters,
  digits, `-` and `_`; the fingerprint is lowercase hexadecimal SHA-256; both times are
  `YYYY-MM-DDTHH:MM:SSZ`;
- the ticket names a key the verifier holds;
- the span from start to end is at most 120 seconds;
- the clock may read from 30 seconds before the start to 30 seconds after the end;
- the provider, the match and the seat are the ones being redeemed.

One rule is not a sentence of the format but follows from it: the provider ID and the game version
may hold no line break, LF or CR. Otherwise ("a\\nb", "c") and ("a", "b\\nc") would join to the same
signed lines, and two different tickets would share one signature.

What it does not check, because the format leaves it to later decisions: the session key behind the
fingerprint (P-2), the operations a ticket permits (P-3), and any other part of the format of the
provider ID and the game version, which the admitted manifest defines.
"""

from __future__ import annotations

import base64
import binascii
import re
from datetime import UTC, datetime, timedelta
from typing import Final

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

VERSION: Final = "agentnexus-grant-v1"
SIGNED_LINES: Final = (
    "key_id",
    "ticket_id",
    "match_id",
    "seat",
    "provider_id",
    "game_version",
    "session_key_fingerprint",
    "not_before",
    "not_after",
)

UUID: Final = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
)
SEAT: Final = re.compile(r"[A-Za-z0-9_-]{1,64}")
FINGERPRINT: Final = re.compile(r"[0-9a-f]{64}")
TIME: Final = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")
#: A line break inside a field would move text from one signed line into the next, so two tickets
#: could share one signature. CR is refused with LF: a normaliser that turned it into LF would open
#: the same second reading. Nothing else about the manifest values is fixed here.
LINE_BREAK: Final = re.compile(r"[\r\n]")
MAX_LIFETIME: Final = timedelta(seconds=120)
SKEW: Final = timedelta(seconds=30)


def canonical(fields: dict[str, str]) -> bytes:
    """The signed bytes: the version line and each field, in order, joined by LF."""
    return "\n".join([VERSION, *(fields[name] for name in SIGNED_LINES)]).encode(
        "utf-8"
    )


def _time(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)


def _well_formed(fields: dict[str, str]) -> bool:
    if not all(isinstance(fields[name], str) for name in SIGNED_LINES):
        return False
    if not all(
        UUID.fullmatch(fields[name]) for name in ("key_id", "ticket_id", "match_id")
    ):
        return False
    if not SEAT.fullmatch(fields["seat"]):
        return False
    if any(LINE_BREAK.search(fields[name]) for name in ("provider_id", "game_version")):
        return False
    if not FINGERPRINT.fullmatch(fields["session_key_fingerprint"]):
        return False
    if not all(TIME.fullmatch(fields[name]) for name in ("not_before", "not_after")):
        return False
    try:
        _time(fields["not_before"])
        _time(fields["not_after"])
    except ValueError:
        return False
    return True


def verify(
    fields: dict[str, str],
    signature: str,
    keys: dict[str, str],
    context: dict[str, str],
) -> tuple[str, str]:
    """Return ("accepted", "") or ("refused", the rule that refused it).

    `keys` maps a key ID to a raw Ed25519 public key in standard base64; `context` names the
    provider, the match and the seat being redeemed, and the time the verifier's clock reads.
    """
    if set(fields) != set(SIGNED_LINES):
        return "refused", "fields"
    if not _well_formed(fields):
        return "refused", "format"

    public = keys.get(fields["key_id"])
    if public is None:
        return "refused", "key"
    try:
        key = Ed25519PublicKey.from_public_bytes(
            base64.b64decode(public, validate=True)
        )
        key.verify(base64.b64decode(signature, validate=True), canonical(fields))
    except (InvalidSignature, ValueError, binascii.Error):
        return "refused", "signature"

    start, end = _time(fields["not_before"]), _time(fields["not_after"])
    if not timedelta(0) <= end - start <= MAX_LIFETIME:
        return "refused", "lifetime"
    now = _time(context["now"])
    if not start - SKEW <= now <= end + SKEW:
        return "refused", "clock"

    if fields["provider_id"] != context["provider_id"]:
        return "refused", "provider"
    if fields["match_id"] != context["match_id"]:
        return "refused", "match"
    if fields["seat"] != context["seat"]:
        return "refused", "seat"
    return "accepted", ""
