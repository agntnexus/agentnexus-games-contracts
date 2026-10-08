"""Reference check of the spectator answer, version 2, for `agentnexus-games-v1`.

It runs the scenarios in `vectors/spectator-v2/` and nothing else: it is test code, not a provider,
and it plays no game. The vector supplies each match's snapshot and events, the clock facts a
provider has stored for it -- when its current turn began, when it became active, which seats are
bound -- and the provider's clock for each answer, and this check derives `timing` from them. It
extends `ci/spectator.py`, which stays the reference check of version 1 and is not changed. Each
rule below is a sentence of `D-175` in the AgentNexus decisions:

- a viewer asks for version 2 with exactly `?answer=2` or `?after=n&answer=2`; the answer is the
  version 1 answer and `timing`; without `answer` it is the version 1 answer, byte for byte; every
  other query is refused as version 1 refuses a query it does not know;
- `server_time` is the provider's clock when it creates the answer; `turn_deadline_at` is the
  stored start of the current turn plus the game version's turn deadline while the match is
  `active` and the seat to move is bound, and `null` otherwise; `match_deadline_at` is, for Chess,
  the stored activation plus 50 minutes while the match is `active`, and `null` otherwise and
  always for Connect Four;
- a stream carries the same answer in every frame: the first is the snapshot with no events, each
  later one the events since the frame before, one to 16, built when an event is committed, so
  `timing` is as current as the last frame;
- a viewer that offers `agentnexus-watch-v2` first and the capability second gets version 2 from a
  provider that implements it, and is refused before the stream opens by one that does not.

The schema says that a match that is not `active` has no deadline and that Connect Four has no
match deadline. What it cannot say, this check does, for the published game versions: a deadline is
at most 60 seconds (a turn) or 50 minutes (a Chess match) after `server_time`, because a turn or a
match never begins in the future, and no earlier bound, because a deadline that has just passed is
valid; a Chess match that is `active` has its limit running; the views are the game version's own;
an answer fits version 1's size bound.

What no decision fixes raises `Undecided`, and no case sends it: a game version this check does not
know, and everything `ci/spectator.py` leaves undecided.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime, timedelta
from functools import cache
from itertools import pairwise
from pathlib import Path
from typing import Any, Final, NamedTuple

from json_schema import valid
from spectator import EVENTS, HEADER, Undecided, Watch

#: The turn deadline, in seconds, of every published game version.
TURN: Final = 60
#: The limit of an active Chess match, in seconds: 50 minutes.
MATCH_LIMIT: Final = 50 * 60
STREAM_V1: Final = "agentnexus-watch-v1"
STREAM_V2: Final = "agentnexus-watch-v2"
#: The version each stream subprotocol selects.
WATCH: Final = {STREAM_V1: 1, STREAM_V2: 2}
CAPABILITY_FORM: Final = re.compile(r"[A-Za-z0-9_-]{43}")
#: Exactly the two forms that ask for version 2, `answer=2` last.
VERSION_2: Final = re.compile(
    r"(?P<path>/agentnexus-games/v1/matches/[^/?]+/spectator)"
    r"\?(?:after=(?P<after>[^&]*)&)?answer=2"
)
ENDED: Final = frozenset({"ended", "aborted"})


class Game(NamedTuple):
    """What this check knows of a published game version."""

    directory: str  #: `games/<directory>/<game version>/`
    limit: int | None  #: the active-match limit in seconds: Chess only
    seats: dict[str, str]  #: the seat that plays each role the view names in `to_move`


CONNECT_FOUR: Final = Game("connect-four", None, {"first": "first", "second": "second"})
CHESS: Final = Game("chess", MATCH_LIMIT, {"white": "first", "black": "second"})
GAMES: Final = {
    "connect-four-1": CONNECT_FOUR,
    "connect-four-1-solo": CONNECT_FOUR,
    "chess-1": CHESS,
    "chess-1-solo": CHESS,
}


class Refused(Exception):
    """The reference provider would send an answer that this check refuses."""

    def __init__(self, layer: str, rule: str | None) -> None:
        super().__init__(f"{layer}: {rule or 'the schema'}")
        self.layer = layer
        self.rule = rule


def parse(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)


def stamp(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def _optional(value: str | None) -> datetime | None:
    return None if value is None else parse(value)


def _game(game_version: str) -> Game:
    if game_version not in GAMES:
        raise Undecided("a game version this check does not know")
    return GAMES[game_version]


@cache
def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


@cache
def _is_view(text: str, schema: Path) -> bool:
    return valid(json.loads(text), _load(schema))


def views_valid(answer: Any, games: Path) -> bool:
    """Whether the snapshot and every event's view are the game version's own spectator view."""
    version = answer["game_version"]
    schema = games / _game(version).directory / version / "spectator.schema.json"
    views = [answer["snapshot"], *(event["view"] for event in answer["events"])]
    return all(_is_view(json.dumps(view, sort_keys=True), schema) for view in views)


def refusal(answer: Any, schemas: Path, games: Path) -> tuple[str, str | None] | None:
    """Why this answer is refused, or `None`: the layer, `schema` or `reference`, and the rule."""
    if not valid(answer, _load(schemas / "spectator-answer-v2.schema.json")):
        return "schema", None
    version = answer["game_version"]
    game = _game(version)
    observation = _load(games / game.directory / version / "observation.schema.json")
    bound = 1024 + 17 * observation["x-agentnexus-max-bytes"]
    if len(json.dumps(answer, separators=(",", ":")).encode("utf-8")) > bound:
        return "reference", "answer-too-large"
    if not views_valid(answer, games):
        return "reference", "view-refused"
    timing = answer["timing"]
    try:
        server = parse(timing["server_time"])
        turn = _optional(timing["turn_deadline_at"])
        end = _optional(timing["match_deadline_at"])
    except ValueError:
        return "reference", "not-an-instant"
    if turn is not None and turn > server + timedelta(seconds=TURN):
        return "reference", "turn-deadline-too-far"
    limit = None if game.limit is None else server + timedelta(seconds=game.limit)
    if end is not None and limit is not None and end > limit:
        return "reference", "match-deadline-too-far"
    if game.limit is not None and answer["status"] == "active" and end is None:
        return "reference", "chess-needs-a-match-deadline"
    return None


def answer_version(body: Any, schemas: Path) -> int | None:
    """Which version an answer is, by the schemas alone; no answer passes both."""
    if valid(body, _load(schemas / "spectator-answer-v2.schema.json")):
        return 2
    if valid(body, _load(schemas / "spectator-answer.schema.json")):
        return 1
    return None


class WatchV2(Watch):
    """A provider that implements versions 1 and 2. Version 1 is `ci/spectator.py`, unchanged."""

    def handle(
        self,
        method: str,
        path: str,
        headers: dict[str, str],
        body: bytes,
        now: str,
        issues: dict[str, str] | None = None,
        facts: dict[str, Any] | None = None,
    ) -> tuple[int, dict[str, Any] | None]:
        """As `Watch.handle`; `facts` are what the provider has stored for the match it answers."""
        asked = VERSION_2.fullmatch(path)
        if asked is None:
            return super().handle(method, path, headers, body, now, issues)
        after = "" if asked["after"] is None else f"?after={asked['after']}"
        status, answer = super().handle(
            method, asked["path"] + after, headers, body, now, issues
        )
        if status != 200 or answer is None:
            return status, answer
        if facts is None:
            raise ValueError("the vector gives no clock facts for a version 2 answer")
        answer = {**answer, "timing": self._timing(answer, facts, now)}
        found = refusal(answer, self.schemas, self.games)
        if found is not None:
            raise Refused(*found)
        return 200, answer

    def cross_origin(
        self, method: str, path: str, headers: dict[str, str]
    ) -> dict[str, str]:
        """The `Access-Control-Allow-*` headers: version 2 adds no header and asks for none."""
        asked = VERSION_2.fullmatch(path)
        return super().cross_origin(method, asked["path"] if asked else path, headers)

    @staticmethod
    def _timing(
        answer: dict[str, Any], facts: dict[str, Any], now: str
    ) -> dict[str, str | None]:
        game = _game(answer["game_version"])
        running = answer["status"] == "active"
        seat = game.seats.get(answer["snapshot"]["to_move"])
        turn = end = None
        if running and seat in facts["bound_seats"]:
            turn = stamp(parse(facts["turn_started_at"]) + timedelta(seconds=TURN))
        if running and game.limit is not None:
            end = stamp(parse(facts["activated_at"]) + timedelta(seconds=game.limit))
        return {
            "server_time": stamp(parse(now)),
            "turn_deadline_at": turn,
            "match_deadline_at": end,
        }


def _known(path: str) -> str:
    """The path without any query parameter but `after`."""
    head, _, query = path.partition("?")
    kept = [part for part in query.split("&") if part.partition("=")[0] == "after"]
    return head + ("?" + "&".join(kept) if kept else "")


class V1OnlyWatch(Watch):
    """A provider that implements only version 1 and ignores a query parameter it does not know.

    It is one of the two things the version 1 text lets such a provider do with `answer=2`; the
    other is to refuse it as `ci/spectator.py` does, which is `Watch` itself.
    """

    def handle(
        self,
        method: str,
        path: str,
        headers: dict[str, str],
        body: bytes,
        now: str,
        issues: dict[str, str] | None = None,
        facts: dict[str, Any] | None = None,
    ) -> tuple[int, dict[str, Any] | None]:
        return super().handle(method, _known(path), headers, body, now, issues)


def state_at(match: dict[str, Any], through: int, status: str) -> dict[str, Any]:
    """The match as a provider holds it once `through` events are committed and it shows `status`."""
    events = match["events"][:through]
    if not events:
        raise ValueError("a stream starts at an event")
    return {
        "game_version": match["game_version"],
        "status": status,
        "snapshot": events[-1]["view"],
        "events": events,
    }


def frames(
    match_id: str,
    match: dict[str, Any],
    specs: list[dict[str, Any]],
    schemas: Path,
    games: Path,
) -> list[dict[str, Any]]:
    """The frames a provider sends one stream, one for each of `specs`.

    A spec is the provider's clock when it creates the frame (`now`), the events committed so far
    (`through`), the status the match shows and the clock facts it has stored. The first frame is
    the snapshot, no events; each later one is the version 2 answer to `after` the last event
    already sent, which must be one to 16: a frame is built for an event, never for time passing.
    """
    sent = None
    built = []
    for spec in specs:
        if sent is not None and not 1 <= spec["through"] - sent <= EVENTS:
            raise ValueError("a later frame carries one to 16 events")
        provider = WatchV2(
            {match_id: state_at(match, spec["through"], spec["status"])}, schemas, games
        )
        # The stream's capability was checked when it opened (`D-161`); this one lasts the frame.
        token = "x" * 43
        provider.capabilities[token] = (match_id, parse(spec["now"]))
        query = "answer=2" if sent is None else f"after={sent}&answer=2"
        status, answer = provider.handle(
            "GET",
            f"/agentnexus-games/v1/matches/{match_id}/spectator?{query}",
            {HEADER: token},
            b"",
            spec["now"],
            None,
            spec["facts"],
        )
        if status != 200 or answer is None:
            raise ValueError("the provider does not build this frame")
        built.append(answer)
        sent = spec["through"]
    return built


def stream_refusal(
    stream: list[dict[str, Any]], snapshot: dict[str, Any] | None = None
) -> str | None:
    """The first rule these frames break, by name, or `None`.

    `snapshot` is the answer an HTTP read gives at the first frame's instant, which that frame must
    equal. After the first, every frame carries the next events, one to 16, in order and without a
    gap or a repeat; `server_time` never goes back; a frame that shows an active match after an
    accepted move has a later turn deadline than the frame before; and nothing follows the frame
    that shows the match ended or aborted.
    """
    first = stream[0]
    if snapshot is not None and first != snapshot:
        return "first-frame-differs-from-the-snapshot"
    if first["events"]:
        return "first-frame-carries-events"
    for before, after in pairwise(stream):
        if before["status"] in ENDED:
            return "frame-after-the-end"
        if not 1 <= len(after["events"]) <= EVENTS:
            return "later-frame-event-count"
        numbers = [event["event_seq"] for event in after["events"]]
        if numbers != list(range(before["event_seq"] + 1, after["event_seq"] + 1)):
            return "events-do-not-continue"
        if parse(after["timing"]["server_time"]) < parse(
            before["timing"]["server_time"]
        ):
            return "server-time-goes-back"
        old = before["timing"]["turn_deadline_at"]
        new = after["timing"]["turn_deadline_at"]
        if after["status"] == "active" and old and new and parse(new) <= parse(old):
            return "deadline-not-renewed"
    return None


def selected(offered: list[str], implements: tuple[int, ...] = (1, 2)) -> str | None:
    """The subprotocol a provider selects for an offer, or `None`: refused before it opens.

    The offer is exactly two subprotocols, the version first and the capability second (`D-161`);
    a provider selects the version it implements and refuses every other offer.
    """
    if len(offered) != 2 or not CAPABILITY_FORM.fullmatch(offered[1]):
        return None
    return offered[0] if WATCH.get(offered[0]) in implements else None
