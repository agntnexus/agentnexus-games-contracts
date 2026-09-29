"""The provider manifest of `agentnexus-games-v1`, and the check of its form and compatibility.

`protocol/v1/manifest.schema.json` is the form `D-123` and `D-124` fix, and
`vectors/manifest-v1/cases.json` holds one manifest the check accepts and one for every rule it
refuses. Admission itself, and every value of a deadline, rate or retention, stay with `#82` and
`#87`; this is only the form a provider declares and the check that it fits this contract.
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
from json_schema import unknown_keywords, valid
from manifest import IMPLEMENTED, check

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "protocol" / "v1" / "manifest.schema.json"
VECTOR = ROOT / "vectors" / "manifest-v1" / "cases.json"
DIALECT = "https://json-schema.org/draft/2020-12/schema"

#: The refusals of the compatibility check (`D-123`), each shown by one case.
COMPATIBILITY = {"contract_version", "game_version", "operations", "origin"}
#: The form rules `D-124` adds, each broken by one case the schema refuses.
FORM = {
    "an IP address as host",
    "a path after the origin",
    "a trailing slash",
    "port 0",
    "port 65536",
    "a zero turn deadline",
    "a zero action rate",
    "a zero retention",
    "a version number instead of its name",
    "five origins",
    "an unknown member",
}


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def schema() -> dict[str, Any]:
    return load(SCHEMA)


def cases() -> list[dict[str, Any]]:
    return load(VECTOR)["cases"]


def names() -> list[str]:
    return [case["name"] for case in load(VECTOR)["cases"]]


def case(name: str) -> dict[str, Any]:
    (found,) = [c for c in cases() if c["name"] == name]
    return found


def test_the_schema_is_strict_2020_12_in_keywords_the_check_knows() -> None:
    manifest = schema()
    assert manifest["$schema"] == DIALECT
    assert manifest["additionalProperties"] is False
    assert unknown_keywords(manifest) == []
    assert manifest["properties"]["version"] == {"const": "agentnexus-manifest-v1"}


def test_the_schema_holds_every_member_d123_names() -> None:
    assert set(schema()["required"]) == {
        "version",
        "provider_id",
        "contract_versions",
        "origins",
        "games",
        "operations",
        "outcome_keys",
        "action_rate_per_minute",
        "replay_retention_days",
    }
    game = schema()["properties"]["games"]["items"]
    assert set(game["required"]) == {"game_version", "turn_deadline_seconds"}


def test_the_numbers_are_positive_integers_without_a_ceiling() -> None:
    """`D-124`: at least 1, no upper bound; the values belong to `#82` and `#87`."""
    properties = schema()["properties"]
    numbers = [
        properties["action_rate_per_minute"],
        properties["replay_retention_days"],
        properties["games"]["items"]["properties"]["turn_deadline_seconds"],
    ]
    for number in numbers:
        assert number == {"type": "integer", "minimum": 1}


def test_the_implemented_version_is_d124s_name() -> None:
    assert IMPLEMENTED == frozenset({"agentnexus-games-v1"})


def test_the_outcome_key_is_what_its_published_seed_produces() -> None:
    entry = load(VECTOR)["outcome_test_key"]
    seed = hashlib.sha256(entry["seed_is_sha256_of"].encode("utf-8")).digest()
    key = Ed25519PrivateKey.from_private_bytes(seed)
    raw = key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    assert base64.b64encode(raw).decode("ascii") == entry["public_key"]


@pytest.mark.parametrize("name", names())
def test_each_case_gets_its_published_verdict(name: str) -> None:
    c = case(name)
    reasons = check(c["manifest"], ROOT)
    if c["expected"] == "accepted":
        assert reasons == []
    else:
        assert c["refused_for"] in reasons, reasons


def test_every_compatibility_refusal_is_shown_once() -> None:
    shown = [c["refused_for"] for c in cases() if c["expected"] == "refused"]
    assert COMPATIBILITY <= set(shown)
    assert all(shown.count(reason) == 1 for reason in COMPATIBILITY)


def test_every_form_rule_is_broken_once() -> None:
    broken = {c["breaks"] for c in cases() if c.get("refused_for") == "schema"}
    assert broken == FORM


def test_each_refused_case_differs_from_the_accepted_one_in_one_member() -> None:
    """Otherwise its refusal could come from something other than the rule it breaks."""
    (accepted,) = [c["manifest"] for c in cases() if c["expected"] == "accepted"]
    for c in cases():
        if c["expected"] == "refused":
            changed = {k for k in accepted.keys() | c["manifest"].keys()}
            changed = {k for k in changed if accepted.get(k) != c["manifest"].get(k)}
            assert len(changed) == 1, (c["name"], changed)


def test_the_accepted_manifest_is_valid_against_the_schema() -> None:
    (accepted,) = [c["manifest"] for c in cases() if c["expected"] == "accepted"]
    assert valid(accepted, schema())


def test_a_manifest_offers_the_solo_game_version_in_its_existing_games() -> None:
    """`D-142`: a provider offers `connect-four-1-solo` in the `games` its manifest already has."""
    accepted = next(c for c in cases() if c["expected"] == "accepted")["manifest"]
    deadline = accepted["games"][0]["turn_deadline_seconds"]
    offered = {
        **accepted,
        "games": [
            *accepted["games"],
            {"game_version": "connect-four-1-solo", "turn_deadline_seconds": deadline},
        ],
    }
    assert valid(offered, schema())
    assert check(offered, ROOT) == []
    unknown = {
        **offered,
        "games": [
            {"game_version": "connect-four-2-solo", "turn_deadline_seconds": deadline}
        ],
    }
    assert check(unknown, ROOT) == ["game_version"]
