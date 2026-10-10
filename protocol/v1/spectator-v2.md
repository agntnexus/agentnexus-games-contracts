# The spectator answer, version 2

**Not a published contract version.** This file becomes part of `agentnexus-games-v1` only when the
owner approves a named commit of this repository as it; merging a change here publishes nothing,
and no tag is required for it, as for [`README.md`](README.md). It follows `D-175` in the AgentNexus
decisions. Every capability in its vectors is test bytes, valid nowhere.

Version 2 is additive. [`spectator-answer`](spectator-answer.schema.json), its vectors and
[`README.md`](README.md) stay exactly as published, and a viewer that never asks for version 2 gets
version 1 byte for byte. It changes no message, path, signed line or code that exists, so it is no
new major version. A provider may serve both versions; a viewer must work against one that serves
only version 1.

## What it adds

The version 1 answer carries a position and the side to move, and no time. A viewer cannot count a
turn down from the moment a frame arrived, or from `updated_at`: that is wrong under network delay,
a reconnect or a deferred frame. Version 2 carries the provider's own clock facts instead, as
absolute canonical UTC instants in one small fixed object.

[`spectator-answer-v2`](spectator-answer-v2.schema.json) is the version 1 answer with one more
required member, `timing`; its six other members are the version 1 members, unchanged. Like every
schema here it is closed: a member it does not name is refused. `timing` belongs to the answer and
never to a game's spectator view, whose schema in [`games/`](../../games/) does not change.

| Member of `timing` | Value |
| --- | --- |
| `server_time` | The provider's clock when it created this snapshot or frame |
| `turn_deadline_at` | The instant by which the seat whose turn it is must have moved, or `null` |
| `match_deadline_at` | Chess only: the end of the active-match limit, or `null` |

```json
"timing": {
  "server_time": "2026-10-08T12:00:00Z",
  "turn_deadline_at": "2026-10-08T12:00:42Z",
  "match_deadline_at": null
}
```

All three members are required: a deadline that does not apply is `null`, never absent. An instant
is canonical UTC, as everywhere in this contract: whole seconds and a literal `Z`, with no fraction
and no offset. There is no other member, and no generic map.

## Asking for version 2

**Over HTTP,** by the query parameter `answer=2`, in one of two forms and in this order only:

```
GET /agentnexus-games/v1/matches/{match_id}/spectator?answer=2
GET /agentnexus-games/v1/matches/{match_id}/spectator?after=<n>&answer=2
```

Without `answer` the answer is the version 1 answer, unchanged. A provider that implements version 2
answers no other use of `answer` with a version 2 answer: a value but `2` (`answer=1`, `answer=02`,
an empty `answer=`), a repeated `answer`, and `answer` before `after` are refused. Which status and
body the refusal has is not decided here, as for a malformed `after` in version 1; the reference
check answers 404 with no body, as it does for any query it does not know, and a provider that
ignores a parameter other than `after` and `answer` is not in conflict with this text. The
capability travels in the header `AgentNexus-Watch-Capability` as before, and any method but `GET`
is refused 405 `read_only` before it is looked at. No new request header is added, so the one
preflight of `D-139`, which allows that header alone, is unchanged and stays the only one.

**Over a stream,** by offering `agentnexus-watch-v2` in place of `agentnexus-watch-v1` as the first
of exactly two subprotocols, the capability second: `[agentnexus-watch-v2, <capability>]`. A
provider that implements version 2 selects `agentnexus-watch-v2`, and every frame on that stream is
a version 2 answer. `[agentnexus-watch-v1, <capability>]` keeps version 1 frames. Any other offer,
with one subprotocol, three, the capability first or no capability, is refused before the stream
opens with nothing sent, as `D-161` says. The capability belongs to the match and not to a version:
the same capability opens either stream and reads over HTTP.

**A provider that implements only version 1** does not know `answer`. Over HTTP it may ignore the
parameter and answer with the plain version 1 answer, or refuse the request as it refuses any query
it does not know. A viewer that asked for version 2 accepts both. An answer without `timing` is a
version 1 answer and carries no numeric clock; after a refusal the viewer repeats the request once
without `answer`. The two are told apart by the schemas alone: a version 1 answer passes
`spectator-answer` and fails `spectator-answer-v2`, which requires `timing`, and a version 2 answer
is the reverse, so no answer passes both. Over a stream such a provider refuses
`[agentnexus-watch-v2, <capability>]` before it opens, by the rule it has had since `D-161`: its
first subprotocol must be `agentnexus-watch-v1`. The viewer then opens a new connection, once, and
offers `[agentnexus-watch-v1, <capability>]`.

## The answer and the stream

Over HTTP a read without `after` carries the current snapshot and no events, and a read with
`after=n` the snapshot and at most 16 events from n+1, as in version 1. A stream frame is by
definition one version 2 answer, within the bound below. The first frame carries the current
snapshot with no events. Each later frame carries the new snapshot and, in order, every event since
the frame before, at least one and at most 16, as in `D-161`. A snapshot and a frame have one
schema and one set of rules, and the first frame is what an HTTP read at that instant gives.

`server_time` is read from the provider's clock when that snapshot or frame is created, and every
frame has its own. It never goes back from one frame to the next, and two frames may share a second.
Provider and viewer never compare clocks beyond this: a viewer reads a deadline against the
`server_time` of the answer that carries it, and this contract defines no other clock agreement and
no correction for delay.

**Timing is as current as its last event.** A frame is built when an event is committed: the first
on connect, a later one for new events, at least one each. So `timing` in a stream changes only with
a frame. A change of timing that records no event, for example a seat binding that starts a turn
deadline, reaches a stream only with the next frame, while an HTTP read shows it at once. This is a
known property of the stream, not a defect: no frame is built for time passing, or for a change that
no event records.

## The deadlines

- `turn_deadline_at` is the provider's stored `turn_started_at` plus the turn deadline of the game
  version, which is 60 seconds for the published game versions. Each accepted move, and the
  built-in computer's reply, starts a fresh deadline; there is no cumulative account of a player's
  time, no increment and no delay. It is `null` when the match is not `active`, when the side to
  move has no bound seat, and so for a match that has not started, has ended or has aborted. A role
  without a bound seat gets no running timer: the computer's in a solo match, or a seat that has
  not yet bound.
- `match_deadline_at` exists for Chess only. It is the provider's `activated_at` plus 50 minutes
  while the match is `active`, and `null` in every other state. For Connect Four, which has no
  active-match limit, it is always `null`: no limit is made up.

Both come only from the provider's stored state and clock, never from a viewer, a Connector, an
agent or a model. A turn or a match never begins in the future, so a deadline is never later than
`server_time` plus 60 seconds, or plus 50 minutes for a Chess match. The schema cannot say that;
the reference check does, for the published game versions, and a viewer need not apply it. There is
no lower bound.

**What the values are not.** They are not the capability's `expires_at`, which stays a separate
access fact and is never copied into `timing`; not the API's 60-minute outcome deadline; not the
seat-binding deadline; not the 400-ply Chess cap; not the built-in computer's 2-second search
bound; and not a value a browser derived. The provider is the only clock and the only result
authority.

**A deadline is not a result.** `timing` in an answer that is not terminal says when the provider
will act, never that it has. A deadline may already be at or slightly before `server_time`, because
the provider enforces a deadline on its own tick and its instants are whole seconds. A viewer
tolerates that and infers no result from it: a deadline that has passed is not a timeout until a
provider frame reports the match ended or aborted.

## What the schema says, and what it does not

The schema says that a match that is `awaiting_seats`, `ended` or `aborted` has `null` for both
deadlines, and that a game version beginning `connect-four-` has `null` for `match_deadline_at`.
[`ci/spectator_v2.py`](../../ci/spectator_v2.py) checks the rest for the published game versions:
the two upper bounds above, that an `active` Chess match has a `match_deadline_at`, that the views
are the game version's own, and the size. The vectors, which show every one of these and how a
viewer asks for each version, are in [`vectors/spectator-v2/`](../../vectors/spectator-v2/).

## Size

The size bound of version 1 holds unchanged: an answer, over HTTP or in a frame, is at most 1024
bytes plus 17 times the game's observation bound. `timing` is at most 132 bytes compact, 133 with
the comma before it, and counts against that allowance; it is not added to it.

## Compatibility and rollback

Every version 1 file, vector and rule stays as published, and version 1 is the default. A provider
serves version 2 only to a viewer that asks for it. A viewer must work against a provider that
serves only version 1: it then has no `timing`, so no numeric clock, and shows what version 1
shows. A provider rolled back to version 1 loses the numbers and nothing else; the board stays
usable.

## Publication

As for `D-123` and `D-161`: this file, its schema and its vectors become part of
`agentnexus-games-v1` only when the owner approves a named commit of this repository that contains
them. Merging a change here publishes nothing, and no tag is required. Until then, nothing here is a
contract anyone may rely on.
