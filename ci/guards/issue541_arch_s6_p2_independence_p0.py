#!/usr/bin/env python3
"""Read-only S6 P2 closure gate; NOT a Native or P3 run.

Verifies that pinned integration-HEAD S6-417/941 P2 evidence is independent of
later owner-approved P3 replay failure. External GitHub job/artifact statuses
were observed separately; this guard checks the frozen receipt and source
contracts, not the live GitHub API or the ZIP contents.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RECEIPT = ROOT / "ci/baselines/issue541_arch_s6_p2_independent_closure_20261116.json"
CI = ROOT / ".github/workflows/ci.yml"
P2 = ROOT / "ci/guards/issue541_arch_s6_native_p2_only.py"
OLD = ROOT / ".github/workflows/issue402-hybrid-json-s6-p3-p4-once.yml"

SOURCE_SHA = "5d15c4054a00aa9fa8a778a87bb21690a3a5469b"
ARTIFACT_SHA = "7d2b1593f9ef7e4cbce714d637a9894a6109f2738e721be751ecb9609828f634"
HISTORICAL_SHA = "29d1acc6ef7969908b86719e4b95c73a1565136d"
OCI = "sha256:2c3352da4f5c1b2ae98475fc01463ad0cdbc6ce7d221ce55055ddea152182008"
CI_BLOB = "84cd7d60508f9a93739e50fa93dfc4405ddc8dc1"
RUNNER_BLOB = "533dfa16395c041c610130f90d0489300fdd548f"
ORIGINAL_BLOB = "485439a723584ca5bbc8632a86c53574b0b1eb9a"


def need(condition: bool, reason: str) -> None:
    if not condition:
        raise ValueError("S6_P2_CLOSURE_" + reason)


def blob(text: str) -> str:
    raw = text.encode("utf-8")
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()


def p2_job(ci: str) -> str:
    marker = "\n  issue541_arch_s6_hybrid_native_p2:\n"
    need(ci.count(marker) == 1, "NATIVE_JOB_IDENTITY")
    tail = ci.split(marker, 1)[1]
    next_job = re.search(r"(?m)^  [A-Za-z_][A-Za-z0-9_-]*:\s*$", tail)
    return tail[:next_job.start()] if next_job else tail


def validate(record: dict, ci: str, runner: str, original: str) -> None:
    need(record["schema"] == "issue541.arch.s6_p2_independent_closure.v1", "SCHEMA")
    need((record["authority_issue"], record["retirement_issue"], record["science_issue"])
         == (541, 535, 402), "AUTHORITY")
    need(record["scope"] == "S6_417_941_NATIVE_CHECK_INPUT_P2_ONLY", "SCOPE")

    base = record["baseline"]
    need(base["integration_pr"] == 578 and
         base["exact_source_sha"] == SOURCE_SHA and
         base["ci_run_id"] == 43883076025 and
         base["native_p2_job_id"] == 133353818041 and
         base["native_p2_job_conclusion"] == "success", "SOURCE_CI_P2_RECEIPT")
    need(base["artifact_id"] == 14234186951 and
         base["artifact_bytes"] == 8675 and
         base["artifact_sha256"] == ARTIFACT_SHA and
         base["artifact_integrity_proof"] == "PR578_INTEGRATION_READBACK_CRC_SHA256_PASS",
         "P2_ZIP_RECEIPT")
    need(base["historical_input_sha"] == HISTORICAL_SHA and
         base["oci_digest"] == OCI, "PINNED_INPUT_AND_OCI")
    need(base["ci_workflow_blob"] == CI_BLOB and blob(ci) == CI_BLOB and
         base["native_p2_runner_blob"] == RUNNER_BLOB and blob(runner) == RUNNER_BLOB,
         "EXACT_P2_EXECUTION_CONTRACT_BLOBS")
    need(base["legacy_s6_workflow_blob"] == ORIGINAL_BLOB and
         blob(original) == ORIGINAL_BLOB, "UNCHANGED_ORIGINAL_WORKFLOW")

    cases = record["cases"]
    need(set(cases) == {"417", "941"}, "TWO_CASES")
    for case in ("417", "941"):
        c = cases[case]
        need(c["P0"] == "PASS" and c["P1"] == "PASS_SOURCE_BOUND_BINARY" and
             c["P2"] == "PASS" and c["P3"] == "NOT_RUN" and c["P4"] == "NOT_RUN" and
             c["science"] == "SCIENCE_HOLD" and
             c["status"] == "ARCH_S6_HYBRID_NATIVE_P2_PASS_NO_P3",
             "CASE_STATE_" + case)

    need(record["p2_decision"] == "SOURCE_BOUND_P2_VERIFIED_ON_PINNED_HEAD" and
         record["newer_head_p2_acceptance"] == "REVALIDATE_WHEN_EXACT_HEAD_CHANGES",
         "NO_FALSE_NEW_HEAD_PROMOTION")
    replay = record["p3_replay"]
    need(replay["run_id"] == 43892446918 and
         replay["source_sha"] == "6efeb8bbc519914099380e02ad60364b1c87032f" and
         replay["classification"] == "HYBRID_POST_CHEMISTRY_OWNER_CUTOVER_PRE_NATIVE_INPUT_FAILURE" and
         replay["disposition"] == "SEPARATE_REPLAY_HOLD" and
         replay["result_not_usable_for_p2"] == "TRUE", "P3_SEPARATE_FAILURE")
    for case, job, artifact in (("417", 133386980384, 14236309715),
                                ("941", 133386979669, 14237158635)):
        c = replay["case_" + case]
        need(c["job_id"] == job and c["artifact_id"] == artifact and
             c["conclusion"] == "failure" and
             c["error"] == "HYBRID_OWNER_COUNT_Variables_log_e: 0" and
             c["native_p3"] == "NOT_RUN", "P3_FAILURE_NOT_P2_" + case)

    need(record["owner_external_caller_attestation"] == "OWNER_ATTESTED_ABSENT" and
         record["original_s6_workflow_retirement"] == "KEEP_HOLD" and
         record["p4"] == "DIAGNOSTIC_ONLY" and
         record["science"] == "SCIENCE_HOLD" and
         record["global_workflow_surface"] == "UNWAIVED_FAIL" and
         record["global_repository_release"] == "KEEP_HOLD", "NO_RETIREMENT_SCIENCE_PROMOTION")
    need(record["integration_policy"] ==
         "ONLY_P2_CLOSURE_RECEIPT_MAY_BE_CONSIDERED_SEPARATELY_NO_P3_ONE_SHOT_OR_GUARD_WAIVER",
         "SELECTIVE_INTEGRATION")

    job = p2_job(ci)
    need("Issue541 ARCH S6 417+941 hybrid native P1/P2 exact-source (no P3)" in job,
         "P2_JOB_LABEL")
    need("--case 417" in job and "--case 941" in job and
         "test \"$first\" -eq 0" in job and "test \"$second\" -eq 0" in job,
         "BOTH_REAL_P2_REQUIRED")
    need("ci/guards/issue541_arch_s6_native_p2_only.py" in job and
         "ISSUE541_ARCH_S6_BOTH_NATIVE_P2_PASS_P3_NOT_RUN_SCIENCE_HOLD" in job,
         "P2_NO_P3_RECEIPT")
    need("P3" not in job.split("P2 real hybrid JSON+Native check-input", 1)[-1].split(
         "Always upload both S6 P2 diagnostics", 1)[0].replace(
         "P3_NOT_RUN", ""), "P2_JOB_NO_P3_EXECUTION")
    need("--authorize-p3" not in job and
         "run_chemistry_s6_p3_once.py" not in job and
         "run_canonical_s6_p3_once.py" not in job, "P2_JOB_NO_SOLVER_P3")
    need("ref: \u0024{{ github.event.pull_request.head.sha }}" in job and
         "EXPECTED_HEAD: \u0024{{ github.event.pull_request.head.sha }}" in job and
         "ref: " + HISTORICAL_SHA in job and
         OCI in job and
         "if: always()" in job, "EXACT_SHA_OCI_EVIDENCE")
    need("issue541_arch_s6_p2_evidence/*/status.json" in job and
         "issue541_arch_s6_p2_evidence/*/native_P2.log" in job and
         "native_p1_identity.json" in job, "P2_ARTIFACT_CONTENTS")
    need("chemistry_cutover=chem_cutover" in runner and
         "prepare_chemistry(chemistry, layers, case)" in runner and
         "prepare_hybrid(" in runner, "EXACT_HYBRID_HANDOFF")
    need("option.run_one(" in runner and
         "option.sha_file(binary) != identity[\"binary_sha256\"]" in runner and
         "ARCH_S6_HYBRID_NATIVE_P2_PASS_NO_P3" in runner and
         "\"P3\": \"NOT_RUN\"" in runner, "P2_RUNNER_NATIVE_AND_NO_P3")
    need("run_chemistry_s6_p3_once" not in runner and
         "--authorize-p3" not in runner, "P2_RUNNER_NO_P3")


def load() -> tuple[dict, str, str, str]:
    return (json.loads(RECEIPT.read_text()),
            CI.read_text(), P2.read_text(), OLD.read_text())


def self_test() -> None:
    record, ci, runner, original = load()
    validate(record, ci, runner, original)
    mutants: list[tuple[str, dict, str, str, str]] = []
    def changed(label: str, update) -> None:
        trial = copy.deepcopy(record)
        update(trial)
        mutants.append((label, trial, ci, runner, original))

    changed("P2_FALSE_417", lambda d: d["cases"]["417"].update(P2="FAIL"))
    changed("P2_FALSE_941", lambda d: d["cases"]["941"].update(P2="HOLD"))
    changed("FORGED_ZIP", lambda d: d["baseline"].update(artifact_sha256="0" * 64))
    changed("FORGED_SOURCE", lambda d: d["baseline"].update(exact_source_sha="0" * 40))
    changed("FALSE_NEW_HEAD_ACCEPTANCE", lambda d: d.update(newer_head_p2_acceptance="ACCEPTED"))
    changed("FALSE_P3_SUCCESS", lambda d: d["p3_replay"]["case_417"].update(native_p3="PASS"))
    changed("FALSE_RETIREMENT", lambda d: d.update(original_s6_workflow_retirement="RETIRED_VERIFIED"))
    changed("FALSE_SCIENCE", lambda d: d.update(science="SCIENCE_ACCEPTED"))
    changed("GUARD_WAIVER", lambda d: d.update(global_workflow_surface="WAIVED"))
    changed("CASE_941_REMOVED", lambda d: d["cases"].pop("941"))
    mutants.append(("REMOVED_CHEM_HANDOFF", record, ci,
                    runner.replace("chemistry_cutover=chem_cutover", ""), original))
    mutants.append(("P3_LEAK", record, ci,
                    runner + "\n# run_chemistry_s6_p3_once.py\n", original))
    mutants.append(("REMOVED_CASE_941", record,
                    ci.replace("--case 941", "--case 417"), runner, original))
    mutants.append(("ORIGINAL_WORKFLOW_MODIFIED", record, ci, runner,
                    original + "# unapproved deletion\n"))

    for label, r, c, p, o in mutants:
        try:
            validate(r, c, p, o)
        except ValueError:
            continue
        raise ValueError("S6_P2_CLOSURE_UNREJECTED_MUTATION_" + label)
    print("ISSUE541_S6_P2_INDEPENDENCE_NEGATIVE_14_REJECTED")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    try:
        if args.self_test:
            self_test()
        if args.check or not args.self_test:
            validate(*load())
            print("ISSUE541_S6_417_941_P2_PINNED_SOURCE_VERIFIED_P3_REPLAY_HOLD_SCIENCE_HOLD")
    except (OSError, KeyError, ValueError) as exc:
        print("ISSUE541_S6_P2_INDEPENDENCE_FAIL", exc)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
