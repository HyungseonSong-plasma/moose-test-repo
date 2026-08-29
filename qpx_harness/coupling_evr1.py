"""Issue #31 EVR1 optimized-monolithic feasibility discriminator.

Builds two cases from the archived #29 Q0 reference:
  T3 transport_only: heavy + solved electron, Poisson variable/solve removed
  T4 monolithic_q0: heavy + solved electron + solved Poisson

Both retain the same mesh/assets, physical dt, NEWTON formulation and direct-LU
baseline. Each case is measured with PF-1 BENCHMARK/PROFILE and checked against
the existing r29 runtime physics observables.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .dmix_equivalence_structured import legacy_source_transform
from .moose_input import MooseInput, MooseInputError, self_test as moose_input_self_test
from .performance_core import PerformanceContractError, run_measurement
from .performance_investigation import build_investigation_summary
from .performance_smoke import (
    build_smoke_manifest,
    compare_smoke_results,
    default_results_root,
)
from .preflight import validate_parser_symbols_text
from .runtime import resolve_executable, validate_executable


BASE_INPUT_RELATIVE = Path(
    "archive/Issue29_monolithic_performance_bound/monolithic_q0_reference.i"
)
DEFAULT_ASSET_CASE_RELATIVE = Path(
    "temp/tests/Issue22_qvt_transient_species_accumulation"
)
SOURCE_RELATIVE = Path("src/materials/QPXThermalDiffusionMaterial.C")
SPECIES = ("O2s", "O2p", "O", "Om", "Op", "Os")
TRANSPORT_REMOVE_PATHS = (
    "Variables/potential_plasma",
    "FVKernels/r30_phi_diffusion",
    "FVKernels/r30_phi_charge_source",
    "FVBCs/r30_phi_plasma_metal",
    "FVBCs/r30_phi_plasma_electrode",
    "FVBCs/r30_phi_plasma_right",
    "FVBCs/r30_phi_inlet",
    "FVBCs/r30_phi_outlet",
    "Postprocessors/r29_phi_min",
    "Postprocessors/r29_phi_max",
    "Postprocessors/r29_phi_integral",
)
E_CHARGE = 1.602176634e-19
SUM_W_TOL = 1e-10
BOUND_TOL = 1e-10
CHARGE_REL_TOL = 1e-3
PHI_NONTRIVIAL_TOL = 1e-14


class CouplingEVR1Error(RuntimeError):
    pass


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text())
    if not isinstance(payload, dict):
        raise CouplingEVR1Error(f"expected JSON object: {path}")
    return payload


def _create_root(results_root: Path) -> Path:
    results_root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    root = results_root / f"coupling_evr1_Issue31_{stamp}"
    index = 1
    while root.exists():
        root = results_root / f"coupling_evr1_Issue31_{stamp}_{index:02d}"
        index += 1
    root.mkdir()
    return root


def _purge_stale(case: Path) -> None:
    for path in case.rglob(".jitcache"):
        if path.is_dir():
            shutil.rmtree(path)
    for pattern in (
        "input_out*",
        "r29_csv*",
        "perfgraph*",
        "petsc_log*",
        "metrics*",
    ):
        for path in case.glob(pattern):
            if path.is_file():
                path.unlink()
            elif path.is_dir():
                shutil.rmtree(path)


_FILE_PARAM_RE = re.compile(
    r"""^\s*(?P<name>file|[A-Za-z_][A-Za-z0-9_]*_file)\s*=\s*
        (?:
          '(?P<single>[^']+)'
          |
          \"(?P<double>[^\"]+)\"
          |
          (?P<bare>[^\s#]+)
        )
    """,
    re.MULTILINE | re.VERBOSE,
)


def _referenced_files(text: str, case_dir: Path) -> list[dict[str, str]]:
    refs: list[dict[str, str]] = []
    for match in _FILE_PARAM_RE.finditer(text):
        raw = match.group("single") or match.group("double") or match.group("bare") or ""
        if not raw or "${" in raw:
            continue
        path = Path(raw).expanduser()
        resolved = path if path.is_absolute() else case_dir / path
        refs.append(
            {
                "parameter": match.group("name"),
                "raw": raw,
                "resolved": str(resolved.resolve()),
            }
        )
    return refs


def _validate_referenced_files(text: str, case_dir: Path) -> list[dict[str, str]]:
    refs = _referenced_files(text, case_dir)
    missing = [ref for ref in refs if not Path(ref["resolved"]).is_file()]
    if missing:
        lines = ", ".join(f"{ref['parameter']}={ref['resolved']}" for ref in missing)
        raise CouplingEVR1Error(f"missing referenced input file(s): {lines}")
    return refs


def transport_only_input(base_text: str) -> tuple[str, dict[str, Any]]:
    try:
        doc = MooseInput(base_text)
        transformed, removed = doc.remove_paths(TRANSPORT_REMOVE_PATHS)
    except MooseInputError as exc:
        raise CouplingEVR1Error(f"transport-only structural transform failed: {exc}") from exc

    if "potential_plasma" in transformed:
        raise CouplingEVR1Error(
            "transport-only transform left a potential_plasma reference; "
            "refuse to run an ambiguously coupled control"
        )
    required = ("n_e_solved", "r30_e_time", "r30_e_diffusion", "r30_charge_density")
    missing = [token for token in required if token not in transformed]
    if missing:
        raise CouplingEVR1Error(
            "transport-only transform removed required electron/charge state: "
            + ", ".join(missing)
        )
    return transformed, {
        "removed_paths": list(TRANSPORT_REMOVE_PATHS),
        "removed_spans": removed,
        "retained_required_tokens": list(required),
    }


def _copy_case(asset_dir: Path, target: Path, input_text: str) -> None:
    shutil.copytree(asset_dir, target)
    _purge_stale(target)
    (target / "input.i").write_text(input_text)


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
        manifest = build_smoke_manifest(
            mode=mode,
            case_dir=case_dir,
            input_name="input.i",
            experiment_id="issue31-evr1-optimized-monolithic",
            case_id=case_id,
            num_steps=1,
            species=list(SPECIES),
        )
        manifest_path = pair_root / f"{mode.lower()}_manifest.json"
        _write_json(manifest_path, manifest)
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


def _float(row: dict[str, str], key: str) -> float:
    try:
        value = float(row[key])
    except (KeyError, ValueError) as exc:
        raise CouplingEVR1Error(f"missing/non-numeric physics column {key!r}") from exc
    if not math.isfinite(value):
        raise CouplingEVR1Error(f"non-finite physics value {key}={value}")
    return value


def _physics_csv(case_dir: Path, *, monolithic: bool) -> tuple[Path, dict[str, str]]:
    required = {
        "time",
        "r29_ne_min",
        "r29_ne_max",
        "r29_charge_min",
        "r29_charge_max",
        "r29_charge_integral",
        "r29_heavy_charge_number_integral",
        "r29_electron_charge_number_integral",
        "r29_sum_w_min",
        "r29_sum_w_max",
    }
    for species in SPECIES:
        required.add(f"r29_w_{species}_min")
        required.add(f"r29_w_{species}_max")
    if monolithic:
        required.update({"r29_phi_min", "r29_phi_max", "r29_phi_integral"})

    candidates: list[tuple[Path, list[dict[str, str]]]] = []
    for path in sorted(case_dir.glob("*.csv")):
        try:
            with path.open(newline="") as handle:
                rows = list(csv.DictReader(handle))
        except (OSError, csv.Error):
            continue
        if not rows:
            continue
        if required.issubset(rows[0].keys()):
            candidates.append((path, rows))

    if len(candidates) != 1:
        raise CouplingEVR1Error(
            "expected one runtime physics CSV with r29 observables, found "
            f"{len(candidates)}: {[str(path) for path, _ in candidates]}"
        )
    path, rows = candidates[0]
    physical = [row for row in rows if _float(row, "time") > 1e-15]
    if not physical:
        raise CouplingEVR1Error(f"no positive solved-time row in {path}")
    return path, physical[-1]


def physics_check(case_dir: Path, *, monolithic: bool) -> dict[str, Any]:
    path, row = _physics_csv(case_dir, monolithic=monolithic)
    checks: dict[str, bool] = {}

    ne_min = _float(row, "r29_ne_min")
    ne_max = _float(row, "r29_ne_max")
    checks["electron_nonnegative"] = ne_min >= -BOUND_TOL and ne_max >= ne_min

    sum_min = _float(row, "r29_sum_w_min")
    sum_max = _float(row, "r29_sum_w_max")
    checks["constrained_sum_unity"] = (
        abs(sum_min - 1.0) <= SUM_W_TOL and abs(sum_max - 1.0) <= SUM_W_TOL
    )

    species_values: dict[str, dict[str, float]] = {}
    for species in SPECIES:
        low = _float(row, f"r29_w_{species}_min")
        high = _float(row, f"r29_w_{species}_max")
        species_values[species] = {"min": low, "max": high}
        checks[f"{species}_bounds"] = (
            low >= -BOUND_TOL and high <= 1.0 + BOUND_TOL and high >= low
        )

    charge_min = _float(row, "r29_charge_min")
    charge_max = _float(row, "r29_charge_max")
    charge_integral = _float(row, "r29_charge_integral")
    heavy_number = _float(row, "r29_heavy_charge_number_integral")
    electron_number = _float(row, "r29_electron_charge_number_integral")
    expected_charge = E_CHARGE * (heavy_number + electron_number)
    charge_scale = max(abs(charge_integral), abs(expected_charge), 1e-300)
    charge_rel = abs(charge_integral - expected_charge) / charge_scale
    checks["charge_finite_ordered"] = charge_max >= charge_min
    checks["charge_integral_identity"] = charge_rel <= CHARGE_REL_TOL

    phi: dict[str, float] | None = None
    if monolithic:
        phi = {
            "min": _float(row, "r29_phi_min"),
            "max": _float(row, "r29_phi_max"),
            "integral": _float(row, "r29_phi_integral"),
        }
        checks["potential_ordered"] = phi["max"] >= phi["min"]
        checks["potential_nontrivial"] = max(abs(phi["min"]), abs(phi["max"])) > PHI_NONTRIVIAL_TOL

    return {
        "status": "PASS" if all(checks.values()) else "FAIL",
        "csv": str(path),
        "time": _float(row, "time"),
        "checks": checks,
        "electron": {"min": ne_min, "max": ne_max},
        "sum_w": {"min": sum_min, "max": sum_max},
        "species": species_values,
        "charge": {
            "min": charge_min,
            "max": charge_max,
            "integral": charge_integral,
            "expected_integral": expected_charge,
            "relative_identity_error": charge_rel,
        },
        "potential": phi,
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
        if moose_input_self_test():
            raise AssertionError("MooseInput self-test failed")

        base = """
[Variables]
  [u]
  []
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
        transformed, meta = transport_only_input(base)
        if "potential_plasma" in transformed:
            raise AssertionError("potential remained in transport-only synthetic")
        if len(meta["removed_paths"]) != len(TRANSPORT_REMOVE_PATHS):
            raise AssertionError("wrong removal count")
        if "n_e_solved" not in transformed or "r30_e_diffusion" not in transformed:
            raise AssertionError("electron control was removed")

        bad = base.replace("[r29_phi_integral]\n  []\n", "")
        try:
            transport_only_input(bad)
        except CouplingEVR1Error:
            pass
        else:
            raise AssertionError("missing expected Poisson block mutation was not rejected")

        fake_transport = {
            "benchmark": {
                "validation": {"status": "P2_PASS_P3_PASS"},
                "performance": {"wall_seconds": 10.0},
            }
        }
        fake_mono = {
            "benchmark": {
                "validation": {"status": "P2_PASS_P3_PASS"},
                "performance": {"wall_seconds": 15.0},
            },
            "investigation": {
                "classification": {"bottleneck_class": "PC_FACTORIZATION"}
            },
        }
        ok_physics = {"status": "PASS"}
        pre = preliminary_classification(fake_transport, fake_mono, ok_physics, ok_physics)
        if pre["class"] != "MONOLITHIC_LINEAR_ALGEBRA_BOUND_CANDIDATE":
            raise AssertionError(pre)
    except Exception as exc:
        print(f"ISSUE31_EVR1_SELFTEST: FAIL ({exc})")
        return 1
    print("ISSUE31_EVR1_SELFTEST: PASS")
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
        else repo_root / BASE_INPUT_RELATIVE
    )
    asset_dir = (
        args.asset_case.resolve()
        if args.asset_case
        else qpx_root / DEFAULT_ASSET_CASE_RELATIVE
    )
    source = qpx_root / SOURCE_RELATIVE

    if not base_input.is_file():
        raise CouplingEVR1Error(f"missing archived #29 Q0 reference: {base_input}")
    if not asset_dir.is_dir():
        raise CouplingEVR1Error(
            f"missing asset case: {asset_dir}; pass --asset-case with qvt.msh and transport_data.txt"
        )
    if not source.is_file():
        raise CouplingEVR1Error(f"missing QPX transport source: {source}")

    source_text = source.read_text()
    _, source_parse = legacy_source_transform(source_text)
    if source_parse.get("parser") != "CppSource+CppCallArguments":
        raise CouplingEVR1Error("optimized D_mix source identity could not be structurally verified")

    base_text = base_input.read_text()
    parser_errors = validate_parser_symbols_text(base_text, str(base_input))
    if parser_errors:
        raise CouplingEVR1Error("base input parser-symbol preflight failed: " + " | ".join(parser_errors))

    transport_text, transform_meta = transport_only_input(base_text)
    parser_errors = validate_parser_symbols_text(transport_text, "<transport-only>")
    if parser_errors:
        raise CouplingEVR1Error(
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
    _copy_case(asset_dir, monolithic_case, base_text)
    _copy_case(asset_dir, transport_case, transport_text)

    monolithic_refs = _validate_referenced_files(base_text, monolithic_case)
    transport_refs = _validate_referenced_files(transport_text, transport_case)

    identity = {
        "qpx_realpath": str(exe),
        "qpx_sha256": _sha256(exe),
        "transport_source": str(source),
        "transport_source_sha256": _sha256(source),
        "optimized_dmix_source_parse": source_parse,
        "base_input": str(base_input),
        "base_input_sha256": _sha256(base_input),
        "asset_case": str(asset_dir),
        "referenced_files_monolithic": monolithic_refs,
        "referenced_files_transport": transport_refs,
        "transport_transform": transform_meta,
    }
    _write_json(root / "identity.json", identity)
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
            transport_physics = physics_check(transport_case, monolithic=False)
        except CouplingEVR1Error as exc:
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
            monolithic_physics = physics_check(monolithic_case, monolithic=True)
        except CouplingEVR1Error as exc:
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
    _write_json(root / "summary.json", summary)

    print("ISSUE31_EVR1_TRANSPORT_PHYSICS:", (transport_physics or {}).get("status", "NOT_RUN"))
    print("ISSUE31_EVR1_MONOLITHIC_PHYSICS:", (monolithic_physics or {}).get("status", "NOT_RUN"))
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

    return 0 if decision["class"] not in {"HARNESS_OR_CONSTRUCTION_FAIL", "PHYSICS_CHECK_FAIL"} else 2


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
    except (CouplingEVR1Error, PerformanceContractError, SystemExit) as exc:
        print(f"ISSUE31_EVR1_FATAL: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
