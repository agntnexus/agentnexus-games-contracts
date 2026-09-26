"""The grant ticket verification vector, and the reference check that runs it.

`vectors/grant-ticket-v1/verification.json` holds two cases: a control ticket that verifies, and
the same ticket presented in another match, which is refused on the match binding. These tests
require both verdicts, require the file to be reproducible from its published test seeds, and break
every rule of the grant ticket format once -- each break has to be refused, for its own reason.

Every key here is a published test key that is valid nowhere. No ticket here is a grant.
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
from grant_ticket import SIGNED_LINES, canonical, verify

VECTOR = (
    Path(__file__).resolve().parents[1]
    / "vectors"
    / "grant-ticket-v1"
    / "verification.json"
)


def load() -> dict[str, Any]:
    return json.loads(VECTOR.read_text(encoding="utf-8"))


def keys(doc: dict[str, Any]) -> dict[str, str]:
    return {key["key_id"]: key["public_key"] for key in doc["grant_verification_keys"]}


def case(doc: dict[str, Any], name: str) -> dict[str, Any]:
    (found,) = [c for c in doc["cases"] if c["name"] == name]
    return copy.deepcopy(found)


def signer(doc: dict[str, Any]) -> Ed25519PrivateKey:
    seed = bytes.fromhex(doc["grant_verification_keys"][0]["test_private_seed_hex"])
    return Ed25519PrivateKey.from_private_bytes(seed)


def resign(doc: dict[str, Any], fields: dict[str, str]) -> str:
    return base64.b64encode(signer(doc).sign(canonical(fields))).decode("ascii")


# The vector as published.


@pytest.mark.parametrize("name", ["control", "another-match"])
def test_each_case_gets_its_published_verdict(name: str) -> None:
    doc = load()
    c = case(doc, name)
    verdict, reason = verify(c["fields"], c["signature"], keys(doc), c["context"])
    assert verdict == c["expected"], reason
    if verdict == "refused":
        assert reason == c["refused_on"]


def test_the_refused_case_differs_from_the_control_only_in_the_match() -> None:
    """Otherwise the refusal could come from something other than the match binding."""
    doc = load()
    control, other = case(doc, "control"), case(doc, "another-match")
    assert (
        control["fields"] == other["fields"]
        and control["signature"] == other["signature"]
    )
    changed = {
        k for k in control["context"] if control["context"][k] != other["context"][k]
    }
    assert changed == {"match_id"}


def test_the_signed_lines_are_the_d100_lines() -> None:
    assert load()["signed_lines"] == ["agentnexus-grant-v1", *SIGNED_LINES]


def test_the_vector_is_what_its_published_test_seeds_produce() -> None:
    """Anyone can regenerate the keys and the signature; Ed25519 signing is deterministic."""
    doc = load()
    grant = doc["grant_verification_keys"][0]
    seed = hashlib.sha256(grant["seed_is_sha256_of"].encode("utf-8")).digest()
    assert seed.hex() == grant["test_private_seed_hex"]
    public = signer(doc).public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    assert base64.b64encode(public).decode("ascii") == grant["public_key"]

    session = doc["session_test_key"]
    session_seed = hashlib.sha256(session["seed_is_sha256_of"].encode("utf-8")).digest()
    session_public = (
        Ed25519PrivateKey.from_private_bytes(session_seed)
        .public_key()
        .public_bytes(Encoding.Raw, PublicFormat.Raw)
    )
    assert session_public.hex() == session["public_key_hex"]

    control = case(doc, "control")
    assert (
        control["fields"]["session_key_fingerprint"]
        == hashlib.sha256(session_public).hexdigest()
    )
    assert resign(doc, control["fields"]) == control["signature"]


def test_every_published_key_says_it_is_valid_nowhere() -> None:
    doc = load()
    phrases = [k["seed_is_sha256_of"] for k in doc["grant_verification_keys"]]
    phrases.append(doc["session_test_key"]["seed_is_sha256_of"])
    assert all(phrase.endswith("valid nowhere") for phrase in phrases)


# Every rule of the format, broken once. Each starts from the control case, which is accepted.


def control() -> tuple[dict[str, Any], dict[str, Any]]:
    doc = load()
    return doc, case(doc, "control")


def refused_on(doc: dict[str, Any], c: dict[str, Any], reason: str) -> None:
    verdict, why = verify(c["fields"], c["signature"], keys(doc), c["context"])
    assert (verdict, why) == ("refused", reason)


def test_a_changed_signature_is_refused() -> None:
    doc, c = control()
    raw = bytearray(base64.b64decode(c["signature"]))
    raw[0] ^= 1
    c["signature"] = base64.b64encode(bytes(raw)).decode("ascii")
    refused_on(doc, c, "signature")


@pytest.mark.parametrize("field", SIGNED_LINES)
def test_a_signed_field_changed_after_signing_is_refused(field: str) -> None:
    """The provider rebuilds the signed string from the fields; a changed field breaks it."""
    doc, c = control()
    value = c["fields"][field]
    c["fields"][field] = value[:-1] + ("0" if value[-1] != "0" else "1")
    verdict, _ = verify(c["fields"], c["signature"], keys(doc), c["context"])
    assert verdict == "refused"


def test_an_unknown_key_is_refused() -> None:
    doc, c = control()
    refused_on_keys = {"00000000-0000-4000-8000-000000000000": keys(doc).popitem()[1]}
    verdict, why = verify(c["fields"], c["signature"], refused_on_keys, c["context"])
    assert (verdict, why) == ("refused", "key")


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        (lambda f: f.update(extra="x"), "fields"),
        (lambda f: f.pop("seat"), "fields"),
        (lambda f: f.update(match_id=f["match_id"].upper()), "format"),
        (lambda f: f.update(seat="seat a"), "format"),
        (lambda f: f.update(seat="s" * 65), "format"),
        (lambda f: f.update(not_after="2026-09-26T08:02:00+00:00"), "format"),
        (lambda f: f.update(session_key_fingerprint="ab" * 31), "format"),
        (lambda f: f.update(not_after="2026-09-26T08:02:01Z"), "lifetime"),
        (lambda f: f.update(not_after="2026-09-26T07:59:59Z"), "lifetime"),
    ],
)
def test_a_malformed_or_overlong_ticket_is_refused(change: Any, reason: str) -> None:
    """Re-signed, so the refusal is the format's and not the signature's."""
    doc, c = control()
    change(c["fields"])
    if reason != "fields":
        c["signature"] = resign(doc, c["fields"])
    refused_on(doc, c, reason)


@pytest.mark.parametrize(
    ("now", "verdict"),
    [
        ("2026-09-26T07:59:30Z", "accepted"),
        ("2026-09-26T07:59:29Z", "refused"),
        ("2026-09-26T08:02:30Z", "accepted"),
        ("2026-09-26T08:02:31Z", "refused"),
    ],
)
def test_the_clock_skew_is_thirty_seconds_on_either_side(
    now: str, verdict: str
) -> None:
    doc, c = control()
    c["context"]["now"] = now
    got, why = verify(c["fields"], c["signature"], keys(doc), c["context"])
    assert got == verdict, why
    if verdict == "refused":
        assert why == "clock"


@pytest.mark.parametrize(
    ("binding", "value"),
    [
        ("match_id", "c4b3a291-8e7d-4f6c-a5b4-3c2d1e0f9a8b"),
        ("provider_id", "another-provider"),
        ("seat", "seat-b"),
    ],
)
def test_each_binding_is_checked_against_the_redemption(
    binding: str, value: str
) -> None:
    doc, c = control()
    c["context"][binding] = value
    refused_on(
        doc,
        c,
        {"match_id": "match", "provider_id": "provider", "seat": "seat"}[binding],
    )


# One signed string, one ticket. A line break inside a field would let two different tickets share
# the same signed bytes, and so the same signature.


def test_two_tickets_with_the_same_signed_bytes_are_not_both_accepted() -> None:
    """("a\\nb", "c") and ("a", "b\\nc") join to the same lines; neither may verify."""
    doc, c = control()
    first = dict(c["fields"], provider_id="a\nb", game_version="c")
    second = dict(c["fields"], provider_id="a", game_version="b\nc")
    assert canonical(first) == canonical(second), (
        "the counterexample would prove nothing"
    )
    signature = resign(doc, first)
    verdicts = [
        verify(fields, signature, keys(doc), dict(c["context"], provider_id=provider))
        for fields, provider in ((first, "a\nb"), (second, "a"))
    ]
    assert verdicts == [("refused", "format"), ("refused", "format")]


@pytest.mark.parametrize("field", ["provider_id", "game_version"])
@pytest.mark.parametrize("brk", ["\n", "\r", "\r\n"])
def test_a_line_break_in_a_manifest_value_is_refused(field: str, brk: str) -> None:
    """A carriage return too: a normaliser that turned it into LF would open a second reading."""
    doc, c = control()
    c["fields"][field] = c["fields"][field] + brk + "x"
    c["signature"] = resign(doc, c["fields"])
    if field == "provider_id":
        c["context"]["provider_id"] = c["fields"]["provider_id"]
    refused_on(doc, c, "format")
