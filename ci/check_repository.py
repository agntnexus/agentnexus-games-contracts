"""Check what this repository may hold, and how its CI may run.

This is the public home of the AgentNexus Games provider protocol: versioned contracts, JSON
Schemas and test vectors, and nothing else. It is public so that a third party can implement a
provider without private access, and that is also why it has to stay free of anything operational
and why its CI may never reach an operator's machine.

Every rule here refuses rather than warns, and the script exits non-zero if any refusal is found.
It reads the files of the working tree only: no network, no credential, no other repository.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Final

#: The files this repository holds today, each by name. Contract, schema and vector files are added
#: to this list by the reviewed change that adds them; anything else is a third kind of file nobody
#: decided on.
DECLARED: Final = frozenset(
    {
        ".github/workflows/ci.yml",
        "LICENSE",
        "README.md",
        "SECURITY.md",
        "ci/check_repository.py",
        "ci/test_repository.py",
        "ci/grant_ticket.py",
        "ci/test_grant_ticket.py",
        "vectors/grant-ticket-v1/README.md",
        "vectors/grant-ticket-v1/verification.json",
    }
)

#: The Apache License 2.0, byte for byte as published, with line endings normalised to LF.
LICENSE_SHA256: Final = (
    "c95bae1d1ce0235ecccd3560b772ec1efb97f348a79f0fbe0a634f0c2ccefe2c"
)

#: Runtime code, by suffix or by name. The only code this repository holds is its own check, under
#: `ci/`, which runs in CI and nowhere else.
RUNTIME_SUFFIXES: Final = frozenset(
    {
        ".py", ".pyw", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".go", ".rs", ".java",
        ".kt", ".rb", ".php", ".cs", ".c", ".cc", ".cpp", ".h", ".hpp", ".swift", ".sh",
        ".bash", ".ps1", ".bat", ".cmd", ".exe", ".dll", ".so", ".dylib", ".wasm", ".jar",
    }
)  # fmt: skip
RUNTIME_NAMES: Final = frozenset(
    {
        "Dockerfile",
        "Containerfile",
        "Makefile",
        "package.json",
        "pyproject.toml",
        "setup.py",
        "go.mod",
        "Cargo.toml",
        "pom.xml",
        "build.gradle",
    }
)
CI_CODE: Final = "ci/"

#: Local tool caches, never tracked and never part of the tree this checks.
NOT_CONTENT: Final = frozenset(
    {".git", "__pycache__", ".ruff_cache", ".pytest_cache", ".mypy_cache"}
)

#: Credential and private-host shapes, as the public Connector refuses them.
CREDENTIAL: Final = re.compile(
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----"
    r"|gh[pousr]_[A-Za-z0-9]{30,}"
    r"|github_pat_[A-Za-z0-9_]{30,}"
    r"|xox[abprs]-[A-Za-z0-9-]{10,}"
    r"|AKIA[0-9A-Z]{16}"
    r"|[a-z0-9][a-z0-9-]*\.tail[0-9a-z]+\.ts\.net"
    # Split so that this file does not match its own pattern.
    r"|-----BEGIN AGE ENCRYPTED"
    r" FILE-----"
)

#: What a workflow may select to run on: a GitHub-hosted Ubuntu image, named literally.
HOSTED_RUNNER: Final = re.compile(r"^\s*runs-on:\s*ubuntu-(?:latest|\d{2}\.\d{2})\s*$")
RUNS_ON: Final = re.compile(r"^\s*runs-on:")
SECRET: Final = re.compile(r"\$\{\{\s*(?:secrets\.|github\.token\b)", re.IGNORECASE)
PRIVILEGED_TRIGGER: Final = re.compile(
    r"^\s*(?:pull_request_target|workflow_run)\s*:", re.MULTILINE
)
READ_ONLY: Final = re.compile(
    r"^permissions:\s*\n\s+contents:\s*read\s*$", re.MULTILINE
)
WRITE: Final = re.compile(r":\s*write\b|permissions:\s*write-all", re.IGNORECASE)
USES: Final = re.compile(r"^\s*(?:-\s*)?uses:\s*([^\s@]+)", re.MULTILINE)
CHECKOUT: Final = re.compile(r"uses:\s*actions/checkout@")
KEEPS_NO_CREDENTIAL: Final = re.compile(r"persist-credentials:\s*false\b")


def _files(root: Path) -> list[str]:
    found = []
    for path in root.rglob("*"):
        parts = path.relative_to(root).parts
        if path.is_file() and not NOT_CONTENT.intersection(parts):
            found.append(path.relative_to(root).as_posix())
    return sorted(found)


def _text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8").replace("\r\n", "\n")
    except UnicodeDecodeError:
        return None


def _check_workflow(relative: str, text: str) -> list[str]:
    refusals = []
    for line in text.splitlines():
        if RUNS_ON.match(line) and not HOSTED_RUNNER.match(line):
            refusals.append(
                f"{relative}: `{line.strip()}` is not a GitHub-hosted Ubuntu runner; a public "
                "pull request must never run on an operator's machine"
            )
    if SECRET.search(text):
        refusals.append(
            f"{relative}: uses a secret or the job token; CI here needs neither"
        )
    if PRIVILEGED_TRIGGER.search(text):
        refusals.append(
            f"{relative}: uses a privileged trigger that runs with repository access"
        )
    if not READ_ONLY.search(text) or WRITE.search(text):
        refusals.append(
            f"{relative}: is not read-only; it must declare `contents: read` only"
        )
    if len(CHECKOUT.findall(text)) != len(KEEPS_NO_CREDENTIAL.findall(text)):
        refusals.append(
            f"{relative}: a checkout keeps its credential; set persist-credentials"
        )
    third_party = sorted(
        {name for name in USES.findall(text) if not name.startswith("actions/")}
    )
    if third_party:
        refusals.append(
            f"{relative}: uses a third-party action: {', '.join(third_party)}"
        )
    return refusals


def check(root: Path) -> list[str]:
    """Return every refusal for the tree at `root`; an empty list means it holds."""
    refusals: list[str] = []
    files = _files(root)

    for relative in files:
        name = relative.rsplit("/", 1)[-1]
        suffix = "." + name.rsplit(".", 1)[-1] if "." in name else ""
        if not relative.startswith(CI_CODE) and (
            suffix in RUNTIME_SUFFIXES or name in RUNTIME_NAMES
        ):
            refusals.append(f"{relative}: runtime code; this repository holds none")
        elif relative not in DECLARED:
            refusals.append(
                f"{relative}: undeclared; add it to DECLARED deliberately, or remove it"
            )

    licence = root / "LICENSE"
    text = _text(licence) if licence.is_file() else None
    if (
        text is None
        or hashlib.sha256(text.encode("utf-8")).hexdigest() != LICENSE_SHA256
    ):
        refusals.append("LICENSE: is not the unmodified Apache-2.0 licence text")

    for relative in files:
        text = _text(root / relative)
        if text is None:
            continue
        if relative.endswith(".json"):
            try:
                json.loads(text)
            except json.JSONDecodeError as error:
                refusals.append(f"{relative}: not valid JSON ({error.msg})")
        if CREDENTIAL.search(text):
            refusals.append(
                f"{relative}: contains something shaped like a credential or host"
            )
        if relative.startswith(".github/workflows/"):
            refusals.extend(_check_workflow(relative, text))

    return refusals


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    refusals = check(root)
    for refusal in refusals:
        print(f"REFUSED  {refusal}")
    if refusals:
        return 1
    print(
        f"{len(_files(root))} declared files, no runtime code, the Apache-2.0 licence unchanged;"
    )
    print(
        "workflows GitHub-hosted and read-only, without secrets or third-party actions."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
