#!/usr/bin/env python3
"""Consolidated read-only structural/import gate for Issue55."""
from __future__ import annotations

import ast
import hashlib
import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
root_text = str(ROOT)
if root_text not in sys.path:
    sys.path.insert(0, root_text)

FACADE = ROOT / "qpx_harness" / "issue43_fast_relaxation.py"
COUPLING = ROOT / "qpx_harness" / "issue43_coupling_diagnostic.py"
QPX_CLI = ROOT / "scripts" / "qpx.py"

UNCHANGED_BLOBS = {
    "W1_scale_audit": (
        ROOT / "qpx_harness" / "scale_audit.py",
        "1d197b66e48f519539079d327e854e96e6dc6147",
    ),
    "W3_coupling_diagnostic": (
        COUPLING,
        "dedda10e8db74e81c32d86d2ccf17f3dd996595b",
    ),
    "W4_jacobian_localization": (
        ROOT / "qpx_harness" / "issue46_jacobian_localization.py",
        "a39d914330ec43da3612910b83c53e167f921b7c",
    ),
    "W5_fd_reference": (
        ROOT / "qpx_harness" / "issue46_fd_reference.py",
        "16194cc4d696f883e41fb0d7ab302b5e203f634c",
    ),
    "qpx_cli": (QPX_CLI, "b48c6ad0427ad1fe8cfdb7a3b0e54ff4335fb45f"),
}

OWNER_FUNCTIONS = {
    "issue43_fast_base.py": {
        "_write_json",
        "_create_root",
        "_stage_case",
        "_build_feedback_fixed",
    },
    "issue43_fast_contract.py": {
        "_build_execution_contract",
        "_run_case_safe",
    },
    "issue43_fast_v3_characterization.py": {"_v3_compat_self_test"},
    "issue43_fast_output_contract.py": {
        "_build_feedback_v5",
        "_augment_execution_contract",
    },
    "issue43_fast_output_analysis.py": {
        "_solver_trajectory",
        "_framework_output_evidence",
        "_evaluate_output_runtime_confirmation",
    },
    "issue43_fast_output_execution.py": {
        "_run_output_preflight",
        "_run_output_runtime_confirmation",
    },
    "issue43_fast_orchestration.py": {
        "_install_artifact_namespace",
        "_guarded_classify",
        "_run_issue43_guarded",
    },
    "issue43_fast_characterization.py": {"self_test"},
}


def git_blob_sha(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()


def functions(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(), filename=str(path))
    return {
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def main() -> int:
    ok = True

    for label, (path, expected) in UNCHANGED_BLOBS.items():
        observed = git_blob_sha(path) if path.is_file() else "MISSING"
        passed = observed == expected
        print(
            f"ISSUE55_FINAL_UNCHANGED: {'PASS' if passed else 'FAIL'} "
            f"{label} observed={observed} expected={expected}"
        )
        ok = ok and passed

    facade_functions = functions(FACADE)
    thin = facade_functions == {"main"}
    print(
        "ISSUE55_FINAL_W2_THIN_FACADE:",
        "PASS" if thin else "FAIL functions=" + ",".join(sorted(facade_functions)),
    )
    ok = ok and thin

    owner_root = ROOT / "qpx_harness"
    for filename, required in OWNER_FUNCTIONS.items():
        path = owner_root / filename
        if not path.is_file():
            print(f"ISSUE55_FINAL_W2_OWNER: FAIL {filename} missing")
            ok = False
            continue
        try:
            observed = functions(path)
        except Exception as exc:
            print(f"ISSUE55_FINAL_W2_OWNER: FAIL {filename} parse={exc}")
            ok = False
            continue
        missing = required - observed
        if missing:
            print(
                f"ISSUE55_FINAL_W2_OWNER: FAIL {filename} missing="
                + ",".join(sorted(missing))
            )
            ok = False
        else:
            print(
                f"ISSUE55_FINAL_W2_OWNER: PASS {filename} "
                f"loc={len(path.read_text().splitlines())}"
            )

    try:
        facade = importlib.import_module("qpx_harness.issue43_fast_relaxation")
        contract = importlib.import_module("qpx_harness.issue43_fast_contract")
        output_contract = importlib.import_module("qpx_harness.issue43_fast_output_contract")
        output_analysis = importlib.import_module("qpx_harness.issue43_fast_output_analysis")
        output_execution = importlib.import_module("qpx_harness.issue43_fast_output_execution")
        orchestration = importlib.import_module("qpx_harness.issue43_fast_orchestration")
        characterization = importlib.import_module("qpx_harness.issue43_fast_characterization")
        identities = (
            facade._build_feedback_v5 is output_contract._build_feedback_v5
            and facade._augment_execution_contract is output_contract._augment_execution_contract
            and facade._solver_trajectory is output_analysis._solver_trajectory
            and facade._run_output_preflight is output_execution._run_output_preflight
            and facade._run_output_runtime_confirmation
            is output_execution._run_output_runtime_confirmation
            and facade._run_issue43_guarded is orchestration._run_issue43_guarded
            and facade.self_test is characterization.self_test
        )
    except Exception as exc:
        print(f"ISSUE55_FINAL_W2_IMPORT_IDENTITY: FAIL ({exc})")
        ok = False
        contract = None
        orchestration = None
    else:
        print("ISSUE55_FINAL_W2_IMPORT_IDENTITY:", "PASS" if identities else "FAIL")
        ok = ok and identities

    if contract is not None and orchestration is not None:
        original_writer = contract._CONTRACT_ARTIFACT_WRITER
        try:
            orchestration._install_artifact_namespace()
            routed = (
                contract._CONTRACT_ARTIFACT_WRITER
                is orchestration._write_contract_artifacts_isolated
            )
        finally:
            contract._CONTRACT_ARTIFACT_WRITER = original_writer
        print("ISSUE55_FINAL_W2_WRITER_ROUTING:", "PASS" if routed else "FAIL")
        ok = ok and routed

    coupling_text = COUPLING.read_text()
    downstream_ok = (
        "from . import issue43_fast_relaxation as v5" in coupling_text
        and "v5._build_feedback_v5" in coupling_text
        and "v5._augment_execution_contract" in coupling_text
    )
    print("ISSUE55_FINAL_W3_FACADE_CONSUMER:", "PASS" if downstream_ok else "FAIL")
    ok = ok and downstream_ok

    cli_text = QPX_CLI.read_text()
    cli_ok = (
        "from qpx_harness.issue43_fast_relaxation import" in cli_text
        and '"fast-relaxation"' in cli_text
        and "fast_relaxation_self_test" in cli_text
    )
    print("ISSUE55_FINAL_CLI_SURFACE:", "PASS" if cli_ok else "FAIL")
    ok = ok and cli_ok

    print("ISSUE55_FINAL_W1_DECISION: KEEP_COHESIVE")
    print("ISSUE55_FINAL_W2_DECISION: SPLIT_APPLIED")
    print("ISSUE55_FINAL_W3_DECISION: KEEP_COHESIVE")
    print("ISSUE55_FINAL_W4_DECISION: KEEP_COHESIVE")
    print("ISSUE55_FINAL_W5_DECISION: KEEP_COHESIVE")
    print("ISSUE55_FINAL_W2_FACADE_LOC:", len(FACADE.read_text().splitlines()))
    print("ISSUE55_FINAL_REFACTOR_EVRS: 0")
    print("ISSUE55_FINAL_GUARD:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
