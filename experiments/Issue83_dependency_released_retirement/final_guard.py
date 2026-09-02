#!/usr/bin/env python3
"""Final dependency-released retirement sweep guard for Issue #83."""
from __future__ import annotations
import ast
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

CENSUS = ROOT / "docs/development/2026-09-02_issue83_dependency_released_retirement_census.json"
CENSUS80 = ROOT / "docs/development/2026-09-02_issue80_migration_test_retirement_census.json"
CENSUS84 = ROOT / "docs/development/2026-09-02_issue84_live_owner_migration_census.json"

def _module(path: Path) -> str:
    parts=list(path.relative_to(ROOT).with_suffix("").parts)
    if parts and parts[-1]=="__init__": parts.pop()
    return ".".join(parts)

def _imports(path: Path) -> set[str]:
    source=path.read_text(encoding="utf-8"); tree=ast.parse(source,filename=str(path)); module=_module(path); package=module if path.name=="__init__.py" else module.rpartition(".")[0]; out=set()
    for node in ast.walk(tree):
        if isinstance(node,ast.Import): out.update(a.name for a in node.names)
        elif isinstance(node,ast.ImportFrom):
            if node.level:
                try: base=importlib.util.resolve_name("."*node.level+(node.module or ""),package)
                except (ImportError,ValueError): continue
            else: base=node.module or ""
            if base: out.add(base)
            out.update(f"{base}.{a.name}" if base else a.name for a in node.names if a.name!="*")
    return out

def _candidate_module(rel: str) -> str | None:
    if not rel.startswith("qpx_harness/") or not rel.endswith(".py"): return None
    return rel[:-3].replace("/",".")

def _check_census() -> set[str]:
    data=json.loads(CENSUS.read_text(encoding="utf-8")); assert data["issue"]==83; assert data["scientific_semantic_impact"]=="NONE"; assert data["scientific_p3"]=="NOT_RUN"
    rows=data["candidates"]; assert len(rows)==data["summary"]["candidate_paths_reviewed"]==42; assert len({r["path"] for r in rows})==42; assert all(r["terminal_class"]=="ALREADY_RETIRED" for r in rows); assert data["summary"]["retired_in_issue83"]==1; assert data["summary"]["retirement_blocker_defects"]==0; assert data["acceptance"]["eligible_retirement_residual_count"]==0
    for row in rows:
        assert not (ROOT/row["path"]).exists(), f"eligible retirement remains: {row['path']}"; assert row["consumer_count"]==0; assert row["unique_behavior_or_invariant"]=="NONE"; assert row["canonical_replacement"]; assert row["replacement_guard"]
    paths={r["path"] for r in rows}; handoff="qpx_harness/performance_transport_probe_runtime.py"; handoff_row=next(r for r in rows if r["path"]==handoff); assert handoff_row.get("retired_in_issue83") is True; assert handoff_row["retirement_issue"]==83
    c84=json.loads(CENSUS84.read_text(encoding="utf-8")); assert c84["unresolved_ownership_blockers"]==0; assert {r["old_path"] for r in c84["migrations"]} <= paths; assert {r["path"] for r in c84["retirement_handoff"]} <= paths
    c80=json.loads(CENSUS80.read_text(encoding="utf-8")); deleted80={p for p,d in c80["dispositions"].items() if d in {"PROMOTE_INVARIANT_THEN_RETIRE","RETIRE_SUPERSEDED_MIGRATION_ONLY"}}; assert deleted80 <= paths
    return paths

def _check_no_consumers(paths: set[str]) -> None:
    modules={m for p in paths if (m:=_candidate_module(p))}; violations={}
    for root_name in ("qpx_harness","recipes","bin","tests"):
        root=ROOT/root_name
        if not root.exists(): continue
        for path in root.rglob("*.py"):
            if path.resolve()==Path(__file__).resolve(): continue
            hits=sorted(i for i in _imports(path) if i in modules)
            if hits: violations[str(path.relative_to(ROOT))]=hits
    assert violations=={}, violations
    init=(ROOT/"qpx_harness/__init__.py").read_text(encoding="utf-8"); assert "performance_transport_probe_runtime" not in init
    cli_text="\n".join(p.read_text(encoding="utf-8") for p in (ROOT/"qpx_harness/cli").rglob("*.py")); assert "performance_transport_probe_runtime" not in cli_text

def _run(*args: str) -> str:
    p=subprocess.run([sys.executable,*args],cwd=ROOT,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,check=False)
    if p.returncode: raise AssertionError(f"rc={p.returncode}: {' '.join(args)}\n{p.stdout}")
    return p.stdout

def _safety_net() -> None:
    assert "ISSUE80_MIGRATION_TEST_RETIREMENT_GUARD: PASS" in _run(str(ROOT/"tests/Issue80_migration_test_retirement/final_guard.py")); assert "ISSUE84_LIVE_OWNER_MIGRATION_GUARD: PASS" in _run(str(ROOT/"tests/Issue84_live_owner_migration/final_guard.py")); assert "ISSUE70_ARCHITECTURE_CENSUS: PASS" in _run(str(ROOT/"tools/qpx_architecture_census.py")); assert "QPX_HARNESS_SELFTEST: PASS" in _run(str(ROOT/"bin/qpx.py"),"self-test")

def main() -> int:
    paths=_check_census(); _check_no_consumers(paths); _safety_net(); print("ISSUE83_DEPENDENCY_RELEASED_RETIREMENT_GUARD: PASS"); print("Issue83 scientific P3: NOT_RUN"); return 0

if __name__=="__main__": raise SystemExit(main())
