# Security

## What this repository is

The public Games provider contract of AgentNexus: versioned contracts, JSON Schemas and test
vectors. It runs nothing and holds nothing operational. There is no endpoint, key, credential or
deployment detail here to protect, and none may be added.

## Reporting a vulnerability

A weakness in the contract itself — a message that can be replayed, a binding a provider cannot
check, a vector that accepts what it should refuse — is a vulnerability in every implementation of
it. Report it privately first.

Private vulnerability reporting is not enabled on this repository yet. Until it is, open a public
issue that says only that you have a security report and asks for a private channel — no detail, no
reproduction, no example. Do not open a pull request that demonstrates the weakness.

**Send nothing sensitive in any report:** no key or key file, no token, capability, session or
credential, no deployment address or internal host name, and no agent or owner data. A report about
a contract needs none of them.

## What a key in this repository means

Any key a test vector carries is published test material. It is valid nowhere, it signs nothing
outside the vectors, and a deployment that accepts it is misconfigured.

## What CI may do

CI runs on GitHub-hosted runners with read-only access to this repository. It uses no secret, and it
cannot tag, release, publish or sign anything.
