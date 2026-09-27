"""Reference check of the read-only spectator contract, for `agentnexus-games-v1`.

It runs the scenario in `vectors/spectator-v1/` and nothing else: it is test code, not a provider,
and it plays no game; the vector supplies each match's snapshot and events, and the capability a
provider issues. Each rule below is a sentence of `D-123` or `D-124` in the AgentNexus decisions:

- `POST /agentnexus-games/v1/matches/{match_id}/spectator/capability`, public and with an empty
  body, issues a match-bound, opaque capability of 43 characters of base64url, valid for at most
  300 seconds, answered 200 with `capability` and `expires_at`;
- any method but `GET` on `/agentnexus-games/v1/matches/{match_id}/spectator` is refused 405
  `read_only`, before the capability is looked at;
- a `GET` without a capability in the header `AgentNexus-Watch-Capability`, or with an unknown,
  expired or another match's, is refused 401 `unauthenticated`, with no reason given;
- without `after`, the answer carries the current snapshot and no events; with `after=n`, the
  snapshot and at most 16 events from n+1, in order.

What no decision fixes raises `Undecided`, and no case sends it: another method or a body on the
capability path, an `after` that is not a whole number from 0, and a match the provider does not
serve.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Final

LIFETIME: Final = 300
EVENTS: Final = 16
HEADER: Final = "AgentNexus-Watch-Capability"
CAPABILITY: Final = re.compile(
    r"/agentnexus-games/v1/matches/(?P<match_id>[^/?]+)/spectator/capability"
)
SPECTATOR: Final = re.compile(
    r"/agentnexus-games/v1/matches/(?P<match_id>[^/?]+)/spectator(?:\?after=(?P<after>[^&]*))?"
)


class Undecided(Exception):
    """No decision fixes the answer to this request, so the check does not choose one."""


def _time(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)


def _refusal(status: int, code: str) -> tuple[int, dict[str, Any]]:
    return status, {"error": {"code": code}}


class Watch:
    """One provider's spectator side: the capabilities it issued, and its public matches."""

    def __init__(
        self, matches: dict[str, dict[str, Any]], schemas: Path, games: Path
    ) -> None:
        self.matches = matches
        self.schemas = schemas
        self.games = games
        self.capabilities: dict[str, tuple[str, datetime]] = {}

    def handle(
        self,
        method: str,
        path: str,
        headers: dict[str, str],
        body: bytes,
        now: str,
        issues: dict[str, str] | None = None,
    ) -> tuple[int, dict[str, Any] | None]:
        """Return the status and body the provider answers; `issues` is the capability it mints."""
        issuing = CAPABILITY.fullmatch(path)
        if issuing:
            return self._issue(issuing["match_id"], method, body, now, issues)
        watching = SPECTATOR.fullmatch(path)
        if watching is None:
            return 404, None
        if method != "GET":
            return _refusal(405, "read_only")
        match_id = watching["match_id"]
        capability = headers.get(HEADER)
        held = self.capabilities.get(capability) if capability else None
        if held is None or held[0] != match_id or _time(now) > held[1]:
            return _refusal(401, "unauthenticated")
        match = self._match(match_id)
        answer = {
            "match_id": match_id,
            "game_version": match["game_version"],
            "status": match["status"],
            "event_seq": len(match["events"]),
            "snapshot": match["snapshot"],
            "events": [],
        }
        after = watching["after"]
        if after is not None:
            if not re.fullmatch(r"0|[1-9][0-9]*", after):
                raise Undecided("an after that is not a whole number from 0")
            answer["events"] = match["events"][int(after) : int(after) + EVENTS]
        return 200, answer

    def _match(self, match_id: str) -> dict[str, Any]:
        match = self.matches.get(match_id)
        if match is None:
            raise Undecided("a match the provider does not serve")
        return match

    def _issue(
        self,
        match_id: str,
        method: str,
        body: bytes,
        now: str,
        issues: dict[str, str] | None,
    ) -> tuple[int, dict[str, Any]]:
        if method != "POST" or body:
            raise Undecided("another method, or a body, on the capability path")
        self._match(match_id)
        if issues is None:
            raise ValueError("the vector gives no capability for an issuing step")
        expires = _time(issues["expires_at"])
        if not timedelta(0) < expires - _time(now) <= timedelta(seconds=LIFETIME):
            raise ValueError("the vector issues a capability outside its lifetime")
        self.capabilities[issues["capability"]] = (match_id, expires)
        return 200, dict(issues)
