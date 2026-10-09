"""The bounded Connect Four role-to-public-seat contract (#225)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from json_schema import unknown_keywords, valid

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "protocol" / "public-role-bindings-v1" / "answer.schema.json"
VECTOR_PATH = ROOT / "vectors" / "public-role-bindings-v1" / "cases.json"
DIALECT = "https://json-schema.org/draft/2020-12/schema"


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def test_role_binding_contract_has_zero_one_and_two_binding_cases() -> None:
    schema = load(SCHEMA_PATH)
    vector = load(VECTOR_PATH)
    assert schema["$schema"] == DIALECT
    assert schema["additionalProperties"] is False
    assert unknown_keywords(schema) == []

    accepted = vector["accepted"]
    assert [case["name"] for case in accepted] == [
        "zero-bindings",
        "one-binding",
        "two-bindings-reversed",
        "two-bindings-arena-ordered",
    ]
    for case in accepted:
        assert valid(case["answer"], schema), case["name"]


def test_foreign_duplicate_and_private_members_are_refused() -> None:
    schema = load(SCHEMA_PATH)
    vector = load(VECTOR_PATH)
    refused = vector["refused"]
    assert {case["name"] for case in refused} == {
        "foreign-seat-identifier",
        "duplicate-seat-mapping",
        "unknown-role",
        "session-key",
        "owner-identity",
    }
    for case in refused:
        assert not valid(case["answer"], schema), case["name"]
