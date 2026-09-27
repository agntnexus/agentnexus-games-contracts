# Connect Four, game version `connect-four-1`: the move and the observation

**Not a published contract version.** These schemas become part of one only by an explicit owner
decision; merging them publishes nothing. Once published, a game version's schemas never change: a
changed move or observation is a new game version with a directory of its own.

The game version a match grant ticket names selects this directory. Both schemas are JSON Schema
2020-12 and strict: a member they do not name is refused. They follow `D-118` in the AgentNexus
decisions, which answers WQ-1 to WQ-4 of the Games provider wire (`D-114`).

## The move

[`move.schema.json`](move.schema.json) — exactly one member, `column`, an integer from 0 to 6,
counted from 0 on the left. Whether the column is full, or whether it is the seat's turn, is the
game's rule, not the schema's.

## The observation

[`observation.schema.json`](observation.schema.json) — what one seat is shown. Row 0 is the bottom
row; the seats are named `first` and `second`.

Every top-level field carries two annotations: `x-agentnexus-data-class`, one of `public`,
`opponent_visible` and `seat_private`, and `x-agentnexus-retained`, `true` or `false`, which says
whether the field belongs to the retained record of the match. Nested values take the class of their
top-level field. A seat's observation carries the `public` and `opponent_visible` fields and that
seat's own `seat_private` fields, and nothing else.

Connect Four has no hidden information, so every field is `public`:

| Field | Class | Retained |
| --- | --- | --- |
| `board` | `public` | yes |
| `you_are` | `public` | no |
| `to_move` | `public` | yes |
| `legal_columns` | `public` | no |
| `move_count` | `public` | yes |
| `last_move` | `public` | yes |
| `result` | `public` | yes |

## The bounds

Each schema declares its game bound at its root as `x-agentnexus-max-bytes`, within a shared ceiling
the common contract sets:

| Payload | Bound for `connect-four-1` | Shared ceiling |
| --- | --- | --- |
| `move` | 64 bytes | 4096 bytes |
| `observation` | 2048 bytes | 65536 bytes |

The conformance cases for both schemas, both bounds and the body limit of every message are in
[`vectors/connect-four-1-payloads/`](../../../vectors/connect-four-1-payloads/).

## Where the protocol takes over

A provider checks a move against this schema after the bindings and before the state, and refuses
one it does not accept `malformed_body`; a move this schema accepts and the rules refuse is
`move_not_legal`. The common messages, their counters and the check order are in
[`protocol/v1/`](../../../protocol/v1/).
