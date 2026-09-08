#!/usr/bin/env python3
"""Read-only M0/final ownership inventory for Issue55."""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

BASELINE = {
    "W1": ("qpx_harness/scale_audit.py", 22046, "KEEP_COHESIVE"),
    "W2": ("qpx_harness/issue43_fast_relaxation.py", 74106, "SPLIT_APPLIED"),
    "W3": ("qpx_harness/issue43_coupling_diagnostic.py", 37630, "KEEP_COHESIVE"),
    "W4": ("qpx_harness/issue46_jacobian_localization.py", 39568, "KEEP_COHESIVE"),
    "W5": ("qpx_harness/issue46_fd_reference.py", 29894, "KEEP_COHESIVE"),
}

W2_OWNERS = (
    "qpx_harness/issue43_fast_base.py",
    "qpx_harness/issue43_fast_contract.py",
    "qpx_harness/issue43_fast_v3_characterization.py",
    "qpx_harness/issue43_fast_output_contract.py",
    "qpx_harness/issue43_fast_output_analysis.py",
    "qpx_harness/issue43_fast_output_execution.py",
    "qpx_harness/issue43_fast_orchestration.py",
    "qpx_harness/issue43_fast_characterization.py",
)


def top_level_symbols(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(), filename=str(path))
    symbols: list[str] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            symbols.append(node.name)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, ast.Name):
                    symbols.append(target.id)
    return symbols


def main() -> int:
    ok = True
    for work_id, (relative, baseline_bytes, decision) in BASELINE.items():
        path = ROOT / relative
        if not path.is_file():
            print(f"ISSUE55_M0_TARGET: FAIL {work_id} missing={relative}")
            ok = False
            continue
        data = path.read_bytes()
        symbols = top_level_symbols(path)
        print(
            f"ISSUE55_M0_TARGET: PASS {work_id} decision={decision} "
            f"baseline_bytes={baseline_bytes} current_bytes={len(data)} "
            f"current_loc={len(path.read_text().splitlines())}"
        )
        for symbol in symbols:
            print(f"ISSUE55_M0_SYMBOL: {work_id} {symbol}")

    for relative in W2_OWNERS:
        path = ROOT / relative
        if not path.is_file():
            print(f"ISSUE55_M0_W2_OWNER: FAIL missing={relative}")
            ok = False
            continue
        print(
            f"ISSUE55_M0_W2_OWNER: PASS {relative} "
            f"bytes={len(path.read_bytes())} loc={len(path.read_text().splitlines())}"
        )

    print("ISSUE55_M0_REFACTOR_EVRS: 0")
    print("ISSUE55_M0_INVENTORY:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
