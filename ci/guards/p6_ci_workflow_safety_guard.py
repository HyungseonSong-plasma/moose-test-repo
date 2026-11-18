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
}
LEGACY_ARTIFACT_NAMES = {
    "issue402_core_four_native_p2": "issue541-core-four-native-${{ github.run_id }}",
    "plasma_native_regression": "plasma-native-regression-${{ github.event.pull_request.head.sha }}",
    "issue541_arch_dd_native_p2": "issue541-arch-dd-p1-p2-${{ github.event.pull_request.head.sha }}",
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
                in block and "            exit 1" in block,
                "REQUIRED_PUBLIC_P0_PREFLIGHT"
            )
            need("P2 - Public S6-417 and S6-941 four-way Native input checks" not in block,
                 "HISTORICAL_PUBLIC_P2_MUST_BE_MANUAL")

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
        proof = block[step_start:block.rfind("      - name: Upload first-attempt legacy artifact alias (compatibility only)")]
        need(
            "if: always()" in proof and
            "uses: actions/upload-artifact@v4" in proof and
            "if-no-files-found: error" in proof and
            "retention-days: 30" in proof,
            "ARTIFACT_FAIL_CLOSED_" + name
        )
        # Preserve old artifact name only on attempt 1; no overwriting on reruns.
        legacy_marker = "          name: " + LEGACY_ARTIFACT_NAMES[name] + "\n"
        need(block.count(legacy_marker) == 1, "LEGACY_ALIAS_IDENTITY_" + name)
        legacy_pos = block.index(legacy_marker)
        legacy_start = block.rfind("      - name:", 0, legacy_pos)
        need(legacy_start >= 0 and legacy_start > step_start,
             "LEGACY_ALIAS_ORDER_" + name)
        canonical_step = block[step_start:legacy_start]
        legacy_step = block[legacy_start:].split("\n      - name:", 1)[0]
        need(
            "Upload first-attempt legacy artifact alias (compatibility only)"
            in legacy_step and
            "if: ${{ always() && github.run_attempt == 1 }}" in legacy_step and
            "uses: actions/upload-artifact@v4" in legacy_step and
            "if-no-files-found: error" in legacy_step and
            "retention-days: 30" in legacy_step,
            "LEGACY_ALIAS_FAIL_CLOSED_" + name
        )
        def payload(step: str) -> str:
            need(step.count("          path:") == 1 and
                 step.count("          if-no-files-found:") == 1,
                 "ARTIFACT_PATH_STRUCTURE_" + name)
            return step.split("          path:", 1)[1].split(
                "          if-no-files-found:", 1)[0]
        need(payload(canonical_step) == payload(legacy_step),
             "LEGACY_ALIAS_SAME_BOUNDED_PROOF_" + name)

    # The Issue633 gate verifies both actual Native cases, protected Scratch,
    # exact HEAD, historical manual KEEP_HOLD, and the new artifact contract.
    import runpy
    guard = runpy.run_path(str(ROOT / "ci/guards/issue633_s6_ci_route_guard.py"))
    try:
        guard["check"](
            workflow, template,
            (ROOT / ".github/workflows/issue541-arch-s6-hybrid-p2-compat.yml").read_text(),
            (ROOT / "ci/issue633_required_newonly_s6_native_p2.py").read_text(),
            (ROOT / "ci/guards/workflow_surface_guard.py").read_text(),
        )
    except (AssertionError, ValueError) as exc:
        raise ValueError("P6_NEWONLY_HYBRID_ROUTE_" + str(exc)) from exc
    need("python3 ci/guards/issue633_s6_ci_route_guard.py --check --self-test"
         in validate_job, "NEWONLY_ROUTE_GUARD_NOT_WIRED")
    need("\n  issue541_arch_s6_hybrid_native_p2:" not in workflow,
         "OLD_ARCH_AUTOMATIC_JOB_STILL_PRESENT")
    new_job = job_block(workflow, "issue633_newonly_s6_native_p2_required")
    for banned in BANNED_NATIVE:
        need(banned not in new_job, "NEWONLY_BYPASS_" + banned.replace(" ", "_"))

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

    def mutate_canonical(name: str, old: str, new: str) -> str:
        """Mutate only the run/attempt/HEAD upload, preserving the legacy alias."""
        job = job_block(workflow, name)
        delim = "      - name: Upload first-attempt legacy artifact alias (compatibility only)"
        need(job.count(delim) == 1, "CANONICAL_MUTATION_SCOPE_" + name)
        before, after = job.split(delim, 1)
        need(before.count(old) == 1, "CANONICAL_MUTATION_TARGET_" + name)
        return workflow.replace(job, before.replace(old, new, 1) + delim + after, 1)

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
        workflow, "issue633_newonly_s6_native_p2_required",
        "github.event.pull_request.head.repo.full_name",
        "github.event.pull_request.base.repo.full_name"
    ))
    add("artifact_attempt_missing", mutate_canonical( "plasma_native_regression",
        "github.run_attempt", "run_attempt_removed"
    ))
    add("artifact_became_optional", mutate_canonical( "issue541_arch_dd_native_p2",
        "if-no-files-found: error", "if-no-files-found: warn"
    ))
    add("artifact_on_success_only", edit_job(
        workflow, "plasma_native_regression",
        "if: always()", "if: success()"
    ))
    add("weakened_native_check", edit_job(
        workflow, "issue633_newonly_s6_native_p2_required",
        "ISSUE633_NEWONLY_S6_417_941_BOTH_REQUIRED_P2_PASS", "FALSE_TWO_CASE_P2_SUCCESS"
    ))
    add("skipped_second_case", edit_job(
        workflow, "issue633_newonly_s6_native_p2_required",
        "P2 REQUIRED actual protected S6-417 AND 941 Native --check-input using SAME ELF", "P2 REQUIRED actual protected S6-417 ONLY Native --check-input using SAME ELF"
    ))
    add("p05_bypass", edit_job(
        workflow, "issue633_newonly_s6_native_p2_required",
        "echo ISSUE633_NEWONLY_S6_417_941_BOTH_REQUIRED_P2_PASS",
        "dont_create_kernels = true"
    ))
    add("p3_auto_launch", edit_job(
        workflow, "issue633_newonly_s6_native_p2_required",
        "echo ISSUE633_NEWONLY_S6_417_941_BOTH_REQUIRED_P2_PASS",
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
        workflow, "issue633_newonly_s6_native_p2_required",
        '--expected-head "$EXPECTED_HEAD"',
        '--expected-head "$WRONG_HEAD"'
    ))
    add("weaken_p05", workflow, cpp=dd_source.replace(
        "P05 FV Native/Physics duplicate or unexpected owner", "P05_BYPASS", 1
    ))
    add("undeclared_provenance", mutate_canonical( "plasma_native_regression",
        "          path: experiments/Issue402_plasma_dsl_g1/evidence/**",
        "          path: experiments/Issue402_plasma_dsl_g1/chemistry/**"
    ))

    def mutate_legacy(name: str, old: str, new: str) -> str:
        """Change only the legacy alias step, never canonical receipt."""
        job = job_block(workflow, name)
        suffix = "      - name: Upload first-attempt legacy artifact alias (compatibility only)"
        need(job.count(suffix) == 1, "LEGACY_MUTATION_SCOPE_" + name)
        before, after = job.split(suffix, 1)
        need(after.count(old) == 1, "LEGACY_MUTATION_TARGET_" + name)
        return workflow.replace(job, before + suffix + after.replace(old, new, 1), 1)

    add("legacy_name_drift", mutate_legacy(
        "issue402_core_four_native_p2",
        "issue541-core-four-native-${{ github.run_id }}",
        "issue541-core-four-native-silent-rename"
    ))
    add("legacy_alias_unconditional_on_rerun", mutate_legacy(
        "plasma_native_regression",
        "if: ${{ always() && github.run_attempt == 1 }}",
        "if: always()"
    ))
    add("legacy_alias_evidence_optional", mutate_legacy(
        "issue541_arch_dd_native_p2",
        "if-no-files-found: error", "if-no-files-found: warn"
    ))
    add("legacy_alias_proof_path_drift", mutate_legacy(
        "plasma_native_regression",
        "          path: experiments/Issue402_plasma_dsl_g1/evidence/**",
        "          path: experiments/Issue402_plasma_dsl_g1/chemistry/**"
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
