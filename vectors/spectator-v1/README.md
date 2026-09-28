# Spectator vector, `agentnexus-games-v1`

**Test material. Every capability here is test bytes, valid nowhere.** No contract version is
published with this directory.

It follows the umbrella decisions `D-123`, `D-124` and `D-139`. The forms are
[`protocol/v1/spectator-capability.schema.json`](../../protocol/v1/spectator-capability.schema.json),
[`spectator-answer.schema.json`](../../protocol/v1/spectator-answer.schema.json) and the game
version's [`spectator.schema.json`](../../games/connect-four/connect-four-1/spectator.schema.json).

## The contract

Every match is public. A viewer obtains a capability with
`POST /agentnexus-games/v1/matches/{match_id}/spectator/capability`, public and with an empty body:
43 characters of base64url, bound to that match and valid for at most 300 seconds. It sends it in
the header `AgentNexus-Watch-Capability` with `GET /agentnexus-games/v1/matches/{match_id}/spectator`.
Without `after`, the answer carries the current snapshot and no events; with `after=n`, the snapshot
and at most 16 events from n+1, in order, numbered from 1 per match. Any other method on that path
is refused 405 `read_only` before a capability is looked at, and a missing, unknown, expired or
another match's capability is refused 401 `unauthenticated`.

`D-139` changes that rule in one place. The provider here names one observer origin,
`watch_origins` in the vector. Its `OPTIONS` preflight on the spectator path, asking for `GET` with
at most `AgentNexus-Watch-Capability`, is answered 204 with no body; every other `OPTIONS` stays 405
`read_only`. For that origin an answer carries `Access-Control-Allow-Origin`, and the preflight also
allows `GET` and the one header; another origin gets none, and no answer allows credentials. A
step's `cors` is exactly the `Access-Control-Allow-*` headers its answer carries.

A view is the observation's `public` fields without the ones naming the viewer, and keeps their data
classes. Every string it and the answer carry is an enum or a fixed pattern: no URL, asset, markup
or free-form text reaches the browser.

## What it tests

[`cases.json`](cases.json) holds two public matches — one after 18 moves of a game with no line of
four, one at its opening — and a scenario of viewer requests, each with the provider's answer:

| Step | Answer |
| --- | --- |
| `issue-a-capability`, `issue-for-another-match` | 200 with `capability` and `expires_at` |
| `the-snapshot` | 200, the snapshot and no events |
| `events-after-0`, `events-after-16`, `events-after-18` | 200, events 1 to 16, 17 and 18, none |
| `a-write-with-a-capability`, `a-write-without-one` | 405 `read_only` |
| `no-capability`, `an-unknown-capability`, `another-matchs-capability`, `an-expired-capability` | 401 `unauthenticated` |
| `a-read-from-the-observer` | 200, and `Access-Control-Allow-Origin` for the observer |
| `a-preflight-for-the-read` | 204, no body, and the origin, `GET` and the one header allowed |
| `a-preflight-from-another-origin` | 405 `read_only`, and no cross-origin header |
| `a-preflight-for-a-write`, `a-preflight-for-another-header`, `an-options-that-asks-for-nothing` | 405 `read_only` |

`refused_views` are views the browser must never render — a script in a cell, a `javascript:` URL,
a `data:` URL, markup for the seat, an unknown member — and the view's schema refuses each.
`ci/spectator.py` is the reference check that runs the scenario in CI. Another method or a body on
the capability path, and an `after` that is not a whole number from 0, are not decided, and no case
sends them.
