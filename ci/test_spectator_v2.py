"""The spectator answer, version 2, of `agentnexus-games-v1`, and its reference check.

`protocol/v1/spectator-answer-v2.schema.json` is the version 1 spectator answer and one more
required member, `timing`: the provider's own clock facts as absolute canonical UTC instants.
`vectors/spectator-v2/` holds a scenario of requests with the provider's answers, answers every
check must refuse, the frames of two streams, and how a viewer asks for each version. `D-175` in
the AgentNexus decisions fixes all of it. These tests require:

- every version 1 spectator file to stay as published, and the new schema to be the pinned one;
- the schema to be strict, closed, and the version 1 schema plus `timing`, nothing else;
- every step to get its published answer from the reference check, and every answer the vectors
  show to be accepted, whose six version 1 members are byte for byte the version 1 answer;
- every answer the vectors refuse to be refused by the layer that is named: the schema, or a rule
  of the reference check that the schema cannot say;
- the deadlines of every named case to be the exact instants written here, which the vector did
  not choose, and a deadline that has just passed to stay valid;
- a stream to start with the snapshot, to carry one to 16 events in every later frame, never to
  go back in time, and to end with no deadline;
- a viewer's two ways to ask for version 2, and what a provider that implements only version 1
  answers: either the plain version 1 answer, which is no version 2 answer, or a refusal.

Every capability here is test bytes, valid nowhere.
"""

from __future__ import annotations

import base64
import copy
import hashlib
import importlib
import json
import re
from datetime import UTC, datetime, timedelta
from functools import cache
from itertools import pairwise
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from check_repository import DECLARED, check
from json_schema import unknown_keywords, valid
from spectator import HEADER, LIFETIME, Watch

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT / "protocol" / "v1"
GAMES = ROOT / "games"
V1_SCHEMA = PROTOCOL / "spectator-answer.schema.json"
V2_SCHEMA = PROTOCOL / "spectator-answer-v2.schema.json"
V2_PROSE = PROTOCOL / "spectator-v2.md"
V1_VECTOR = ROOT / "vectors" / "spectator-v1" / "cases.json"
VECTOR = ROOT / "vectors" / "spectator-v2" / "cases.json"
VECTOR_README = ROOT / "vectors" / "spectator-v2" / "README.md"
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
DIALECT = "https://json-schema.org/draft/2020-12/schema"
ORIGIN = "https://observer.test.invalid"
V1_STREAM = "agentnexus-watch-v1"
V2_STREAM = "agentnexus-watch-v2"
INSTANT = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$")

#: The version 1 spectator files as `origin/main` published them (47457ec): the SHA-256 of the
#: canonical JSON of the two schemas (sorted keys, no whitespace), and of the bytes of the rest
#: with line endings normalised to LF, so that a checkout with CRLF gives the same digest.
V1_CANONICAL_SHA256 = {
    "protocol/v1/spectator-answer.schema.json": (
        "b8197fb5a8b2b56aab5457356a64f29447cf635ed832fbc2b0e54e457b835f7b"
    ),
    "protocol/v1/spectator-capability.schema.json": (
        "1246eec0226f510a9dd3ff2e48451c37bdc8ada33c74587c6caa2f12edb81fe8"
    ),
}
V1_RAW_SHA256 = {
    "protocol/v1/README.md": (
        "c685950a66338f9b834bd0d1a03a3cb98bb0a3ce9e08bfe5230eb4232ef5bdad"
    ),
    "vectors/spectator-v1/README.md": (
        "c1fe3b11242dc3175517fc6ed9aa68dd90d1ca3f58e54405ae9e3a0ac54fdc99"
    ),
    "vectors/spectator-v1/cases.json": (
        "b4860baee481971c938fd02d4880b435a1b7963638e5ca87b51016999b2e6bf0"
    ),
}
#: The new schema, pinned the same way as the common schemas of `protocol/v1/`.
V2_SCHEMA_SHA256 = "c62c313e72bee3878391ec4dc1b1b1dbd3f6f965a7b532838b0da09ff0e1feb8"

#: Every file this change adds, which the repository check must declare.
NEW_FILES = (
    "protocol/v1/spectator-answer-v2.schema.json",
    "protocol/v1/spectator-v2.md",
    "vectors/spectator-v2/README.md",
    "vectors/spectator-v2/cases.json",
    "ci/spectator_v2.py",
    "ci/test_spectator_v2.py",
)

#: The scenario's steps, in order. Capabilities are issued first, so every read is inside its
#: capability's 300 seconds, and the provider's clock never goes back.
STEP_NAMES = [
    "issue-a-capability",
    "issue-for-the-opening",
    "issue-for-a-seat-that-has-not-bound",
    "issue-for-an-ended-match",
    "issue-for-an-unstarted-chess-match",
    "issue-for-a-chess-match",
    "issue-for-an-aborted-match",
    "issue-for-a-streamed-chess-match",
    "the-v2-snapshot",
    "the-v2-events-after-3",
    "the-same-read-without-answer-is-the-v1-answer",
    "a-later-poll-keeps-the-deadline",
    "a-deadline-that-is-now",
    "a-deadline-one-second-ago",
    "the-opening-without-answer-is-the-published-v1-answer",
    "a-v2-read-from-the-observer",
    "a-preflight-for-the-v2-read",
    "a-write-to-the-v2-path",
    "the-v2-path-without-a-capability",
    "an-unstarted-match",
    "an-ended-match",
    "a-seat-that-has-not-bound",
    "a-chess-match-right-after-a-move",
    "an-active-chess-match",
    "an-aborted-match",
]

#: What `D-175` fixes for each named read, written out here so that the vector is checked against
#: numbers it did not choose: game version, status, `server_time`, `turn_deadline_at` and
#: `match_deadline_at`. T is 12:00:00. A Connect Four turn that began at 11:59:42 ends at T+42 s;
#: the Chess match began at 11:45:28 and its limit, 50 minutes later, is 34 minutes 18 seconds
#: after the read at 12:01:10.
DEADLINES: dict[str, tuple[str, str, str, str | None, str | None]] = {
    "the-v2-snapshot": (
        "connect-four-1",
        "active",
        "2026-10-08T12:00:00Z",
        "2026-10-08T12:00:42Z",
        None,
    ),
    "the-v2-events-after-3": (
        "connect-four-1",
        "active",
        "2026-10-08T12:00:01Z",
        "2026-10-08T12:00:42Z",
        None,
    ),
    "a-later-poll-keeps-the-deadline": (
        "connect-four-1",
        "active",
        "2026-10-08T12:00:20Z",
        "2026-10-08T12:00:42Z",
        None,
    ),
    "a-deadline-that-is-now": (
        "connect-four-1",
        "active",
        "2026-10-08T12:00:42Z",
        "2026-10-08T12:00:42Z",
        None,
    ),
    "a-deadline-one-second-ago": (
        "connect-four-1",
        "active",
        "2026-10-08T12:00:43Z",
        "2026-10-08T12:00:42Z",
        None,
    ),
    "a-v2-read-from-the-observer": (
        "connect-four-1",
        "active",
        "2026-10-08T12:00:45Z",
        "2026-10-08T12:01:00Z",
        None,
    ),
    "an-unstarted-match": (
        "chess-1",
        "awaiting_seats",
        "2026-10-08T12:00:47Z",
        None,
        None,
    ),
    "an-ended-match": (
        "connect-four-1",
        "ended",
        "2026-10-08T12:00:48Z",
        None,
        None,
    ),
    "a-seat-that-has-not-bound": (
        "connect-four-1",
        "active",
        "2026-10-08T12:00:49Z",
        None,
        None,
    ),
    "a-chess-match-right-after-a-move": (
        "chess-1",
        "active",
        "2026-10-08T12:00:50Z",
        "2026-10-08T12:01:50Z",
        "2026-10-08T12:35:28Z",
    ),
    "an-active-chess-match": (
        "chess-1",
        "active",
        "2026-10-08T12:01:10Z",
        "2026-10-08T12:01:50Z",
        "2026-10-08T12:35:28Z",
    ),
    "an-aborted-match": (
        "chess-1",
        "aborted",
        "2026-10-08T12:01:20Z",
        None,
        None,
    ),
}

#: Every answer the vector refuses, and the layer that refuses it: the schema, or a rule of the
#: reference check that the schema cannot say (the layer, and the rule's name).
REFUSED: dict[str, tuple[str, str | None]] = {
    "no-timing": ("schema", None),
    "timing-is-null": ("schema", None),
    "timing-without-server-time": ("schema", None),
    "timing-without-turn-deadline-at": ("schema", None),
    "timing-without-match-deadline-at": ("schema", None),
    "timing-with-an-extra-member": ("schema", None),
    "timing-with-the-capability-expiry": ("schema", None),
    "an-extra-member-next-to-timing": ("schema", None),
    "server-time-with-a-space-for-the-t": ("schema", None),
    "server-time-with-an-offset": ("schema", None),
    "server-time-with-a-fraction": ("schema", None),
    "server-time-in-lower-case-z": ("schema", None),
    "server-time-as-a-number": ("schema", None),
    "server-time-empty": ("schema", None),
    "turn-deadline-with-a-fraction": ("schema", None),
    "turn-deadline-as-a-number": ("schema", None),
    "match-deadline-with-an-offset": ("schema", None),
    "match-deadline-empty": ("schema", None),
    "ended-keeps-a-turn-deadline": ("schema", None),
    "ended-keeps-a-match-deadline": ("schema", None),
    "aborted-keeps-a-turn-deadline": ("schema", None),
    "aborted-keeps-a-match-deadline": ("schema", None),
    "awaiting-seats-keeps-a-turn-deadline": ("schema", None),
    "awaiting-seats-keeps-a-match-deadline": ("schema", None),
    "connect-four-with-a-match-deadline": ("schema", None),
    "connect-four-solo-with-a-match-deadline": ("schema", None),
    "a-turn-deadline-61-seconds-ahead": ("reference", "turn-deadline-too-far"),
    "the-two-deadlines-swapped": ("reference", "turn-deadline-too-far"),
    "a-match-deadline-3001-seconds-ahead": ("reference", "match-deadline-too-far"),
    "an-active-chess-match-without-a-match-deadline": (
        "reference",
        "chess-needs-a-match-deadline",
    ),
    "a-timestamp-that-is-no-instant": ("reference", "not-an-instant"),
    "a-view-that-is-not-the-games": ("reference", "view-refused"),
}

#: The two streams: each frame's events so far and the status it shows, and the exact timing each
#: carries: `server_time`, `turn_deadline_at`, `match_deadline_at`. A new accepted move starts a
#: fresh 60 seconds; the Chess limit stays where it was; the last frame has no deadline.
STREAMS: dict[str, list[tuple[int, str, tuple[str, str | None, str | None]]]] = {
    "a-connect-four-match-to-its-end": [
        (5, "active", ("2026-10-08T12:00:00Z", "2026-10-08T12:00:42Z", None)),
        (6, "active", ("2026-10-08T12:00:21Z", "2026-10-08T12:01:21Z", None)),
        (7, "ended", ("2026-10-08T12:00:38Z", None, None)),
    ],
    "a-chess-match-to-its-end": [
        (
            3,
            "active",
            ("2026-10-08T12:01:10Z", "2026-10-08T12:01:50Z", "2026-10-08T12:35:28Z"),
        ),
        (
            4,
            "active",
            ("2026-10-08T12:01:30Z", "2026-10-08T12:02:30Z", "2026-10-08T12:35:28Z"),
        ),
        (
            5,
            "active",
            ("2026-10-08T12:01:45Z", "2026-10-08T12:02:45Z", "2026-10-08T12:35:28Z"),
        ),
        (
            7,
            "active",
            ("2026-10-08T12:02:10Z", "2026-10-08T12:03:10Z", "2026-10-08T12:35:28Z"),
        ),
        (8, "ended", ("2026-10-08T12:02:30Z", None, None)),
    ],
}

#: How a viewer asks over HTTP: the query, what the reference check answers, and the query the
#: version 1 reference check sees once `answer=2` is taken away.
HTTP_FORMS: dict[str, tuple[str, str, str]] = {
    "answer-2": ("?answer=2", "v2", ""),
    "after-3-and-answer-2": ("?after=3&answer=2", "v2", "?after=3"),
    "no-query": ("", "v1", ""),
    "after-3": ("?after=3", "v1", "?after=3"),
    "answer-1": ("?answer=1", "refused", "?answer=1"),
    "answer-02": ("?answer=02", "refused", "?answer=02"),
    "answer-2-before-after": ("?answer=2&after=3", "refused", "?answer=2&after=3"),
    "answer-2-twice": ("?answer=2&answer=2", "refused", "?answer=2&answer=2"),
    "after-3-and-answer-2-twice": (
        "?after=3&answer=2&answer=2",
        "refused",
        "?after=3&answer=2&answer=2",
    ),
    "an-empty-answer": ("?answer=", "refused", "?answer="),
    "an-unknown-parameter": ("?x=1", "refused", "?x=1"),
    "answer-2-and-an-unknown-parameter": (
        "?after=3&answer=2&x=1",
        "refused",
        "?after=3&answer=2&x=1",
    ),
}

#: How a viewer asks over a stream: the offer (`v1`, `v2` and `cap` stand for the two subprotocols
#: and the capability), the versions the provider implements, and the subprotocol it selects, or
#: `None` when it refuses before the stream opens.
OFFERS: dict[str, tuple[tuple[str, ...], tuple[int, ...], str | None]] = {
    "v2-offer-to-a-provider-with-both": (("v2", "cap"), (1, 2), "v2"),
    "v1-offer-to-a-provider-with-both": (("v1", "cap"), (1, 2), "v1"),
    "v2-offer-to-a-v1-only-provider": (("v2", "cap"), (1,), None),
    "v1-offer-to-a-v1-only-provider": (("v1", "cap"), (1,), "v1"),
    "v2-without-the-capability": (("v2",), (1, 2), None),
    "the-capability-before-v2": (("cap", "v2"), (1, 2), None),
    "v2-v1-and-the-capability": (("v2", "v1", "cap"), (1, 2), None),
    "v1-without-the-capability": (("v1",), (1, 2), None),
    "v1-and-v2": (("v1", "v2"), (1, 2), None),
}

#: What a provider that implements only version 1 may do with `answer=2`: answer with the plain
#: version 1 answer (it ignores the parameter), or refuse as it refuses any query it does not know.
V1_ONLY = (
    "answer-2-to-a-provider-that-implements-only-version-1",
    "after-3-and-answer-2-to-a-provider-that-implements-only-version-1",
)

#: Forms a timestamp must not take. Each is tried in every member.
MALFORMED = {
    "a-space-for-the-t": "2026-10-08 12:00:00Z",
    "an-offset": "2026-10-08T12:00:00+00:00",
    "a-fraction": "2026-10-08T12:00:00.5Z",
    "a-lower-case-z": "2026-10-08T12:00:00z",
    "a-number": 1759924800,
    "an-empty-string": "",
    "a-trailing-line-feed": "2026-10-08T12:00:00Z\n",
    "no-z": "2026-10-08T12:00:00",
    "a-date-only": "2026-10-08",
}
MEMBERS = ("server_time", "turn_deadline_at", "match_deadline_at")


def missing(path: Path) -> None:
    """Fail with the one sentence a missing file deserves."""
    pytest.fail(
        f"{path.relative_to(ROOT).as_posix()} does not exist yet", pytrace=False
    )


def load(path: Path) -> Any:
    if not path.is_file():
        missing(path)
    return json.loads(path.read_text(encoding="utf-8"))


def reference() -> ModuleType:
    """The reference check of version 2, `ci/spectator_v2.py`."""
    try:
        return importlib.import_module("spectator_v2")
    except ModuleNotFoundError as error:
        if error.name != "spectator_v2":
            raise
        pytest.fail("ci/spectator_v2.py does not exist yet", pytrace=False)


@cache
def vector() -> dict[str, Any]:
    """The vector; a test that changes anything in it changes a copy."""
    return load(VECTOR)


def steps() -> list[dict[str, Any]]:
    return vector()["steps"]


def step(name: str) -> dict[str, Any]:
    found = [s for s in steps() if s["name"] == name]
    if len(found) != 1:
        pytest.fail(f"the vector has no single step {name}", pytrace=False)
    return found[0]


def compact(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"))


def canonical_sha256(value: Any) -> str:
    text = json.dumps(value, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def raw_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def moment(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)


def stamp(value: datetime) -> str:
    return value.strftime("%Y-%m-%dT%H:%M:%SZ")


def new_provider(cls: str = "WatchV2") -> Any:
    data = vector()
    provider = getattr(reference(), cls)(data["matches"], PROTOCOL, GAMES)
    provider.watch_origins = tuple(data["watch_origins"])
    return provider


def send(provider: Any, one: dict[str, Any]) -> tuple[int, Any]:
    request = one["request"]
    return provider.handle(
        request["method"],
        request["path"],
        request["headers"],
        request["body"].encode("utf-8"),
        one["now"],
        one.get("issues"),
        one.get("facts"),
    )


@cache
def replayed() -> tuple[Any, tuple[tuple[int, Any], ...]]:
    """The provider after the whole scenario, and what it answered each step."""
    provider = new_provider()
    return provider, tuple(send(provider, one) for one in steps())


def v1_provider() -> Watch:
    """The version 1 reference check, unchanged, serving the same matches and capabilities."""
    watch = Watch(vector()["matches"], PROTOCOL, GAMES)
    watch.watch_origins = tuple(vector()["watch_origins"])
    watch.capabilities = dict(replayed()[0].capabilities)
    return watch


def without_answer(path: str) -> str:
    return path.replace("&answer=2", "").replace("?answer=2", "")


def v2_reads() -> list[dict[str, Any]]:
    """Every step answered 200 with a version 2 answer."""
    return [
        s
        for s in steps()
        if s["expected"]["status"] == 200 and s["request"]["path"].endswith("answer=2")
    ]


def stream_case(name: str) -> dict[str, Any]:
    found = [s for s in vector().get("streams", []) if s["name"] == name]
    if len(found) != 1:
        pytest.fail(f"the vector has no single stream {name}", pytrace=False)
    return found[0]


def frame_bodies() -> list[dict[str, Any]]:
    return [f["expected"] for s in vector()["streams"] for f in s["frames"]]


def every_v2_body() -> list[tuple[str, dict[str, Any]]]:
    found = [(s["name"], s["expected"]["body"]) for s in v2_reads()]
    for stream in vector()["streams"]:
        for index, frame in enumerate(stream["frames"]):
            found.append((f"{stream['name']}/{index}", frame["expected"]))
    return found


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


def objects(schema: Any) -> list[dict[str, Any]]:
    """Every subschema that says `type: object`."""
    found = []
    if isinstance(schema, dict):
        if schema.get("type") == "object":
            found.append(schema)
        for value in schema.values():
            found.extend(objects(value))
    elif isinstance(schema, list):
        for value in schema:
            found.extend(objects(value))
    return found


# The version 1 files stay as published, and the new schema is the one pinned.


@pytest.mark.parametrize("relative", sorted(V1_CANONICAL_SHA256))
def test_a_version_1_schema_is_as_published(relative: str) -> None:
    assert canonical_sha256(load(ROOT / relative)) == V1_CANONICAL_SHA256[relative]


@pytest.mark.parametrize("relative", sorted(V1_RAW_SHA256))
def test_a_version_1_text_or_vector_is_as_published(relative: str) -> None:
    assert raw_sha256(ROOT / relative) == V1_RAW_SHA256[relative]


def test_the_version_2_schema_is_the_pinned_one() -> None:
    assert canonical_sha256(load(V2_SCHEMA)) == V2_SCHEMA_SHA256


# The schema.


def test_the_schema_is_strict_2020_12_in_keywords_the_check_knows() -> None:
    schema = load(V2_SCHEMA)
    assert schema["$schema"] == DIALECT
    assert schema["additionalProperties"] is False
    assert unknown_keywords(schema) == []


def test_the_schema_is_the_version_1_schema_and_timing() -> None:
    v1, v2 = load(V1_SCHEMA), load(V2_SCHEMA)
    assert v2["type"] == v1["type"] == "object"
    assert v2["required"] == [*v1["required"], "timing"]
    assert list(v2["properties"]) == [*v1["properties"], "timing"]
    for name, definition in v1["properties"].items():
        assert v2["properties"][name] == definition, name
    assert v2["$defs"]["game_view"] == v1["$defs"]["game_view"]
    assert v2["properties"]["timing"] == {"$ref": "#/$defs/timing"}


def test_every_string_is_an_enum_or_a_fixed_pattern() -> None:
    """`D-123`: no URL, asset, markup or free-form text reaches the browser."""
    found = strings(load(V2_SCHEMA))
    assert found
    for subschema in found:
        assert "pattern" in subschema or "enum" in subschema, subschema


def test_every_object_is_closed_but_the_game_view() -> None:
    schema = load(V2_SCHEMA)
    for subschema in objects(schema):
        if subschema is schema["$defs"]["game_view"]:
            continue
        assert subschema.get("additionalProperties") is False, subschema


def test_an_instant_is_whole_seconds_and_a_literal_z() -> None:
    utc = load(V2_SCHEMA)["$defs"]["utc"]
    assert utc["type"] == "string"
    assert utc["pattern"] == INSTANT.pattern


def test_timing_has_three_required_members_and_room_for_nothing_else() -> None:
    schema = load(V2_SCHEMA)
    timing = schema["$defs"]["timing"]
    assert timing["required"] == list(MEMBERS)
    assert list(timing["properties"]) == list(MEMBERS)
    for name in ("turn_deadline_at", "match_deadline_at"):
        branches = timing["properties"][name]["anyOf"]
        assert branches == [{"type": "null"}, {"$ref": "#/$defs/utc"}], name
    assert timing["properties"]["server_time"]["$ref"] == "#/$defs/utc"


def test_no_member_could_carry_the_capability_or_its_expiry() -> None:
    schema = load(V2_SCHEMA)
    names = set(schema["properties"]) | set(schema["$defs"]["timing"]["properties"])
    assert names == {*load(V1_SCHEMA)["properties"], "timing", *MEMBERS}
    assert not [n for n in names if "expir" in n or "capab" in n]


def test_timing_adds_at_most_132_bytes() -> None:
    """The member, `"timing":{...}`, with all three instants set: 132 bytes (133 with its comma)."""
    instant = "2026-10-08T12:00:00Z"
    member = {"timing": dict.fromkeys(MEMBERS, instant)}
    assert len(compact(member)) - len("{}") == 132
    for name, body in every_v2_body():
        assert len(compact({"timing": body["timing"]})) - len("{}") <= 132, name


# The vector holds what the decision requires.


def test_the_vector_is_made_of_the_steps_the_decision_requires() -> None:
    assert [s["name"] for s in steps()] == STEP_NAMES
    assert vector()["decisions"] == ["D-175"]
    assert set(vector()) >= {
        "matches",
        "steps",
        "refused_answers",
        "streams",
        "negotiation",
        "test_capabilities",
        "watch_origins",
    }


@pytest.mark.parametrize("name", STEP_NAMES)
def test_each_step_gets_its_published_answer(name: str) -> None:
    index = STEP_NAMES.index(name)
    expected = step(name)["expected"]
    assert replayed()[1][index] == (expected["status"], expected["body"])


@pytest.mark.parametrize("name", sorted(DEADLINES))
def test_each_named_read_has_its_exact_timing(name: str) -> None:
    game, status, server, turn, match = DEADLINES[name]
    body = step(name)["expected"]["body"]
    assert (body["game_version"], body["status"]) == (game, status)
    assert body["timing"] == {
        "server_time": server,
        "turn_deadline_at": turn,
        "match_deadline_at": match,
    }
    assert step(name)["now"] == server


def test_the_deadlines_are_the_numbers_of_the_decision() -> None:
    """Computed here with `timedelta`, not read from the vector: 42 s, 60 s, 0, -1 s, 34:18."""

    def ahead(name: str, member: str) -> timedelta:
        timing = step(name)["expected"]["body"]["timing"]
        return moment(timing[member]) - moment(timing["server_time"])

    assert ahead("the-v2-snapshot", "turn_deadline_at") == timedelta(seconds=42)
    assert ahead("a-chess-match-right-after-a-move", "turn_deadline_at") == timedelta(
        seconds=60
    )
    assert ahead("a-deadline-that-is-now", "turn_deadline_at") == timedelta(0)
    assert ahead("a-deadline-one-second-ago", "turn_deadline_at") == timedelta(
        seconds=-1
    )
    assert ahead("an-active-chess-match", "turn_deadline_at") == timedelta(seconds=40)
    assert ahead("an-active-chess-match", "match_deadline_at") == timedelta(
        minutes=34, seconds=18
    )


def test_a_poll_never_moves_the_deadline() -> None:
    """The deadline is the stored turn start plus 60 seconds, however often it is read."""
    deadlines = {
        step(name)["expected"]["body"]["timing"]["turn_deadline_at"]
        for name in (
            "the-v2-snapshot",
            "the-v2-events-after-3",
            "a-later-poll-keeps-the-deadline",
            "a-deadline-that-is-now",
            "a-deadline-one-second-ago",
        )
    }
    assert deadlines == {"2026-10-08T12:00:42Z"}
    chess = {
        step(name)["expected"]["body"]["timing"]["match_deadline_at"]
        for name in ("a-chess-match-right-after-a-move", "an-active-chess-match")
    }
    assert chess == {"2026-10-08T12:35:28Z"}


def test_connect_four_never_has_a_match_deadline() -> None:
    reads = [
        (n, b) for n, b in every_v2_body() if b["game_version"].startswith("connect")
    ]
    assert reads
    for name, body in reads:
        assert body["timing"]["match_deadline_at"] is None, name


def test_a_deadline_that_is_not_running_is_null_never_absent() -> None:
    for name, body in every_v2_body():
        assert set(body["timing"]) == set(MEMBERS), name
        if body["status"] != "active":
            assert body["timing"]["turn_deadline_at"] is None, name
            assert body["timing"]["match_deadline_at"] is None, name


def test_a_seat_that_is_not_bound_runs_no_timer_but_the_match_is_active() -> None:
    body = step("a-seat-that-has-not-bound")["expected"]["body"]
    facts = step("a-seat-that-has-not-bound")["facts"]
    assert body["status"] == "active"
    assert body["snapshot"]["to_move"] == "second"
    assert "second" not in facts["bound_seats"]
    assert body["timing"]["turn_deadline_at"] is None
    assert facts["turn_started_at"] is not None


def test_the_clock_facts_are_facts_a_provider_can_have() -> None:
    """A turn never starts in the future: that is why a deadline is at most 60 s ahead."""
    seen = 0
    for one in steps():
        facts = one.get("facts")
        if facts is None:
            continue
        seen += 1
        started, activated = facts["turn_started_at"], facts["activated_at"]
        if started is not None:
            assert moment(started) <= moment(one["now"]), one["name"]
        if started is not None and activated is not None:
            assert moment(activated) <= moment(started), one["name"]
    assert seen
    for stream in vector()["streams"]:
        for frame in stream["frames"]:
            facts = frame["facts"]
            assert moment(facts["activated_at"]) <= moment(facts["turn_started_at"])
            assert moment(facts["turn_started_at"]) <= moment(frame["now"])


def test_every_instant_in_the_vector_is_canonical() -> None:
    def walk(node: Any, path: str) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                walk(value, f"{path}/{key}")
        elif isinstance(node, list):
            for index, value in enumerate(node):
                walk(value, f"{path}[{index}]")
        elif isinstance(node, str) and re.search(r"(_at|_time|/now)$", path):
            assert INSTANT.fullmatch(node), (path, node)
            moment(node)

    data = vector()
    walk(data["steps"], "steps")
    walk(data["streams"], "streams")
    walk(data["negotiation"], "negotiation")
    assert INSTANT.fullmatch(data["negotiation"]["http"]["now"])
    assert INSTANT.fullmatch(data["negotiation"]["v1_only_provider"]["now"])


# Every answer the vectors show is accepted, and it is the version 1 answer plus timing.


def test_every_v2_answer_in_the_vector_is_accepted() -> None:
    ref = reference()
    seen = every_v2_body()
    assert len(seen) >= len(DEADLINES) - 1
    for name, body in seen:
        assert valid(body, load(V2_SCHEMA)), name
        assert ref.refusal(body, PROTOCOL, GAMES) is None, name
        assert ref.answer_version(body, PROTOCOL) == 2, name


def test_a_v2_answer_minus_timing_is_the_version_1_answer_byte_for_byte() -> None:
    provider = v1_provider()
    seen = 0
    for one in v2_reads():
        request = one["request"]
        status, v1 = provider.handle(
            "GET",
            without_answer(request["path"]),
            request["headers"],
            b"",
            one["now"],
        )
        body = one["expected"]["body"]
        assert status == 200 and v1 is not None, one["name"]
        stripped = {k: v for k, v in body.items() if k != "timing"}
        assert compact(stripped) == compact(v1), one["name"]
        assert list(body) == [*v1, "timing"], one["name"]
        seen += 1
    assert seen >= 10


def test_a_request_without_answer_gets_the_version_1_body_and_no_timing() -> None:
    plain = [
        s
        for s in steps()
        if s["request"]["method"] == "GET"
        and s["expected"]["status"] == 200
        and "/capability" not in s["request"]["path"]
        and "answer" not in s["request"]["path"]
    ]
    assert {s["name"] for s in plain} == {
        "the-same-read-without-answer-is-the-v1-answer",
        "the-opening-without-answer-is-the-published-v1-answer",
    }
    provider = v1_provider()
    for one in plain:
        body = one["expected"]["body"]
        assert list(body) == list(load(V1_SCHEMA)["required"]), one["name"]
        status, v1 = provider.handle(
            "GET", one["request"]["path"], one["request"]["headers"], b"", one["now"]
        )
        assert (status, compact(v1)) == (200, compact(body)), one["name"]
        assert valid(body, load(V1_SCHEMA)), one["name"]


def test_the_opening_without_answer_is_the_body_version_1_published() -> None:
    published = [
        s for s in load(V1_VECTOR)["steps"] if s["name"] == "a-read-from-the-observer"
    ]
    assert len(published) == 1
    ours = step("the-opening-without-answer-is-the-published-v1-answer")
    assert ours["request"]["path"] == published[0]["request"]["path"]
    assert compact(ours["expected"]["body"]) == compact(
        published[0]["expected"]["body"]
    )


def test_each_snapshot_and_event_view_is_the_games() -> None:
    ref = reference()
    for name, body in every_v2_body():
        assert ref.views_valid(body, GAMES), name


def test_every_answer_is_within_the_version_1_size_bound() -> None:
    """An answer is at most 1024 bytes plus 17 times the game's observation bound."""
    for name, body in every_v2_body():
        family = "chess" if body["game_version"].startswith("chess") else "connect-four"
        observation = load(
            GAMES / family / body["game_version"] / "observation.schema.json"
        )
        limit = 1024 + 17 * observation["x-agentnexus-max-bytes"]
        assert len(compact(body).encode()) <= limit, name


def test_an_answer_over_the_version_1_size_bound_is_refused() -> None:
    ref = reference()
    body = copy.deepcopy(step("the-v2-snapshot")["expected"]["body"])
    assert ref.refusal(body, PROTOCOL, GAMES) is None
    body["snapshot"]["padding"] = "x" * (1024 + 17 * 2048)
    assert ref.refusal(body, PROTOCOL, GAMES) == ("reference", "answer-too-large")


# Every answer the vector refuses is refused by the layer that is named.


def refused_case(name: str) -> dict[str, Any]:
    found = [c for c in vector()["refused_answers"] if c["name"] == name]
    if len(found) != 1:
        pytest.fail(f"the vector has no single refused answer {name}", pytrace=False)
    return found[0]


def test_the_vector_refuses_exactly_the_answers_the_decision_names() -> None:
    names = [c["name"] for c in vector()["refused_answers"]]
    assert len(names) == len(set(names))
    assert set(names) == set(REFUSED)


@pytest.mark.parametrize("name", sorted(REFUSED))
def test_each_refused_answer_is_refused_by_its_layer(name: str) -> None:
    layer, rule = REFUSED[name]
    case = refused_case(name)
    assert (case["layer"], case.get("rule")) == (layer, rule)
    assert case["because"]
    schema = load(V2_SCHEMA)
    # The schema refuses it, or the schema accepts it and the reference check refuses it.
    assert valid(case["answer"], schema) is (layer == "reference")
    assert reference().refusal(case["answer"], PROTOCOL, GAMES) == (layer, rule)


@pytest.mark.parametrize(
    "name", sorted(set(REFUSED) - {"a-view-that-is-not-the-games"})
)
def test_a_refused_answer_is_at_fault_only_where_it_says(name: str) -> None:
    """Its views are the game's, so the one thing wrong with it is the one thing it names."""
    assert reference().views_valid(refused_case(name)["answer"], GAMES)


@pytest.mark.parametrize("member", MEMBERS)
@pytest.mark.parametrize("form", sorted(MALFORMED))
def test_a_malformed_timestamp_is_refused_in_every_member(
    member: str, form: str
) -> None:
    answer = copy.deepcopy(step("an-active-chess-match")["expected"]["body"])
    assert reference().refusal(answer, PROTOCOL, GAMES) is None
    answer["timing"][member] = MALFORMED[form]
    assert not valid(answer, load(V2_SCHEMA))
    assert reference().refusal(answer, PROTOCOL, GAMES) == ("schema", None)


@pytest.mark.parametrize("member", MEMBERS)
@pytest.mark.parametrize("value", ["2026-13-45T25:61:61Z", "2026-02-30T12:00:00Z"])
def test_a_shape_that_is_no_instant_passes_the_schema_and_not_the_check(
    member: str, value: str
) -> None:
    answer = copy.deepcopy(step("an-active-chess-match")["expected"]["body"])
    answer["timing"][member] = value
    assert valid(answer, load(V2_SCHEMA))
    assert reference().refusal(answer, PROTOCOL, GAMES) == (
        "reference",
        "not-an-instant",
    )


@pytest.mark.parametrize(
    ("member", "seconds", "rule"),
    [
        ("turn_deadline_at", 60, None),
        ("turn_deadline_at", 61, "turn-deadline-too-far"),
        ("turn_deadline_at", 3000, "turn-deadline-too-far"),
        ("match_deadline_at", 3000, None),
        ("match_deadline_at", 3001, "match-deadline-too-far"),
        ("turn_deadline_at", 0, None),
        ("turn_deadline_at", -1, None),
        ("turn_deadline_at", -5, None),
        ("match_deadline_at", 0, None),
        ("match_deadline_at", -1, None),
    ],
)
def test_the_bounds_are_an_upper_bound_only(
    member: str, seconds: int, rule: str | None
) -> None:
    """60 s and 50 minutes ahead are the most a provider can have; a passed deadline is valid."""
    answer = copy.deepcopy(step("a-chess-match-right-after-a-move")["expected"]["body"])
    server = moment(answer["timing"]["server_time"])
    answer["timing"][member] = stamp(server + timedelta(seconds=seconds))
    found = reference().refusal(answer, PROTOCOL, GAMES)
    assert found == (None if rule is None else ("reference", rule))


def test_a_chess_match_is_only_active_with_its_limit_running() -> None:
    answer = copy.deepcopy(step("an-active-chess-match")["expected"]["body"])
    answer["timing"]["match_deadline_at"] = None
    assert reference().refusal(answer, PROTOCOL, GAMES) == (
        "reference",
        "chess-needs-a-match-deadline",
    )
    answer["status"] = "ended"
    answer["timing"]["turn_deadline_at"] = None
    assert reference().refusal(answer, PROTOCOL, GAMES) is None


def test_more_than_16_events_is_refused() -> None:
    answer = copy.deepcopy(step("the-v2-events-after-3")["expected"]["body"])
    answer["events"] = [copy.deepcopy(answer["events"][0]) for _ in range(17)]
    assert reference().refusal(answer, PROTOCOL, GAMES) == ("schema", None)


def test_facts_a_provider_cannot_have_are_refused() -> None:
    """A turn that starts after `server_time` would end more than 60 seconds ahead of it."""
    ref = reference()
    one = copy.deepcopy(step("the-v2-snapshot"))
    one["facts"]["turn_started_at"] = "2026-10-08T12:00:01Z"
    provider = new_provider()
    send(provider, steps()[0])
    with pytest.raises(ref.Refused) as refused:
        send(provider, one)
    assert (refused.value.layer, refused.value.rule) == (
        "reference",
        "turn-deadline-too-far",
    )
    # The same facts one second earlier are a turn that began in the past, and are accepted.
    one["facts"]["turn_started_at"] = "2026-10-08T11:59:59Z"
    assert send(provider, one)[0] == 200


# The capability is separate from the clock.


def test_each_test_capability_is_what_its_published_phrase_produces() -> None:
    entries = vector()["test_capabilities"]
    assert len(entries) >= 8
    for entry in entries:
        assert re.fullmatch(
            r"agentnexus-watch-v2 published test capability [0-9]+(, never issued)?"
            r", valid nowhere",
            entry["is_sha256_of"],
        )
        digest = hashlib.sha256(entry["is_sha256_of"].encode("utf-8")).digest()
        token = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
        assert token == entry["capability"]


def test_a_capability_lives_at_most_300_seconds() -> None:
    issued = [s for s in steps() if s.get("issues")]
    assert len(issued) == 8
    for one in issued:
        lifetime = moment(one["issues"]["expires_at"]) - moment(one["now"])
        assert timedelta(0) < lifetime <= timedelta(seconds=LIFETIME), one["name"]


def test_the_capability_expiry_is_never_a_timing_member() -> None:
    """Neither in the published answers nor in what the reference check builds."""
    provider, answers = replayed()
    checked = 0
    for one, (status, body) in zip(steps(), answers, strict=True):
        if "answer=2" not in one["request"]["path"] or status != 200:
            continue
        held = provider.capabilities[one["request"]["headers"][HEADER]]
        expiry = stamp(held[1])
        for answer in (body, one["expected"]["body"]):
            assert expiry not in answer["timing"].values(), one["name"]
        checked += 1
    assert checked >= 10
    expiries = {s["issues"]["expires_at"] for s in steps() if s.get("issues")}
    instants = {v for _, body in every_v2_body() for v in body["timing"].values()}
    assert len(expiries) == 8
    assert not expiries & instants


def test_the_cross_origin_headers_of_the_v2_path_are_version_1s() -> None:
    """No request header names the version, so the one preflight header stays the only one."""
    provider = replayed()[0]
    stated = [s for s in steps() if "cors" in s["expected"]]
    assert {s["name"] for s in stated} == {
        "a-v2-read-from-the-observer",
        "a-preflight-for-the-v2-read",
    }
    for one in stated:
        request = one["request"]
        assert (
            provider.cross_origin(
                request["method"], request["path"], request["headers"]
            )
            == one["expected"]["cors"]
        ), one["name"]
        assert "answer=2" in request["path"]
    preflight = step("a-preflight-for-the-v2-read")
    assert preflight["expected"]["status"] == 204
    assert preflight["expected"]["cors"] == {
        "Access-Control-Allow-Origin": ORIGIN,
        "Access-Control-Allow-Methods": "GET",
        "Access-Control-Allow-Headers": HEADER,
    }
    for cors in (s["expected"]["cors"] for s in stated):
        assert "Access-Control-Allow-Credentials" not in cors


def test_a_write_to_the_v2_path_is_read_only_before_the_capability_is_looked_at() -> (
    None
):
    write = step("a-write-to-the-v2-path")
    assert write["request"]["method"] != "GET"
    assert write["expected"] == {
        "status": 405,
        "body": {"error": {"code": "read_only"}},
    }
    bare = step("the-v2-path-without-a-capability")
    assert HEADER not in bare["request"]["headers"]
    assert bare["expected"] == {
        "status": 401,
        "body": {"error": {"code": "unauthenticated"}},
    }
    provider = replayed()[0]
    path = bare["request"]["path"]
    assert provider.handle("DELETE", path, {}, b"", bare["now"]) == (
        405,
        {"error": {"code": "read_only"}},
    )


# The streams.


@pytest.mark.parametrize("name", sorted(STREAMS))
def test_each_stream_is_the_frames_the_decision_requires(name: str) -> None:
    stream = stream_case(name)
    shape = [(f["through"], f["status"]) for f in stream["frames"]]
    assert shape == [(through, status) for through, status, _ in STREAMS[name]]
    assert stream["offered"][0] == V2_STREAM
    assert stream["selects"] == V2_STREAM
    held = {s["issues"]["capability"] for s in steps() if s.get("issues")}
    assert stream["offered"][1] in held


@pytest.mark.parametrize("name", sorted(STREAMS))
def test_each_frame_is_what_the_provider_builds(name: str) -> None:
    stream = stream_case(name)
    match = vector()["matches"][stream["match_id"]]
    specs = [
        {key: frame[key] for key in ("now", "through", "status", "facts")}
        for frame in stream["frames"]
    ]
    built = reference().frames(stream["match_id"], match, specs, PROTOCOL, GAMES)
    assert built == [frame["expected"] for frame in stream["frames"]]


@pytest.mark.parametrize("name", sorted(STREAMS))
def test_each_frame_has_the_exact_timing_of_the_decision(name: str) -> None:
    stream = stream_case(name)
    for frame, (_, status, timing) in zip(stream["frames"], STREAMS[name], strict=True):
        body = frame["expected"]
        assert body["status"] == status
        assert body["timing"] == dict(zip(MEMBERS, timing, strict=True))
        assert frame["now"] == timing[0]
    for index, (_, _, timing) in enumerate(STREAMS[name]):
        turn = timing[1]
        if turn is not None:
            started = moment(stream["frames"][index]["facts"]["turn_started_at"])
            assert moment(turn) - started == timedelta(seconds=60)


@pytest.mark.parametrize("name", sorted(STREAMS))
def test_the_first_frame_is_the_snapshot_at_that_instant(name: str) -> None:
    ref = reference()
    stream = stream_case(name)
    first = stream["frames"][0]
    match = vector()["matches"][stream["match_id"]]
    provider = ref.WatchV2(
        {stream["match_id"]: ref.state_at(match, first["through"], first["status"])},
        PROTOCOL,
        GAMES,
    )
    token = vector()["test_capabilities"][0]["capability"]
    provider.capabilities[token] = (stream["match_id"], moment(first["now"]))
    status, snapshot = provider.handle(
        "GET",
        f"/agentnexus-games/v1/matches/{stream['match_id']}/spectator?answer=2",
        {HEADER: token},
        b"",
        first["now"],
        None,
        first["facts"],
    )
    assert status == 200
    assert first["expected"]["events"] == []
    assert first["expected"] == snapshot
    assert (
        ref.stream_refusal([f["expected"] for f in stream["frames"]], snapshot) is None
    )
    # The first frame the stream builds is that snapshot too.
    specs = [
        {key: frame[key] for key in ("now", "through", "status", "facts")}
        for frame in stream["frames"]
    ]
    built = ref.frames(stream["match_id"], match, specs, PROTOCOL, GAMES)
    assert built[0] == snapshot


@pytest.mark.parametrize("name", sorted(STREAMS))
def test_a_stream_frame_is_the_version_1_answer_since_the_frame_before_and_timing(
    name: str,
) -> None:
    ref = reference()
    stream = stream_case(name)
    match = vector()["matches"][stream["match_id"]]
    sent = None
    for index, frame in enumerate(stream["frames"]):
        watch = Watch(
            {
                stream["match_id"]: ref.state_at(
                    match, frame["through"], frame["status"]
                )
            },
            PROTOCOL,
            GAMES,
        )
        token = vector()["test_capabilities"][0]["capability"]
        watch.capabilities[token] = (stream["match_id"], moment(frame["now"]))
        after = "" if sent is None else f"?after={sent}"
        _, v1 = watch.handle(
            "GET",
            f"/agentnexus-games/v1/matches/{stream['match_id']}/spectator{after}",
            {HEADER: token},
            b"",
            frame["now"],
        )
        body = frame["expected"]
        stripped = {k: v for k, v in body.items() if k != "timing"}
        assert compact(stripped) == compact(v1), (name, index)
        sent = frame["through"]


@pytest.mark.parametrize("name", sorted(STREAMS))
def test_every_frame_after_the_first_carries_one_to_16_events(name: str) -> None:
    """`D-161`'s rule, unchanged: a frame is built for an event; no frame is without one."""
    frames = stream_case(name)["frames"]
    bodies = [f["expected"] for f in frames]
    assert bodies[0]["events"] == []
    sent = frames[0]["through"]
    for frame, body in zip(frames[1:], bodies[1:], strict=True):
        assert 1 <= len(body["events"]) <= 16
        assert [e["event_seq"] for e in body["events"]] == list(
            range(sent + 1, frame["through"] + 1)
        )
        assert body["event_seq"] == frame["through"] == body["events"][-1]["event_seq"]
        sent = frame["through"]


def test_a_frame_carries_every_event_since_the_frame_before() -> None:
    """Two events committed together reach the viewer in one frame, in order."""
    bodies = [f["expected"] for f in stream_case("a-chess-match-to-its-end")["frames"]]
    assert [len(b["events"]) for b in bodies] == [0, 1, 1, 2, 1]
    assert [e["event_seq"] for e in bodies[3]["events"]] == [6, 7]


def test_a_later_frame_without_a_new_event_is_not_built() -> None:
    """Timing without an event reaches a stream with the next frame; no frame is built for it."""
    ref = reference()
    stream = stream_case("a-connect-four-match-to-its-end")
    match = vector()["matches"][stream["match_id"]]
    first = stream["frames"][0]
    specs = [
        {key: first[key] for key in ("now", "through", "status", "facts")},
        {
            "now": "2026-10-08T12:00:10Z",
            "through": first["through"],
            "status": "active",
            "facts": first["facts"],
        },
    ]
    with pytest.raises(ValueError, match="one to 16 events"):
        ref.frames(stream["match_id"], match, specs, PROTOCOL, GAMES)


@pytest.mark.parametrize("name", sorted(STREAMS))
def test_server_time_never_goes_back_and_a_move_gives_a_fresh_deadline(
    name: str,
) -> None:
    frames = [f["expected"] for f in stream_case(name)["frames"]]
    for before, after in pairwise(frames):
        assert moment(after["timing"]["server_time"]) >= moment(
            before["timing"]["server_time"]
        )
        old, new = (
            before["timing"]["turn_deadline_at"],
            after["timing"]["turn_deadline_at"],
        )
        if after["status"] == "active":
            assert moment(new) > moment(old)
            if len(after["events"]) == 1:
                assert after["snapshot"]["to_move"] != before["snapshot"]["to_move"]
        else:
            assert new is None


@pytest.mark.parametrize("name", sorted(STREAMS))
def test_the_final_frame_shows_the_end_and_has_no_deadline(name: str) -> None:
    last = stream_case(name)["frames"][-1]["expected"]
    assert last["status"] == "ended"
    assert last["snapshot"]["to_move"] is None
    assert last["snapshot"]["result"] is not None
    assert last["timing"]["turn_deadline_at"] is None
    assert last["timing"]["match_deadline_at"] is None


def test_the_stream_rules_name_what_a_broken_stream_breaks() -> None:
    ref = reference()
    frames = [f["expected"] for f in stream_case("a-chess-match-to-its-end")["frames"]]
    assert ref.stream_refusal(frames) is None

    def refused(changed: list[dict[str, Any]], snapshot: Any = None) -> str | None:
        return ref.stream_refusal(changed, snapshot)

    other = copy.deepcopy(frames)
    other[0]["timing"]["server_time"] = "2026-10-08T12:01:11Z"
    assert refused(frames, other[0]) == "first-frame-differs-from-the-snapshot"
    with_events = copy.deepcopy(frames)
    with_events[0]["events"] = copy.deepcopy(frames[1]["events"])
    assert refused(with_events) == "first-frame-carries-events"
    assert refused([frames[0], frames[2]]) == "events-do-not-continue"
    assert refused([frames[0], frames[1], frames[1]]) == "events-do-not-continue"
    assert refused([frames[0], frames[2], frames[1]]) == "events-do-not-continue"
    quiet = copy.deepcopy(frames)
    quiet[1]["events"] = []
    assert refused(quiet) == "later-frame-event-count"
    back = copy.deepcopy(frames)
    back[2]["timing"]["server_time"] = "2026-10-08T12:01:29Z"
    assert refused(back) == "server-time-goes-back"
    same = copy.deepcopy(frames)
    same[2]["timing"]["server_time"] = frames[1]["timing"]["server_time"]
    assert refused(same) is None
    stale = copy.deepcopy(frames)
    stale[2]["timing"]["turn_deadline_at"] = frames[1]["timing"]["turn_deadline_at"]
    assert refused(stale) == "deadline-not-renewed"
    after_the_end = frames + [copy.deepcopy(frames[-1])]
    after_the_end[-1]["event_seq"] += 1
    after_the_end[-1]["events"] = [{**frames[-1]["events"][0], "event_seq": 9}]
    assert refused(after_the_end) == "frame-after-the-end"


# How a viewer asks.


def http_form(name: str) -> dict[str, Any]:
    forms = vector()["negotiation"]["http"]["requests"]
    found = [f for f in forms if f["name"] == name]
    if len(found) != 1:
        pytest.fail(f"the vector has no single form {name}", pytrace=False)
    return found[0]


def test_the_vector_shows_exactly_the_http_forms_the_decision_names() -> None:
    forms = vector()["negotiation"]["http"]["requests"]
    assert [f["name"] for f in forms] == list(HTTP_FORMS)
    for name, (query, result, _) in HTTP_FORMS.items():
        assert (http_form(name)["query"], http_form(name)["result"]) == (query, result)


@pytest.mark.parametrize("name", sorted(HTTP_FORMS))
def test_each_http_form_gets_its_published_result(name: str) -> None:
    query, result, v1_query = HTTP_FORMS[name]
    negotiation = vector()["negotiation"]["http"]
    provider = replayed()[0]
    base = f"/agentnexus-games/v1/matches/{negotiation['match_id']}/spectator"
    headers = {HEADER: negotiation["capability"]}
    got = provider.handle(
        "GET",
        base + query,
        headers,
        b"",
        negotiation["now"],
        None,
        negotiation["facts"],
    )
    v1 = v1_provider().handle("GET", base + v1_query, headers, b"", negotiation["now"])
    if result == "refused":
        assert got == (404, None)
        assert v1 == (404, None)
        return
    status, body = got
    assert status == 200
    ref = reference()
    if result == "v1":
        assert "timing" not in body
        assert compact(body) == compact(v1[1])
        assert ref.answer_version(body, PROTOCOL) == 1
    else:
        assert ref.answer_version(body, PROTOCOL) == 2
        assert compact({k: v for k, v in body.items() if k != "timing"}) == compact(
            v1[1]
        )


def test_the_subprotocol_offers_are_the_ones_the_decision_names() -> None:
    entries = vector()["negotiation"]["stream"]
    assert [e["name"] for e in entries] == list(OFFERS)
    token = vector()["test_capabilities"][0]["capability"]
    symbols = {"v1": V1_STREAM, "v2": V2_STREAM, "cap": token}
    for entry in entries:
        offer, implements, selected = OFFERS[entry["name"]]
        assert entry["offered"] == [symbols[s] for s in offer], entry["name"]
        assert entry["implements"] == list(implements), entry["name"]
        expected = None if selected is None else symbols[selected]
        assert entry["selects"] == expected, entry["name"]


@pytest.mark.parametrize("name", sorted(OFFERS))
def test_each_subprotocol_offer_gets_its_published_selection(name: str) -> None:
    entry = next(e for e in vector()["negotiation"]["stream"] if e["name"] == name)
    ref = reference()
    assert (
        ref.selected(entry["offered"], tuple(entry["implements"])) == entry["selects"]
    )


def test_the_capability_is_the_same_for_both_versions_over_both_ways() -> None:
    """One capability opens a version 1 or a version 2 stream, and reads over HTTP."""
    ref = reference()
    token = vector()["test_capabilities"][0]["capability"]
    assert ref.selected([V1_STREAM, token]) == V1_STREAM
    assert ref.selected([V2_STREAM, token]) == V2_STREAM
    assert step("issue-a-capability")["issues"]["capability"] == token


def test_a_viewer_that_is_refused_version_2_by_a_v1_only_provider_watches_with_version_1() -> (
    None
):
    ref = reference()
    token = vector()["test_capabilities"][0]["capability"]
    assert ref.selected([V2_STREAM, token], (1,)) is None
    assert ref.selected([V1_STREAM, token], (1,)) == V1_STREAM


def v1_only_case(name: str) -> dict[str, Any]:
    requests = vector()["negotiation"]["v1_only_provider"]["requests"]
    found = [c for c in requests if c["name"] == name]
    if len(found) != 1:
        pytest.fail(f"the vector has no single v1-only request {name}", pytrace=False)
    return found[0]


def test_the_vector_shows_what_a_v1_only_provider_may_do_with_answer_2() -> None:
    section = vector()["negotiation"]["v1_only_provider"]
    assert [c["name"] for c in section["requests"]] == list(V1_ONLY)
    for case in section["requests"]:
        assert "answer=2" in case["path"]
        assert set(case) >= {"name", "path", "ignoring", "refusing", "because"}


@pytest.mark.parametrize("name", V1_ONLY)
def test_a_v1_only_provider_may_ignore_answer_2_and_answer_in_version_1(
    name: str,
) -> None:
    ref = reference()
    case = v1_only_case(name)
    section = vector()["negotiation"]["v1_only_provider"]
    headers = {HEADER: section["capability"]}
    ignoring = ref.V1OnlyWatch(vector()["matches"], PROTOCOL, GAMES)
    ignoring.capabilities = dict(replayed()[0].capabilities)
    got = ignoring.handle("GET", case["path"], headers, b"", section["now"])
    assert got == (case["ignoring"]["status"], case["ignoring"]["body"])
    status, body = got
    assert status == 200
    # It is a version 1 answer, and no version 2 answer: a viewer tells them apart by schema.
    assert valid(body, load(V1_SCHEMA))
    assert not valid(body, load(V2_SCHEMA))
    assert "timing" not in body
    assert ref.answer_version(body, PROTOCOL) == 1
    # It is the answer the same request gets without `answer`: nothing else was said.
    v1 = v1_provider().handle(
        "GET", without_answer(case["path"]), headers, b"", section["now"]
    )
    assert v1 == (200, body)


@pytest.mark.parametrize("name", V1_ONLY)
def test_a_v1_only_provider_may_refuse_answer_2_as_any_query_it_does_not_know(
    name: str,
) -> None:
    case = v1_only_case(name)
    section = vector()["negotiation"]["v1_only_provider"]
    headers = {HEADER: section["capability"]}
    refusing = v1_provider()  # the version 1 reference check, unchanged
    got = refusing.handle("GET", case["path"], headers, b"", section["now"])
    assert got == (case["refusing"]["status"], case["refusing"]["body"]) == (404, None)


def test_no_answer_is_both_a_version_1_and_a_version_2_answer() -> None:
    ref = reference()
    v1, v2 = load(V1_SCHEMA), load(V2_SCHEMA)
    bodies = [b for _, b in every_v2_body()]
    for case in vector()["negotiation"]["v1_only_provider"]["requests"]:
        bodies.append(case["ignoring"]["body"])
    for one in steps():
        body = one["expected"]["body"]
        if (
            one["expected"]["status"] == 200
            and isinstance(body, dict)
            and "match_id" in body
        ):
            bodies.append(body)
    assert len(bodies) >= 30
    for body in bodies:
        assert valid(body, v1) != valid(body, v2)
        assert ref.answer_version(body, PROTOCOL) == (2 if "timing" in body else 1)
    assert ref.answer_version({"match_id": "x"}, PROTOCOL) is None


def test_a_v2_answer_is_never_produced_without_answer_2() -> None:
    provider = replayed()[0]
    for one in steps():
        request = one["request"]
        if request["method"] != "GET" or "/capability" in request["path"]:
            continue
        if "answer=2" in request["path"]:
            continue
        status, body = provider.handle(
            "GET",
            request["path"],
            request["headers"],
            b"",
            one["now"],
            None,
            one.get("facts"),
        )
        assert status in (200, 401), one["name"]
        if status == 200:
            assert "timing" not in body, one["name"]


# What this change adds is declared, run and listed.


def test_every_new_file_is_declared() -> None:
    assert set(NEW_FILES) <= DECLARED
    for relative in NEW_FILES:
        assert (ROOT / relative).is_file(), relative


def test_the_committed_tree_passes_the_repository_check() -> None:
    assert check(ROOT) == []


def test_the_workflow_runs_this_file_before_the_repository_check() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    runs = "python -m pytest ci/test_spectator_v2.py -q"
    assert text.count(runs) == 1
    assert text.index(runs) < text.index("python ci/check_repository.py")
    assert text.index("python -m pytest ci/test_spectator.py -q") < text.index(runs)


def test_the_root_readme_lists_the_version_2_text_in_one_line() -> None:
    """The root README is not vendored: one line points to the new text, which links the rest."""
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    lines = [line for line in text.splitlines() if "spectator-v2" in line]
    assert len(lines) == 1
    assert lines[0].startswith(
        "- [`protocol/v1/spectator-v2.md`](protocol/v1/spectator-v2.md)"
    )


def test_the_prose_states_how_to_ask_and_what_a_v1_only_provider_may_do() -> None:
    if not V2_PROSE.is_file():
        missing(V2_PROSE)
    text = " ".join(V2_PROSE.read_text(encoding="utf-8").split())
    for phrase in (
        "?answer=2",
        "?after=<n>&answer=2",
        V2_STREAM,
        "spectator-answer-v2.schema.json",
        "`server_time`",
        "`turn_deadline_at`",
        "`match_deadline_at`",
        "may ignore",
        "An answer without `timing` is a version 1 answer",
        "as current as its last event",
        "an HTTP read shows it at once",
        "at most 132 bytes",
        "merging a change here publishes nothing",
    ):
        assert phrase in text, phrase


def test_the_vector_readme_says_the_same() -> None:
    if not VECTOR_README.is_file():
        missing(VECTOR_README)
    text = " ".join(VECTOR_README.read_text(encoding="utf-8").split())
    for phrase in (
        "Test material",
        "valid nowhere",
        "D-175",
        "may ignore",
        "is not a valid version 2 answer",
        "as current as its last event",
        "ci/spectator_v2.py",
    ):
        assert phrase in text, phrase
