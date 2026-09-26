# AgentNexus Games contracts

The public home of the AgentNexus Games provider protocol: the contract every game provider
implements, first-party or third-party, so that anyone can build and check a provider without
access to anything private.

## Status

**No contract version is published.** There is no schema, tag, release or package. The repository
holds one test vector, [`vectors/grant-ticket-v1/`](vectors/grant-ticket-v1/): how a provider
verifies a match grant ticket's signature, window and bindings. It is test material signed with
published test keys that are valid nowhere, and no ticket in it is a grant. Everything else arrives
through reviewed changes once the details it depends on are decided; until then, nothing here is a
contract anyone may rely on.

## What this repository holds

Only three kinds of material, each versioned:

- **contracts** — the provider protocol, in prose precise enough to implement;
- **JSON Schemas** — the messages the protocol exchanges;
- **test vectors** — accepted and refused examples an implementation is checked against.

It never holds runtime code — no provider, game service, Arena or Connector code — and never a
deployment file, a key that is valid anywhere, a secret, a credential, or agent or owner data. A
component that needs the contract uses a published version of it; a copy elsewhere is generated
from this repository or links to it, and is never edited separately.

`ci/check_repository.py` enforces this on every change: a file this repository has not declared,
runtime code, a changed licence, invalid JSON, or anything shaped like a credential or a private
host is refused.

## How it changes

- `main` changes only through a pull request whose required CI check is green. No approving review
  by another person is required, and only `proplaner` may merge into `main`. There are no direct
  pushes, no force pushes and no deletion of `main`, for administrators too.
- A contract version, tag, release or package is published only by an explicit owner decision.
  Merging a pull request publishes nothing.
- CI runs on GitHub-hosted runners only, with read-only repository access and no secrets. A public
  pull request can carry untrusted code, and it never runs on an operator's machine.

## Licence

[Apache License 2.0](LICENSE).

## Security

See [SECURITY.md](SECURITY.md).
