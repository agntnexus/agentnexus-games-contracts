# Connect Four payload and size-limit vector, game version `connect-four-1`

**Test material. No case here is a move in a real match, and no contract version is published with
this file.**

## What it tests

[`cases.json`](cases.json) checks the schemas in
[`games/connect-four/connect-four-1/`](../../games/connect-four/connect-four-1/) and the size limits
`D-118` fixes:

| Cases | What each one holds | Expected |
| --- | --- | --- |
| `move_cases` | a move | `valid` or `invalid` against the move schema |
| `observation_cases` | an observation | `valid` or `invalid` against the observation schema |
| `payload_size_cases` | a valid payload, padded with spaces to a length | `within_bound` or `over_bound` its game bound |
| `message_size_cases` | a message and a body length | `within_limit`, or `over_limit` with the refusal it gets |

Every invalid case breaks one rule and says which in `because`. The size cases sit at the edge of
each bound and limit: one exactly at it, one a byte over.

## The limits

`shared_ceilings` holds the ceiling no game bound may exceed: 4096 bytes for a move, 65536 for an
observation. `message_limits` holds each message's body limit as fixed bytes, plus a payload bound
where the message carries a payload:

| Message | Limit | Over the limit |
| --- | --- | --- |
| redemption | 4096 | refused `too_large` |
| resumption | 1024 | refused `too_large` |
| action | 1024 + the move ceiling = 5120 | refused `too_large` |
| resignation instruction | 2048 | refused `too_large` |
| resignation acknowledgement | 1024 | not refused with a code; the reader stops reading |
| seat answer | 1024 + the observation's game bound = 3072 for `connect-four-1` | not refused with a code; the reader stops reading |
| refusal | 1024 | not refused with a code; the reader stops reading |

A message the provider receives over its limit is refused `too_large` before it is parsed. An answer
is not refused with a code; its reader stops reading and treats it as a provider fault. A limit is a
bound the contract sets, not the largest message a schema allows: JSON can spell a valid body at any
length.

A size case measures the UTF-8 bytes of the text it builds: the payload's compact JSON followed by
spaces up to `pad_to_bytes`, or a body of `length` bytes. `ci/game_payloads.py` is the reference
check that runs every case in CI.

## What it does not fix

How a verifier finds a payload's bytes inside a body, to measure it against its bound, is not
fixed. The payload cases give a verdict — `invalid` or `over_bound` — and name no code; where a
payload is checked in the refusal order, and with which code, is in
[`protocol/v1/`](../../protocol/v1/).
