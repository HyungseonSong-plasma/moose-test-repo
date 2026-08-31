"""Issue #31 EVR2 timestep/scaling discriminator for transport-only convergence.

EVR1 established that the optimized transport-only control (heavy + solved
electron, Poisson OFF, electrostatic drift OFF) did not converge at dt=1e-4
within 80 Newton iterations.  This runner does not retest Poisson.  It tests
whether the failure is explained by electron-containing transient stiffness or
by nonlinear scaling.

Branch-aware order:
  KG-E  accepted real-qvt electron control at dt=1e-8
  T6    transport-only dt=1e-6, current scaling policy
  T8    transport-only dt=1e-8, current scaling policy
  S8    transport-only dt=1e-8, compute_scaling_once=true
        only when T6 and T8 both fail by runtime/nonconvergence
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from . import coupling_evr1 as evr1
from .coupling_evr1_safe import physics_csv as safe_physics_csv
from .dmix_equivalence import legacy_source_transform
from .moose_input import MooseInput, MooseInputError, self_test as moose_input_self_test
from .performance_core import PerformanceContractError, run_measurement
from .performance_smoke import build_smoke_manifest, default_results_root
from .preflight import validate_parser_symbols_text
from .runtime import resolve_executable, validate_executable
from .temporal import normalize_from_manifest


KG_E_PARENT_RELATIVE = Path("tests/Issue2_electron_bulk_drift")
EVR1_BASELINE = {
    "dt": 1.0e-4,
    "status": "RUNTIME_FAIL_OR_NONCONVERGENCE",
    "signature": "DIVERGED_MAX_IT",
    "nonlinear_iterations": 80,
    "physics": "NOT_RUN",
    "source": "user-returned Issue31 EVR1 transport-only evidence",
}
DT_1E6 = 1.0e-6
DT_1E8 = 1.0e-8


class CouplingEVR2Error(RuntimeError):
    pass


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    payload = json.loads(path.read_text())
    return payload if isinstance(payload, dict) else None


def _create_root(results_root: Path) -> Path:
    results_root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    stem = f"coupling_evr2_Issue31_{stamp}"
    root = results_root / stem
    index = 1
    while root.exists():
        root = results_root / f"{stem}_{index:02d}"
        index += 1
    root.mkdir()
    return root


def _purge_runtime_artifacts(root: Path) -> None:
    for path in root.rglob(".jitcache"):
        if path.is_dir():
            shutil.rmtree(path)
    for pattern in (
        "input_out*",
        "r29_csv*",
        "qpxperf*",
        "perfgraph*",
        "petsc_log*",
        "metrics*",
    ):
        for path in root.rglob(pattern):
            if path.is_file():
                path.unlink()
            elif path.is_dir():
                shutil.rmtree(path)


def configured_transport_input(
    base_text: str,
    *,
    dt: float,
    compute_scaling_once: bool,
) -> tuple[str, dict[str, Any]]:
    """Build the exact EVR1 transport-only control with only time/scaling changed."""
    try:
        transport_text, transport_meta = evr1.transport_only_input(base_text)
        transformed, param_meta = MooseInput(transport_text).replace_parameters(
            "Executioner",
            {
                "dt": f"{dt:.17g}",
                "end_time": f"{dt:.17g}",
                "compute_scaling_once": "true" if compute_scaling_once else "false",
            },
        )
    except (evr1.CouplingEVR1Error, MooseInputError) as exc:
        raise CouplingEVR2Error(f"transport configuration failed: {exc}") from exc

    if "potential_plasma" in transformed:
        raise CouplingEVR2Error("configured transport case unexpectedly references potential_plasma")
    if "r30_e_diffusion" not in transformed or "n_e_solved" not in transformed:
        raise CouplingEVR2Error("configured transport case lost solved electron diffusion state")
    return transformed, {
        "transport_transform": transport_meta,
        "executioner_parameters": param_meta,
        "dt": dt,
        "compute_scaling_once": compute_scaling_once,
    }


def _copy_transport_case(asset_dir: Path, target: Path, input_text: str) -> None:
    shutil.copytree(asset_dir, target)
    _purge_runtime_artifacts(target)
    (target / "input.i").write_text(input_text)


def _copy_kg_e(repo_root: Path, cases_root: Path) -> Path:
    source_parent = repo_root / KG_E_PARENT_RELATIVE
    if not source_parent.is_dir():
        raise CouplingEVR2Error(f"missing accepted electron control tree: {source_parent}")
    target_parent = cases_root / "kg_e_parent"
    shutil.copytree(source_parent, target_parent)
    _purge_runtime_artifacts(target_parent)
    case = target_parent / "qvt_prepoisson"
    if not case.is_dir():
        raise CouplingEVR2Error(f"copied electron control missing qvt_prepoisson: {case}")
    return case


def _manifest(
    *,
    case_dir: Path,
    case_id: str,
    experiment_id: str,
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


def _failure_signature(result: dict[str, Any] | None) -> dict[str, Any]:
    if not result:
        return {"signature": "NO_RESULT"}
    evidence = result.get("evidence", {})
    log_raw = evidence.get("p3_log") or evidence.get("p2_log")
    log = Path(log_raw) if isinstance(log_raw, str) else None
    text = log.read_text(errors="replace") if log and log.is_file() else ""

    patterns = (
        ("DIVERGED_MAX_IT", r"DIVERGED_MAX_IT(?:\s+iterations\s+(\d+))?"),
        ("DIVERGED_LINE_SEARCH", r"DIVERGED_LINE_SEARCH"),
        ("DIVERGED_FNORM_NAN", r"DIVERGED_FNORM_NAN|NaN"),
        ("NONLINEAR_DID_NOT_CONVERGE", r"Nonlinear solve did not converge|Solve Did NOT Converge"),
    )
    for name, pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            iterations = None
            if match.lastindex and match.group(1):
                try:
                    iterations = int(match.group(1))
                except ValueError:
                    pass
            return {"signature": name, "iterations": iterations, "log": str(log)}
    return {"signature": None, "iterations": None, "log": str(log) if log else None}


def _run_benchmark(
    *,
    case_dir: Path,
    case_id: str,
    exe: Path,
    measurements_root: Path,
    experiment_id: str,
    species: list[str] | None = None,
) -> dict[str, Any]:
    case_root = measurements_root / case_id
    case_root.mkdir(parents=True)
    manifest = _manifest(
        case_dir=case_dir,
        case_id=case_id,
        experiment_id=experiment_id,
        species=species,
    )
    manifest_path = case_root / "benchmark_manifest.json"
    _write_json(manifest_path, manifest)
    out = case_root / "benchmark"

    print(f"ISSUE31_EVR2_CASE_START: {case_id}")
    rc = run_measurement(manifest_path, executable=exe, out_dir=out)
    print(f"ISSUE31_EVR2_CASE_END: {case_id} rc={rc}")

    result = _load_json(out / "result.json")
    return {
        "case_id": case_id,
        "returncode": rc,
        "result": result,
        "failure": _failure_signature(result),
        "measurement_root": str(case_root),
    }


def _result_status(case: dict[str, Any] | None) -> str | None:
    if not case:
        return None
    result = case.get("result")
    if not isinstance(result, dict):
        return None
    return result.get("validation", {}).get("status")


def _runtime_nonconvergence(case: dict[str, Any] | None) -> bool:
    return (
        _result_status(case) == "RUNTIME_FAIL_OR_NONCONVERGENCE"
        and (case or {}).get("failure", {}).get("signature")
        in {
            "DIVERGED_MAX_IT",
            "DIVERGED_LINE_SEARCH",
            "DIVERGED_FNORM_NAN",
            "NONLINEAR_DID_NOT_CONVERGE",
        }
    )


def _transport_physics(case_dir: Path) -> dict[str, Any]:
    original = evr1._physics_csv
    evr1._physics_csv = safe_physics_csv
    try:
        return evr1.physics_check(case_dir, monolithic=False)
    finally:
        evr1._physics_csv = original


def _attach_transport_physics(case: dict[str, Any], case_dir: Path) -> None:
    if _result_status(case) != "P2_PASS_P3_PASS":
        case["physics"] = None
        return
    try:
        case["physics"] = _transport_physics(case_dir)
    except evr1.CouplingEVR1Error as exc:
        case["physics"] = {"status": "FAIL", "error": str(exc)}


def _case_pass(case: dict[str, Any] | None) -> bool:
    return (
        _result_status(case) == "P2_PASS_P3_PASS"
        and isinstance((case or {}).get("physics"), dict)
        and (case or {})["physics"].get("status") == "PASS"
    )


def _canonical_checker_self_test(repo_root: Path) -> dict[str, Any]:
    checker = repo_root / KG_E_PARENT_RELATIVE / "check_case.py"
    if not checker.is_file():
        raise CouplingEVR2Error(f"missing accepted electron checker: {checker}")
    proc = subprocess.run(
        [sys.executable, str(checker), "--self-test"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    return {
        "returncode": proc.returncode,
        "output": proc.stdout,
        "status": "PASS" if proc.returncode == 0 else "FAIL",
    }


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
        experiment_id="issue31-evr2-timestep-scaling",
    )
    case["physics"] = None
    if _result_status(case) != "P2_PASS_P3_PASS":
        return case

    cfg = json.loads((case_dir / "test.json").read_text())
    for spec in cfg.get("temporal_csv", []):
        normalize_from_manifest(case_dir, spec)

    checker = (case_dir / cfg["checker"]).resolve()
    checker_args = [str(value) for value in cfg.get("checker_args", [])]
    log = Path(case["measurement_root"]) / "canonical_checker.log"
    with log.open("w") as handle:
        proc = subprocess.run(
            [sys.executable, str(checker), *checker_args],
            cwd=case_dir,
            stdout=handle,
            stderr=subprocess.STDOUT,
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
        _result_status(case) == "P2_PASS_P3_PASS"
        and case.get("canonical_checker", {}).get("status") == "PASS"
    )


def classify(
    kg_e: dict[str, Any],
    dt1e6: dict[str, Any] | None,
    dt1e8: dict[str, Any] | None,
    scaling1e8: dict[str, Any] | None,
) -> dict[str, Any]:
    if not _kg_e_pass(kg_e):
        status = _result_status(kg_e)
        cls = (
            "HARNESS_OR_CONSTRUCTION_FAIL"
            if status == "HARNESS_OR_CONSTRUCTION_FAIL"
            else "KNOWN_GOOD_ELECTRON_CONTROL_FAIL"
        )
        return {
            "class": cls,
            "reason": "accepted real-qvt electron control did not pass on the current executable/environment",
        }

    for label, case in (("dt1e6", dt1e6), ("dt1e8", dt1e8)):
        if case is None:
            return {"class": "HARNESS_OR_CONSTRUCTION_FAIL", "reason": f"{label} was not run"}
        if _result_status(case) == "HARNESS_OR_CONSTRUCTION_FAIL":
            return {
                "class": "HARNESS_OR_CONSTRUCTION_FAIL",
                "reason": f"{label} failed before interpretable physics runtime",
            }
        if _result_status(case) == "P2_PASS_P3_PASS" and not _case_pass(case):
            return {
                "class": "PHYSICS_CHECK_FAIL",
                "reason": f"{label} runtime completed but transport physics checks failed",
            }

    p6 = _case_pass(dt1e6)
    p8 = _case_pass(dt1e8)

    if p6 and p8:
        return {
            "class": "TIMESTEP_STIFFNESS_CONFIRMED_RECOVERY_BY_1E6",
            "reason": "EVR1 dt=1e-4 failed; unchanged transport/scaling recovers at both 1e-6 and 1e-8",
        }
    if (not p6) and p8 and _runtime_nonconvergence(dt1e6):
        return {
            "class": "TIMESTEP_STIFFNESS_CONFIRMED_RECOVERY_ONLY_BY_1E8",
            "reason": "dt=1e-6 still fails by nonlinear convergence while dt=1e-8 recovers with unchanged scaling",
        }
    if p6 and (not p8):
        return {
            "class": "NONMONOTONIC_TIMESTEP_RESPONSE",
            "reason": "dt=1e-6 passes but smaller dt=1e-8 does not; simple timestep-stiffness explanation is insufficient",
        }

    if _runtime_nonconvergence(dt1e6) and _runtime_nonconvergence(dt1e8):
        if scaling1e8 is None:
            return {
                "class": "SCALING_BRANCH_REQUIRED",
                "reason": "both smaller timesteps remain nonlinear-convergence failures",
            }
        if _result_status(scaling1e8) == "HARNESS_OR_CONSTRUCTION_FAIL":
            return {
                "class": "HARNESS_OR_CONSTRUCTION_FAIL",
                "reason": "scaling discriminator failed before interpretable physics runtime",
            }
        if _result_status(scaling1e8) == "P2_PASS_P3_PASS" and not _case_pass(scaling1e8):
            return {
                "class": "PHYSICS_CHECK_FAIL",
                "reason": "scaling discriminator converged but physics checks failed",
            }
        if _case_pass(scaling1e8):
            return {
                "class": "NONLINEAR_SCALING_SENSITIVITY_CONFIRMED",
                "reason": "dt=1e-8 fails with current scaling policy and recovers when only compute_scaling_once changes to true",
            }
        if _runtime_nonconvergence(scaling1e8):
            return {
                "class": "T3_COUPLING_OR_JACOBIAN_FAIL_PERSISTS",
                "reason": "accepted electron control passes, but T3 fails at 1e-6 and 1e-8 and does not recover with accepted scaling-once policy",
            }

    return {
        "class": "UNRESOLVED_RUNTIME_RESPONSE",
        "reason": "observed result signature does not match a predeclared discriminator branch",
    }


def self_test() -> int:
    try:
        if moose_input_self_test():
            raise AssertionError("MooseInput self-test failed")

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
        transformed, meta = configured_transport_input(
            synthetic, dt=DT_1E8, compute_scaling_once=True
        )
        if "potential_plasma" in transformed:
            raise AssertionError("Poisson reference survived EVR2 transform")
        if "dt = 1e-08" not in transformed and "dt = 1e-8" not in transformed:
            raise AssertionError("dt transform did not apply")
        if "compute_scaling_once = true" not in transformed:
            raise AssertionError("scaling transform did not apply")
        if meta["executioner_parameters"]["dt"]["old"] != "1.0e-4":
            raise AssertionError("dt mutation metadata incorrect")

        def result(status: str, physics: str | None = None, signature: str | None = None):
            case = {
                "result": {"validation": {"status": status}},
                "failure": {"signature": signature},
            }
            if physics is not None:
                case["physics"] = {"status": physics}
            return case

        kg = result("P2_PASS_P3_PASS", "PASS")
        kg["canonical_checker"] = {"status": "PASS"}
        pass_case = result("P2_PASS_P3_PASS", "PASS")
        fail_case = result(
            "RUNTIME_FAIL_OR_NONCONVERGENCE", None, "DIVERGED_MAX_IT"
        )

        if classify(kg, pass_case, pass_case, None)["class"] != (
            "TIMESTEP_STIFFNESS_CONFIRMED_RECOVERY_BY_1E6"
        ):
            raise AssertionError("timestep recovery classifier failed")
        if classify(kg, fail_case, pass_case, None)["class"] != (
            "TIMESTEP_STIFFNESS_CONFIRMED_RECOVERY_ONLY_BY_1E8"
        ):
            raise AssertionError("tight timestep classifier failed")
        if classify(kg, fail_case, fail_case, pass_case)["class"] != (
            "NONLINEAR_SCALING_SENSITIVITY_CONFIRMED"
        ):
            raise AssertionError("scaling classifier failed")
        if classify(kg, fail_case, fail_case, fail_case)["class"] != (
            "T3_COUPLING_OR_JACOBIAN_FAIL_PERSISTS"
        ):
            raise AssertionError("persistent coupling classifier failed")

        bad_kg = result(
            "RUNTIME_FAIL_OR_NONCONVERGENCE", None, "DIVERGED_MAX_IT"
        )
        if classify(bad_kg, None, None, None)["class"] != (
            "KNOWN_GOOD_ELECTRON_CONTROL_FAIL"
        ):
            raise AssertionError("known-good control classifier failed")

    except Exception as exc:
        print(f"ISSUE31_EVR2_SELFTEST: FAIL ({exc})")
        return 1

    print("ISSUE31_EVR2_SELFTEST: PASS")
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
        else repo_root / evr1.BASE_INPUT_RELATIVE
    )
    asset_dir = (
        args.asset_case.resolve()
        if args.asset_case
        else qpx_root / evr1.DEFAULT_ASSET_CASE_RELATIVE
    )
    source = qpx_root / evr1.SOURCE_RELATIVE

    if not base_input.is_file():
        raise CouplingEVR2Error(f"missing #29 Q0 reference: {base_input}")
    if not asset_dir.is_dir():
        raise CouplingEVR2Error(
            f"missing heavy asset case: {asset_dir}; pass --asset-case if needed"
        )
    if not source.is_file():
        raise CouplingEVR2Error(f"missing QPX transport source: {source}")

    source_text = source.read_text()
    _, source_parse = legacy_source_transform(source_text)
    if source_parse.get("parser") != "CppSource+CppCallArguments":
        raise CouplingEVR2Error("optimized D_mix source identity could not be verified")

    checker_selftest = _canonical_checker_self_test(repo_root)
    if checker_selftest["status"] != "PASS":
        raise CouplingEVR2Error(
            "accepted electron checker self-test failed: "
            + checker_selftest["output"].strip()
        )

    base_text = base_input.read_text()
    transport_variants: dict[str, tuple[str, dict[str, Any]]] = {
        "dt1e6": configured_transport_input(
            base_text, dt=DT_1E6, compute_scaling_once=False
        ),
        "dt1e8": configured_transport_input(
            base_text, dt=DT_1E8, compute_scaling_once=False
        ),
        "scaling1e8": configured_transport_input(
            base_text, dt=DT_1E8, compute_scaling_once=True
        ),
    }

    parser_errors: dict[str, list[str]] = {}
    for label, (text, _) in transport_variants.items():
        errors = validate_parser_symbols_text(text, f"<{label}>")
        if errors:
            parser_errors[label] = errors
    if parser_errors:
        raise CouplingEVR2Error(
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
    root = _create_root(results_root)
    cases_root = root / "cases"
    cases_root.mkdir()

    kg_e_case = _copy_kg_e(repo_root, cases_root)

    case_dirs: dict[str, Path] = {}
    refs: dict[str, Any] = {}
    for label, (text, _) in transport_variants.items():
        case_dir = cases_root / label
        _copy_transport_case(asset_dir, case_dir, text)
        refs[label] = evr1._validate_referenced_files(text, case_dir)
        case_dirs[label] = case_dir

    identity = {
        "qpx_realpath": str(exe),
        "qpx_sha256": _sha256(exe),
        "transport_source": str(source),
        "transport_source_sha256": _sha256(source),
        "optimized_dmix_source_parse": source_parse,
        "base_input": str(base_input),
        "base_input_sha256": _sha256(base_input),
        "asset_case": str(asset_dir),
        "kg_e_control_source": str(repo_root / KG_E_PARENT_RELATIVE / "qvt_prepoisson"),
        "kg_e_checker_selftest": checker_selftest,
        "evr1_baseline": EVR1_BASELINE,
        "transport_variants": {
            label: meta for label, (_, meta) in transport_variants.items()
        },
        "referenced_files": refs,
    }
    _write_json(root / "identity.json", identity)

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
            experiment_id="issue31-evr2-timestep-scaling",
            species=list(evr1.SPECIES),
        )
        _attach_transport_physics(dt1e6, case_dirs["dt1e6"])

        dt1e8 = _run_benchmark(
            case_dir=case_dirs["dt1e8"],
            case_id="Issue31_T3_dt1e8",
            exe=exe,
            measurements_root=measurements,
            experiment_id="issue31-evr2-timestep-scaling",
            species=list(evr1.SPECIES),
        )
        _attach_transport_physics(dt1e8, case_dirs["dt1e8"])

        if _runtime_nonconvergence(dt1e6) and _runtime_nonconvergence(dt1e8):
            scaling1e8 = _run_benchmark(
                case_dir=case_dirs["scaling1e8"],
                case_id="Issue31_T3_dt1e8_scaling_once",
                exe=exe,
                measurements_root=measurements,
                experiment_id="issue31-evr2-timestep-scaling",
                species=list(evr1.SPECIES),
            )
            _attach_transport_physics(scaling1e8, case_dirs["scaling1e8"])

    decision = classify(kg_e, dt1e6, dt1e8, scaling1e8)
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
    _write_json(root / "summary.json", summary)

    def brief(case: dict[str, Any] | None, *, kg: bool = False) -> str:
        if case is None:
            return "SKIPPED"
        if kg:
            if _kg_e_pass(case):
                return "PASS"
        elif _case_pass(case):
            return "PASS"
        status = _result_status(case) or "NO_RESULT"
        sig = case.get("failure", {}).get("signature")
        return f"{status}:{sig}" if sig else status

    print("ISSUE31_EVR2_KGE:", brief(kg_e, kg=True))
    print("ISSUE31_EVR2_DT1E6:", brief(dt1e6))
    print("ISSUE31_EVR2_DT1E8:", brief(dt1e8))
    print("ISSUE31_EVR2_SCALING1E8:", brief(scaling1e8))
    print("ISSUE31_EVR2_CLASS:", decision["class"])
    print("ISSUE31_EVR2_REASON:", decision["reason"])
    print("ISSUE31_EVR2_SUMMARY:", root / "summary.json")

    terminal_ok = decision["class"] in {
        "TIMESTEP_STIFFNESS_CONFIRMED_RECOVERY_BY_1E6",
        "TIMESTEP_STIFFNESS_CONFIRMED_RECOVERY_ONLY_BY_1E8",
        "NONLINEAR_SCALING_SENSITIVITY_CONFIRMED",
        "T3_COUPLING_OR_JACOBIAN_FAIL_PERSISTS",
        "NONMONOTONIC_TIMESTEP_RESPONSE",
    }
    return 0 if terminal_ok else 2


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="qpx coupling-evr2")
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
    except (CouplingEVR2Error, PerformanceContractError, SystemExit) as exc:
        print(f"ISSUE31_EVR2_FATAL: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
