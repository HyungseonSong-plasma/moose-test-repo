"""Fail-closed P0 contract for the FLOW Native P2 Actions trigger (#541/#14).

This checker validates the real source workflow and deliberate trigger mutations.
It does not execute Native P2 or authorize Physics P3.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest


WORKFLOW = (
    Path(__file__).resolve().parents[1]
    / ".github/workflows/issue402-flow-native-p2-regression.yml"
)

EXPECTED_GATE = """    if: >-
      github.event_name != 'pull_request' ||
      (github.event.pull_request.head.repo.full_name == 'HyungseonSong-plasma/moose-test-repo' &&
       (github.event.action != 'edited' || github.event.changes.base != null))"""

REQUIRED_SOURCE_PATHS = {
    ".github/workflows/issue402-flow-native-p2-regression.yml",
    ".github/workflows/issue402-rate-coef-ideal-gas-native-once.yml",
    ".github/workflows/issue402-reaction-reduction-native-once.yml",
    "physics_app/**",
    "experiments/Issue402_plasma_dsl_g1/**",
    "experiments/Issue493_s6_boltzmann/public_p2_check.py",
    "requirements-evidence-engine.txt",
    "requirements-ontology.txt",
}


def assert_flow_native_trigger_contract(source: str) -> None:
    assert "\non:\n" in source and "\npermissions:\n" in source
    trigger = source.split("\non:\n", 1)[1].split("\npermissions:\n", 1)[0]
    events = re.findall(r"^  ([A-Za-z_]+):", trigger, re.MULTILINE)
    assert events == ["pull_request", "workflow_dispatch"], events

    pr_trigger = trigger.split("  pull_request:\n", 1)[1].split(
        "  workflow_dispatch:\n", 1
    )[0]
    assert "    branches: [main]\n" in pr_trigger
    assert (
        "    types: [opened, synchronize, reopened, edited]\n" in pr_trigger
    )

    paths = re.findall(r"^      - '([^']+)'$", pr_trigger, re.MULTILINE)
    assert paths and len(paths) == len(set(paths)), "FLOW_TRIGGER_DUPLICATE_PATH"
    assert REQUIRED_SOURCE_PATHS.issubset(paths), "FLOW_TRIGGER_SOURCE_PATH_MISSING"

    # Every explicit pytest input consumed by this P0/P1/P2 workflow must
    # trigger a recheck on PR synchronize, not just C++/experiment changes.
    jobs = source.split("\njobs:\n", 1)[1]
    consumed_tests = set(
        re.findall(r"tests/(?:characterization/)?[A-Za-z0-9_.-]+\.py", jobs)
    )
    assert consumed_tests, "FLOW_TRIGGER_NO_TEST_CONSUMERS"
    assert consumed_tests.issubset(paths), (
        "FLOW_TRIGGER_TEST_PATH_MISSING",
        sorted(consumed_tests - set(paths)),
    )

    # PR title/body-only edits must not launch expensive Native P1/P2.
    # A base-branch edit is permitted when the path filter also matches.
    assert EXPECTED_GATE in jobs, "FLOW_TRIGGER_EDIT_OR_FORK_GATE_MISSING"

    # The exact source head must remain the PR source, not the merge commit.
    assert "EXPECTED_HEAD: ${{ github.event.pull_request.head.sha || github.sha }}" in jobs
    assert "ref: ${{ github.event.pull_request.head.sha || github.sha }}" in jobs


def test_current_flow_native_trigger_contract() -> None:
    assert_flow_native_trigger_contract(WORKFLOW.read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    ("needle", "replacement"),
    [
        (
            "types: [opened, synchronize, reopened, edited]",
            "types: [opened, synchronize, reopened]",
        ),
        ("\n  workflow_dispatch:\n", "\n  push:\n"),
        ("      - 'tests/test_issue541_flow_dbase_sheath_p2.py'\n", ""),
        ("      - 'tests/test_issue402_public_option_s6_p2.py'\n", ""),
        ("      - 'requirements-ontology.txt'\n", ""),
        (
            "      - 'experiments/Issue493_s6_boltzmann/public_p2_check.py'\n",
            "",
        ),
        ("github.event.changes.base != null", "true"),
        (
            "github.event.pull_request.head.repo.full_name == "
            "'HyungseonSong-plasma/moose-test-repo'",
            "true",
        ),
        ("    branches: [main]", "    branches: [main, feature]"),
    ],
)
def test_mutated_flow_native_trigger_fails_closed(
    needle: str, replacement: str
) -> None:
    original = WORKFLOW.read_text(encoding="utf-8")
    assert needle in original, "FLOW_TRIGGER_NEGATIVE_MUTATION_NOT_APPLIED"
    mutated = original.replace(needle, replacement, 1)
    assert mutated != original
    with pytest.raises(AssertionError):
        assert_flow_native_trigger_contract(mutated)
