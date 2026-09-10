#!/usr/bin/env python3
"""P0 acceptance guard for historical Issue82 performance ownership after retirement."""
from __future__ import annotations

import ast
import csv
import tempfile
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from physics_harness.adapters.moose import source_inspection
from physics_harness.adapters.moose.performance import profile as moose_profile
from physics_harness.adapters.petsc import performance as petsc_performance
from physics_harness.analysis.performance import profile as performance_profile

HISTORICAL_FACTS = {
    "issue": 82,
    "scientific_semantic_impact": "NONE",
    "candidate_top_level_owners_before": 5,
    "candidate_top_level_owners_after": 0,
    "surface_count": 6,
    "pf2_implemented_slice": False,
    "pf2_issue40_status_claim": "UNCHANGED_OPEN_NOT_CLOSED_BY_REFACTOR",
    "scientific_p3": "NOT_RUN",
}

HISTORICAL_SURFACE_DISPOSITIONS = {
    "qpx_harness/performance_core.py": "RETIRED_AFTER_CONSUMER_MIGRATION",
    "qpx_harness/performance_smoke.py": "RETIRED_AFTER_CONSUMER_MIGRATION",
    "qpx_harness/performance_investigation.py": "RETIRED_AFTER_CONSUMER_MIGRATION",
    "qpx_harness/performance_transport_probe_direct.py": "RETIRED_AFTER_CONSUMER_MIGRATION",
    "qpx_harness/performance_cache_audit.py": "BEHAVIOR_SPLIT_THEN_RETIRED",
    "qpx_harness/analysis/performance/legacy.py": "PUBLIC_BEHAVIOR_PROMOTED_THEN_RETIRED",
}

HISTORICAL_PUBLIC_SYMBOL_DISPOSITIONS = {
    "analyze": "PROMOTE_TO_FOCUSED_CAPABILITY",
    "event_time": "PROMOTE_TO_FOCUSED_CAPABILITY",
    "load_petsc_events": "PROMOTE_TO_FOCUSED_CAPABILITY",
    "perfgraph_jacobian_self": "PROMOTE_TO_FOCUSED_CAPABILITY",
}

CURRENT_PUBLIC_SYMBOL_OWNERS = {
    "analyze": (
        "physics_harness/analysis/performance/profile.py::analyze_facts",
        "physics_harness/application/performance.py::analyze_profile",
    ),
    "event_time": (
        "physics_harness/adapters/petsc/performance.py::event_time",
    ),
    "load_petsc_events": (
        "physics_harness/adapters/petsc/performance.py::load_events",
    ),
    "perfgraph_jacobian_self": (
        "physics_harness/adapters/moose/performance/profile.py::jacobian_self_time",
    ),
}

RETIRED_PERFORMANCE_PATHS = (
    "physics_harness/performance_core.py",
    "physics_harness/performance_smoke.py",
    "physics_harness/performance_investigation.py",
    "physics_harness/performance_transport_probe_direct.py",
    "physics_harness/performance_cache_audit.py",
    "physics_harness/analysis/performance/legacy.py",
    "physics_harness/performance/runner.py",
    "physics_harness/performance/smoke.py",
    "physics_harness/performance/probes/runtime.py",
    "physics_harness/performance/probes/transport.py",
    "physics_harness/analysis/performance/cache.py",
    "physics_harness/analysis/performance/investigation.py",
    "physics_harness/cpp/functor_usage.py",
)

CURRENT_OWNER_REQUIREMENTS = {
    "physics_harness/application/performance.py": {
        "PerformanceContractError",
        "validate_experiment_manifest",
        "validate_result_record",
        "run_measurement",
        "analyze_profile",
        "self_test",
    },
    "physics_harness/analysis/performance/profile.py": {
        "analyze_facts",
        "self_test",
    },
    "physics_harness/adapters/petsc/performance.py": {
        "collect_log_view_csv",
        "load_events",
        "event_time",
        "decode_timing_facts",
    },
    "physics_harness/adapters/moose/performance/profile.py": {
        "jacobian_self_time",
    },
    "physics_harness/adapters/moose/source_inspection.py": {
        "FunctorInspectionError",
        "extract_functor_property_declaration",
        "parameter_functor_calls",
    },
    "physics_harness/observation/source_code/cpp.py": {
        "CppSource",
        "split_call_arguments",
    },
    "physics_harness/evidence/artifacts.py": {
        "write_json_bundle",
    },
    "physics_harness/execution/runtime.py": {
        "resolve_executable",
        "run_physics",
        "validate_executable",
    },
    "physics_harness/cli/commands/performance.py": {
        "measure_main",
        "analyze_main",
    },
}

HISTORICAL_PERFORMANCE_COMMANDS = {
    "measure",
    "measure-smoke",
    "investigate",
    "transport-probe",
    "cache-audit",
    "analyze",
}
CURRENT_PERFORMANCE_COMMANDS = {"measure", "analyze"}
RETIRED_PERFORMANCE_COMMANDS = HISTORICAL_PERFORMANCE_COMMANDS - CURRENT_PERFORMANCE_COMMANDS


def _top_level_symbols(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    symbols: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            symbols.add(node.name)
    return symbols


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def _literal_assignment(path: Path, name: str):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in tree.body:
        if isinstance(node, ast.Assign):
            if any(isinstance(target, ast.Name) and target.id == name for target in node.targets):
                return ast.literal_eval(node.value)
        elif isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name) and node.target.id == name:
                return ast.literal_eval(node.value)
    raise AssertionError(f"missing literal assignment: {path}: {name}")


def _check_historical_contract() -> None:
    expected_facts = {
        "issue": 82,
        "scientific_semantic_impact": "NONE",
        "candidate_top_level_owners_before": 5,
        "candidate_top_level_owners_after": 0,
        "surface_count": 6,
        "pf2_implemented_slice": False,
        "pf2_issue40_status_claim": "UNCHANGED_OPEN_NOT_CLOSED_BY_REFACTOR",
        "scientific_p3": "NOT_RUN",
    }
    if HISTORICAL_FACTS != expected_facts:
        raise AssertionError("Issue82 historical acceptance facts drifted")
    if len(HISTORICAL_SURFACE_DISPOSITIONS) != HISTORICAL_FACTS["surface_count"]:
        raise AssertionError("Issue82 historical surface census drifted")
    if set(HISTORICAL_PUBLIC_SYMBOL_DISPOSITIONS) != set(CURRENT_PUBLIC_SYMBOL_OWNERS):
        raise AssertionError("Issue82 historical public symbol disposition drifted")
    if any(
        disposition != "PROMOTE_TO_FOCUSED_CAPABILITY"
        for disposition in HISTORICAL_PUBLIC_SYMBOL_DISPOSITIONS.values()
    ):
        raise AssertionError("Issue82 public symbol disposition changed")
    print("ISSUE82_HISTORICAL_ACCEPTANCE_CONTRACT: PASS")


def _check_current_owners() -> None:
    resurrected = [rel for rel in RETIRED_PERFORMANCE_PATHS if (ROOT / rel).exists()]
    if resurrected:
        raise AssertionError(f"retired Issue82 performance owner resurrected: {resurrected}")

    missing_files: list[str] = []
    missing_symbols: dict[str, list[str]] = {}
    for rel, required in CURRENT_OWNER_REQUIREMENTS.items():
        path = ROOT / rel
        if not path.is_file():
            missing_files.append(rel)
            continue
        missing = sorted(required - _top_level_symbols(path))
        if missing:
            missing_symbols[rel] = missing
    if missing_files or missing_symbols:
        raise AssertionError(
            f"current Issue82 owners incomplete: files={missing_files} symbols={missing_symbols}"
        )

    application_imports = _imports(ROOT / "physics_harness/application/performance.py")
    required_application_edges = {
        "physics_harness.adapters.moose.performance.collection",
        "physics_harness.adapters.moose.performance.measurement",
        "physics_harness.adapters.moose.performance.profile",
        "physics_harness.adapters.petsc.performance",
        "physics_harness.analysis.performance.profile",
        "physics_harness.evidence",
        "physics_harness.execution.runtime",
    }
    if not required_application_edges <= application_imports:
        raise AssertionError(
            "performance application boundary drift: "
            f"missing={sorted(required_application_edges - application_imports)}"
        )

    capability_paths = (
        "physics_harness/application/performance.py",
        "physics_harness/analysis/performance/profile.py",
        "physics_harness/adapters/petsc/performance.py",
        "physics_harness/adapters/moose/performance/profile.py",
        "physics_harness/adapters/moose/source_inspection.py",
    )
    cli_edges = {
        rel: sorted(module for module in _imports(ROOT / rel) if module.startswith("physics_harness.cli"))
        for rel in capability_paths
    }
    cli_edges = {rel: modules for rel, modules in cli_edges.items() if modules}
    if cli_edges:
        raise AssertionError(f"performance capability imports CLI presentation: {cli_edges}")

    print("ISSUE82_CURRENT_OWNER_BOUNDARIES: PASS")


def _check_promoted_behavior() -> None:
    summary = {
        "p2_returncode": 0,
        "p3_returncode": 0,
        "label": "issue82-synthetic",
        "wall_seconds": 10.0,
        "last_metrics_row": {
            "qpxh_num_dofs": "42",
            "qpxh_nonlinear_iterations": "2",
            "qpxh_linear_iterations": "3",
            "qpxh_residual_evaluations": "4",
        },
    }
    timings = {
        "snes_solve": 10.0,
        "jacobian_eval": 6.0,
        "residual_eval": 1.0,
        "pc_setup": 1.0,
        "linear_solve": 1.0,
        "matrix_assembly_end": 0.0,
    }
    analyzed = performance_profile.analyze_facts(
        summary,
        timings,
        {"self_seconds": 5.5},
    )
    if analyzed.get("classification") != "JACOBIAN_EVALUATION_DOMINANT":
        raise AssertionError(f"performance analysis classification drift: {analyzed}")
    if analyzed.get("dofs") != 42 or analyzed.get("perfgraph_jacobian_self") != {"self_seconds": 5.5}:
        raise AssertionError(f"performance analysis fact mapping drift: {analyzed}")

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        petsc_csv = root / "petsc.csv"
        with petsc_csv.open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=["Rank", "Event Name", "Count", "Time"])
            writer.writeheader()
            writer.writerow({"Rank": "0", "Event Name": "SNESSolve", "Count": "2", "Time": "4.5"})
            writer.writerow({"Rank": "1", "Event Name": "SNESSolve", "Count": "99", "Time": "99"})
            writer.writerow({"Rank": "0", "Event Name": "SNESJacobianEval", "Count": "3", "Time": "2.5"})
        events = petsc_performance.load_events(petsc_csv)
        if events != {
            "SNESSolve": {"count": 2.0, "time": 4.5},
            "SNESJacobianEval": {"count": 3.0, "time": 2.5},
        }:
            raise AssertionError(f"PETSc event decoding drift: {events}")
        if petsc_performance.event_time(events, "SNESJacobianEval") != 2.5:
            raise AssertionError("PETSc event_time drift")

        perf_log = root / "perf.log"
        perf_log.write_text(
            "| NonlinearSystemBase::computeJacobianInternal | 3 | 2.5 | 0.833333 | 25.0 |\n",
            encoding="utf-8",
        )
        jacobian = moose_profile.jacobian_self_time(perf_log)
        if jacobian != {
            "calls": 3.0,
            "self_seconds": 2.5,
            "avg_seconds": 0.833333,
            "percent_application": 25.0,
        }:
            raise AssertionError(f"MOOSE PerfGraph Jacobian decode drift: {jacobian}")

    if not callable(source_inspection.extract_functor_property_declaration):
        raise AssertionError("MOOSE functor declaration inspection owner missing")
    if not callable(source_inspection.parameter_functor_calls):
        raise AssertionError("MOOSE functor-call inspection owner missing")

    print("ISSUE82_PROMOTED_BEHAVIOR: PASS")


def _check_cli_convergence() -> None:
    app_path = ROOT / "physics_harness/cli/app.py"
    commands = set(_literal_assignment(app_path, "COMMANDS"))
    if not CURRENT_PERFORMANCE_COMMANDS <= commands:
        raise AssertionError(
            f"current generic performance commands missing: {sorted(CURRENT_PERFORMANCE_COMMANDS - commands)}"
        )
    unexpected = RETIRED_PERFORMANCE_COMMANDS & commands
    if unexpected:
        raise AssertionError(f"retired Issue82 campaign commands resurrected: {sorted(unexpected)}")

    cli_source = (ROOT / "physics_harness/cli/commands/performance.py").read_text(encoding="utf-8")
    for required in (
        'argparse.ArgumentParser(prog="physics measure")',
        'argparse.ArgumentParser(prog="physics analyze")',
        "performance.run_measurement(",
        "performance.analyze_profile(",
    ):
        if required not in cli_source:
            raise AssertionError(f"generic performance CLI wiring drift: {required}")
    for retired in RETIRED_PERFORMANCE_COMMANDS:
        if f'prog="physics {retired}"' in cli_source:
            raise AssertionError(f"retired Issue82 CLI parser resurrected: {retired}")

    print("ISSUE82_CLI_CONVERGENCE: PASS")


def main() -> int:
    _check_historical_contract()
    _check_current_owners()
    _check_promoted_behavior()
    _check_cli_convergence()
    print("ISSUE82_PF2_FEATURE_SLICE: NOT_IMPLEMENTED")
    print("ISSUE82_SCIENTIFIC_P3: NOT_RUN")
    print("ISSUE82_PERFORMANCE_OWNERSHIP_GUARD: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
