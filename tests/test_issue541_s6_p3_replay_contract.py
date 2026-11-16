"""S6-only fail-closed P0 contract for the approved 400W/100us two-case P3 replay.

No runtime, dispatch, acceptance promotion, or mutable API calls are performed.
Historical ZIP hashes are verified separately in the #541 retention readback.
"""
import hashlib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
REPLAY = ROOT / ".github/workflows/issue541-arch-s6-p3-p4-replay.yml"
ORIGINAL_LIVE = ROOT / ".github/workflows/issue402-hybrid-json-s6-p3-p4-once.yml"
ORIGINAL_ARCHIVE = ROOT / "docs/development/archive/issue402-hybrid-json-s6-p3-p4-once.yml.txt"
ORIGINAL = ORIGINAL_LIVE if ORIGINAL_LIVE.is_file() else ORIGINAL_ARCHIVE
ORIGINAL_BLOB = "485439a723584ca5bbc8632a86c53574b0b1eb9a"
OCI_DIGEST = "2c3352da4f5c1b2ae98475fc01463ad0cdbc6ce7d221ce55055ddea152182008"
APPROVAL = "ISSUE541_S6_400W_100US_BOTH_CASES_APPROVED"


def _need(predicate: bool, reason: str) -> None:
    if not predicate:
        raise ValueError("S6_P3_CONTRACT_" + reason)


def _blob(text: str) -> str:
    content = text.encode("utf-8")
    return hashlib.sha1(b"blob " + str(len(content)).encode() + b"\0" + content).hexdigest()


def validate(workflow: str, original: str) -> None:
    _need(_blob(original) == ORIGINAL_BLOB, "ORIGINAL_BYTE_IDENTITY")
    _need("\non:\n" in workflow and "\npermissions:" in workflow, "TRIGGER_PARSE")
    trigger = workflow.split("\non:\n", 1)[1].split("\npermissions:", 1)[0]
    _need(trigger.startswith("  workflow_dispatch:\n"), "MANUAL_TRIGGER")
    for event in ("push", "pull_request", "workflow_call", "schedule", "repository_dispatch"):
        _need("\n  " + event + ":" not in trigger, "AUTO_EVENT_" + event)
    _need("      source_sha:" in trigger and "      p3_approval:" in trigger,
          "REQUIRED_INPUTS")
    _need(trigger.count("        required: true") == 2, "TWO_REQUIRED_INPUTS")
    _need('test "$GITHUB_EVENT_NAME" = "workflow_dispatch"' in workflow,
          "EVENT_CHECK")
    _need('test "$APPROVAL" = "' + APPROVAL + '"' in workflow, "COST_APPROVAL")
    _need('test "$REQUESTED_SHA" = "$GITHUB_SHA"' in workflow, "SOURCE_IDENTITY")
    _need(workflow.index("Fail closed unless both") < workflow.index("uses: actions/checkout@"),
          "GATE_MUST_PRECEDE_CHECKOUT")
    _need("case: ['417', '941']" in workflow and "fail-fast: false" in workflow,
          "TWO_INDEPENDENT_CASES")
    _need("max-parallel: 2" in workflow and "timeout-minutes: 360" in workflow,
          "COST_AND_TIMEOUT_BOUND")
    _need("OXYGEN_RESEARCH_400: '1'" in workflow and
          "OXYGEN_RESEARCH_QUICK_5MIN: '0'" in workflow and
          "--timeout-seconds 18000" in workflow, "FULL_100US_NOT_QUICK")
    _need("physics-build-base@sha256:" + OCI_DIGEST in workflow and
          "HISTORICAL_SHA: 29d1acc6ef7969908b86719e4b95c73a1565136d" in workflow,
          "SOURCE_AND_OCI_PINS")
    _need(workflow.count("native_p1_identity.json") >= 2 and
          '"binary_sha256":hash_file(binary)' in workflow, "BINARY_RECEIPT")
    _need("--case \"\u0024{{ matrix.case }}\"" in workflow and
          "--hybrid-json" in workflow and "--authorize-p3" in workflow,
          "ACTUAL_P3_CASE_COMMAND")
    _need('x["P3"]=="PASS"' in workflow and
          'x["P4"]=="DIAGNOSTIC_ONLY"' in workflow and
          'x["science"]=="SCIENCE_HOLD"' in workflow, "P3_VS_P4_SCIENCE")
    _need('Path(os.environ["RUNNER_TEMP"])' in workflow and
          'Path("$RUNNER_TEMP")' not in workflow, "POST_SOLVE_PATH")
    _need("if: always()" in workflow and
          "if-no-files-found: error" in workflow and
          "retention-days: 45" in workflow and
          "results/**" in workflow, "FAIL_CLOSED_ARTIFACT")
    _need("tests/test_issue541_s6_p3_replay_contract.py" in workflow,
          "S6_NEGATIVE_TEST_HOOK")


def test_retired_s6_original_remains_byte_pinned() -> None:
    # Archived original is source evidence, not an executable GitHub workflow.
    # Never accept missing archival evidence or changed original bytes.
    if not ORIGINAL_LIVE.is_file():
        _need(ORIGINAL_ARCHIVE.is_file(), "ARCHIVED_ORIGINAL_MISSING")
    _need(_blob(ORIGINAL.read_text()) == ORIGINAL_BLOB, "ORIGINAL_BYTE_IDENTITY")


def test_original_and_manual_replay_p0() -> None:
    validate(REPLAY.read_text(), ORIGINAL.read_text())


@pytest.mark.parametrize(
    ("before", "after"),
    [
        ("  workflow_dispatch:", "  push:"),
        ("  workflow_dispatch:", "  schedule:"),
        ('test "$APPROVAL" = "' + APPROVAL + '"', "true"),
        ('test "$REQUESTED_SHA" = "$GITHUB_SHA"', "true"),
        ('test "$GITHUB_EVENT_NAME" = "workflow_dispatch"', "true"),
        ("case: ['417', '941']", "case: ['417']"),
        ("fail-fast: false", "fail-fast: true"),
        ("max-parallel: 2", "max-parallel: 1"),
        ("timeout-minutes: 360", "timeout-minutes: 1"),
        ("OXYGEN_RESEARCH_QUICK_5MIN: '0'", "OXYGEN_RESEARCH_QUICK_5MIN: '1'"),
        ("--authorize-p3", "--deny-p3"),
        ('Path(os.environ["RUNNER_TEMP"])', 'Path("$RUNNER_TEMP")'),
        ('x["P4"]=="DIAGNOSTIC_ONLY"', 'x["P4"]=="SCIENCE_PASS"'),
        ('x["science"]=="SCIENCE_HOLD"', 'x["science"]=="SCIENCE_ACCEPTED"'),
        ("if: always()", "if: success()"),
        ("if-no-files-found: error", "if-no-files-found: warn"),
        ("retention-days: 45", "retention-days: 1"),
        ("native_p1_identity.json", "missing_p1_identity.json"),
        ("--timeout-seconds 18000", "--timeout-seconds 10"),
    ],
)
def test_reject_live_replay_mutations(before: str, after: str) -> None:
    original = ORIGINAL.read_text()
    workflow = REPLAY.read_text()
    assert before in workflow, before
    with pytest.raises(ValueError, match="S6_P3_CONTRACT_"):
        validate(workflow.replace(before, after, 1), original)


def test_reject_forged_historical_source() -> None:
    with pytest.raises(ValueError, match="ORIGINAL_BYTE_IDENTITY"):
        validate(REPLAY.read_text(), ORIGINAL.read_text() + "# unapproved mutation\n")
