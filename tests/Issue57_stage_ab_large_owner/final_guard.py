#!/usr/bin/env python3
"""Final structural/compatibility guard for Issue57 Stage A/B campaign."""
from __future__ import annotations

import ast
import hashlib
import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

UNCHANGED = {
    "A2_fd_reference": (Path("qpx_harness/issue46_fd_reference.py"), "16194cc4d696f883e41fb0d7ab302b5e203f634c"),
    "A3_jacobian_localization": (Path("qpx_harness/issue46_jacobian_localization.py"), "a39d914330ec43da3612910b83c53e167f921b7c"),
    "A4_coupling_evr2": (Path("qpx_harness/coupling_evr2_runtime.py"), "ab74a0180ae2b512109e006de46c3708508832e2"),
    "A5_scale_audit": (Path("qpx_harness/scale_audit.py"), "1d197b66e48f519539079d327e854e96e6dc6147"),
    "B1_issue45_orchestration": (Path("qpx_harness/issue45/orchestration.py"), "26234925916de99fdb268b0fa6bf6f11490d032f"),
    "B2_execution_contract": (Path("qpx_harness/execution_contract.py"), "1755597f9d16d0d147742cb51d9cb4d3925b057a"),
    "B3_performance_cache": (Path("qpx_harness/performance_cache_audit.py"), "38e4aa90e67829b536cdf690c7a32596c282ae95"),
    "B5_relaxation_runtime": (Path("qpx_harness/issue43_relaxation_runtime.py"), "5aaaa9e3d73da0a8679e07f0129542383341c19c"),
    "qpx_cli": (Path("scripts/qpx.py"), "b48c6ad0427ad1fe8cfdb7a3b0e54ff4335fb45f"),
}

A1_FACADE = Path("qpx_harness/issue43_coupling_diagnostic.py")
A1_OWNERS = (
    Path("qpx_harness/issue43_coupling/constants.py"),
    Path("qpx_harness/issue43_coupling/structure.py"),
    Path("qpx_harness/issue43_coupling/analysis.py"),
    Path("qpx_harness/issue43_coupling/orchestration.py"),
    Path("qpx_harness/issue43_coupling/characterization.py"),
)
B4_FACADE = Path("qpx_harness/coupling_evr1_runtime.py")
B4_OWNERS = (
    Path("qpx_harness/coupling_evr1/classification.py"),
    Path("qpx_harness/coupling_evr1/orchestration.py"),
    Path("qpx_harness/coupling_evr1/characterization.py"),
)


def git_blob_sha(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def facade_functions(path: Path) -> set[str]:
    tree = ast.parse(path.read_text())
    return {
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def owner_guard(group: str, rels: tuple[Path, ...]) -> bool:
    ok = True
    for rel in rels:
        path = ROOT / rel
        if not path.is_file():
            print(f"ISSUE57_FINAL_{group}_OWNER: FAIL missing={rel}")
            ok = False
            continue
        loc = len(path.read_text().splitlines())
        passed = loc <= 500
        print(f"ISSUE57_FINAL_{group}_OWNER: {'PASS' if passed else 'FAIL'} {rel.name} loc={loc}")
        ok = ok and passed
    return ok


def main() -> int:
    failed = False

    for label, (rel, expected) in UNCHANGED.items():
        path = ROOT / rel
        observed = git_blob_sha(path) if path.is_file() else "MISSING"
        passed = observed == expected
        print(
            f"ISSUE57_FINAL_UNCHANGED: {'PASS' if passed else 'FAIL'} {label} "
            f"observed={observed} expected={expected}"
        )
        failed = failed or not passed

    for group, rel in (("A1", A1_FACADE), ("B4", B4_FACADE)):
        path = ROOT / rel
        funcs = facade_functions(path) if path.is_file() else set()
        loc = len(path.read_text().splitlines()) if path.is_file() else 10**9
        thin = funcs <= {"main"} and loc <= 140
        print(f"ISSUE57_FINAL_{group}_THIN_FACADE: {'PASS' if thin else 'FAIL'}")
        print(f"ISSUE57_FINAL_{group}_FACADE_LOC: {loc}")
        failed = failed or not thin

    failed = failed or not owner_guard("A1", A1_OWNERS)
    failed = failed or not owner_guard("B4", B4_OWNERS)

    try:
        a1 = importlib.import_module("qpx_harness.issue43_coupling_diagnostic")
        a1_structure = importlib.import_module("qpx_harness.issue43_coupling.structure")
        a1_analysis = importlib.import_module("qpx_harness.issue43_coupling.analysis")
        a1_orch = importlib.import_module("qpx_harness.issue43_coupling.orchestration")
        a1_char = importlib.import_module("qpx_harness.issue43_coupling.characterization")
        a3 = importlib.import_module("qpx_harness.issue46_jacobian_localization")
        a1_identity = (
            a1.instrument_input is a1_structure.instrument_input
            and a1.analyze_log_text is a1_analysis.analyze_log_text
            and a1.analyze_jacobian_text is a1_analysis.analyze_jacobian_text
            and a1.run_preflight is a1_orch.run_preflight
            and a1.run_runtime is a1_orch.run_runtime
            and a1.run_jacobian_runtime is a1_orch.run_jacobian_runtime
            and a1.self_test is a1_char.self_test
            and a1.DIAGNOSTIC_PETSC_OPTIONS is a1.recipe.DIAGNOSTIC_PETSC_OPTIONS
            and a1.JACOBIAN_PETSC_OPTIONS is a1.recipe.JACOBIAN_PETSC_OPTIONS
        )
        a3_consumer = a3.coupling_diag.analyze_jacobian_text is a1.analyze_jacobian_text
    except Exception as exc:
        print(f"ISSUE57_FINAL_A1_IMPORT_IDENTITY: FAIL ({exc})")
        print(f"ISSUE57_FINAL_A3_A1_CONSUMER_IDENTITY: FAIL ({exc})")
        a1_identity = False
        a3_consumer = False
    else:
        print(f"ISSUE57_FINAL_A1_IMPORT_IDENTITY: {'PASS' if a1_identity else 'FAIL'}")
        print(f"ISSUE57_FINAL_A3_A1_CONSUMER_IDENTITY: {'PASS' if a3_consumer else 'FAIL'}")
    failed = failed or not a1_identity or not a3_consumer

    try:
        b4 = importlib.import_module("qpx_harness.coupling_evr1_runtime")
        b4_class = importlib.import_module("qpx_harness.coupling_evr1.classification")
        b4_orch = importlib.import_module("qpx_harness.coupling_evr1.orchestration")
        b4_char = importlib.import_module("qpx_harness.coupling_evr1.characterization")
        dmix = importlib.import_module("qpx_harness.dmix_equivalence")
        b4_identity = (
            b4.preliminary_classification is b4_class.preliminary_classification
            and b4.run is b4_orch.run
            and b4._create_root is b4_orch._create_root
            and b4.self_test is b4_char.self_test
        )
        dmix_identity = b4_orch.legacy_source_transform is dmix.legacy_source_transform
    except Exception as exc:
        print(f"ISSUE57_FINAL_B4_IMPORT_IDENTITY: FAIL ({exc})")
        print(f"ISSUE57_FINAL_B4_DMIX_IDENTITY: FAIL ({exc})")
        b4_identity = False
        dmix_identity = False
    else:
        print(f"ISSUE57_FINAL_B4_IMPORT_IDENTITY: {'PASS' if b4_identity else 'FAIL'}")
        print(f"ISSUE57_FINAL_B4_DMIX_IDENTITY: {'PASS' if dmix_identity else 'FAIL'}")
    failed = failed or not b4_identity or not dmix_identity

    qpx_text = (ROOT / "scripts/qpx.py").read_text()
    cli_ok = all(
        token in qpx_text
        for token in (
            '"fast-coupling-diagnostic"',
            '"coupling-evr1"',
            "issue43_coupling_diagnostic import main as fast_coupling_diagnostic_main",
            "coupling_evr1_runtime import main as coupling_evr1_main",
        )
    )
    print(f"ISSUE57_FINAL_CLI_SURFACE: {'PASS' if cli_ok else 'FAIL'}")
    failed = failed or not cli_ok

    decisions = {
        "A1": "SPLIT_APPLIED",
        "A2": "KEEP_COHESIVE",
        "A3": "KEEP_COHESIVE",
        "A4": "KEEP_COHESIVE",
        "A5": "KEEP_COHESIVE",
        "B1": "KEEP_COHESIVE",
        "B2": "KEEP_COHESIVE",
        "B3": "KEEP_COHESIVE",
        "B4": "SPLIT_APPLIED",
        "B5": "KEEP_COHESIVE",
    }
    for label, decision in decisions.items():
        print(f"ISSUE57_FINAL_{label}_DECISION: {decision}")
    print("ISSUE57_FINAL_REFACTOR_EVRS: 0")
    print(f"ISSUE57_FINAL_GUARD: {'FAIL' if failed else 'PASS'}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
