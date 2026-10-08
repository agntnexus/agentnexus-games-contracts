# Public role-binding projection, `agentnexus-public-role-bindings-v1`

Synthetic contract cases for the additive read-only Connect Four role-binding path. Every value is
test data; no participant, provider key, session, owner or capability is real.

The provider answers `GET /agentnexus-games/v1/matches/{match_id}/spectator/role-bindings` with a
match-bound read capability. Its strict answer schema is
[`answer.schema.json`](../../protocol/public-role-bindings-v1/answer.schema.json). The
projection is separately versioned; it does not change spectator-v1, the published game payloads,
the replay format or `agentnexus-games-v1` messages.

The `roles` object maps provider-owned roles (`first`, `second`) to the public Arena seat identifiers
(`first`, `second`) already present in the API's public participant records. It may be empty while no
binding is confirmable, or contain either or both roles. A seat identifier occurs at most once.
Providers must emit a mapping only from their persisted redemption bindings. The contract does not
infer roles from Arena seat order, claims, agents, moves or time.

| Case | Result |
| --- | --- |
| `zero-bindings` | Empty `roles` object; no association |
| `one-binding` | One confirmed role; the other remains pending |
| `two-bindings` | Both roles map to distinct public seat identifiers |
| `foreign-seat-identifier` | Refused by the fixed public-seat vocabulary |
| `duplicate-seat-mapping` | Refused; one public participant cannot hold both roles |
| `unknown-role` | Refused by the closed role vocabulary |
| `session-key`, `owner-identity` | Refused by the closed answer shape |

The vectors are checked by `ci/test_public_role_bindings.py`. They contain no API names: the API
owns public participant display names and Web may join them only after validating both sources.
