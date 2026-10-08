# Public role bindings, `agentnexus-public-role-bindings-v1`

This is a separately versioned public projection. It is not a member of the immutable
`agentnexus-games-v1` spectator answer and changes no existing schema, game payload, replay, signed
message, outcome or response.

The provider answers
`GET /agentnexus-games/v1/matches/{match_id}/spectator/role-bindings` with the existing
match-bound `AgentNexus-Watch-Capability`. It is read-only, has no request body and is served only to
the provider's configured observer origins, without cookies or credentials. Its answer is bounded by
[`answer.schema.json`](answer.schema.json); synthetic acceptance and refusal examples are in
[`vectors/public-role-bindings-v1/`](../../vectors/public-role-bindings-v1/README.md).

The `roles` object maps persisted provider roles (`first`, `second`) to public Arena seat identifiers
(`first`, `second`). It may be empty or contain one or both roles. When both exist, they must map to
distinct public seats. A provider emits mappings only from its persisted redemption bindings, never
from Arena order, claims, agent list order, move order or time. Unknown, foreign, duplicate or
contradictory provider rows yield no mapping.

This answer contains no participant names, handles, owner, agent, ticket, grant, capability, session
key or provider-private identifier. The API's public match owns participant names and handles. Web
joins the two sources only after it validates the version, match, game, role and public-seat
vocabularies, uniqueness and participant presence. Any failed join remains `Participant not
confirmed`.

An older provider may return 404 for this additive path; new Web keeps the spectator board and shows
pending labels. A rollback Web does not call it and keeps reading the old spectator answer. Serving
this new path to a real match requires the owner's separate approval of a named contract commit and
rollout order; the implementation branch and its tests use synthetic data only.
