# Provider manifest vector, `agentnexus-manifest-v1`

**Test material.** The outcome key is a published test key that is valid nowhere, the origins are
documentation hosts, and the turn deadline, action rate and retention are illustrative numbers,
not values: those belong to `#82` and `#87`. No contract version is published with this directory.

It follows the umbrella decisions `D-123` and `D-124`. Admission is administrative and belongs to
`#87`; this vector shows only the manifest's form, [`protocol/v1/manifest.schema.json`](../../protocol/v1/manifest.schema.json),
and the check that a manifest fits this contract.

## What it tests

[`cases.json`](cases.json) holds one manifest the check accepts and, beside it, one manifest for
every rule the check refuses. Each refused manifest differs from the accepted one in one member
only, so its refusal can come from nothing but the rule it breaks.

| Refused for | Because |
| --- | --- |
| `contract_version` | None of its contract versions is one this contract implements |
| `game_version` | A game version has no directory in [`games/`](../../games/) |
| `operations` | The operations are not exactly `move` and `resign` |
| `origin` | An origin is not `https` |
| `schema` | The form breaks: an IP address as host, a path after the origin, a trailing slash, port 0 or 65536, a zero deadline, rate or retention, a version number instead of its name, five origins, an unknown member |

`ci/manifest.py` is the reference check that runs every case in CI.
