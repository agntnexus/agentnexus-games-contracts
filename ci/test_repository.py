"""Mutation cases for ci/check_repository.py.

Each case copies the repository into a temporary directory, breaks one rule, and requires the check
to refuse -- naming the rule, so a case cannot pass because some other rule happened to fire. The
unmodified copy has to pass, or every refusal below proves only that the check can fail.

Credential-shaped strings are assembled at run time, so this file does not itself trip the
credential rule it tests.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from check_repository import check

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = Path(".github/workflows/ci.yml")


@pytest.fixture
def tree(tmp_path: Path) -> Path:
    copy = tmp_path / "tree"
    shutil.copytree(
        REPOSITORY_ROOT,
        copy,
        ignore=shutil.ignore_patterns(
            ".git", "__pycache__", ".ruff_cache", ".pytest_cache"
        ),
    )
    return copy


def refused(tree: Path, rule: str) -> None:
    refusals = check(tree)
    assert any(rule in refusal for refusal in refusals), refusals


def edit(tree: Path, relative: Path, old: str, new: str) -> None:
    path = tree / relative
    text = path.read_text(encoding="utf-8")
    assert old in text, f"{old!r} is not in {relative}; this case would prove nothing"
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def test_the_repository_as_committed_passes(tree: Path) -> None:
    assert check(tree) == []


# What the repository may hold.


@pytest.mark.parametrize(
    "relative",
    [
        "notes.md",
        "contracts/v1/grant.schema.json",
        "docs/design.md",
        ".github/CODEOWNERS",
    ],
)
def test_an_undeclared_file_is_refused(tree: Path, relative: str) -> None:
    path = tree / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{}\n", encoding="utf-8")
    refused(tree, "undeclared")


@pytest.mark.parametrize(
    "relative",
    [
        "provider.py",
        "src/server.ts",
        "service/main.go",
        "tools/run.sh",
        "Dockerfile",
        "package.json",
        "pyproject.toml",
        "lib/grant.wasm",
    ],
)
def test_runtime_code_is_refused(tree: Path, relative: str) -> None:
    path = tree / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x\n", encoding="utf-8")
    refused(tree, "runtime code")


def test_a_changed_licence_is_refused(tree: Path) -> None:
    edit(tree, Path("LICENSE"), "Version 2.0", "Version 3.0")
    refused(tree, "Apache-2.0")


def test_a_missing_licence_is_refused(tree: Path) -> None:
    (tree / "LICENSE").unlink()
    refused(tree, "Apache-2.0")


def test_invalid_json_is_refused(tree: Path) -> None:
    (tree / "ci" / "broken.json").write_text("{not json\n", encoding="utf-8")
    refused(tree, "not valid JSON")


# How the workflows may run.


@pytest.mark.parametrize(
    "runner",
    [
        "self-hosted",
        "[self-hosted, linux]",
        "private-ci",
        "agntnexus-linux",
        "${{ matrix.runner }}",
        "windows-latest",
    ],
)
def test_a_runner_that_is_not_github_hosted_ubuntu_is_refused(
    tree: Path, runner: str
) -> None:
    edit(tree, WORKFLOW, "runs-on: ubuntu-latest", f"runs-on: {runner}")
    refused(tree, "GitHub-hosted")


def test_a_runner_group_is_refused(tree: Path) -> None:
    edit(
        tree,
        WORKFLOW,
        "runs-on: ubuntu-latest",
        "runs-on:\n      group: private-ci\n      labels: agntnexus-linux",
    )
    refused(tree, "GitHub-hosted")


def test_a_secret_is_refused(tree: Path) -> None:
    edit(
        tree,
        WORKFLOW,
        "    steps:\n",
        "    env:\n      T: ${{ secrets.TOKEN }}\n    steps:\n",
    )
    refused(tree, "secret")


def test_the_github_token_is_refused(tree: Path) -> None:
    edit(
        tree,
        WORKFLOW,
        "    steps:\n",
        "    env:\n      T: ${{ github.token }}\n    steps:\n",
    )
    refused(tree, "secret")


@pytest.mark.parametrize("trigger", ["pull_request_target", "workflow_run"])
def test_a_privileged_trigger_is_refused(tree: Path, trigger: str) -> None:
    edit(tree, WORKFLOW, "  pull_request:\n", f"  pull_request:\n  {trigger}:\n")
    refused(tree, "privileged trigger")


def test_a_write_permission_is_refused(tree: Path) -> None:
    edit(tree, WORKFLOW, "  contents: read\n", "  contents: write\n")
    refused(tree, "read-only")


def test_missing_permissions_are_refused(tree: Path) -> None:
    edit(tree, WORKFLOW, "permissions:\n  contents: read\n", "")
    refused(tree, "read-only")


def test_a_checkout_that_keeps_its_credential_is_refused(tree: Path) -> None:
    edit(tree, WORKFLOW, "persist-credentials: false", "persist-credentials: true")
    refused(tree, "persist-credentials")


def test_a_third_party_action_is_refused(tree: Path) -> None:
    edit(
        tree, WORKFLOW, "uses: actions/setup-python@v6", "uses: someone/setup-python@v6"
    )
    refused(tree, "third-party action")


# Nothing secret, in any file.


@pytest.mark.parametrize(
    "value",
    [
        "-----BEGIN " + "OPENSSH PRIVATE KEY-----",
        "ghp_" + "a" * 36,
        "github_pat_" + "b" * 40,
        "AKIA" + "ABCDEFGHIJKLMNOP",
        "host.tail" + "1234ab.ts.net",
    ],
)
def test_a_credential_or_private_host_is_refused(tree: Path, value: str) -> None:
    (tree / "README.md").write_text(
        (tree / "README.md").read_text(encoding="utf-8") + f"\n{value}\n",
        encoding="utf-8",
    )
    refused(tree, "credential")
