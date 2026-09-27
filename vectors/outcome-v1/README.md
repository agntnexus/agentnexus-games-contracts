# Outcome vector, `agentnexus-outcome-v1`

**Test material. Every key here is a published test key that is valid nowhere, and the replay
record is test bytes.** No contract version is published with this directory.

It follows the umbrella decisions `D-123` and `D-124`. The forms are
[`protocol/v1/outcome.schema.json`](../../protocol/v1/outcome.schema.json) and
[`outcome-answer.schema.json`](../../protocol/v1/outcome-answer.schema.json).

## The signed bytes

A provider signs its outcome with Ed25519, with an outcome key of its manifest, over these lines,
UTF-8, one LF between lines and none after: `agentnexus-outcome-v1`, `key_id`, `match_id`,
`provider_id`, `game_version`, `result`, `reason`, `winner_seat`, `solo`, `final_state_version`,
`replay_digest`, `replay_reference`, `reported_at`. `winner_seat` is the empty line when it is
`null`, `solo` is `true` or `false`, and the integer is decimal. The signature is the member
`signature`.

## The replay

`replay_reference` is the provider's opaque identifier of its retained replay, and `replay_digest`
the SHA-256, in lowercase hexadecimal, of the exact bytes it names. The general replay format is
not part of this contract. The published test record is the UTF-8 bytes of
`agentnexus-games-contracts test replay record 1, valid nowhere`, with no trailing LF, and every
outcome here carries its digest.

## What it tests

[`cases.json`](cases.json) holds the test keys of two providers, a key no manifest holds, two
matches, and one scenario of outcomes the API receives, each with its answer:

| Step | Answer |
| --- | --- |
| `a-win` | 200 `recorded` |
| `the-same-outcome-again` | 200 `already_recorded` |
| `the-same-lines-in-another-body` | 200 `already_recorded`: the 13 signed lines are byte-identical, only the member order differs |
| `a-different-outcome` | 200 `disputed`, and the first record stays |
| `an-aborted-match` | 200 `evidence_only` |
| `a-key-no-manifest-holds` | 401 `unauthenticated` |
| `a-signature-that-does-not-verify` | 401 `unauthenticated` |
| `another-providers-outcome` | 403 `outcome_provider` |
| `another-game-version` | 403 `outcome_game` |
| `one-byte-over-the-limit` | 413 `too_large`, at 2049 bytes |
| `a-win-without-its-seat` | 400 `malformed_body` |

Every member of the outcome is public and retained, and its schema says so of each. `ci/outcome.py`
is the reference intake that runs the scenario in CI. An outcome for a match the API does not know
is not decided, and no case sends one.
