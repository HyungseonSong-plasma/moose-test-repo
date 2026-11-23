#!/usr/bin/env python3
"""#665 P6 fail-closed source review for main's split CI owners.

The old 3,000-line ci.yml does not own Native jobs after repository CI
migration. Preserve the main-only general CI/template and require the three
actual P6 W1/New-only/Public-D jobs in physics-native-ci.yml. Source-only:
never launches an OCI build, private EI data, or a scientific solve.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/ci.yml"
TEMPLATE = ROOT / "ci/workflow_templates/general-ci.yml"
NATIVE = ROOT / ".github/workflows/physics-native-ci.yml"
DD = ROOT / "physics_app/src/physics/plasma/DDContinuityEq.C"

P6 = ("p6_newonly_s6_build", "p6_newonly_s6_native_p2",
      "p6_public_d_100row_native_p2")
HEAD_SCOPE = "github.event.pull_request.head.repo.full_name == 'HyungseonSong-plasma/moose-test-repo'"
EXPECTED_OCI = "ghcr.io/hyungseonsong-plasma/physics-build-base@sha256:2c3352da4f5c1b2ae98475fc01463ad0cdbc6ce7d221ce55055ddea152182008"
TYPE_COUNT = "assert len(expected_kernels)==12 and len(expected_bc)==12 and len(expected_e)==8"
CHECKED_HEAD = "github.event.pull_request.head.sha"
NETWORKLESS = "--network none"
REGRESSION_STEP = "Require explicit Public D KEEP_HOLD evidence, not Native D PASS"


def need(ok: bool, label: str) -> None:
    if not ok:
        raise ValueError("P6_SPLIT_CI_" + label)


def job_block(text: str, name: str) -> str:
    pattern = re.compile(r"(?m)^  " + re.escape(name) + r":\s*$")
    match = pattern.search(text)
    need(match is not None, "MISSING_JOB_" + name)
    tail = text[match.start():]
    other = re.search(r"(?m)^  [a-z][a-z0-9_-]*:\s*$", tail[match.end()-match.start():])
    if other:
        return tail[:match.end()-match.start()+other.start()]
    return tail


def validate(workflow: str, template: str, dd_source: str,
             *, native_source: str | None = None) -> None:
    native = NATIVE.read_text() if native_source is None else native_source
    need(workflow == template, "CANONICAL_BYTE_PARITY")
    need("  push:\n    branches: [main]" in workflow and
         "  pull_request:\n    branches: [main]" in workflow,
         "CANONICAL_MAIN_TRIGGERS")
    need("  workflow_dispatch:" not in workflow, "NO_MANUAL_GENERAL_CI")
    general_jobs = workflow.split("\njobs:\n", 1)
    need(len(general_jobs) == 2 and
         set(re.findall(r"(?m)^  ([a-z][a-z0-9_-]*):\s*$",
                        general_jobs[1])) == {"validate"},
         "CANONICAL_ONLY_VALIDATE_JOB")
    need(all(("  " + job + ":\n") not in workflow for job in P6),
         "NO_OLD_MONOLITHIC_NATIVE_JOBS")
    need(native.startswith("name: Physics Native CI\n\non:\n  pull_request:\n"
                           "    branches: [main]\n"),
         "NATIVE_MAIN_ONLY_TRIGGER")
    header = native.split("\njobs:\n", 1)
    need(len(header) == 2 and "  workflow_dispatch:" not in header[0]
         and "  schedule:" not in header[0], "NO_UNAPPROVED_NATIVE_TRIGGER")
    native_jobs = set(re.findall(r"(?m)^  ([a-z][a-z0-9_-]*):\s*$",
                                 header[1]))
    need(set(P6) <= native_jobs, "ALL_P6_JOBS_REQUIRED")

    for name in P6:
        block = job_block(native, name)
        need(HEAD_SCOPE in block and CHECKED_HEAD in block
             and "github.event_name == 'pull_request'" in block,
             "SOURCE_HEAD_AND_INTERNAL_PR_SCOPE_" + name)
        need(EXPECTED_OCI in block, "OCI_PIN_MISSING_" + name)
        need("if-no-files-found: error" in block,
             "MISSING_EVIDENCE_MUST_FAIL_" + name)
        for forbidden in ("continue-on-error: true", "dont_create_kernels = true",
                          "dont_create_kernels=true", "--authorize-p3",
                          "run_chemistry_s6_p3_once.py", "run_canonical_s6_p3_once.py",
                          "|| true"):
            need(forbidden not in block,
                 "UNSAFE_BYPASS_" + name + "_" + forbidden[:12])

    w1 = job_block(native, P6[0])
    need(all(v in w1 for v in (
        "build_count", "physics-opt-and-app-libs.tar.gz",
        "SOURCE_HEAD", "persist-credentials: false",
        "archive_roundtrip_check", "sha256sums.txt")),
        "W1_SINGLE_BUILD_AND_SAME_HEAD_CUSTODY")
    need("make -C physics_app" in w1,
         "W1_BUILD_MISSING")

    n = job_block(native, P6[1])
    d = job_block(native, P6[2])
    for name, block in ((P6[1], n), (P6[2], d)):
        need(all(v in block for v in (
            "needs: p6_newonly_s6_build", "actions/download-artifact@v4",
            "P6_NEWONLY_EXACT_HEAD_ONE_W1_THREE_BINARY_BYTES_VERIFIED",
            "PROTECTED_ARCHIVE_B64:", "PASS_16_INTENDED_NATIVE_REJECTIONS",
            TYPE_COUNT, "tmpfs_cleanup_verified", "source_restoration",
            NETWORKLESS)),
            "NATIVE_W1_P05_PRIVATE_AND_TYPED_32_" + name)
        need("make -C physics_app" not in block,
             "NATIVE_MUST_NOT_REBUILD_W1_" + name)
    need("994f6b1deece3c53be7fb3e7f9526555d0f9314fd58749bea6346639f08aa387"
         in d and "stage_public_d_physics" in d and
         "PUBLIC_D_100ROW_TWO_CASES_STAGED_EXACT_PHYSICS_NO_REBUILD_PASS" in d,
         "PUBLIC_D_100ROW_ORIGINAL_SOURCE")
    regression = job_block(native, "plasma_native_regression")
    need("P6_PUBLIC_B_PASS_D_KEEP_HOLD_EVIDENCE_NOT_NATIVE_D_PASS" in regression
         and "p6_legacy_hold_receipt.py --mode public" in regression
         and "P6 FAIL_CLOSED: required S6-417/941 input gate is missing" in regression
         and REGRESSION_STEP in regression,
         "LEGACY_D_HOLD_NOT_NATIVE_PASS")
    need(all(v in dd_source for v in (
        "P05 FV Native/Physics duplicate or unexpected owner",
        "P05 missing or duplicate FV Kernel",
        "P05 legacy, duplicate or unexpected FV BC",
        "P05 partial or duplicate FV BC owner",
        "getProblem().theWarehouse()",
        'registerMooseAction("PhysicsApp", DDContinuityEq, "check_integrity")')),
        "DD_WAREHOUSE_P05_GUARDS")


def self_test(workflow: str, template: str, dd_source: str) -> int:
    native = NATIVE.read_text()
    validate(workflow, template, dd_source, native_source=native)
    cases: list[tuple[str, str, str, str, str]] = []

    def add(label: str, *, ci: str | None = None, tpl: str | None = None,
            nat: str | None = None, dd: str | None = None) -> None:
        cases.append((label, workflow if ci is None else ci,
                      template if tpl is None else tpl,
                      native if nat is None else nat,
                      dd_source if dd is None else dd))

    def edit(name: str, old: str, new: str) -> str:
        part = job_block(native, name)
        need(old in part and old != new,
             "NEGATIVE_FIXTURE_" + name + "_" + old[:16])
        return native.replace(part, part.replace(old, new), 1)

    add("template_drift", tpl=template + "\n# unreviewed drift\n")
    add("core_not_main", ci=workflow.replace(
        "  push:\n    branches: [main]",
        "  push:\n    branches: [testing]", 1))
    add("core_not_pr", ci=workflow.replace(
        "  pull_request:\n    branches: [main]",
        "  workflow_dispatch:\n    branches: [main]", 1))
    add("core_rogue_job", ci=workflow.replace(
        "\njobs:\n", "\njobs:\n  rogue:\n    runs-on: ubuntu-latest\n", 1))
    add("native_wrong_branch", nat=native.replace(
        "  pull_request:\n    branches: [main]",
        "  pull_request:\n    branches: [review]", 1))
    add("native_unapproved_dispatch", nat=native.replace(
        "\njobs:\n", "  workflow_dispatch:\n\njobs:\n", 1))
    for name in P6:
        add("missing_job_" + name,
            nat=native.replace("  " + name + ":\n",
                               "  disabled_" + name + ":\n", 1))
    add("missing_build_count", nat=edit(P6[0], "build_count", "build_counter_unverified"))
    add("missing_w1_tar", nat=edit(P6[0], "physics-opt-and-app-libs.tar.gz",
                                   "not_the_same_W1.tar.gz"))
    add("w1_upload_optional", nat=edit(P6[0], "if-no-files-found: error",
                                      "if-no-files-found: warn"))
    add("p05_no_dependency", nat=edit(P6[1], "needs: p6_newonly_s6_build",
                                      "needs: runtime-smoke"))
    add("p05_no_download", nat=edit(P6[1], "actions/download-artifact@v4",
                                    "actions/upload-artifact@v4"))
    add("p05_no_elf_verification", nat=edit(
        P6[1], "P6_NEWONLY_EXACT_HEAD_ONE_W1_THREE_BINARY_BYTES_VERIFIED",
        "BINARY_VERIFICATION_BYPASSED"))
    add("p05_no_private_rates", nat=edit(P6[1], "PROTECTED_ARCHIVE_B64:",
                                         "NO_PROTECTED_RATE_SOURCE:"))
    add("p05_no_negative_controls", nat=edit(
        P6[1], "PASS_16_INTENDED_NATIVE_REJECTIONS", "NEGATIVES_SKIPPED"))
    add("p05_no_typed_32", nat=edit(P6[1], TYPE_COUNT,
                                   "assert len(expected_kernels)>0"))
    add("p05_no_cleanup", nat=edit(P6[1], "tmpfs_cleanup_verified",
                                   "cleanup_not_observed"))
    add("publicd_no_dependency", nat=edit(P6[2], "needs: p6_newonly_s6_build",
                                          "needs: plasma_native_regression"))
    add("publicd_no_download", nat=edit(P6[2], "actions/download-artifact@v4",
                                        "actions/upload-artifact@v4"))
    add("publicd_table_sha_missing", nat=edit(
        P6[2], "994f6b1deece3c53be7fb3e7f9526555d0f9314fd58749bea6346639f08aa387",
        "unverified_100row_source"))
    add("publicd_generated_stage_skipped", nat=edit(
        P6[2], "PUBLIC_D_100ROW_TWO_CASES_STAGED_EXACT_PHYSICS_NO_REBUILD_PASS",
        "PUBLIC_D_GENERATION_SKIPPED"))
    add("publicd_negative_controls_missing", nat=edit(
        P6[2], "PASS_16_INTENDED_NATIVE_REJECTIONS", "NEGATIVES_SKIPPED"))
    add("publicd_cleanup_not_checked", nat=edit(
        P6[2], "tmpfs_cleanup_verified", "cleanup_not_observed"))
    add("publicd_upload_optional", nat=edit(
        P6[2], "if-no-files-found: error", "if-no-files-found: warn"))
    add("p05_continue_on_error", nat=edit(
        P6[1], "    steps:\n", "    continue-on-error: true\n    steps:\n"))
    add("historical_D_falsely_promoted", nat=edit(
        "plasma_native_regression",
        "P6_PUBLIC_B_PASS_D_KEEP_HOLD_EVIDENCE_NOT_NATIVE_D_PASS",
        "HISTORICAL_D_NATIVE_P2_PASS"))
    add("DD_P05_removed", dd=dd_source.replace(
        "P05 FV Native/Physics duplicate or unexpected owner", "P05_DISABLED", 1))
    need(len(cases) == 29, "NEGATIVE_COUNT_NOT_29")
    for label, ci, tpl, nat, dd in cases:
        need((ci, tpl, nat, dd) != (workflow, template, native, dd_source),
             "NEGATIVE_NO_MUTATION_" + label)
        try:
            validate(ci, tpl, dd, native_source=nat)
        except ValueError:
            continue
        raise ValueError("P6_SPLIT_CI_FALSE_PASS_" + label)
    print("P6_SPLIT_CI_29_NEGATIVES_REJECTED")
    return len(cases)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--check", action="store_true")
    p.add_argument("--self-test", action="store_true")
    args = p.parse_args()
    try:
        ci, template, dd = WORKFLOW.read_text(), TEMPLATE.read_text(), DD.read_text()
        if args.self_test:
            self_test(ci, template, dd)
        if args.check or not args.self_test:
            validate(ci, template, dd)
            print("P6_SPLIT_CI_SOURCE_TRIGGER_ARTIFACT_P05=PASS")
    except (OSError, ValueError) as e:
        print("P6_SPLIT_CI_FAIL", str(e)[:240])
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
