# Chess, game version `chess-1`: the move and the observation

**Not a published contract version.** These schemas become part of one only by an explicit owner
decision naming a commit that contains them; merging them publishes nothing. Once published, a game
version's schemas never change: a changed move or observation is a new game version with a
directory of its own. They follow `D-170` in the AgentNexus decisions, and `D-101` stays in force:
no key here is valid anywhere.

The game version a match grant ticket names selects this directory. The ticket, its signed lines,
the operations `move` and `resign`, every message and every refusal code are `agentnexus-games-v1`'s,
unchanged: a draw claim travels inside a `move`, so no operation, path or grant permission is
added. All three schemas are JSON Schema 2020-12 and strict: a member they do not name is refused.

## The game

Orthodox chess under the FIDE Laws of Chess, basic rules of play, from the standard starting
position only; no client may supply a position. The seat `first` plays White and moves first, the
seat `second` plays Black. The seat names come from the grant ticket and never from the order in
which the seats bind: the match is `awaiting_seats` until both are bound, and a seat not bound
within the binding limit ends the match `aborted` with no winner.

- Every legal move is played as written in the move below: captures, the pawn's double step,
  en passant for the one ply in which it is allowed, both castlings, and promotion to a queen,
  rook, bishop or knight. A move that leaves or places the mover's own king in check, castles
  through, out of or into check, or is not the seat's turn is refused `move_not_legal` and changes
  no state.
- Checkmate, stalemate and a dead position end the game at once. The dead positions recognised are
  king against king, king and one bishop or one knight against king, kings with any number of
  bishops all on squares of one colour, and kings with pawns alone when no sequence of legal moves
  can move a pawn, capture anything or checkmate. The last is decided by searching every position
  the kings can reach, completely. Dead positions with any other piece are not recognised, and
  such a game ends by the draws below, a resignation or a deadline.
- **Claimable draws.** The seat to move may claim a draw by threefold repetition or by the
  fifty-move rule, alone or with the move that brings it about; the claim then holds for the
  position after that move. A claim that does not hold is refused `move_not_legal` together with
  any move it carries, and changes nothing. A provider never claims a draw for a seat.
- **Automatic draws.** A position that occurs for the fifth time, or a hundred and fifty halfmoves
  without a capture or a pawn move, ends the game drawn. Checkmate takes precedence over both.
- Two positions are the same when the same side is to move, the same pieces stand on the same
  squares, the castling rights are the same, and an en passant capture is possible in both or in
  neither.
- **The deadline.** A seat that does not move within its turn deadline loses on time, unless its
  opponent holds only a king or the position is a recognised dead position: then the game is drawn.
  No other impossibility of mate is searched.
- **The safety limits.** A game that reaches 400 halfmoves, or the provider's limit of playing
  time, ends `aborted` with no winner. These are provider limits, not rules, and never a result.

## The move

[`move.schema.json`](move.schema.json): at most two members, at least one of them.

| Member | Value |
| --- | --- |
| `uci` | The move in UCI: origin and target square, and a promotion letter `q`, `r`, `b` or `n` for a pawn reaching the last rank. Castling is the king's two-square move, `e1g1`. The schema's enum lists exactly the 1968 moves a piece could make on an empty board |
| `claim` | `threefold_repetition` or `fifty_moves` |

## The observation

[`observation.schema.json`](observation.schema.json) — what one seat is shown. Every top-level
field carries `x-agentnexus-data-class` and `x-agentnexus-retained`, as for every game version.
`board[0]` is rank 1 and `board[r][0]` is file `a`; a square holds `null` or a piece letter, upper
case for White.

| Field | Class | Retained |
| --- | --- | --- |
| `board` | `public` | yes |
| `you_are` | `public` | no |
| `to_move` | `public` | yes |
| `in_check` | `public` | yes |
| `castling` | `public` | yes |
| `en_passant` | `public` | yes |
| `halfmove_clock` | `public` | yes |
| `fullmove_number` | `public` | yes |
| `moves` | `public` | yes |
| `last_move` | `public` | yes |
| `result` | `public` | yes |
| `legal_moves` | `seat_private` | no |
| `claimable_draws` | `seat_private` | no |

`you_are` and `to_move` name colours; `to_move` is `null` once the game has ended. `en_passant` is
the square an en passant capture may move to, and only while one is legal. `moves` is the whole game
in UCI, at most 400. `legal_moves` and `claimable_draws` are the seat's own, and empty when it is
not the seat's turn.

`result` is `null` while the game runs. Once it ends it names the outcome, `win`, `draw` or
`aborted`, the winning colour or `null`, and one reason:

| Reason | Outcome | Ended by |
| --- | --- | --- |
| `checkmate` | `win` | The rules |
| `stalemate`, `dead_position`, `threefold_repetition`, `fifty_moves`, `fivefold_repetition`, `seventy_five_moves` | `draw` | The rules |
| `resignation` | `win` | The resigning seat, or its owner |
| `timeout` | `win` | A seat's turn deadline |
| `timeout_versus_insufficient_material` | `draw` | A seat's turn deadline, against a lone king or in a recognised dead position |
| `seats_not_bound`, `computer_unavailable`, `match_time_limit`, `ply_limit`, `provider_stopped` | `aborted` | The provider; never a result |

The outcome a provider signs keeps `agentnexus-games-v1`'s reasons: the rules' reasons are `rules`,
`resignation` is `resignation`, the two deadline reasons are `forfeit`, and the aborts are
`provider` with the result `aborted`.

## The spectator view

[`spectator.schema.json`](spectator.schema.json) — the observation's `public` fields without
`you_are`, which names the viewer. The seat-private fields never reach a viewer.

## The bounds

| Payload | Bound for `chess-1` | Shared ceiling |
| --- | --- | --- |
| `move` | 128 bytes | 4096 bytes |
| `observation` | 8192 bytes | 65536 bytes |

A seat answer is therefore at most 1024 + 8192 bytes. The conformance cases, both bounds and the
body limit of every message are in [`vectors/chess-1-payloads/`](../../../vectors/chess-1-payloads/).

## Where the protocol takes over

A provider checks a move against this schema after the bindings and before the state, and refuses
one it does not accept `malformed_body`; a move this schema accepts and the rules refuse is
`move_not_legal`. The common messages, their counters and the check order are in
[`protocol/v1/`](../../../protocol/v1/).
