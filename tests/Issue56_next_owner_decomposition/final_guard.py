#!/usr/bin/env python3
"""Final structural/compatibility guard for Issue56."""
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
    "W1_performance_cache_audit": (
        Path("qpx_harness/performance_cache_audit.py"),
        "38e4aa90e67829b536cdf690c7a32596c282ae95",
    ),
    "W2_execution_contract": (
        Path("qpx_harness/execution_contract.py"),
        "1755597f9d16d0d147742cb51d9cb4d3925b057a",
    ),
    "W3_coupling_evr2": (
        Path("qpx_harness/coupling_evr2_runtime.py"),
        "ab74a0180ae2b512109e006de46c3708508832e2",
    ),
    "qpx_cli": (
        Path("scripts/qpx.py"),
        "b48c6ad0427ad1fe8cfdb7a3b0e54ff4335fb45f",
    ),
}

W4_FACADE = Path("qpx_harness/issue45_first_linear.py")
W4_OWNERS = (
    Path("qpx_harness/issue45/first_linear_structure.py"),
    Path("qpx_harness/issue45/first_linear_stats.py"),
    Path("qpx_harness/issue45/first_linear_orchestration.py"),
    Path("qpx_harness/issue45/first_linear_characterization.py"),
)
W5_FACADE = Path("qpx_harness/dmix_equivalence.py")
W5_OWNERS = (
    Path("qpx_harness/dmix/source_transform.py"),
    Path("qpx_harness/dmix/analysis.py"),
    Path("qpx_harness/dmix/runtime.py"),
    Path("qpx_harness/dmix/characterization.py"),
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
            print(f"ISSUE56_FINAL_{group}_OWNER: FAIL missing={rel}")
            ok = False
            continue
        loc = len(path.read_text().splitlines())
        status = "PASS" if loc <= 500 else "FAIL"
        print(f"ISSUE56_FINAL_{group}_OWNER: {status} {rel.name} loc={loc}")
        ok = ok and status == "PASS"
    return ok


def main() -> int:
    failed = False

    for label, (rel, expected) in UNCHANGED.items():
        path = ROOT / rel
        observed = git_blob_sha(path) if path.is_file() else "MISSING"
        status = "PASS" if observed == expected else "FAIL"
        print(
            f"ISSUE56_FINAL_UNCHANGED: {status} {label} "
            f"observed={observed} expected={expected}"
        )
        failed = failed or status != "PASS"

    for group, rel in (("W4", W4_FACADE), ("W5", W5_FACADE)):
        path = ROOT / rel
        funcs = facade_functions(path) if path.is_file() else set()
        loc = len(path.read_text().splitlines()) if path.is_file() else 10**9
        thin = funcs <= {"main"} and loc <= 120
        print(f"ISSUE56_FINAL_{group}_THIN_FACADE: {'PASS' if thin else 'FAIL'}")
        print(f"ISSUE56_FINAL_{group}_FACADE_LOC: {loc}")
        failed = failed or not thin

    failed = failed or not owner_guard("W4", W4_OWNERS)
    failed = failed or not owner_guard("W5", W5_OWNERS)

    try:
        w4 = importlib.import_module("qpx_harness.issue45_first_linear")
        w4_structure = importlib.import_module("qpx_harness.issue45.first_linear_structure")
        w4_stats = importlib.import_module("qpx_harness.issue45.first_linear_stats")
        w4_orch = importlib.import_module("qpx_harness.issue45.first_linear_orchestration")
        w4_char = importlib.import_module("qpx_harness.issue45.first_linear_characterization")
        w4_identity = (
            w4.audit_first_linear_structure is w4_structure.audit_first_linear_structure
            and w4.build_first_linear_stats is w4_stats.build_first_linear_stats
            and w4.run_preflight is w4_orch.run_preflight
            and w4.run_diagnostic is w4_orch.run_diagnostic
            and w4.self_test is w4_char.self_test
            and w4.instrument_first_linear is w4.first_linear_recipe.instrument_first_linear
            and w4.analyze_first_linear_text is w4.first_linear_recipe.analyze_first_linear_text
        )
    except Exception as exc:
        print(f"ISSUE56_FINAL_W4_IMPORT_IDENTITY: FAIL ({exc})")
        w4_identity = False
    else:
        print(f"ISSUE56_FINAL_W4_IMPORT_IDENTITY: {'PASS' if w4_identity else 'FAIL'}")
    failed = failed or not w4_identity

    try:
        w5 = importlib.import_module("qpx_harness.dmix_equivalence")
        w5_source = importlib.import_module("qpx_harness.dmix.source_transform")
        w5_analysis = importlib.import_module("qpx_harness.dmix.analysis")
        w5_runtime = importlib.import_module("qpx_harness.dmix.runtime")
        w5_char = importlib.import_module("qpx_harness.dmix.characterization")
        evr2 = importlib.import_module("qpx_harness.coupling_evr2_runtime")
        w5_identity = (
            w5.legacy_source_transform is w5_source.legacy_source_transform
            and w5.legacy_source is w5_source.legacy_source
            and w5.compare is w5_analysis.compare
            and w5.trace_input is w5_analysis.trace_input
            and w5.validate is w5_runtime.validate
            and w5.self_test is w5_char.self_test
        )
        consumer_identity = evr2.legacy_source_transform is w5.legacy_source_transform
    except Exception as exc:
        print(f"ISSUE56_FINAL_W5_IMPORT_IDENTITY: FAIL ({exc})")
        print(f"ISSUE56_FINAL_W3_W5_CONSUMER_IDENTITY: FAIL ({exc})")
        w5_identity = False
        consumer_identity = False
    else:
        print(f"ISSUE56_FINAL_W5_IMPORT_IDENTITY: {'PASS' if w5_identity else 'FAIL'}")
        print(
            "ISSUE56_FINAL_W3_W5_CONSUMER_IDENTITY: "
            + ("PASS" if consumer_identity else "FAIL")
        )
    failed = failed or not w5_identity or not consumer_identity

    qpx_text = (ROOT / "scripts/qpx.py").read_text()
    cli_ok = all(
        token in qpx_text
        for token in (
            '"coupling-evr2"',
            '"inventory-first-linear"',
            '"dmix-equivalence"',
            "issue45_first_linear import main as first_linear_main",
            "dmix_equivalence import main as dmix_equivalence_main",
        )
    )
    print(f"ISSUE56_FINAL_CLI_SURFACE: {'PASS' if cli_ok else 'FAIL'}")
    failed = failed or not cli_ok

    print("ISSUE56_FINAL_W1_DECISION: KEEP_COHESIVE")
    print("ISSUE56_FINAL_W2_DECISION: KEEP_COHESIVE")
    print("ISSUE56_FINAL_W3_DECISION: KEEP_COHESIVE")
    print("ISSUE56_FINAL_W4_DECISION: SPLIT_APPLIED")
    print("ISSUE56_FINAL_W5_DECISION: SPLIT_APPLIED")
    print("ISSUE56_FINAL_REFACTOR_EVRS: 0")
    print(f"ISSUE56_FINAL_GUARD: {'FAIL' if failed else 'PASS'}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
