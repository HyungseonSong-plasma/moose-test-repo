"""Issue #31 EVR1 runtime orchestration.

Scientific input construction and r29 physics interpretation live in
``recipes.issue31_coupling``. This module owns EVR1 case staging, PF-1
BENCHMARK/PROFILE execution, evidence assembly, and the EVR1 preliminary
runtime classification contract.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Iterable

from recipes import issue31_coupling as recipe

from .artifacts import write_json_bundle
from .cases import CaseError, stage_case, validate_referenced_files
from .dmix_equivalence import legacy_source_transform
from .evidence import sha256_file, utc_timestamp
from .performance_core import PerformanceContractError, run_measurement
from .performance_investigation import build_investigation_summary
from .performance_smoke import (
    build_smoke_manifest,
    compare_smoke_results,
    default_results_root,
)
from .preflight import validate_parser_symbols_text
from .runtime import resolve_executable, validate_executable


EXPERIMENT_ID = "issue31-evr1-optimized-monolithic"
PURGE_DIRECTORY_NAMES = (".jitcache",)
PURGE_PATTERNS = (
    "input_out*",
    "r29_csv*",
    "perfgraph*",
    "petsc_log*",
    "metrics*",
)


class CouplingEVR1RuntimeError(RuntimeError):
    pass


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text())
    if not isinstance(payload, dict):
        raise CouplingEVR1RuntimeError(f"expected JSON object: {path}")
    return payload


def _create_root(results_root: Path, *, timestamp: str | None = None) -> Path:
    results_root.mkdir(parents=True, exist_ok=True)
    stamp = timestamp or utc_timestamp()
    stem = f"coupling_evr1_Issue31_{stamp}"
    root = results_root / stem
    index = 1
    while root.exists():
        root = results_root / f"{stem}_{index:02d}"
        index += 1
    root.mkdir()
    return root


def _manifest(*, mode: str, case_dir: Path, case_id: str) -> dict[str, Any]:
    return build_smoke_manifest(
        mode=mode,
        case_dir=case_dir,
        input_name="input.i",
        experiment_id=EXPERIMENT_ID,
        case_id=case_id,
        num_steps=1,
        species=list(recipe.SPECIES),
    )


def _run_pair(
    *,
    case_dir: Path,
    case_id: str,
    exe: Path,
    results_root: Path,
) -> dict[str, Any]:
    pair_root = results_root / case_id
    pair_root.mkdir(parents=True)
    results: dict[str, Any] = {}
    returncodes: dict[str, int | None] = {"BENCHMARK": None, "PROFILE": None}

    for mode in ("BENCHMARK", "PROFILE"):
        if mode == "PROFILE" and returncodes["BENCHMARK"] not in (0,):
            break
        manifest = _manifest(mode=mode, case_dir=case_dir, case_id=case_id)
        manifest_path = pair_root / f"{mode.lower()}_manifest.json"
        write_json_bundle(
            pair_root,
            {f"{mode.lower()}_manifest": (manifest_path.name, manifest)},
        )
        out = pair_root / mode.lower()
        print(f"ISSUE31_EVR1_CASE_START: {case_id} {mode}")
        rc = run_measurement(manifest_path, executable=exe, out_dir=out)
        print(f"ISSUE31_EVR1_CASE_END: {case_id} {mode} rc={rc}")
        returncodes[mode] = rc
        result_path = out / "result.json"
        if result_path.is_file():
            results[mode.lower()] = _load_json(result_path)

    benchmark = results.get("benchmark")
    profile = results.get("profile")
    smoke = compare_smoke_results(benchmark, profile)
    investigation = None
    if (
        benchmark
        and profile
        and benchmark.get("validation", {}).get("status") == "P2_PASS_P3_PASS"
        and profile.get("validation", {}).get("status") == "P2_PASS_P3_PASS"
    ):
        investigation = build_investigation_summary(benchmark, profile, smoke)

    return {
        "root": str(pair_root),
        "returncodes": returncodes,
        "benchmark": benchmark,
        "profile": profile,
        "smoke": smoke,
        "investigation": investigation,
    }


def _status(result: dict[str, Any] | None) -> str | None:
    if not result:
        return None
    return result.get("validation", {}).get("status")


def _wall(pair: dict[str, Any], mode: str = "benchmark") -> float | None:
    result = pair.get(mode)
    value = result.get("performance", {}).get("wall_seconds") if result else None
    return float(value) if isinstance(value, (int, float)) else None


def preliminary_classification(
    transport: dict[str, Any],
    monolithic: dict[str, Any],
    transport_physics: dict[str, Any] | None,
    monolithic_physics: dict[str, Any] | None,
) -> dict[str, Any]:
    """Classify the accepted EVR1 runtime outcomes without changing the experiment."""
    if _status(transport.get("benchmark")) != "P2_PASS_P3_PASS":
        return {
            "class": "HARNESS_OR_CONSTRUCTION_FAIL",
            "reason": "transport-only known-good control did not complete",
        }
    if transport_physics is None or transport_physics.get("status") != "PASS":
        return {
            "class": "PHYSICS_CHECK_FAIL",
            "reason": "transport-only runtime completed but physics checker failed",
        }

    mono_status = _status(monolithic.get("benchmark"))
    if mono_status == "HARNESS_OR_CONSTRUCTION_FAIL":
        return {
            "class": "HARNESS_OR_CONSTRUCTION_FAIL",
            "reason": "monolithic Q0 failed P2/construction",
        }
    if mono_status == "RUNTIME_FAIL_OR_NONCONVERGENCE":
        log = Path(monolithic["root"]) / "benchmark" / "p3_run.log"
        text = log.read_text(errors="replace") if log.is_file() else ""
        if re.search(r"DIVERGED|did not converge|Nonlinear solve.*fail", text, re.IGNORECASE):
            return {
                "class": "MONOLITHIC_NONLINEAR_CONVERGENCE_FAIL",
                "reason": "monolithic Q0 reached runtime but nonlinear solve did not converge",
            }
        return {
            "class": "MONOLITHIC_RUNTIME_FAIL",
            "reason": "monolithic Q0 failed at runtime without a proven convergence signature",
        }
    if mono_status != "P2_PASS_P3_PASS":
        return {
            "class": "HARNESS_OR_CONSTRUCTION_FAIL",
            "reason": f"monolithic benchmark status is {mono_status!r}",
        }
    if monolithic_physics is None or monolithic_physics.get("status") != "PASS":
        return {
            "class": "PHYSICS_CHECK_FAIL",
            "reason": "monolithic Q0 runtime completed but physics checker failed",
        }

    investigation = monolithic.get("investigation") or {}
    classification = investigation.get("classification", {})
    bottleneck = classification.get("bottleneck_class")
    if bottleneck in {"PC_FACTORIZATION", "LINEAR_SOLVE"}:
        label = "MONOLITHIC_LINEAR_ALGEBRA_BOUND_CANDIDATE"
    elif bottleneck in {"APPLICATION_EVALUATION", "JACOBIAN_AD"}:
        label = "MONOLITHIC_APPLICATION_OR_JACOBIAN_BOUND_CANDIDATE"
    else:
        label = "MONOLITHIC_VIABILITY_REVIEW"

    t_wall = _wall(transport)
    m_wall = _wall(monolithic)
    ratio = m_wall / t_wall if t_wall and m_wall is not None else None
    return {
        "class": label,
        "reason": "monolithic one-step completed; final viability requires evidence review",
        "transport_benchmark_wall_seconds": t_wall,
        "monolithic_benchmark_wall_seconds": m_wall,
        "monolithic_to_transport_wall_ratio": ratio,
        "bottleneck": classification,
    }


def self_test() -> int:
    try:
        base = """
[Variables]
  [n_e_solved]
  []
  [potential_plasma]
  []
[]
[FunctorMaterials]
  [r30_charge_density]
  []
[]
[FVKernels]
  [r30_e_time]
  []
  [r30_e_diffusion]
  []
  [r30_phi_diffusion]
  []
  [r30_phi_charge_source]
  []
[]
[FVBCs]
  [r30_phi_plasma_metal]
  []
  [r30_phi_plasma_electrode]
  []
  [r30_phi_plasma_right]
  []
  [r30_phi_inlet]
  []
  [r30_phi_outlet]
  []
[]
[Postprocessors]
  [r29_phi_min]
  []
  [r29_phi_max]
  []
  [r29_phi_integral]
  []
[]
"""
        transformed, meta = recipe.transport_only_input(base)
        if "potential_plasma" in transformed:
            raise AssertionError("recipe transform left potential_plasma")
        if len(meta["removed_paths"]) != len(recipe.TRANSPORT_REMOVE_PATHS):
            raise AssertionError("recipe transform removal count drift")

        transport = {
            "benchmark": {
                "validation": {"status": "P2_PASS_P3_PASS"},
                "performance": {"wall_seconds": 10.0},
            }
        }
        monolithic = {
            "benchmark": {
                "validation": {"status": "P2_PASS_P3_PASS"},
                "performance": {"wall_seconds": 15.0},
            },
            "investigation": {
                "classification": {"bottleneck_class": "PC_FACTORIZATION"}
            },
        }
        physics = {"status": "PASS"}
        decision = preliminary_classification(transport, monolithic, physics, physics)
        if decision["class"] != "MONOLITHIC_LINEAR_ALGEBRA_BOUND_CANDIDATE":
            raise AssertionError("EVR1 classifier drift")
        if decision["monolithic_to_transport_wall_ratio"] != 1.5:
            raise AssertionError("EVR1 wall-ratio drift")

        import tempfile

        with tempfile.TemporaryDirectory() as tmp_name:
            root = Path(tmp_name)
            first = _create_root(root, timestamp="20000101T000000Z")
            second = _create_root(root, timestamp="20000101T000000Z")
            if first.name != "coupling_evr1_Issue31_20000101T000000Z":
                raise AssertionError("EVR1 root naming drift")
            if second.name != "coupling_evr1_Issue31_20000101T000000Z_01":
                raise AssertionError("EVR1 root collision policy drift")
    except Exception as exc:
        print(f"ISSUE31_EVR1_RUNTIME_SELFTEST: FAIL ({exc})")
        return 1
    print("ISSUE31_EVR1_RUNTIME_SELFTEST: PASS")
    return 0


def run(args: argparse.Namespace) -> int:
    if self_test():
        return 2

    exe = resolve_executable(args.qpx)
    validate_executable(exe)
    qpx_root = exe.parent.resolve()
    repo_root = Path(__file__).resolve().parents[1]
    base_input = (
        args.base_input.resolve()
        if args.base_input
        else repo_root / recipe.BASE_INPUT_RELATIVE
    )
    asset_dir = (
        args.asset_case.resolve()
        if args.asset_case
        else qpx_root / recipe.DEFAULT_ASSET_CASE_RELATIVE
    )
    source = qpx_root / recipe.SOURCE_RELATIVE

    if not base_input.is_file():
        raise CouplingEVR1RuntimeError(f"missing archived #29 Q0 reference: {base_input}")
    if not asset_dir.is_dir():
        raise CouplingEVR1RuntimeError(
            f"missing asset case: {asset_dir}; pass --asset-case with qvt.msh and transport_data.txt"
        )
    if not source.is_file():
        raise CouplingEVR1RuntimeError(f"missing QPX transport source: {source}")

    source_text = source.read_text()
    _, source_parse = legacy_source_transform(source_text)
    if source_parse.get("parser") != "CppSource+CppCallArguments":
        raise CouplingEVR1RuntimeError(
            "optimized D_mix source identity could not be structurally verified"
        )

    base_text = base_input.read_text()
    parser_errors = validate_parser_symbols_text(base_text, str(base_input))
    if parser_errors:
        raise CouplingEVR1RuntimeError(
            "base input parser-symbol preflight failed: " + " | ".join(parser_errors)
        )

    try:
        transport_text, transform_meta = recipe.transport_only_input(base_text)
    except recipe.Issue31CouplingError as exc:
        raise CouplingEVR1RuntimeError(str(exc)) from exc
    parser_errors = validate_parser_symbols_text(transport_text, "<transport-only>")
    if parser_errors:
        raise CouplingEVR1RuntimeError(
            "transport-only parser-symbol preflight failed: " + " | ".join(parser_errors)
        )

    results_root = (
        args.results_root.resolve()
        if args.results_root
        else default_results_root(exe)
    )
    root = _create_root(results_root)
    print(f"ISSUE31_EVR1_ROOT: {root}")

    cases_root = root / "cases"
    monolithic_case = cases_root / "monolithic_q0"
    transport_case = cases_root / "transport_only"
    stage_case(
        asset_dir,
        monolithic_case,
        input_text=base_text,
        purge_directory_names=PURGE_DIRECTORY_NAMES,
        purge_patterns=PURGE_PATTERNS,
    )
    stage_case(
        asset_dir,
        transport_case,
        input_text=transport_text,
        purge_directory_names=PURGE_DIRECTORY_NAMES,
        purge_patterns=PURGE_PATTERNS,
    )

    monolithic_refs = validate_referenced_files(base_text, monolithic_case, skip_dynamic=True)
    transport_refs = validate_referenced_files(transport_text, transport_case, skip_dynamic=True)

    identity = {
        "qpx_realpath": str(exe),
        "qpx_sha256": sha256_file(exe),
        "transport_source": str(source),
        "transport_source_sha256": sha256_file(source),
        "optimized_dmix_source_parse": source_parse,
        "base_input": str(base_input),
        "base_input_sha256": sha256_file(base_input),
        "asset_case": str(asset_dir),
        "referenced_files_monolithic": monolithic_refs,
        "referenced_files_transport": transport_refs,
        "transport_transform": transform_meta,
    }
    write_json_bundle(root, {"identity": ("identity.json", identity)})
    print("ISSUE31_EVR1_P0: PASS")
    print("ISSUE31_EVR1_P1: PASS")

    transport = _run_pair(
        case_dir=transport_case,
        case_id="Issue31_transport_only",
        exe=exe,
        results_root=root / "measurements",
    )
    transport_physics = None
    if _status(transport.get("benchmark")) == "P2_PASS_P3_PASS":
        try:
            transport_physics = recipe.physics_check(transport_case, monolithic=False)
        except recipe.Issue31CouplingError as exc:
            transport_physics = {"status": "FAIL", "error": str(exc)}

    monolithic = _run_pair(
        case_dir=monolithic_case,
        case_id="Issue31_monolithic_q0",
        exe=exe,
        results_root=root / "measurements",
    )
    monolithic_physics = None
    if _status(monolithic.get("benchmark")) == "P2_PASS_P3_PASS":
        try:
            monolithic_physics = recipe.physics_check(monolithic_case, monolithic=True)
        except recipe.Issue31CouplingError as exc:
            monolithic_physics = {"status": "FAIL", "error": str(exc)}

    decision = preliminary_classification(
        transport, monolithic, transport_physics, monolithic_physics
    )
    summary = {
        "schema_version": 1,
        "issue": 31,
        "work_id": "real-qvt-transport-poisson-architecture-selection",
        "evr": 1,
        "identity": identity,
        "transport_only": transport,
        "transport_physics": transport_physics,
        "monolithic_q0": monolithic,
        "monolithic_physics": monolithic_physics,
        "preliminary_classification": decision,
    }
    write_json_bundle(root, {"summary": ("summary.json", summary)})

    print(
        "ISSUE31_EVR1_TRANSPORT_PHYSICS:",
        (transport_physics or {}).get("status", "NOT_RUN"),
    )
    print(
        "ISSUE31_EVR1_MONOLITHIC_PHYSICS:",
        (monolithic_physics or {}).get("status", "NOT_RUN"),
    )
    print("ISSUE31_EVR1_PRECLASS:", decision["class"])
    if "transport_benchmark_wall_seconds" in decision:
        print(
            "ISSUE31_EVR1_TRANSPORT_WALL:",
            f"{decision['transport_benchmark_wall_seconds']:.6g}",
        )
        print(
            "ISSUE31_EVR1_MONOLITHIC_WALL:",
            f"{decision['monolithic_benchmark_wall_seconds']:.6g}",
        )
        ratio = decision.get("monolithic_to_transport_wall_ratio")
        if ratio is not None:
            print("ISSUE31_EVR1_WALL_RATIO:", f"{ratio:.6g}")
    bottleneck = decision.get("bottleneck") or {}
    if bottleneck:
        print("ISSUE31_EVR1_BOTTLENECK:", bottleneck.get("bottleneck_class"))
        print("ISSUE31_EVR1_BOTTLENECK_OUTCOME:", bottleneck.get("outcome"))
        print("ISSUE31_EVR1_BOTTLENECK_CONFIDENCE:", bottleneck.get("confidence"))
    print("ISSUE31_EVR1_SUMMARY:", root / "summary.json")

    return 0 if decision["class"] not in {
        "HARNESS_OR_CONSTRUCTION_FAIL",
        "PHYSICS_CHECK_FAIL",
    } else 2


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="qpx coupling-evr1")
    parser.add_argument("--qpx")
    parser.add_argument("--asset-case", type=Path)
    parser.add_argument("--base-input", type=Path)
    parser.add_argument("--results-root", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)
    if args.self_test:
        return self_test()
    try:
        return run(args)
    except (
        CouplingEVR1RuntimeError,
        CaseError,
        PerformanceContractError,
        SystemExit,
    ) as exc:
        print(f"ISSUE31_EVR1_FATAL: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
