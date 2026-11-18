#!/usr/bin/env python3
"""Fail-closed Issue633 New-only required P2 / historical ARCH compatibility CI route."""
from __future__ import annotations
import argparse
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[2]
def read(p):return (ROOT/p).read_text(encoding="utf-8")
NEW="issue633_newonly_s6_native_p2_required"

def job(ci, name):
    needle=f"\n  {name}:\n"
    assert ci.count(needle)==1, "JOB_MISSING_OR_DUPLICATE:"+name
    rest=ci.split(needle,1)[1]
    later=re.search(r"(?m)^  [a-z][a-z0-9_]*:\s*$",rest)
    return rest[:later.start()] if later else rest

def check(ci, template, manual, runner, surface):
    assert ci==template, "CI_TEMPLATE_SOURCE_DIVERGED"
    assert "\n  pull_request:\n    branches: [main]\n" in ci, "PR_TRIGGER_LOST"
    assert "types: [opened, synchronize, reopened, edited]" in ci, "SYNCHRONIZE_TRIGGER_LOST"
    assert "\n  issue541_arch_s6_hybrid_native_p2:" not in ci, "ARCH_STILL_AUTOMATIC"
    assert "P2 - Public S6-417 and S6-941 four-way Native input checks" not in ci, "PUBLIC_HISTORICAL_STILL_REQUIRED"
    core=job(ci,"plasma_native_regression")
    assert "run_native_binding_smoke.sh" in core, "CORE_NATIVE_P1_REMOVED"
    assert "Require actual native regression evidence before success" in core, "CORE_NATIVE_EVIDENCE_REMOVED"
    required=job(ci,NEW)
    assert "github.event_name == 'pull_request'" in required, "PR_GATE_LOST"
    assert "github.event.pull_request.head.repo.full_name == 'HyungseonSong-plasma/moose-test-repo'" in required, "FORK_GUARD_LOST"
    assert "github.event.action != 'edited' || github.event.changes.base != null" in required, "EDIT_GUARD_LOST"
    assert "EXPECTED_HEAD: ${{ github.event.pull_request.head.sha }}" in required, "SOURCE_HEAD_UNPINNED"
    assert "ref: ${{ github.event.pull_request.head.sha }}" in required, "SOURCE_CHECKOUT_UNPINNED"
    assert 'test "$(git rev-parse HEAD)" = "$EXPECTED_HEAD"' in required, "EXACT_HEAD_CHECK_MISSING"
    assert required.count("make -C physics_app ")==1, "REQUIRED_SINGLE_BUILD_LOST"
    assert "--repo-head \"$EXPECTED_HEAD\"" in required, "NEWONLY_STAGE_NOT_EXACT_HEAD"
    assert "14406746397/zip" in required, "NEWONLY_SOURCE_ARTIFACT_UNPINNED"
    assert "592a7c82834bab841f6a2e1807db305d0eff1e953f50a0dcc6d7e21ff8820111" in required, "NEWONLY_SOURCE_SHA_UNPINNED"
    assert "retire_p4_duplicate_owners(" in required, "P4X_CUTOVER_MISSING"
    assert "OXYGEN24_RATES_TAR_XZ_B64" in required, "PRIVATE_EI_MISSING"
    assert "REQUIRED actual protected S6-417 AND 941 Native --check-input using SAME ELF" in required, "DUAL_NATIVE_P2_REQUIRED_STEP_LOST"
    assert "--expected-head \"$EXPECTED_HEAD\"" in required, "RUNNER_NOT_SOURCE_BOUND"
    assert "continue-on-error:" not in required, "NEWONLY_FALSE_GREEN"
    assert "dont_create_kernels" not in required, "NEWONLY_P05_BYPASS"
    assert "if: always()" in required, "NEGATIVE_ARTIFACT_CUSTODY_LOST"
    artifact=required.split("      - name: Upload REQUIRED New-only dual-case sanitized Native receipts",1)
    assert len(artifact)==2, "REQUIRED_ARTIFACT_STEP_MISSING"
    assert "uses: actions/upload-artifact@v4" in artifact[1], "REQUIRED_UPLOAD_ACTION_MISSING"
    assert "if-no-files-found: error" in artifact[1], "REQUIRED_ARTIFACT_MISSING_MUST_FAIL"
    for item in ("status.json","S6-417-native-P2.log","S6-941-native-P2.log",
                 "p4_receipt.json","current-head-physics-opt.sha256"):
        assert item in artifact[1], "REQUIRED_EVIDENCE_MISSING:"+item
    newonly_canonical, sep, newonly_alias = required.partition(
        "      - name: Upload New-only first-attempt legacy artifact alias (compatibility only)"
    )
    assert sep, "NEWONLY_FIRST_ATTEMPT_LEGACY_ALIAS_MISSING"
    assert "issue633-newonly-s6-417-941-required-native-${{ github.run_id }}-${{ github.run_attempt }}-${{ github.event.pull_request.head.sha }}" in newonly_canonical, "NEWONLY_ARTIFACT_ATTEMPT_IDENTITY"
    assert "issue633-newonly-s6-417-941-required-native-${{ github.event.pull_request.head.sha }}" in newonly_alias, "NEWONLY_OLD_ARTIFACT_CONSUMER"
    assert "if: ${{ always() && github.run_attempt == 1 }}" in newonly_alias, "NEWONLY_ALIAS_RETRY_OVERWRITE"
    def payload(text: str) -> str:
        assert text.count("          path:") == 1, "ARTIFACT_PAYLOAD_STRUCTURE"
        return text.split("          path:", 1)[1].split("          if-no-files-found:", 1)[0]
    canon = newonly_canonical.split("      - name: Upload REQUIRED New-only dual-case sanitized Native receipts", 1)[1]
    assert payload(canon) == payload(newonly_alias), "NEWONLY_LEGACY_ARTIFACT_PAYLOAD_DRIFT"
    assert "if-no-files-found: error" in newonly_alias, "NEWONLY_LEGACY_MISSING_ARTIFACT_MUST_FAIL"
    assert "\non:\n  workflow_dispatch:\npermissions:\n" in manual, "HYBRID_NOT_MANUAL_ONLY"
    assert re.search(r"(?m)^  (push|pull_request|schedule|workflow_call):",manual) is None, "HYBRID_AUTOMATIC_TRIGGER"
    assert "issue541_arch_s6_native_p2_only.py" in manual, "HYBRID_ACTUAL_RUNNER_GONE"
    assert 'test "$first" -eq 3' in manual and 'test "$second" -eq 3' in manual, "HYBRID_EXPECTED_NEGATIVES_GONE"
    assert 'status["P2"]=="HOLD"' in manual, "HYBRID_FALSE_NATIVE_PASS"
    assert "on 'log_O2p': ni_time" in manual and "P05 FV Native/Physics duplicate" in manual, "HYBRID_P05_SIGNATURE_MISSING"
    assert "ARCH_HYBRID_P05_FAILURE_REPRO_BOTH_CASES_KEEP_HOLD" in manual, "HYBRID_HOLD_RECEIPT_GONE"
    assert "continue-on-error:" not in manual and "if-no-files-found: error" in manual, "HYBRID_ARTIFACT_FALSE_GREEN"
    assert "dont_create_kernels" not in manual, "HYBRID_P05_BYPASS"
    arch, sep, rest = manual.partition("\n  historical_public_BD_p2:")
    assert sep, "HISTORICAL_MANUAL_ARCH_BOUNDARY"
    assert "issue541-arch-s6-hybrid-p2-${{ github.run_id }}-${{ github.run_attempt }}-${{ github.sha }}" in arch, "HISTORICAL_ARCH_CANONICAL_ATTEMPT_ARTIFACT"
    assert "issue541-arch-s6-hybrid-p2-${{ github.sha }}" in arch, "HISTORICAL_ARCH_LEGACY_ARTIFACT"
    assert "if: ${{ always() && github.run_attempt == 1 }}" in arch, "HISTORICAL_ARCH_ALIAS_FIRST_ATTEMPT"
    canon, sep, legacy = arch.partition("      - name: Upload first-attempt legacy artifact alias (compatibility only)")
    assert sep, "HISTORICAL_ARCH_LEGACY_ALIAS_STEP_MISSING"
    first = canon.split("      - name: Always upload both S6 P2 diagnostics, no raw scratch or protected archive", 1)[1]
    assert payload(first) == payload(legacy), "HISTORICAL_ARCH_ARTIFACT_BYTES_DRIFT"
    assert arch.count("if-no-files-found: error") == 2, "HISTORICAL_ARCH_BOTH_ARTIFACTS_REQUIRED"
    assert "\n  historical_public_BD_p2:\n" in manual, "PUBLIC_BD_COMPAT_RUNNER_MISSING"
    assert "HISTORICAL_PUBLIC_B_PASS_D_TRANSPORT_KEEP_HOLD_BOTH_CASES" in manual, "PUBLIC_COMPAT_RESULT_GONE"
    assert 'b["P2"]=="PASS"' in manual and 'd["P2"]=="HOLD"' in manual, "PUBLIC_BD_NEGATIVE_CONTRACT_REMOVED"
    assert 'b["layers"]==10' in manual and 'd["layers"]==11' in manual, "PUBLIC_BD_LAYER_CONTRACT_REMOVED"
    assert "Missing drift-diffusion transport JSON record for FEM species 'e'" in manual, "PUBLIC_D_TRANSPORT_FAILURE_LOST"
    assert '"issue541-arch-s6-hybrid-p2-compat.yml": {"workflow_dispatch"}' in surface, "SURFACE_MANUAL_TRIGGER_NOT_PINNED"
    assert 'CASES = ("417", "941")' in runner and "for case in CASES:" in runner, "NEWONLY_CASE_MISSING"
    assert '"--check-input"' in runner and 'code == 0 and "Syntax OK" in log' in runner, "REAL_NATIVE_P2_OR_SYNTAX_MISSING"
    assert "read_hashed_rows()" in runner and 'dir="/dev/shm"' in runner, "PROTECTED_RATE_CUSTODY_MISSING"
    assert '"protected_scratch_removed"' in runner, "SCRATCH_CLEANUP_MISSING"
    assert 'sha(ROOT / "physics_app/physics-opt") == binary_sha' in runner, "SAME_ELF_SHA_MISSING"
    assert 'record["P2"] = "PASS_NATIVE_CHECK_INPUT"' in runner, "NEWONLY_PASS_CRITERIA_MISSING"
    assert "dont_create_kernels" not in runner and "continue-on-error:" not in runner, "NATIVE_P05_BYPASS"
    validate=job(ci,"validate")
    assert "issue633_s6_ci_route_guard.py --check --self-test" in validate, "CI_VALIDATION_ROUTE_GUARD_NOT_WIRED"

def must_reject(label,*args):
    try:check(*args)
    except AssertionError:return
    raise AssertionError("MUTATION_FALSE_PASS:"+label)

def selftest(ci,tmpl,man,run,surface):
    check(ci,tmpl,man,run,surface)
    must_reject("TEMPLATE_DRIFT",ci,tmpl+"\n# drift",man,run,surface)
    must_reject("REQUIRED_REMOVED",ci.replace("  "+NEW+":","  disabled_newonly:"),tmpl,man,run,surface)
    must_reject("ARCH_AUTOMATIC",ci,tmpl,man.replace("  workflow_dispatch:\n","  pull_request:\n",1),run,surface)
    must_reject("HYBRID_FALSE_SUCCESS",ci,tmpl,man.replace('status["P2"]=="HOLD"','status["P2"]=="PASS"'),run,surface)
    must_reject("HYBRID_SECOND_CASE_IGNORED",ci,tmpl,man.replace('test "$second" -eq 3','true'),run,surface)
    must_reject("HYBRID_P05_LOST",ci,tmpl,man.replace("on 'log_O2p': ni_time","on 'log_O2p': unknown"),run,surface)
    must_reject("PUBLIC_BD_COMPAT_REMOVED",ci,tmpl,man.replace("  historical_public_BD_p2:","  removed_public_compat:"),run,surface)
    must_reject("PUBLIC_D_FALSE_PASS",ci,tmpl,man.replace('d["P2"]=="HOLD"','d["P2"]=="PASS"'),run,surface)
    must_reject("REQUIRED_P2_BAD_CASE",ci,tmpl,man,run.replace('CASES = ("417", "941")','CASES = ("417",)'),surface)
    must_reject("REQUIRED_FAKE_SUCCESS",ci,tmpl,man,run.replace('record["P2"] = "PASS_NATIVE_CHECK_INPUT"','record["P2"] = "UNKNOWN"'),surface)
    must_reject("REQUIRED_CHECK_INPUT_REMOVED",ci,tmpl,man,run.replace('"--check-input"','"--version"'),surface)
    must_reject("REQUIRED_BYPASS",ci,tmpl,man,run+"\n# dont_create_kernels",surface)
    must_reject("TRIGGER_SURFACE_DISABLED",ci,tmpl,man,run,surface.replace('"issue541-arch-s6-hybrid-p2-compat.yml": {"workflow_dispatch"},',''))
    artifact="S6-941-native-P2.log"
    must_reject("REQUIRED_941_ARTIFACT_REMOVED",ci.replace(artifact,"deleted"),tmpl.replace(artifact,"deleted"),man,run,surface)
    must_reject("NEWONLY_CANONICAL_HEAD_MISSING",
                ci.replace("issue633-newonly-s6-417-941-required-native-${{ github.run_id }}-${{ github.run_attempt }}-${{ github.event.pull_request.head.sha }}",
                           "issue633-newonly-s6-417-941-required-native-old"),
                tmpl.replace("issue633-newonly-s6-417-941-required-native-${{ github.run_id }}-${{ github.run_attempt }}-${{ github.event.pull_request.head.sha }}",
                             "issue633-newonly-s6-417-941-required-native-old"),
                man,run,surface)
    must_reject("NEWONLY_ALIAS_RETRY_NOT_PINNED",
                ci.replace("Upload New-only first-attempt legacy artifact alias (compatibility only)\n        if: ${{ always() && github.run_attempt == 1 }}",
                           "Upload New-only first-attempt legacy artifact alias (compatibility only)\n        if: always()"),
                tmpl.replace("Upload New-only first-attempt legacy artifact alias (compatibility only)\n        if: ${{ always() && github.run_attempt == 1 }}",
                             "Upload New-only first-attempt legacy artifact alias (compatibility only)\n        if: always()"),
                man,run,surface)
    must_reject("ARCH_CANONICAL_PROVENANCE_MISSING",
                ci,tmpl,
                man.replace("issue541-arch-s6-hybrid-p2-${{ github.run_id }}-${{ github.run_attempt }}-${{ github.sha }}",
                            "issue541-arch-s6-hybrid-p2-unknown"),
                run,surface)
    must_reject("ARCH_LEGACY_ALIAS_DRIFT",
                ci,tmpl,man.replace("issue541-arch-s6-hybrid-p2-${{ github.sha }}",
                                   "issue541-arch-s6-hybrid-legacy-lost"),run,surface)
    print("ISSUE633_ROUTE_MUTATION_SELF_TEST_PASS 18")

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--check",action="store_true")
    parser.add_argument("--self-test",action="store_true")
    args=parser.parse_args()
    if not (args.check or args.self_test):parser.error("use --check or --self-test")
    values=tuple(map(read,(
        ".github/workflows/ci.yml",
        "ci/workflow_templates/general-ci.yml",
        ".github/workflows/issue541-arch-s6-hybrid-p2-compat.yml",
        "ci/issue633_required_newonly_s6_native_p2.py",
        "ci/guards/workflow_surface_guard.py",
    )))
    if args.self_test:selftest(*values)
    if args.check:
        check(*values)
        print("ISSUE633_CI_TEMPLATE_TRIGGER_ARTIFACT_P05_GUARD_PASS")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
