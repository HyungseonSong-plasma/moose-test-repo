#!/usr/bin/env python3
"""M0-AB inventory for Issue57 Stage A/B large-owner campaign."""
from __future__ import annotations

import ast
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

TARGETS = {
    "A1": (Path("qpx_harness/issue43_coupling_diagnostic.py"), "dedda10e8db74e81c32d86d2ccf17f3dd996595b", 1025, "SPLIT_APPLIED"),
    "A2": (Path("qpx_harness/issue46_fd_reference.py"), "16194cc4d696f883e41fb0d7ab302b5e203f634c", 773, "KEEP_COHESIVE"),
    "A3": (Path("qpx_harness/issue46_jacobian_localization.py"), "a39d914330ec43da3612910b83c53e167f921b7c", 698, "KEEP_COHESIVE"),
    "A4": (Path("qpx_harness/coupling_evr2_runtime.py"), "ab74a0180ae2b512109e006de46c3708508832e2", 624, "KEEP_COHESIVE"),
    "A5": (Path("qpx_harness/scale_audit.py"), "1d197b66e48f519539079d327e854e96e6dc6147", 570, "KEEP_COHESIVE"),
    "B1": (Path("qpx_harness/issue45/orchestration.py"), "26234925916de99fdb268b0fa6bf6f11490d032f", 565, "KEEP_COHESIVE"),
    "B2": (Path("qpx_harness/execution_contract.py"), "1755597f9d16d0d147742cb51d9cb4d3925b057a", 528, "KEEP_COHESIVE"),
    "B3": (Path("qpx_harness/performance_cache_audit.py"), "38e4aa90e67829b536cdf690c7a32596c282ae95", 506, "KEEP_COHESIVE"),
    "B4": (Path("qpx_harness/coupling_evr1_runtime.py"), "6b4d849a64abe489f5602128c8a836d2d752b5d8", 503, "SPLIT_APPLIED"),
    "B5": (Path("qpx_harness/issue43_relaxation_runtime.py"), "5aaaa9e3d73da0a8679e07f0129542383341c19c", 476, "KEEP_COHESIVE"),
}

OWNERS = {
    "A1": (
        Path("qpx_harness/issue43_coupling/constants.py"),
        Path("qpx_harness/issue43_coupling/structure.py"),
        Path("qpx_harness/issue43_coupling/analysis.py"),
        Path("qpx_harness/issue43_coupling/orchestration.py"),
        Path("qpx_harness/issue43_coupling/characterization.py"),
    ),
    "B4": (
        Path("qpx_harness/coupling_evr1/classification.py"),
        Path("qpx_harness/coupling_evr1/orchestration.py"),
        Path("qpx_harness/coupling_evr1/characterization.py"),
    ),
}

CONSUMERS = {
    "A1": (
        Path("qpx_harness/issue46_jacobian_localization.py"),
        Path("scripts/qpx.py"),
    ),
    "B4": (Path("scripts/qpx.py"),),
}


def git_blob_sha(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def top_symbols(path: Path) -> list[str]:
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


def main() -> int:
    failed = False
    for label, (rel, baseline_sha, baseline_loc, decision) in TARGETS.items():
        path = ROOT / rel
        if not path.is_file():
            print(f"ISSUE57_M0_TARGET: FAIL {label} missing={rel}")
            failed = True
            continue
        sha = git_blob_sha(path)
        loc = len(path.read_text().splitlines())
        if decision == "KEEP_COHESIVE":
            ok = sha == baseline_sha and loc == baseline_loc
        else:
            ok = sha != baseline_sha and loc <= 140
        print(
            f"ISSUE57_M0_TARGET: {'PASS' if ok else 'FAIL'} {label} "
            f"decision={decision} baseline_loc={baseline_loc} current_loc={loc} "
            f"current_sha={sha}"
        )
        failed = failed or not ok
        for symbol in top_symbols(path):
            print(f"ISSUE57_M0_SYMBOL: {label} {symbol}")
        for consumer in CONSUMERS.get(label, ()):
            if (ROOT / consumer).is_file():
                print(f"ISSUE57_M0_CONSUMER: {label} {consumer}")
            else:
                print(f"ISSUE57_M0_CONSUMER: FAIL {label} missing={consumer}")
                failed = True

    for label, rels in OWNERS.items():
        for rel in rels:
            path = ROOT / rel
            if not path.is_file():
                print(f"ISSUE57_M0_OWNER: FAIL {label} missing={rel}")
                failed = True
                continue
            loc = len(path.read_text().splitlines())
            ok = loc <= 500
            print(f"ISSUE57_M0_OWNER: {'PASS' if ok else 'FAIL'} {label} {rel} loc={loc}")
            failed = failed or not ok

    print("ISSUE57_M0_REFACTOR_EVRS: 0")
    print(f"ISSUE57_M0_INVENTORY: {'FAIL' if failed else 'PASS'}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
