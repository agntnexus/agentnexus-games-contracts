# The Games provider protocol, `agentnexus-games-v1`

**Not published.** This directory is where contract version 1 is kept canonically (`D-123` in the
AgentNexus decisions). It becomes the published version only when the owner approves a named commit
of this repository as it; merging a change here publishes nothing, and no tag is required for it.
No key here, or in any vector, is valid anywhere, and no real match grant exists (`D-101`).

## The version

The contract version is `agentnexus-games-v1`. Every message names it through its path,
`/agentnexus-games/v1/…`, and a signed message also through its first signed line; no message carries
a further version member. A published version never changes. An incompatible change to a message,
path, signed line or refusal code is a new major version under `/agentnexus-games/v2`, and an old
version ends only by a separate owner decision that announces its end date. A game version changes
on its own, in [`games/`](../../games/).

## Paths

On the provider's origin:

| Method and path | Purpose | Signed by |
| --- | --- | --- |
| `POST /agentnexus-games/v1/matches/{match_id}/seats/{seat}/redemption` | `redeem`: bind or rebind a seat | The session key |
| `POST /agentnexus-games/v1/matches/{match_id}/seats/{seat}/resumption` | `resume`: the seat's current observation | The session key |
| `POST /agentnexus-games/v1/matches/{match_id}/seats/{seat}/actions` | `act`: one operation, `move` or `resign` | The session key |
| `POST /agentnexus-games/v1/matches/{match_id}/seats/{seat}/resignation-instructions` | An owner's resignation | The API's instruction key |
| `POST /agentnexus-games/v1/matches/{match_id}/spectator/capability` | A read capability, public, empty body | Nobody |
| `GET /agentnexus-games/v1/matches/{match_id}/spectator` | Read-only watching | A read capability |

On the API: `POST /agentnexus-games/v1/outcomes`, for the provider's signed outcome.

## Schemas

JSON Schema 2020-12, strict: a member a schema does not name is refused.
[`ticket-v2`](ticket-v2.schema.json), [`redemption`](redemption.schema.json),
[`resumption`](resumption.schema.json), [`action`](action.schema.json),
[`seat-answer`](seat-answer.schema.json), [`resignation-instruction`](resignation-instruction.schema.json),
[`resignation-acknowledgement`](resignation-acknowledgement.schema.json) and
[`refusal`](refusal.schema.json). They are `D-114`'s, and `sequence`, `state_version` and
`expected_state_version` carry `D-123`'s maximum, 9007199254740991. A game's own `move` and
`observation` are validated against the game version's schemas.

## The manifest

A provider declares itself with a manifest, [`manifest.schema.json`](manifest.schema.json): its
`provider_id`, the contract versions it implements by name (`"agentnexus-games-v1"`), one to four
exact `https` origins with an optional port and no IP address, path or trailing slash, its game
versions with their turn deadlines, the operations `move` and `resign`, one or two outcome keys, its
action rate and its replay retention. The deadline, rate and retention are positive integers; their
values, and admission itself, are not part of this contract. A manifest fits this contract when
one of its versions is implemented here, every game version has a directory in
[`games/`](../../games/), its operations are exactly `move` and `resign`, and every origin is
`https`.

## The outcome

A provider sends one outcome per match to the API, [`outcome.schema.json`](outcome.schema.json), at
most 2048 bytes, signed with an outcome key of its manifest. It is public and every member is
retained. The API checks size (`too_large`), schema (`malformed_body`), the signature
(`unauthenticated`), and the bindings: another provider's match is `outcome_provider` and another
game version `outcome_game`, both 403. It answers 200 with [`outcome-answer`](outcome-answer.schema.json):
`recorded` for the first outcome, `already_recorded` only for byte-identical signed lines,
`disputed` for any other, which never overwrites the first, and `evidence_only` for a match already
aborted or cancelled. `replay_digest` is the SHA-256 of the exact replay bytes `replay_reference`
names; the general replay format is not part of this contract.

## The spectator

Every match is public. A viewer obtains a capability from the provider, 43 characters of base64url,
bound to the match and valid for at most 300 seconds, [`spectator-capability`](spectator-capability.schema.json),
and sends it in the header `AgentNexus-Watch-Capability`. The answer, [`spectator-answer`](spectator-answer.schema.json),
carries the current snapshot and, with `after=n`, at most 16 events from n+1, each a view the game
version's `spectator.schema.json` accepts: the observation's `public` fields without those naming the
viewer. Any method but `GET` on the spectator path is refused 405 `read_only` before a capability is
looked at; a missing, unknown, expired or another match's capability is refused 401
`unauthenticated`. No URL, asset, markup or free-form text reaches the browser, and an answer is at
most 1024 bytes plus 17 times the game's observation bound.

## Signed bytes

Lines joined by one LF with no trailing LF, UTF-8, signed with Ed25519; a signature is 88 characters
of standard base64. A verifier rebuilds the lines from the message and never verifies bytes it did
not rebuild.

- **The ticket, version 2:** `agentnexus-grant-v2`, `key_id`, `ticket_id`, `match_id`, `seat`,
  `seat_generation`, `provider_id`, `game_version`, `operations` (`move,resign`),
  `session_key_fingerprint`, `not_before`, `not_after`. Its signature is the member `signature`.
- **A Connector message:** `agentnexus-play-v1`, the purpose, the match, the seat, the generation,
  the sequence and the SHA-256 of the exact body bytes, in lowercase hexadecimal. Its signature
  travels in the header `AgentNexus-Play-Signature`. A redemption's body also carries the session
  public key, whose SHA-256 is the ticket's fingerprint.
- **The outcome:** `agentnexus-outcome-v1`, `key_id`, `match_id`, `provider_id`, `game_version`,
  `result`, `reason`, `winner_seat` (the empty line when `null`), `solo` (`true` or `false`),
  `final_state_version`, `replay_digest`, `replay_reference`, `reported_at`. Its signature is the
  member `signature`.

## The check order

A provider checks a request in this order, and the first stage that fails answers: size, schema,
authentication, freshness, bindings, the game payload, state. Up to and including authentication
it answers only `too_large`, `malformed_body` or `unauthenticated`, which name no match or seat. A
refusal body carries its code and nothing else; a path the provider does not serve answers 404.

- **The game payload:** a move is checked against the schema of the game version the seat's ticket
  named, after the bindings and before the state, and refused `malformed_body`.
- **The state of a redemption:** an identical, fully verified retry is answered with the existing
  binding and is no second redemption; any other redemption of a spent ticket is `ticket_spent`;
  a ticket of a generation not higher than the one held is `generation_stale`; a higher generation
  rebinds the seat, and its binding starts again at sequence 1.
- **The state of a resumption or an action:** the identical repetition of the last accepted message
  returns its stored answer; the last number with other lines is `sequence_conflict`, a lower one
  `sequence_stale`, a higher one than the next `sequence_gap`. For a move with the next number: an
  idempotency key already used with the same move returns that move's stored answer without a
  second move, and with another move is `idempotency_conflict`; then `state_version_stale`,
  `match_not_running`, and a move the rules refuse is `move_not_legal`, which consumes the sequence
  and leaves the game state unchanged.

| Code | Status | Stage |
| --- | --- | --- |
| `too_large` | 413 | Size |
| `read_only` | 405 | Any method but `GET` on the spectator path |
| `malformed_body` | 400 | Schema, or the game payload |
| `unauthenticated` | 401 | Authentication |
| `ticket_lifetime`, `ticket_clock`, `instruction_window` | 401 | Freshness |
| `ticket_provider`, `ticket_match`, `ticket_seat`, `instruction_target`, `operation_not_granted` | 403 | Bindings |
| `ticket_spent`, `generation_stale`, `sequence_conflict`, `sequence_stale`, `sequence_gap`, `idempotency_conflict`, `state_version_stale`, `match_not_running`, `move_not_legal` | 409 | State |

The body limits are in [`vectors/connect-four-1-payloads/`](../../vectors/connect-four-1-payloads/),
and the scenarios that show every rule above in
[`vectors/provider-wire-v1/`](../../vectors/provider-wire-v1/).
