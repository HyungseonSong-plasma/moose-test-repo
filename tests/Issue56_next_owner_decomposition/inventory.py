#!/usr/bin/env python3
"""Issue56 campaign-wide structural inventory.

Diagnostic-only guard for the disposable ZIP workflow.  It reports current
ownership, top-level symbols, and branch-local textual consumers without
executing any scientific runtime.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

TARGETS = {
    "W1": (Path("qpx_harness/performance_cache_audit.py"), "KEEP_COHESIVE", 19763),
    "W2": (Path("qpx_harness/execution_contract.py"), "KEEP_COHESIVE", 19273),
    "W3": (Path("qpx_harness/coupling_evr2_runtime.py"), "KEEP_COHESIVE", 19208),
    "W4": (Path("qpx_harness/issue45_first_linear.py"), "SPLIT_APPLIED", 18738),
    "W5": (Path("qpx_harness/dmix_equivalence.py"), "SPLIT_APPLIED", 17326),
}

W4_OWNERS = (
    Path("qpx_harness/issue45/first_linear_structure.py"),
    Path("qpx_harness/issue45/first_linear_stats.py"),
    Path("qpx_harness/issue45/first_linear_orchestration.py"),
    Path("qpx_harness/issue45/first_linear_characterization.py"),
)
W5_OWNERS = (
    Path("qpx_harness/dmix/source_transform.py"),
    Path("qpx_harness/dmix/analysis.py"),
    Path("qpx_harness/dmix/runtime.py"),
    Path("qpx_harness/dmix/characterization.py"),
)


def top_level_symbols(path: Path) -> list[str]:
    tree = ast.parse(path.read_text())
    out: list[str] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            out.append(node.name)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, ast.Name):
                    out.append(target.id)
    return out


def textual_consumers(stem: str, target: Path) -> list[str]:
    hits: list[str] = []
    for path in sorted(ROOT.rglob("*.py")):
        rel = path.relative_to(ROOT)
        if rel == target or "tests/Issue56_next_owner_decomposition" in str(rel):
            continue
        try:
            text = path.read_text(errors="replace")
        except OSError:
            continue
        if stem in text:
            hits.append(str(rel))
    return hits


def main() -> int:
    failed = False
    for work, (rel, decision, baseline_bytes) in TARGETS.items():
        path = ROOT / rel
        if not path.is_file():
            print(f"ISSUE56_M0_TARGET: FAIL {work} missing={rel}")
            failed = True
            continue
        data = path.read_bytes()
        loc = len(path.read_text().splitlines())
        print(
            f"ISSUE56_M0_TARGET: PASS {work} decision={decision} "
            f"baseline_bytes={baseline_bytes} current_bytes={len(data)} current_loc={loc}"
        )
        for symbol in top_level_symbols(path):
            print(f"ISSUE56_M0_SYMBOL: {work} {symbol}")
        for consumer in textual_consumers(rel.stem, rel):
            print(f"ISSUE56_M0_CONSUMER: {work} {consumer}")

    for group, owners in (("W4", W4_OWNERS), ("W5", W5_OWNERS)):
        for rel in owners:
            path = ROOT / rel
            if not path.is_file():
                print(f"ISSUE56_M0_OWNER: FAIL {group} missing={rel}")
                failed = True
                continue
            print(
                f"ISSUE56_M0_OWNER: PASS {group} {rel} "
                f"bytes={path.stat().st_size} loc={len(path.read_text().splitlines())}"
            )

    print("ISSUE56_M0_REFACTOR_EVRS: 0")
    print(f"ISSUE56_M0_INVENTORY: {'FAIL' if failed else 'PASS'}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
