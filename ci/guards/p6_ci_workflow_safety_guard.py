#!/usr/bin/env python3
"""P6-C3: deterministic CI/template trigger, artifact and P05 fail-closed gate.

Source-only guard. Never launches a Native solve, P3/P4 replay, GitHub
workflow dispatch, or modifies protected historical input. All checks apply
to the current checkout; previous run/artifact PASS is not promoted.
"""
from __future__ import annotations

import argparse
import hashlib
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/ci.yml"
TEMPLATE = ROOT / "ci/workflow_templates/general-ci.yml"
DD = ROOT / "physics_app/src/physics/plasma/DDContinuityEq.C"

NATIVE = {
    "issue402_core_four_native_p2": "issue541-core-four-native-",
    "plasma_native_regression": "plasma-native-regression-",
    "issue541_arch_dd_native_p2": "issue541-arch-dd-p1-p2-",
    "issue541_arch_s6_hybrid_native_p2": "issue541-arch-s6-hybrid-p2-",
}
PR_GUARD = (
    "github.event_name == 'pull_request' &&\n"
    "      (github.event.action != 'edited' || "
    "github.event.changes.base != null) &&\n"
    "      github.event.pull_request.head.repo.full_name == "
    "'HyungseonSong-plasma/moose-test-repo'"
)
P05_MESSAGES = (
    "P05 FV Native/Physics duplicate or unexpected owner",
    "P05 missing or duplicate FV Kernel",
    "P05 legacy, duplicate or unexpected FV BC",
    "P05 partial or duplicate FV BC owner",
)
BANNED_NATIVE = (
    "continue-on-error: true",
    "dont_create_kernels = true",
    "dont_create_kernels=true",
    "--authorize-p3",
    "run_chemistry_s6_p3_once.py",
    "run_canonical_s6_p3_once.py",
    "|| true",
)


def need(ok: bool, name: str) -> None:
    if not ok:
        raise ValueError("P6_CI_" + name)


def job_block(workflow: str, name: str) -> str:
    start = re.search(r"(?m)^  " + re.escape(name) + r":\n", workflow)
    need(start is not None, "MISSING_JOB_" + name)
    tail = workflow[start.end():]
    next_job = re.search(r"(?m)^  [A-Za-z][A-Za-z0-9_-]*:\n", tail)
    return tail[:next_job.start()] if next_job else tail


def edit_job(workflow: str, name: str, old: str, new: str) -> str:
    job = job_block(workflow, name)
    need(job.count(old) == 1, "MUTATION_SOURCE_" + name)
    return workflow.replace(job, job.replace(old, new, 1), 1)


def validate(workflow: str, template: str, dd_source: str) -> None:
    need(workflow == template, "TEMPLATE_BYTE_PARITY")
    need(workflow.startswith(
        "name: Repository CI\n\non:\n  push:\n    branches: [main]\n"
        "  pull_request:\n    branches: [main]\n"
        "    types: [opened, synchronize, reopened, edited]\n"
    ), "CI_MAIN_ONLY_TRIGGER")
    header = workflow.split("\njobs:\n", 1)
    need(len(header) == 2, "CI_JOBS")
    need("workflow_dispatch:" not in header[0] and
         "workflow_run:" not in header[0] and
         "schedule:" not in header[0], "NO_AUTOMATIC_P3_SCENARIO")

    validate_job = job_block(workflow, "validate")
    need(
        "github.event_name != 'pull_request' ||\n"
        "      github.event.action != 'edited' ||\n"
        "      github.event.changes.base != null" in validate_job,
        "VALIDATE_EDITED_BASE_GUARD"
    )
    need(
        "python3 ci/workflow_harness.py --self-test" in validate_job and
        "python3 ci/workflow_harness.py --check" in validate_job and
        "python3 ci/guards/workflow_surface_guard.py --check" in validate_job and
        "python3 ci/guards/p6_ci_workflow_safety_guard.py --self-test --check"
        in validate_job,
        "GOVERNED_VALIDATION_GUARDS"
    )

    for name, artifact_prefix in NATIVE.items():
        block = job_block(workflow, name)
        condition = block.split("    runs-on:", 1)[0]
        need(PR_GUARD in condition, "NATIVE_EDIT_TRIGGER_" + name)
        need("github.event.pull_request.head.sha" in block,
             "NATIVE_EXACT_HEAD_" + name)
        for banned in BANNED_NATIVE:
            need(banned not in block, "NATIVE_BYPASS_" + name + "_" +
                 banned.replace(" ", "_"))
        # Never silently promote an absent full S6 source/runner to a green job.
        if name == "plasma_native_regression":
            need(
                "P6 FAIL_CLOSED: required Public S6 option preflight is missing"
                in block and
                "P6 FAIL_CLOSED: required S6-417/941 input gate is missing"
                in block and block.count("            exit 1") >= 2,
                "NO_OPTIONAL_S6_GATE"
            )
        if name == "issue541_arch_s6_hybrid_native_p2":
            need(
                'test "$first" -eq 0' in block and
                'test "$second" -eq 0' in block and
                '--case 417' in block and '--case 941' in block and
                "ISSUE541_ARCH_S6_BOTH_NATIVE_P2_PASS_P3_NOT_RUN_SCIENCE_HOLD"
                in block,
                "TWO_CASES_P2_AND_P05_FAIL_CLOSED"
            )
            need("migrated_continuity.i" not in block, "NO_S6_HYBRID_EDIT")

        artifact_name = re.search(
            r"(?m)^          name: (" + re.escape(artifact_prefix) +
            r"[^\n]+)$", block)
        need(artifact_name is not None, "ARTIFACT_NAME_" + name)
        value = artifact_name.group(1)
        need(
            all(key in value for key in
                ("github.run_id", "github.run_attempt",
                 "github.event.pull_request.head.sha")),
            "ARTIFACT_RUN_ATTEMPT_HEAD_" + name
        )
        step_start = block.rfind("      - name:", 0, artifact_name.start())
        need(step_start >= 0, "ARTIFACT_STEP_START_" + name)
        proof = block[step_start:artifact_name.end()+450]
        need(
            "if: always()" in proof and
            "uses: actions/upload-artifact@v4" in proof and
            "if-no-files-found: error" in proof and
            "retention-days: 30" in proof,
            "ARTIFACT_FAIL_CLOSED_" + name
        )
        if name == "issue541_arch_s6_hybrid_native_p2":
            need(
                "issue541_arch_s6_p2_evidence/*/status.json" in proof and
                "issue541_arch_s6_p2_evidence/*/native_P2.log" in proof and
                "native_p1_identity.json" in proof,
                "ARCH_BOTH_CASES_PROVENANCE"
            )

    for message in P05_MESSAGES:
        need(message in dd_source, "P05_SOURCE_GUARD_" +
             message.split()[1].upper())
    need("getProblem().theWarehouse()" in dd_source and
         'registerMooseAction("PhysicsApp", DDContinuityEq, "check_integrity")'
         in dd_source, "P05_REGISTERED_WAREHOUSE")

    # Explicit manual P3/P4 lane is a separate registered workflow, never
    # inferred from this ordinary PR CI; Python unit tests may mention P3.
    for name in NATIVE:
        block = job_block(workflow, name)
        need("num_steps = 150" not in block and
             "num_steps = 200" not in block and
             "--full-24" not in block,
             "NO_LONG_SCIENCE_IN_NATIVE_P2_" + name)


def self_test(workflow: str, template: str, dd_source: str) -> int:
    validate(workflow, template, dd_source)
    cases: list[tuple[str, str, str, str]] = []

    def add(name: str, candidate: str, *, cpp: str | None = None) -> None:
        cases.append((name, candidate, candidate, dd_source if cpp is None else cpp))

    cases.append(("template_drift", workflow, template + "\n# drift\n", dd_source))
    add("push_nonmain", workflow.replace("branches: [main]", "branches: [testing]", 1))
    add("unapproved_workflow_dispatch", workflow.replace(
        "\njobs:\n", "  workflow_dispatch:\n\njobs:\n", 1))
    add("removed_metadata_trigger", edit_job(
        workflow, "plasma_native_regression",
        "(github.event.action != 'edited' || github.event.changes.base != null)",
        "github.event.action != 'edited'"
    ))
    add("removed_internal_pr_scope", edit_job(
        workflow, "issue541_arch_s6_hybrid_native_p2",
        "github.event.pull_request.head.repo.full_name",
        "github.event.pull_request.base.repo.full_name"
    ))
    add("artifact_attempt_missing", edit_job(
        workflow, "issue541_arch_s6_hybrid_native_p2",
        "github.run_attempt", "run_attempt_removed"
    ))
    add("artifact_became_optional", edit_job(
        workflow, "issue541_arch_dd_native_p2",
        "if-no-files-found: error", "if-no-files-found: warn"
    ))
    add("artifact_on_success_only", edit_job(
        workflow, "plasma_native_regression",
        "if: always()", "if: success()"
    ))
    add("weakened_native_check", edit_job(
        workflow, "issue541_arch_s6_hybrid_native_p2",
        'test "$second" -eq 0', 'echo "ignore 941 exit"'
    ))
    add("skipped_second_case", edit_job(
        workflow, "issue541_arch_s6_hybrid_native_p2",
        "--case 941", "--case 417"
    ))
    add("p05_bypass", edit_job(
        workflow, "issue541_arch_s6_hybrid_native_p2",
        "echo ISSUE541_ARCH_S6_HISTORICAL_400W_PUBLIC_MESH_P0_PASS",
        "echo ISSUE541_ARCH_S6_HISTORICAL_400W_PUBLIC_MESH_P0_PASS\n"
        "          dont_create_kernels = true"
    ))
    add("p3_auto_launch", edit_job(
        workflow, "issue541_arch_s6_hybrid_native_p2",
        "echo ISSUE541_ARCH_S6_BOTH_NATIVE_P2_PASS_P3_NOT_RUN_SCIENCE_HOLD",
        "run_chemistry_s6_p3_once.py --authorize-p3"
    ))
    add("continue_on_error", edit_job(
        workflow, "plasma_native_regression",
        "      - name: P1 - Build PhysicsApp",
        "      - name: P1 - Build PhysicsApp"
        "\n        continue-on-error: true"
    ))
    add("drop_guard", workflow.replace(
        "python3 ci/guards/p6_ci_workflow_safety_guard.py --self-test --check",
        "echo P6_VALIDATOR_REMOVED", 1))
    add("missing_source_gate", edit_job(
        workflow, "plasma_native_regression",
        "P6 FAIL_CLOSED: required S6-417/941 input gate is missing",
        "optional S6 input gate"
    ))
    add("weaken_p05", workflow, cpp=dd_source.replace(
        "P05 FV Native/Physics duplicate or unexpected owner", "P05_BYPASS", 1
    ))
    add("undeclared_provenance", edit_job(
        workflow, "issue541_arch_s6_hybrid_native_p2",
        "native_p1_identity.json", "identity_omitted.json"
    ))

    for name, w, t, c in cases:
        try:
            validate(w, t, c)
        except ValueError:
            continue
        raise ValueError("P6_CI_NEGATIVE_UNREJECTED_" + name)
    print("P6_CI_SAFETY_NEGATIVES_REJECTED", len(cases))
    return len(cases)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    try:
        workflow = WORKFLOW.read_text()
        template = TEMPLATE.read_text()
        dd = DD.read_text()
        if args.self_test:
            self_test(workflow, template, dd)
        if args.check or not args.self_test:
            validate(workflow, template, dd)
            print("P6_CI_TRIGGER_ARTIFACT_P05_FAIL_CLOSED_SOURCE_PASS",
                  hashlib.sha256(workflow.encode()).hexdigest())
    except (OSError, ValueError) as exc:
        print("P6_CI_SAFETY_FAIL", exc)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
