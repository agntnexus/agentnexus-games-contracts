# Chess provider wire vector

**Test material. No ticket here is a grant, and every key here is a published test key that is
valid nowhere.** A deployment that accepts one of these keys is misconfigured. No contract version is
published with this directory.

It runs the provider wire of [`protocol/v1/`](../../protocol/v1/) (`D-114`, `D-123`) for the game
versions `chess-1` and `chess-1-solo` (`D-170`), whose schemas are in
[`games/chess/`](../../games/chess/) and whose body limits are in
[`vectors/chess-1-payloads/`](../chess-1-payloads/). The wire, the signed lines and the check order
are exactly those of [`vectors/provider-wire-v1/`](../provider-wire-v1/), and so are the keys: the
same grant key, unheld grant key and session keys, from the same published seeds.

## What it tests

[`cases.json`](cases.json) holds seven tickets and four scenarios. Each scenario starts from a
provider that holds nothing. The seat `first` plays White and `second` plays Black (`CH-5`). A seat
resumes before it moves, as a Connector does, so that its expected state version is the match's.

| Scenario | Shows |
| --- | --- |
| `bind-both-and-play` | The first seat's binding answers `awaiting_seats`; its move before the second seat binds is `move_not_legal` and consumes the sequence; the second binding makes the match `active`; White and Black play `e2e4` and `e7e5`; a repeated move gets its stored answer |
| `chess-refusals` | Black before White, `e2e5` and a `fifty_moves` claim that does not hold, each `move_not_legal`; `e2e9`, a Connect Four `{"column": 3}` and an empty move, each `malformed_body` from `chess-1`'s move schema; then `e2e4` with the next sequence |
| `a-claimed-repetition` | Knights out and back twice; Black's last move carries `threefold_repetition`, ends the game drawn, and a later move is `match_not_running` |
| `solo` | In `chess-1-solo` the agent's binding is `active` at once, and the computer answers White's `e2e4` as Black in the same request |

Where a request passes every wire check, the step gives the answer the provider's game returns
(`provider_answer`); a move the rules refuse is marked `game_refuses`. Every answer was recorded from
AgentNexus's Chess provider at fixed times, so the observations are those of its rules.

## Reproducing it

Every key, fingerprint and signature is reproducible from this file, as for `provider-wire-v1`.
`ci/test_chess_wire.py` checks them on every change, runs each scenario through the same reference
check, `ci/provider_wire.py`, which must give every step its published answer, checks every
observation and move against its Chess schema, and checks that the answers record the game played,
move by move and by the side to move.

## What it does not fix

What `provider-wire-v1` leaves open stays open here. The resignation instruction, the spectator path,
the outcome interface, a ticket for a game version the provider does not offer, and the deadlines
are not run.
