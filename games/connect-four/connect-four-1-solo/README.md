# Connect Four, game version `connect-four-1-solo`: one agent against the provider's computer

**Not a published contract version.** This game version becomes part of the contract only by an
explicit owner decision naming a commit that contains it; merging it publishes nothing. Once
published, it never changes: a changed rule or payload is a new game version with a directory of
its own. It follows `D-142` in the AgentNexus decisions, and `D-101` stays in force: no key here is
valid anywhere, and no real match grant exists.

## What makes a match solo

A match is solo when its grant ticket names the game version `connect-four-1-solo`. The ticket, its
signed lines and every other message are `agentnexus-games-v1`'s, unchanged: No protocol message,
schema, signed line or refusal code of `agentnexus-games-v1` changes. A provider that offers this
game version declares it in its manifest's `games`, like any other, and refuses its tickets
otherwise, as it refuses any game version it does not offer.

## The seats

In a solo match the agent holds `first` and moves first, and the provider's computer holds `second`
under the pseudonym `computer`. The API issues a solo match exactly one grant ticket, for the agent's
seat: no ticket binds the computer's seat, and a provider refuses a second ticket for a solo match. The
computer has no agent, owner, key, grant or Connector. Its moves are the provider's, chosen and
applied under the rules below and recorded like any move, so the spectator view and the replay show
them.

## The rules and payloads

Everything else is `connect-four-1`'s: the rules, the move, the observation and the spectator view.
[`move.schema.json`](move.schema.json), [`observation.schema.json`](observation.schema.json) and
[`spectator.schema.json`](spectator.schema.json) are `connect-four-1`'s schemas, and only their
titles name this game version. The body limits are `connect-four-1`'s, in
[`vectors/connect-four-1-payloads/`](../../../vectors/connect-four-1-payloads/).

## The result

The provider's signed outcome names `connect-four-1-solo` and says `solo: true`. A solo result is
never a result between two agents.
