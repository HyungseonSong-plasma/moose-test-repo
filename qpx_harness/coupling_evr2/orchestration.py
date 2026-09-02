"""Issue #31 EVR2 runtime orchestration.

Scientific input construction and discriminator interpretation live in
``recipes.issue31_coupling``. This module owns EVR2 case staging, BENCHMARK
execution, accepted-electron checker execution, evidence assembly, and branch
orchestration.
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any, Iterable

from recipes import issue31_coupling as recipe

from ..diagnostics import measurement_failure_signature
from ..evidence.artifacts import write_json_bundle
from ..execution.cases import CaseError, stage_case, validate_referenced_files
from ..dmix.source_transform import legacy_source_transform
from ..evidence import create_collision_safe_directory, sha256_file, utc_timestamp
from ..performance.runner import PerformanceContractError, result_status
from ..performance.smoke import (
    build_smoke_manifest,
    default_results_root,
    run_managed_measurement,
)
from ..moose.preflight import validate_parser_symbols_text
from ..execution.runtime import (
    resolve_executable,
    run_command,
    validate_executable,
)
from ..analysis.temporal import normalize_from_manifest


EXPERIMENT_ID = "issue31-evr2-timestep-scaling"
PURGE_DIRECTORY_NAMES = (".jitcache",)
PURGE_PATTERNS = (
    "input_out*",
    "r29_csv*",
    "qpxperf*",
    "perfgraph*",
    "petsc_log*",
    "metrics*",
)


class CouplingEVR2RuntimeError(RuntimeError):
    pass


def _stage_kg_e(repo_root: Path, cases_root: Path) -> Path:
    source_parent = repo_root / recipe.KG_E_PARENT_RELATIVE
    if not source_parent.is_dir():
        raise CouplingEVR2RuntimeError(
            f"missing accepted electron control tree: {source_parent}"
        )
    target_parent = cases_root / "kg_e_parent"
    stage_case(
        source_parent,
        target_parent,
        purge_directory_names=PURGE_DIRECTORY_NAMES,
        purge_patterns=PURGE_PATTERNS,
    )
    case = target_parent / "qvt_prepoisson"
    if not case.is_dir():
        raise CouplingEVR2RuntimeError(
            f"copied electron control missing qvt_prepoisson: {case}"
        )
    return case


def _manifest(
    *,
    case_dir: Path,
    case_id: str,
    experiment_id: str = EXPERIMENT_ID,
    species: list[str] | None = None,
) -> dict[str, Any]:
    return build_smoke_manifest(
        mode="BENCHMARK",
        case_dir=case_dir,
        input_name="input.i",
        experiment_id=experiment_id,
        case_id=case_id,
        num_steps=1,
        species=species,
    )


def _run_benchmark(
    *,
    case_dir: Path,
    case_id: str,
    exe: Path,
    measurements_root: Path,
    experiment_id: str = EXPERIMENT_ID,
    species: list[str] | None = None,
) -> dict[str, Any]:
    case_root = measurements_root / case_id
    manifest = _manifest(
        case_dir=case_dir,
        case_id=case_id,
        experiment_id=experiment_id,
        species=species,
    )
    print(f"ISSUE31_EVR2_CASE_START: {case_id}")
    managed = run_managed_measurement(
        manifest,
        executable=exe,
        root=case_root,
        manifest_label="benchmark",
        out_label="benchmark",
    )
    rc = managed["returncode"]
    print(f"ISSUE31_EVR2_CASE_END: {case_id} rc={rc}")
    result = managed["result"]
    return {
        "case_id": case_id,
        "returncode": rc,
        "result": result,
        "failure": measurement_failure_signature(result),
        "measurement_root": str(case_root),
    }


def _runtime_nonconvergence(case: dict[str, Any] | None) -> bool:
    return (
        result_status((case or {}).get("result")) == "RUNTIME_FAIL_OR_NONCONVERGENCE"
        and (case or {}).get("failure", {}).get("signature")
        in {
            "DIVERGED_MAX_IT",
            "DIVERGED_LINE_SEARCH",
            "DIVERGED_FNORM_NAN",
            "NONLINEAR_DID_NOT_CONVERGE",
        }
    )


def _transport_physics(case_dir: Path) -> dict[str, Any]:
    return recipe.physics_check(case_dir, monolithic=False)


def _attach_transport_physics(case: dict[str, Any], case_dir: Path) -> None:
    if result_status(case.get("result")) != "P2_PASS_P3_PASS":
        case["physics"] = None
        return
    try:
        case["physics"] = _transport_physics(case_dir)
    except recipe.Issue31CouplingError as exc:
        case["physics"] = {"status": "FAIL", "error": str(exc)}


def _case_pass(case: dict[str, Any] | None) -> bool:
    return (
        result_status((case or {}).get("result")) == "P2_PASS_P3_PASS"
        and isinstance((case or {}).get("physics"), dict)
        and (case or {})["physics"].get("status") == "PASS"
    )


def _run_kg_e(
    *,
    case_dir: Path,
    exe: Path,
    measurements_root: Path,
) -> dict[str, Any]:
    case = _run_benchmark(
        case_dir=case_dir,
        case_id="Issue31_KGE_dt1e8",
        exe=exe,
        measurements_root=measurements_root,
    )
    case["physics"] = None
    if result_status(case.get("result")) != "P2_PASS_P3_PASS":
        return case

    cfg = json.loads((case_dir / "test.json").read_text())
    for spec in cfg.get("temporal_csv", []):
        normalize_from_manifest(case_dir, spec)

    checker = (case_dir / cfg["checker"]).resolve()
    checker_args = [str(value) for value in cfg.get("checker_args", [])]
    log = Path(case["measurement_root"]) / "canonical_checker.log"
    proc = run_command(
        [sys.executable, str(checker), *checker_args],
        cwd=case_dir,
        log_path=log,
    )
    case["canonical_checker"] = {
        "returncode": proc.returncode,
        "log": str(log),
        "status": "PASS" if proc.returncode == 0 else "FAIL",
    }
    case["physics"] = {"status": "PASS" if proc.returncode == 0 else "FAIL"}
    return case


def _kg_e_pass(case: dict[str, Any]) -> bool:
    return (
        result_status(case.get("result")) == "P2_PASS_P3_PASS"
        and case.get("canonical_checker", {}).get("status") == "PASS"
    )


def _brief(case: dict[str, Any] | None, *, kg: bool = False) -> str:
    if case is None:
        return "SKIPPED"
    if kg:
        if _kg_e_pass(case):
            return "PASS"
    elif _case_pass(case):
        return "PASS"
    status = result_status(case.get("result")) or "NO_RESULT"
    sig = case.get("failure", {}).get("signature")
    return f"{status}:{sig}" if sig else status


def self_test() -> int:
    try:
        synthetic = """
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
[Executioner]
  type = Transient
  dt = 1.0e-4
  end_time = 5.0e-4
  compute_scaling_once = false
[]
"""
        transformed, meta = recipe.configured_transport_input(
            synthetic,
            dt=recipe.DT_1E8,
            compute_scaling_once=True,
        )
        if "potential_plasma" in transformed:
            raise AssertionError("Poisson reference survived EVR2 transform")
        if "compute_scaling_once = true" not in transformed:
            raise AssertionError("scaling transform did not apply")
        if meta["executioner_parameters"]["dt"]["old"] != "1.0e-4":
            raise AssertionError("dt mutation metadata incorrect")

        kg = {
            "result": {"validation": {"status": "P2_PASS_P3_PASS"}},
            "failure": {"signature": None},
            "canonical_checker": {"status": "PASS"},
        }
        passed = {
            "result": {"validation": {"status": "P2_PASS_P3_PASS"}},
            "failure": {"signature": None},
            "physics": {"status": "PASS"},
        }
        decision = recipe.classify_evr2(kg, passed, passed, None)
        if decision["class"] != "TIMESTEP_STIFFNESS_CONFIRMED_RECOVERY_BY_1E6":
            raise AssertionError("EVR2 classifier drift")

        with tempfile.TemporaryDirectory() as tmp_name:
            root = Path(tmp_name)
            stem = "coupling_evr2_Issue31_20000101T000000Z"
            first = create_collision_safe_directory(root, stem)
            second = create_collision_safe_directory(root, stem)
            if first.name != "coupling_evr2_Issue31_20000101T000000Z":
                raise AssertionError("EVR2 root naming drift")
            if second.name != "coupling_evr2_Issue31_20000101T000000Z_01":
                raise AssertionError("EVR2 root collision policy drift")

        if measurement_failure_signature(None) != {"signature": "NO_RESULT"}:
            raise AssertionError("EVR2 missing-result signature drift")
    except Exception as exc:
        print(f"ISSUE31_EVR2_RUNTIME_SELFTEST: FAIL ({exc})")
        return 1

    print("ISSUE31_EVR2_RUNTIME_SELFTEST: PASS")
    return 0


def run(args: argparse.Namespace) -> int:
    exe = resolve_executable(args.qpx)
    validate_executable(exe)
    qpx_root = exe.parent.resolve()
    repo_root = Path(__file__).resolve().parents[2]

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
        raise CouplingEVR2RuntimeError(f"missing #29 Q0 reference: {base_input}")
    if not asset_dir.is_dir():
        raise CouplingEVR2RuntimeError(
            f"missing heavy asset case: {asset_dir}; pass --asset-case if needed"
        )
    if not source.is_file():
        raise CouplingEVR2RuntimeError(f"missing QPX transport source: {source}")

    source_text = source.read_text()
    _, source_parse = legacy_source_transform(source_text)
    if source_parse.get("parser") != "CppSource+CppCallArguments":
        raise CouplingEVR2RuntimeError(
            "optimized D_mix source identity could not be verified"
        )

    base_text = base_input.read_text()
    transport_variants: dict[str, tuple[str, dict[str, Any]]] = {
        "dt1e6": recipe.configured_transport_input(
            base_text,
            dt=recipe.DT_1E6,
            compute_scaling_once=False,
        ),
        "dt1e8": recipe.configured_transport_input(
            base_text,
            dt=recipe.DT_1E8,
            compute_scaling_once=False,
        ),
        "scaling1e8": recipe.configured_transport_input(
            base_text,
            dt=recipe.DT_1E8,
            compute_scaling_once=True,
        ),
    }

    parser_errors: dict[str, list[str]] = {}
    for label, (text, _) in transport_variants.items():
        errors = validate_parser_symbols_text(text, f"<{label}>")
        if errors:
            parser_errors[label] = errors
    if parser_errors:
        raise CouplingEVR2RuntimeError(
            "generated transport parser-symbol preflight failed: "
            + " | ".join(
                f"{label}: {'; '.join(errors)}"
                for label, errors in parser_errors.items()
            )
        )

    results_root = (
        args.results_root.resolve()
        if args.results_root
        else default_results_root(exe)
    )
    root = create_collision_safe_directory(
        results_root,
        f"coupling_evr2_Issue31_{utc_timestamp()}",
    )
    cases_root = root / "cases"
    cases_root.mkdir()

    kg_e_case = _stage_kg_e(repo_root, cases_root)

    case_dirs: dict[str, Path] = {}
    refs: dict[str, Any] = {}
    for label, (text, _) in transport_variants.items():
        case_dir = cases_root / label
        stage_case(
            asset_dir,
            case_dir,
            input_text=text,
            purge_directory_names=PURGE_DIRECTORY_NAMES,
            purge_patterns=PURGE_PATTERNS,
        )
        refs[label] = validate_referenced_files(
            text,
            case_dir,
            skip_dynamic=True,
        )
        case_dirs[label] = case_dir

    identity = {
        "qpx_realpath": str(exe),
        "qpx_sha256": sha256_file(exe),
        "transport_source": str(source),
        "transport_source_sha256": sha256_file(source),
        "optimized_dmix_source_parse": source_parse,
        "base_input": str(base_input),
        "base_input_sha256": sha256_file(base_input),
        "asset_case": str(asset_dir),
        "kg_e_control_source": str(
            repo_root / recipe.KG_E_PARENT_RELATIVE / "qvt_prepoisson"
        ),
        "evr1_baseline": recipe.EVR1_BASELINE,
        "transport_variants": {
            label: meta for label, (_, meta) in transport_variants.items()
        },
        "referenced_files": refs,
    }
    write_json_bundle(root, {"identity": ("identity.json", identity)})

    print(f"ISSUE31_EVR2_ROOT: {root}")
    print("ISSUE31_EVR2_P0: PASS")
    print("ISSUE31_EVR2_P1: PASS")

    measurements = root / "measurements"
    kg_e = _run_kg_e(
        case_dir=kg_e_case,
        exe=exe,
        measurements_root=measurements,
    )

    dt1e6 = None
    dt1e8 = None
    scaling1e8 = None

    if _kg_e_pass(kg_e):
        dt1e6 = _run_benchmark(
            case_dir=case_dirs["dt1e6"],
            case_id="Issue31_T3_dt1e6",
            exe=exe,
            measurements_root=measurements,
            species=list(recipe.SPECIES),
        )
        _attach_transport_physics(dt1e6, case_dirs["dt1e6"])

        dt1e8 = _run_benchmark(
            case_dir=case_dirs["dt1e8"],
            case_id="Issue31_T3_dt1e8",
            exe=exe,
            measurements_root=measurements,
            species=list(recipe.SPECIES),
        )
        _attach_transport_physics(dt1e8, case_dirs["dt1e8"])

        if _runtime_nonconvergence(dt1e6) and _runtime_nonconvergence(dt1e8):
            scaling1e8 = _run_benchmark(
                case_dir=case_dirs["scaling1e8"],
                case_id="Issue31_T3_dt1e8_scaling_once",
                exe=exe,
                measurements_root=measurements,
                species=list(recipe.SPECIES),
            )
            _attach_transport_physics(scaling1e8, case_dirs["scaling1e8"])

    decision = recipe.classify_evr2(kg_e, dt1e6, dt1e8, scaling1e8)
    summary = {
        "schema_version": 1,
        "issue": 31,
        "work_id": "real-qvt-transport-poisson-architecture-selection",
        "evr": 2,
        "closure_question": (
            "Did the EVR1 transport-only nonlinear failure primarily arise from "
            "electron-containing timestep stiffness or nonlinear scaling?"
        ),
        "identity": identity,
        "kg_e": kg_e,
        "dt1e6": dt1e6,
        "dt1e8": dt1e8,
        "scaling1e8": scaling1e8,
        "classification": decision,
    }
    write_json_bundle(root, {"summary": ("summary.json", summary)})

    print("ISSUE31_EVR2_KGE:", _brief(kg_e, kg=True))
    print("ISSUE31_EVR2_DT1E6:", _brief(dt1e6))
    print("ISSUE31_EVR2_DT1E8:", _brief(dt1e8))
    print("ISSUE31_EVR2_SCALING1E8:", _brief(scaling1e8))
    print("ISSUE31_EVR2_CLASS:", decision["class"])
    print("ISSUE31_EVR2_REASON:", decision["reason"])
    print("ISSUE31_EVR2_SUMMARY:", root / "summary.json")

    return 0 if decision["class"] in recipe.EVR2_TERMINAL_CLASSES else 2
