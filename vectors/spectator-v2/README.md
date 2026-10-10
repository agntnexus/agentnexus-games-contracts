# Spectator vector, version 2, `agentnexus-games-v1`

**Test material. Every capability here is test bytes, valid nowhere.** No contract version is
published with this directory.

It follows the umbrella decision `D-175`. The forms are
[`protocol/v1/spectator-answer-v2.schema.json`](../../protocol/v1/spectator-answer-v2.schema.json),
the version 1 answer and one more required member, `timing`, and each game version's
`spectator.schema.json` for the views, for example
[`games/chess/chess-1/spectator.schema.json`](../../games/chess/chess-1/spectator.schema.json). The
text is [`protocol/v1/spectator-v2.md`](../../protocol/v1/spectator-v2.md). Nothing of version 1
changes: [`vectors/spectator-v1/`](../spectator-v1/) and every file it uses stay as published, and
`ci/test_spectator_v2.py` pins them.

## The contract

A viewer asks for version 2 with `?answer=2` or `?after=n&answer=2`, in that order, or on a stream
by offering `agentnexus-watch-v2` first and the capability second. The answer is the version 1
answer and `timing`: `server_time`, the provider's clock when it created the answer;
`turn_deadline_at`, the stored start of the current turn plus 60 seconds, or `null`; and
`match_deadline_at`, for Chess the activation plus 50 minutes while the match is `active`, or
`null`. All three are canonical UTC instants, whole seconds and a literal `Z`, and the capability's
expiry appears in none of them.

A step's `facts` are what the provider has stored: when the current turn began (`turn_started_at`),
when the match became active (`activated_at`) and which seats are bound (`bound_seats`). The
reference check plays no game: it derives `timing` from the facts and from the step's `now`, the
provider's clock. A request without `answer` ignores the facts and gets the version 1 answer. A
provider that can reach a step's state can replay it: the match became active at `activated_at`, the
move that gave the position was accepted at `turn_started_at`, the seats in `bound_seats` are bound,
and the answer is made at `now`.

## What it tests

[`cases.json`](cases.json) holds eight public matches, a scenario of viewer requests with the
provider's answers, answers every check must refuse, the frames of two streams, and how a viewer
asks for each version. Times are 2026-10-08, UTC; the read at 12:00:00 is T.

| Step | Answer |
| --- | --- |
| `issue-a-capability` and seven more `issue-for-...` | 200 with `capability` and `expires_at`, 300 seconds |
| `the-v2-snapshot` | Connect Four, mid-turn: `turn_deadline_at` is T+42 s, `match_deadline_at` is `null` |
| `the-v2-events-after-3` | `after` then `answer=2`: events 4 and 5 and the same timing rules |
| `the-same-read-without-answer-is-the-v1-answer` | The version 1 answer: six members, no `timing`, byte for byte |
| `a-later-poll-keeps-the-deadline` | A later read moves `server_time` and nothing else |
| `a-deadline-that-is-now`, `a-deadline-one-second-ago` | A deadline at or just before `server_time` in an `active` match: valid, and no result |
| `the-opening-without-answer-is-the-published-v1-answer` | The bytes `vectors/spectator-v1` published for this match |
| `a-v2-read-from-the-observer` | 200, and `Access-Control-Allow-Origin` for the observer |
| `a-preflight-for-the-v2-read` | 204: version 2 adds no request header, so `D-139`'s one preflight is unchanged |
| `a-write-to-the-v2-path`, `the-v2-path-without-a-capability` | 405 `read_only`, 401 `unauthenticated` |
| `an-unstarted-match` | A Chess match `awaiting_seats`: both deadlines `null` |
| `an-ended-match` | Connect Four `ended`: both `null`, though the provider still holds a turn start |
| `a-seat-that-has-not-bound` | `active`, and the seat to move has not bound: `turn_deadline_at` is `null` |
| `a-chess-match-right-after-a-move` | A fresh 60 seconds, and the Chess limit 34 minutes 38 seconds ahead |
| `an-active-chess-match` | 40 seconds left, and the limit 34 minutes 18 seconds ahead |
| `an-aborted-match` | Chess `aborted` by its 50-minute limit: both `null` |

`refused_answers` are bodies that fail, each with its `because` and the `layer` that refuses it. At
the layer `schema`, [`spectator-answer-v2.schema.json`](../../protocol/v1/spectator-answer-v2.schema.json)
refuses them: no `timing`, a missing or an extra member in it or next to it, an instant that is not
canonical UTC in any member, a deadline in a match that is not `active`, a match deadline for
Connect Four. At the layer `reference`, the schema accepts them and a `rule` of `ci/spectator_v2.py`
refuses them, because the schema cannot say it: a turn deadline more than 60 seconds ahead, which
also catches the two deadlines swapped, a match deadline more than 3000 seconds ahead, an `active`
Chess match without its limit, a shape that is no calendar instant, a view that is not the game
version's.

`streams` holds two streams, and each one's `frames` are what a provider sends for a Connect Four
match and a Chess match, from a snapshot on connect to the frame that shows the end. The first
frame is the snapshot, with no events, and is what an HTTP read at that instant gives. Every later
frame carries the events since the frame before, one to 16, and a move starts a fresh 60 seconds
for the other seat. Each frame has its own `server_time`, which never goes back; the last frame has
no deadline. A stream's timing is as current as its last event: a frame is built when an event is
committed, never for time passing, so the vector holds no frame without an event but the first. A
change of timing that records no event, for example a seat binding that starts a turn deadline,
reaches a stream with the next frame, and an HTTP read shows it at once.

`negotiation` shows how a viewer asks: the HTTP forms `?answer=2` and `?after=3&answer=2` are
version 2, `?answer=1`, `?answer=02`, `?answer=2&after=3`, `?answer=2&answer=2` and the rest are
refused, as the version 1 reference check refuses a query it does not know (that is the reference
check's strictness; a provider that ignores a parameter other than `answer` is not in conflict with
the text). It also shows which subprotocol offers are selected, which are refused before the stream
opens, and what a provider that implements only version 1 may do with `answer=2`. Such a provider
may ignore the parameter and answer with the plain version 1 answer, or refuse the request as it
refuses any query it does not know. A viewer that asked for version 2 accepts both. The version 1
answer it may get back is a valid version 1 answer and is not a valid version 2 answer, because it
has no `timing`, so a viewer tells the two apart by the schemas alone; `v1_only_provider` shows
both outcomes for the same two requests.

`ci/spectator_v2.py` is the reference check that runs it in CI, built on `ci/spectator.py`, which it
does not change. The capabilities are `agentnexus-watch-v2 published test capability N, valid
nowhere`, hashed as in `vectors/spectator-v1`. What the version 1 text leaves undecided stays
undecided here, and no case sends it: a game version this check does not know, and an `after` that
is not a whole number from 0.
