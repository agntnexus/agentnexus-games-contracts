# Games provider wire vector, version 1

**Test material. No ticket here is a grant, and every key here is a published test key that is
valid nowhere.** A deployment that accepts one of these keys is misconfigured. No contract version is
published with this directory.

It follows the umbrella decision `D-114` (the provider wire, W-1 to W-8), with `D-100`'s ticket times
and keys, `D-112`'s answers and `D-118`'s body limits and Connect Four payloads.

## Where the schemas are

The eight common schemas of W-7 are kept here, beside the cases that use them, exactly as `D-114`
accepted them: [`ticket-v2`](ticket-v2.schema.json), [`redemption`](redemption.schema.json),
[`resumption`](resumption.schema.json), [`action`](action.schema.json),
[`seat-answer`](seat-answer.schema.json), [`resignation-instruction`](resignation-instruction.schema.json),
[`resignation-acknowledgement`](resignation-acknowledgement.schema.json) and
[`refusal`](refusal.schema.json). **Where the contract's common schemas finally live, and under which
contract version they are published, is not decided, and this directory decides neither.** The
redemption schema names the ticket schema as `ticket-v2.schema.json`, as `D-114` wrote it.

## The wire

The ticket's second version is signed over these lines, joined by one LF with no trailing LF:
`agentnexus-grant-v2`, then `key_id`, `ticket_id`, `match_id`, `seat`, `seat_generation`,
`provider_id`, `game_version`, `operations` (joined by commas: `move,resign`),
`session_key_fingerprint`, `not_before`, `not_after`.

Every message the Connector sends for a seat is signed with the seat's session key over
`agentnexus-play-v1`, the purpose, the match, the seat, the generation, the sequence and the SHA-256
of the exact body bytes. The signature travels in the header `AgentNexus-Play-Signature`. The purpose
comes from the path:

| Method and path | Purpose |
| --- | --- |
| `POST /agentnexus-games/v1/matches/{match_id}/seats/{seat}/redemption` | `redeem` |
| `POST /agentnexus-games/v1/matches/{match_id}/seats/{seat}/resumption` | `resume` |
| `POST /agentnexus-games/v1/matches/{match_id}/seats/{seat}/actions` | `act` |

A provider checks a request in this order, and the first stage that fails answers: size, schema,
authentication, freshness, bindings, state. Up to and including authentication it answers only
`too_large`, `malformed_body` or `unauthenticated`, which name no match and no seat.

## What it tests

[`cases.json`](cases.json) holds the published test keys, four tickets and seven scenarios. Each
scenario starts from a provider that holds nothing, and each of its steps is a request with the
answer the provider gives:

| Scenario | Shows |
| --- | --- |
| `redeem-and-play` | A seat is bound, moves in column 3, repeats that move identically and gets the stored answer, and resumes |
| `sequence-and-state-refusals` | `sequence_conflict`, `sequence_stale` for an earlier action sent again, `sequence_gap`, `state_version_stale`, `idempotency_conflict`, `unauthenticated` for another session key, `malformed_body` for an unknown member, `too_large` one byte over the action's limit, and 404 for a path not served |
| `another-match` | `ticket_match`: the ticket for one match redeemed on another's path |
| `a-grant-key-the-provider-does-not-hold` | `unauthenticated` |
| `another-session-key` | `unauthenticated`: the session key is not the one the ticket's fingerprint binds |
| `outside-the-window` | `ticket_clock`, one second past the skew |
| `rebinding` | A higher generation rebinds the seat; the earlier key is `unauthenticated`; a ticket of the same generation is `generation_stale` |

Where a request passes every check, the step gives the answer the provider's game returns
(`provider_answer`): a seat answer whose observation `D-118`'s Connect Four schema accepts. The move
played is `D-118`'s `{"column": 3}`.

## Reproducing it

Each test seed is the SHA-256 of the phrase the file names, and Ed25519 signing is deterministic, so
anyone can regenerate every key, fingerprint and signature from the file alone.
`ci/test_provider_wire.py` does exactly that on every change, and `ci/provider_wire.py` is the
reference check that has to give every step its published answer.

## What it does not fix

`D-114` leaves these open, and no case here answers them; the reference check refuses to choose:

- which of `ticket_spent`, `generation_stale` and the stored answer a repeated redemption of a bound
  seat gets, and the order of the state stage's checks when more than one fails;
- the code for a redemption whose body names another generation than its ticket, or a message whose
  generation is not the binding's;
- the answer to another method on a served path, and to an idempotency key sent again with the same
  move;
- at which stage a game payload is checked against its schema and bound, which code refuses it, a
  code for a move the rules refuse, and a maximum for the counters.

The resignation instruction, the spectator path and the outcome interface are not run here, and
neither are the manifest and the spectator capability, whose formats are not decided.
