# Grant ticket verification vector, format v1

**Test material. No ticket here is a grant, and every key here is a published test key that is
valid nowhere.** A deployment that accepts one of these keys is misconfigured. No contract version is
published with this file.

## What it tests

A provider verifies a match grant ticket before it redeems it. `verification.json` holds two cases
for that step:

| Case | Expected |
| --- | --- |
| `control` | **accepted**: signed by the published test key, inside its window, and presented for its own provider, match and seat |
| `another-match` | **refused** on the match binding: the same ticket and signature, presented in another match |

Each case gives the ticket's fields, its signature, and the context the verifier checks it in: the
provider, the match and the seat being redeemed, and the time its clock reads. The grant
verification keys are listed once, each as a key ID and a raw 32-byte Ed25519 public key in
standard base64.

## The format it follows

The signature is Ed25519 over the UTF-8 bytes of these lines, in this order, joined by a single LF
with no trailing LF, and carried as standard base64:

```text
agentnexus-grant-v1
key_id
ticket_id
match_id
seat
provider_id
game_version
session_key_fingerprint
not_before
not_after
```

A verifier rebuilds those bytes from the fields and never verifies bytes it did not rebuild. It
refuses an unknown or missing field, a malformed field, an unknown key, a span longer than 120
seconds, a clock more than 30 seconds outside the window, and a provider, match or seat other than
the one being redeemed. `ci/grant_ticket.py` is the reference check that runs these cases in CI.

## Reproducing it

Each test seed is the SHA-256 of the phrase the file names, and Ed25519 signing is deterministic,
so anyone can regenerate the keys, the session key fingerprint and the signature from the file
alone. `ci/test_grant_ticket.py` does exactly that on every change.

## What it does not fix

- **The ticket's JSON wire form.** The format names the fields and "the signature", not the name
  of the signature's member. This file lists the fields and the signature as its own entries and
  defines no wire object.
- **The format of the provider ID and the game version.** They are values of the admitted provider
  manifest, whose format is not yet fixed. The values here are illustrative.
- **The session key proof** (P-2), **the operations a ticket permits** (P-3), redemption, error codes
  and every other message of the protocol.
