"""The read-only spectator contract of `agentnexus-games-v1`, and the provider's reference check.

`protocol/v1/spectator-capability.schema.json` and `spectator-answer.schema.json`, and the game
version's `spectator.schema.json`, are the forms `D-123` and `D-124` fix. `vectors/spectator-v1/`
holds a public match with its events and a scenario of requests a viewer sends, each with the
provider's answer. These tests require every step to get its published answer, a write to be
refused before the capability is looked at, the view to be the observation's public fields
without the viewer's, every string to be an enum or a fixed pattern, and every view the browser
must never render to be refused. `D-139` changes the write rule in one place: the one CORS preflight
a configured observer origin sends before it reads is answered 204, and nothing else is.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from json_schema import KEYWORDS, unknown_keywords, valid
from spectator import LIFETIME, Watch

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT / "protocol" / "v1"
GAME = ROOT / "games" / "connect-four" / "connect-four-1"
VECTOR = ROOT / "vectors" / "spectator-v1" / "cases.json"
PAYLOADS = ROOT / "vectors" / "connect-four-1-payloads" / "cases.json"
DIALECT = "https://json-schema.org/draft/2020-12/schema"
ANNOTATIONS = frozenset({"x-agentnexus-data-class", "x-agentnexus-retained"})
TOKEN = "^[A-Za-z0-9_-]{43}$"


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def vector() -> dict[str, Any]:
    return load(VECTOR)


def steps() -> list[dict[str, Any]]:
    return vector()["steps"]


def watch() -> Watch:
    provider = Watch(vector()["matches"], PROTOCOL, ROOT / "games")
    provider.watch_origins = tuple(vector()["watch_origins"])
    return provider


def replay(until: int) -> tuple[Watch, list[tuple[int, Any]]]:
    provider = watch()
    found = []
    for step in steps()[: until + 1]:
        request = step["request"]
        found.append(
            provider.handle(
                request["method"],
                request["path"],
                request["headers"],
                request["body"].encode("utf-8"),
                step["now"],
                step.get("issues"),
            )
        )
    return provider, found


def run(until: int) -> list[tuple[int, Any]]:
    return replay(until)[1]


def the_preflight(step: dict[str, Any]) -> bool:
    """`D-139`'s one exception: a configured origin asks to `GET` with at most the header."""
    request = step["request"]
    headers = {name.lower(): value for name, value in request["headers"].items()}
    requested = {
        name.strip().lower()
        for name in headers.get("access-control-request-headers", "").split(",")
        if name.strip()
    }
    return (
        request["method"] == "OPTIONS"
        and headers.get("origin") in vector()["watch_origins"]
        and headers.get("access-control-request-method") == "GET"
        and requested <= {"agentnexus-watch-capability"}
    )


def strings(schema: Any) -> list[dict[str, Any]]:
    """Every subschema that admits a string."""
    found = []
    if isinstance(schema, dict):
        if schema.get("type") == "string":
            found.append(schema)
        for value in schema.values():
            found.extend(strings(value))
    elif isinstance(schema, list):
        for value in schema:
            found.extend(strings(value))
    return found


def test_the_schemas_are_strict_2020_12() -> None:
    for name in ("spectator-capability.schema.json", "spectator-answer.schema.json"):
        schema = load(PROTOCOL / name)
        assert schema["$schema"] == DIALECT, name
        assert schema["additionalProperties"] is False, name
        assert unknown_keywords(schema) == [], name
    view = load(GAME / "spectator.schema.json")
    assert view["$schema"] == DIALECT
    assert view["additionalProperties"] is False
    assert unknown_keywords(view, KEYWORDS | ANNOTATIONS) == []


def test_the_capability_is_43_characters_of_base64url() -> None:
    capability = load(PROTOCOL / "spectator-capability.schema.json")
    assert capability["properties"]["capability"]["pattern"] == TOKEN


def test_the_view_is_the_observations_public_fields_without_the_viewers() -> None:
    """`D-123`: only `public` fields, without those naming the viewer; the classes stay."""
    observation = load(GAME / "observation.schema.json")["properties"]
    view = load(GAME / "spectator.schema.json")
    expected = {
        name: field
        for name, field in observation.items()
        if field["x-agentnexus-data-class"] == "public" and name != "you_are"
    }
    assert view["properties"] == expected
    assert view["required"] == list(expected)


def test_every_string_the_browser_receives_is_an_enum_or_a_fixed_pattern() -> None:
    """`D-123`: no URL, asset, markup or free-form text reaches the browser."""
    for schema in (
        load(PROTOCOL / "spectator-answer.schema.json"),
        load(GAME / "spectator.schema.json"),
        load(PROTOCOL / "spectator-capability.schema.json"),
    ):
        for subschema in strings(schema):
            assert "pattern" in subschema or "enum" in subschema, subschema


@pytest.mark.parametrize(
    "index", range(len(json.loads(VECTOR.read_text("utf-8"))["steps"]))
)
def test_each_step_gets_its_published_answer(index: int) -> None:
    step = steps()[index]
    assert run(index)[index] == (step["expected"]["status"], step["expected"]["body"])


def test_every_answer_has_its_published_form() -> None:
    answer = load(PROTOCOL / "spectator-answer.schema.json")
    capability = load(PROTOCOL / "spectator-capability.schema.json")
    refusal = load(PROTOCOL / "refusal.schema.json")
    view = load(GAME / "spectator.schema.json")
    limit = 1024 + 17 * load(GAME / "observation.schema.json")["x-agentnexus-max-bytes"]
    for step in steps():
        status, body = step["expected"]["status"], step["expected"]["body"]
        if status == 204:
            assert body is None and the_preflight(step), step["name"]
        elif status != 200:
            assert valid(body, refusal), step["name"]
        elif step["request"]["path"].endswith("/capability"):
            assert valid(body, capability), step["name"]
        else:
            assert valid(body, answer), step["name"]
            assert valid(body["snapshot"], view), step["name"]
            assert all(valid(event["view"], view) for event in body["events"]), step[
                "name"
            ]
            assert len(json.dumps(body, separators=(",", ":")).encode()) <= limit


def test_a_capability_lives_at_most_300_seconds() -> None:
    assert LIFETIME == 300
    for step in steps():
        issued = step.get("issues")
        if issued:
            start = datetime.strptime(step["now"], "%Y-%m-%dT%H:%M:%SZ").replace(
                tzinfo=UTC
            )
            end = datetime.strptime(issued["expires_at"], "%Y-%m-%dT%H:%M:%SZ").replace(
                tzinfo=UTC
            )
            assert 0 < (end - start).total_seconds() <= LIFETIME


def test_each_test_capability_is_what_its_published_phrase_produces() -> None:
    import base64

    for entry in vector()["test_capabilities"]:
        digest = hashlib.sha256(entry["is_sha256_of"].encode("utf-8")).digest()
        token = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
        assert token == entry["capability"]


def test_the_events_are_capped_and_ordered() -> None:
    for step in steps():
        body = step["expected"]["body"]
        if step["expected"]["status"] == 200 and "events" in (body or {}):
            numbers = [event["event_seq"] for event in body["events"]]
            assert len(numbers) <= 16
            assert numbers == sorted(numbers)
            if "after=" not in step["request"]["path"]:
                assert numbers == []


def test_a_write_is_refused_before_the_capability_is_looked_at() -> None:
    writes = [
        s
        for s in steps()
        if s["request"]["method"] != "GET"
        and "/capability" not in s["request"]["path"]
        and not the_preflight(s)
    ]
    assert writes
    for step in writes:
        assert (step["expected"]["status"], step["expected"]["body"]) == (
            405,
            {"error": {"code": "read_only"}},
        )
    assert any(
        "AgentNexus-Watch-Capability" not in s["request"]["headers"] for s in writes
    )


def test_every_unauthenticated_case_names_nothing_else() -> None:
    refused = [s for s in steps() if s["expected"]["status"] == 401]
    assert {s["name"] for s in refused} == {
        "no-capability",
        "an-unknown-capability",
        "an-expired-capability",
        "another-matchs-capability",
    }
    for step in refused:
        assert step["expected"]["body"] == {"error": {"code": "unauthenticated"}}


@pytest.mark.parametrize(
    "name", [c["name"] for c in json.loads(VECTOR.read_text("utf-8"))["refused_views"]]
)
def test_a_view_the_browser_must_never_render_is_refused(name: str) -> None:
    view = load(GAME / "spectator.schema.json")
    (case,) = [c for c in vector()["refused_views"] if c["name"] == name]
    assert not valid(case["view"], view)


def test_only_the_one_preflight_escapes_read_only() -> None:
    """`D-139`: every other method, and every other `OPTIONS`, stays 405 `read_only`."""
    answered = [s["name"] for s in steps() if s["expected"]["status"] == 204]
    assert answered == ["a-preflight-for-the-read"]
    options = [s for s in steps() if s["request"]["method"] == "OPTIONS"]
    assert {s["name"] for s in options if not the_preflight(s)} == {
        "a-preflight-from-another-origin",
        "a-preflight-for-a-write",
        "a-preflight-for-another-header",
        "an-options-that-asks-for-nothing",
    }
    for step in options:
        if not the_preflight(step):
            assert step["expected"]["status"] == 405, step["name"]
            assert step["expected"]["body"] == {"error": {"code": "read_only"}}


@pytest.mark.parametrize(
    "index",
    [
        i
        for i, s in enumerate(json.loads(VECTOR.read_text("utf-8"))["steps"])
        if "cors" in s["expected"]
    ],
)
def test_each_step_gets_its_published_cross_origin_headers(index: int) -> None:
    step = steps()[index]
    provider, _ = replay(index)
    request = step["request"]
    found = provider.cross_origin(
        request["method"], request["path"], request["headers"]
    )
    assert found == step["expected"]["cors"]


def test_no_answer_allows_credentials_and_another_origin_gets_nothing() -> None:
    """`D-139`: credentials are never allowed, and no other origin gets a cross-origin header."""
    stated = [s for s in steps() if "cors" in s["expected"]]
    assert stated
    for step in stated:
        cors = step["expected"]["cors"]
        assert "Access-Control-Allow-Credentials" not in cors, step["name"]
        assert set(cors) <= {
            "Access-Control-Allow-Origin",
            "Access-Control-Allow-Methods",
            "Access-Control-Allow-Headers",
        }
        if step["request"]["headers"].get("Origin") not in vector()["watch_origins"]:
            assert cors == {}, step["name"]
        else:
            assert (
                cors["Access-Control-Allow-Origin"]
                == step["request"]["headers"]["Origin"]
            )
        if not the_preflight(step):
            assert "Access-Control-Allow-Methods" not in cors, step["name"]
            assert "Access-Control-Allow-Headers" not in cors, step["name"]
