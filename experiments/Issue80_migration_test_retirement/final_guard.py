#!/usr/bin/env python3
"""Consolidated static/P0 guard for Issue #80 migration-test retirement."""
from __future__ import annotations
import ast
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

CENSUS = ROOT / "docs/development/2026-09-02_issue80_migration_test_retirement_census.json"
ALLOWED = {"KEEP_CANONICAL_REGRESSION", "KEEP_SCIENTIFIC_CHARACTERIZATION", "KEEP_CURRENT_ARCHITECTURE_GUARD", "PROMOTE_INVARIANT_THEN_RETIRE", "RETIRE_SUPERSEDED_MIGRATION_ONLY", "KEEP_HISTORICAL_REPRODUCTION_WITH_JUSTIFICATION"}
DELETE = {"PROMOTE_INVARIANT_THEN_RETIRE", "RETIRE_SUPERSEDED_MIGRATION_ONLY"}
RETIRED_MODULES = {"qpx_harness.artifacts", "qpx_harness.cases", "qpx_harness.runtime", "qpx_harness.workspace", "qpx_harness.performance_core", "qpx_harness.performance_smoke", "qpx_harness.performance_investigation", "qpx_harness.performance_transport_probe_direct", "qpx_harness.performance_cache_audit", "qpx_harness.analysis.performance.legacy", "qpx_harness.coupling_evr1_runtime", "qpx_harness.coupling_evr2_runtime", "qpx_harness.dmix_equivalence", "qpx_harness.petsc_first_linear_diagnostic", "qpx_harness.augmented_jacobian_localization", "qpx_harness.compat.issue46_fd_reference", "qpx_harness.jacobian_fd_reference_audit", "qpx_harness.fast_plasma_coupling_diagnostic", "qpx_harness.fast_plasma_relaxation_v2", "qpx_harness.fast_plasma_relaxation_v5"}
REQUIRED_RETAINED = {"tests/Issue48_qpx_harness_generality/self_test.py", "tests/Issue48_qpx_harness_generality/wp10_issue31_coupling_recipe_characterization.py", "tests/Issue48_qpx_harness_generality/wp11_issue31_evr1_runtime_characterization.py", "tests/Issue48_qpx_harness_generality/wp12_issue31_evr2_recipe_characterization.py", "tests/Issue48_qpx_harness_generality/wp13_issue31_evr2_runtime_characterization.py", "tests/Issue48_qpx_harness_generality/wp14_performance_cache_audit_cpp_characterization.py", "tests/Issue48_qpx_harness_generality/wp4_issue45_first_linear_characterization.py", "tests/Issue48_qpx_harness_generality/wp4_issue45_inventory_constraint_characterization.py", "tests/Issue48_qpx_harness_generality/wp4_issue46_fd_recipe_characterization.py", "tests/Issue48_qpx_harness_generality/wp7_issue43_relaxation_recipe_characterization.py", "tests/Issue48_qpx_harness_generality/wp8_transport_probe_runtime_characterization.py", "tests/Issue48_qpx_harness_generality/wp9_transport_probe_primitives_characterization.py"}

def _module(path: Path) -> str:
    parts = list(path.relative_to(ROOT).with_suffix("").parts)
    if parts and parts[-1] == "__init__": parts.pop()
    return ".".join(parts)

def _imports(source: str, path: Path) -> set[str]:
    tree = ast.parse(source, filename=str(path)); module = _module(path); package = module if path.name == "__init__.py" else module.rpartition(".")[0]; out=set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import): out.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                try: base = importlib.util.resolve_name("." * node.level + (node.module or ""), package)
                except (ImportError, ValueError): continue
            else: base = node.module or ""
            if base: out.add(base)
            out.update(f"{base}.{a.name}" if base else a.name for a in node.names if a.name != "*")
    return out

def _retired_imports(source: str, path: Path) -> set[str]:
    found=set()
    for imported in _imports(source,path):
        for retired in RETIRED_MODULES:
            if imported == retired or imported.startswith(retired + "."): found.add(retired)
    return found

def _check_census() -> None:
    data=json.loads(CENSUS.read_text(encoding="utf-8")); assert data["issue"]==80; assert data["scientific_semantic_impact"]=="NONE"; assert data["scientific_p3"]=="NOT_RUN"
    dispositions=data["dispositions"]; assert len(dispositions)==data["summary"]["reviewed_test_files"]==35; assert set(dispositions.values()) <= ALLOWED
    deleted={p for p,d in dispositions.items() if d in DELETE}; retained=set(dispositions)-deleted
    assert len(deleted)==data["summary"]["retired_migration_only_files"]==19; assert len(retained)==data["summary"]["retained_current_or_scientific_files"]==16; assert REQUIRED_RETAINED <= retained
    for rel in deleted: assert not (ROOT/rel).exists(), f"retired migration test still exists: {rel}"
    for rel in retained: assert (ROOT/rel).is_file(), f"retained test missing: {rel}"
    proof={row["path"]:row for row in data["retirement_proof"]}; assert set(proof)==deleted; assert all(row["scientific_coverage_impact"]=="NONE" for row in proof.values()); assert data["acceptance"]["scientific_coverage_reduced"] is False

def _check_imports_and_entrypoint() -> None:
    violations={}
    for root_name in ("qpx_harness","recipes","bin","tests"):
        root=ROOT/root_name
        if not root.exists(): continue
        for path in root.rglob("*.py"):
            if path.resolve()==Path(__file__).resolve(): continue
            found=sorted(_retired_imports(path.read_text(encoding="utf-8"),path))
            if found: violations[str(path.relative_to(ROOT))]=found
    assert violations=={}, violations; assert not (ROOT/"scripts/qpx.py").exists(); entry=ROOT/"bin/qpx.py"; assert entry.is_file(); assert "from qpx_harness.cli import main" in entry.read_text(encoding="utf-8")
    escaped="|".join(re.escape(x) for x in sorted(RETIRED_MODULES)); execution=re.compile(rf"python(?:3)?\s+-m\s+(?:{escaped})\b"); bad=[]
    for root_name in ("qpx_harness","recipes","bin"):
        for path in (ROOT/root_name).rglob("*"):
            if path.is_file() and path.suffix in {".py",".sh",".json",".yaml",".yml"}:
                text=path.read_text(encoding="utf-8")
                if execution.search(text) or "scripts/qpx.py" in text: bad.append(str(path.relative_to(ROOT)))
    assert bad==[], bad

def _negative_control() -> None:
    probe=ROOT/"tests/Issue80_migration_test_retirement/_probe.py"; assert "qpx_harness.performance_core" in _retired_imports("from qpx_harness import performance_core\n",probe)

def _run(*args: str) -> str:
    p=subprocess.run([sys.executable,*args],cwd=ROOT,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,check=False)
    if p.returncode: raise AssertionError(f"rc={p.returncode}: {' '.join(args)}\n{p.stdout}")
    return p.stdout

def _safety_net() -> None:
    assert "ISSUE79_CLI_ADAPTER_CONVERGENCE_GUARD: PASS" in _run(str(ROOT/"tests/Issue79_cli_adapter_convergence/final_guard.py")); assert "ISSUE84_LIVE_OWNER_MIGRATION_GUARD: PASS" in _run(str(ROOT/"tests/Issue84_live_owner_migration/final_guard.py")); assert "ISSUE70_ARCHITECTURE_CENSUS: PASS" in _run(str(ROOT/"tools/qpx_architecture_census.py")); assert "ISSUE48_GENERALITY_SELFTEST: PASS" in _run(str(ROOT/"tests/Issue48_qpx_harness_generality/self_test.py")); assert "QPX_HARNESS_SELFTEST: PASS" in _run(str(ROOT/"bin/qpx.py"),"self-test")

def main() -> int:
    _check_census(); _check_imports_and_entrypoint(); _negative_control(); _safety_net(); print("ISSUE80_MIGRATION_TEST_RETIREMENT_GUARD: PASS"); print("Issue80 scientific P3: NOT_RUN"); return 0

if __name__ == "__main__": raise SystemExit(main())
