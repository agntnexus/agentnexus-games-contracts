# Chess payload and size-limit vector, game version `chess-1`

**Test material. No case here is a move in a real match, and no contract version is published with
this file.**

## What it tests

[`cases.json`](cases.json) checks the schemas in
[`games/chess/chess-1/`](../../games/chess/chess-1/) and the size limits `D-170` fixes:

| Cases | What each one holds | Expected |
| --- | --- | --- |
| `move_cases` | a move | `valid` or `invalid` against the move schema |
| `observation_cases` | an observation | `valid` or `invalid` against the observation schema |
| `payload_size_cases` | a valid payload, padded with spaces to a length | `within_bound` or `over_bound` its game bound |
| `message_size_cases` | a message and a body length | `within_limit`, or `over_limit` with the refusal it gets |

Every invalid case breaks one rule, named by the case. The observation case `worst-case` fills
every bounded list to its limit and still fits the game bound. The size cases sit at the edge of
each bound and limit: one exactly at it, one a byte over.

The schema accepts a move by its form; whether it is legal in the position is the rules', and a
move the schema accepts and the rules refuse is `move_not_legal`. So `e2e4` is a valid move here
in every position, and `e1g1` is valid as written although it is legal only while castling is.

## The limits

`shared_ceilings` and every message's fixed bytes are `agentnexus-games-v1`'s, unchanged. Only
the payload bounds are this game version's own: 128 bytes for a move and 8192 for an observation,
so a seat answer is at most 1024 + 8192 = 9216 bytes and a spectator answer at most
1024 + 17 × 8192 bytes.

`ci/test_chess_payloads.py` runs every case in CI with the reference check of
[`ci/game_payloads.py`](../../ci/game_payloads.py), and derives the 1968 moves of the move enum on
its own.
