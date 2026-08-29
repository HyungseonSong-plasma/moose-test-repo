"""Issue #45 electron-inventory nullspace and quasi-steady closure preflight.

This harness proves only the structural/framework prerequisites for the current
closed, source-free reduced electron model. It deliberately exposes no P3 mode.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from . import evidence
from . import fast_plasma_relaxation_v2 as v2
from . import fast_plasma_relaxation_v5 as v5
from .moose_input import MooseInput, MooseInputError
from .preflight import validate_parser_symbols_text
from .runtime import run_command, run_qpx


ISSUE = 45
DT_REFERENCE = 1.0e-13
STEPS = 1
DRIFT_TYPE = "QPXFVElectrostaticDrift"
REQUIRED_FVFLUX_SCHEMA_PARAMETERS = (
    "boundaries_to_avoid",
    "boundaries_to_force",
    "force_boundary_execution",
)
EXPECTED_DRIFT_BOUNDARIES = frozenset(
    {
        "inlet",
        "outlet",
        "plasma_electrode",
        "plasma_metal",
        "plasma_right",
        "plasma_cover",
        "plasma_wafer",
        "plasma_focus_ring",
    }
)
EXPECTED_ELECTRON_KERNEL_TYPES = (
    "FVDiffusion",
    "FVTimeKernel",
    DRIFT_TYPE,
)


class ElectronInventoryNullspaceError(RuntimeError):
    pass


def _unquote(value: str | None) -> str | None:
    if value is None:
        return None
    result = value.strip()
    if len(result) >= 2 and result[0] == result[-1] and result[0] in {"'", '"'}:
        result = result[1:-1]
    return result.strip()


def _words(value: str | None) -> list[str]:
    raw = _unquote(value)
    return raw.split() if raw else []


def _parameter_value(text: str, path: str, name: str) -> str | None:
    doc = MooseInput(text)
    span = doc.unique(path)
    block = text[span.start : span.end]
    pattern = re.compile(
        rf"(?m)^\s*{re.escape(name)}\s*=\s*(?P<value>[^#\r\n]*?)\s*(?:#.*)?$"
    )
    matches = list(pattern.finditer(block))
    if len(matches) > 1:
        raise ElectronInventoryNullspaceError(
            f"ambiguous parameter {path}/{name}: {len(matches)} assignments"
        )
    return matches[0].group("value").strip() if matches else None


def _direct_children(text: str, parent: str) -> list[str]:
    depth = parent.count("/") + 1
    prefix = parent + "/"
    return sorted(
        block.path
        for block in MooseInput(text).blocks
        if block.path.startswith(prefix) and block.path.count("/") == depth
    )


def _truthy(value: str | None) -> bool:
    raw = (_unquote(value) or "").lower()
    return raw in {"1", "true", "yes", "on"}


def audit_closed_electron_structure(text: str) -> dict[str, Any]:
    """Audit the exact reduced-model prerequisites for global electron conservation."""
    checks: list[dict[str, Any]] = []

    def add(check_id: str, passed: bool, observed: Any, required: Any) -> None:
        checks.append(
            {
                "id": check_id,
                "status": "PASS" if passed else "FAIL",
                "observed": observed,
                "required": required,
            }
        )

    parser_errors = validate_parser_symbols_text(text, "<issue45-inventory-audit>")
    add("parser-symbol-preflight", not parser_errors, parser_errors, [])

    electron_kernels: list[dict[str, Any]] = []
    for path in _direct_children(text, "FVKernels"):
        if _unquote(_parameter_value(text, path, "variable")) != "n_e":
            continue
        electron_kernels.append(
            {
                "path": path,
                "type": _unquote(_parameter_value(text, path, "type")),
            }
        )

    observed_types = sorted(item["type"] for item in electron_kernels if item["type"])
    expected_types = sorted(EXPECTED_ELECTRON_KERNEL_TYPES)
    add(
        "electron-kernel-set",
        observed_types == expected_types and len(electron_kernels) == 3,
        electron_kernels,
        expected_types,
    )

    drift_paths = [item["path"] for item in electron_kernels if item["type"] == DRIFT_TYPE]
    diffusion_paths = [item["path"] for item in electron_kernels if item["type"] == "FVDiffusion"]
    add("one-electrostatic-drift", len(drift_paths) == 1, drift_paths, 1)
    add("one-electron-diffusion", len(diffusion_paths) == 1, diffusion_paths, 1)

    drift_boundaries: set[str] = set()
    drift_forced: list[str] = []
    drift_force_all = False
    if len(drift_paths) == 1:
        drift = drift_paths[0]
        drift_boundaries = set(_words(_parameter_value(text, drift, "boundaries_to_avoid")))
        drift_forced = _words(_parameter_value(text, drift, "boundaries_to_force"))
        drift_force_all = _truthy(_parameter_value(text, drift, "force_boundary_execution"))
    add(
        "drift-closes-all-plasma-boundaries",
        drift_boundaries == set(EXPECTED_DRIFT_BOUNDARIES),
        sorted(drift_boundaries),
        sorted(EXPECTED_DRIFT_BOUNDARIES),
    )
    add("drift-no-forced-boundaries", not drift_forced, drift_forced, [])
    add("drift-no-force-all-boundaries", not drift_force_all, drift_force_all, False)

    diffusion_forced: list[dict[str, Any]] = []
    for path in diffusion_paths:
        forced = _words(_parameter_value(text, path, "boundaries_to_force"))
        force_all = _truthy(_parameter_value(text, path, "force_boundary_execution"))
        if forced or force_all:
            diffusion_forced.append(
                {"path": path, "boundaries_to_force": forced, "force_boundary_execution": force_all}
            )
    add("diffusion-natural-boundary-path", not diffusion_forced, diffusion_forced, [])

    electron_bcs: list[dict[str, Any]] = []
    for path in _direct_children(text, "FVBCs"):
        if _unquote(_parameter_value(text, path, "variable")) == "n_e":
            electron_bcs.append(
                {"path": path, "type": _unquote(_parameter_value(text, path, "type"))}
            )
    add("no-electron-fvbc", not electron_bcs, electron_bcs, [])

    poisson_bcs: list[str] = []
    for path in _direct_children(text, "FVBCs"):
        if _unquote(_parameter_value(text, path, "variable")) == "potential_plasma":
            poisson_bcs.append(path)
    add("poisson-bcs-remain-distinct", bool(poisson_bcs), poisson_bcs, "one or more potential_plasma FVBCs")

    blockers = [check for check in checks if check["status"] != "PASS"]
    return {
        "status": "PASS" if not blockers else "HOLD",
        "class": (
            "CLOSED_SOURCE_FREE_ELECTRON_STRUCTURE_PASS"
            if not blockers
            else "CONSERVATION_STRUCTURE_FAIL"
        ),
        "checks": checks,
        "blockers": blockers,
        "electron_kernels": electron_kernels,
        "electron_fvbcs": electron_bcs,
        "drift_boundaries_to_avoid": sorted(drift_boundaries),
        "derivation_scope": "steady spatial n_e residual only; transient FVTimeKernel excluded from the nullspace identity",
    }


def _extract_moose_json(text: str) -> Any:
    start_marker = "**START JSON DATA**"
    end_marker = "**END JSON DATA**"
    start = text.find(start_marker)
    end = text.find(end_marker)
    if start < 0 or end < 0 or end <= start:
        raise ElectronInventoryNullspaceError("MOOSE JSON markers are missing")
    payload = text[start + len(start_marker) : end].strip()
    try:
        return json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ElectronInventoryNullspaceError(f"invalid MOOSE JSON payload: {exc}") from exc


def analyze_drift_schema_text(text: str, *, returncode: int = 0) -> dict[str, Any]:
    if returncode != 0:
        return {
            "status": "HOLD",
            "class": "FRAMEWORK_SCHEMA_QUERY_FAIL",
            "reason": f"qpx --json-search returned {returncode}",
        }
    try:
        payload = _extract_moose_json(text)
    except ElectronInventoryNullspaceError as exc:
        return {
            "status": "HOLD",
            "class": "FRAMEWORK_SCHEMA_EVIDENCE_INSUFFICIENT",
            "reason": str(exc),
        }

    serialized = json.dumps(payload, sort_keys=True)
    object_present = DRIFT_TYPE in serialized
    parameter_presence = {
        name: name in serialized for name in REQUIRED_FVFLUX_SCHEMA_PARAMETERS
    }
    fvflux_semantic = "FVFluxKernel" in serialized
    passed = object_present and all(parameter_presence.values()) and fvflux_semantic
    return {
        "status": "PASS" if passed else "HOLD",
        "class": "FVFLUX_SCHEMA_PASS" if passed else "FRAMEWORK_SCHEMA_EVIDENCE_INSUFFICIENT",
        "reason": (
            "QPX object schema exposes FVFluxKernel boundary-execution controls and FVFluxKernel semantics"
            if passed
            else "QPX object schema did not prove all required FVFluxKernel inheritance semantics"
        ),
        "object_present": object_present,
        "required_parameters": parameter_presence,
        "fvfluxkernel_semantic_present": fvflux_semantic,
    }


def _synthetic_closed_input() -> str:
    boundaries = " ".join(sorted(EXPECTED_DRIFT_BOUNDARIES))
    return f"""[Variables]
  [n_e]
    type = MooseVariableFVReal
  []
  [potential_plasma]
    type = MooseVariableFVReal
  []
[]
[FVKernels]
  [time]
    type = FVTimeKernel
    variable = n_e
  []
  [diffusion]
    type = FVDiffusion
    variable = n_e
  []
  [drift]
    type = {DRIFT_TYPE}
    variable = n_e
    boundaries_to_avoid = '{boundaries}'
  []
  [phi]
    type = FVDiffusion
    variable = potential_plasma
  []
[]
[FVBCs]
  [phi_ground]
    type = FVDirichletBC
    variable = potential_plasma
    boundary = plasma_metal
    value = 0
  []
[]
"""


def self_test() -> int:
    try:
        base = _synthetic_closed_input()
        if audit_closed_electron_structure(base)["status"] != "PASS":
            raise AssertionError("positive closed/source-free structure did not pass")

        missing_boundary = base.replace(" plasma_wafer", "", 1)
        if audit_closed_electron_structure(missing_boundary)["status"] == "PASS":
            raise AssertionError("missing drift boundary negative mutation was accepted")

        electron_bc, _ = MooseInput(base).insert_before_close(
            "FVBCs",
            """  [electron_leak]
    type = FVDirichletBC
    variable = n_e
    boundary = plasma_metal
    value = 1e16
  []""",
        )
        if audit_closed_electron_structure(electron_bc)["status"] == "PASS":
            raise AssertionError("n_e FVBC negative mutation was accepted")

        electron_source, _ = MooseInput(base).insert_before_close(
            "FVKernels",
            """  [electron_source]
    type = FVCoupledForce
    variable = n_e
    v = potential_plasma
  []""",
        )
        if audit_closed_electron_structure(electron_source)["status"] == "PASS":
            raise AssertionError("n_e source/sink negative mutation was accepted")

        good_schema = {
            "QPXFVElectrostaticDrift": {
                "description": "derived FVFluxKernel object",
                "parameters": {
                    "boundaries_to_avoid": {"description": "FVFluxKernel avoid"},
                    "boundaries_to_force": {"description": "FVFluxKernel force"},
                    "force_boundary_execution": {"description": "FVFluxKernel boundary execution"},
                },
            }
        }
        wrapped = "**START JSON DATA**\n" + json.dumps(good_schema) + "\n**END JSON DATA**\n"
        if analyze_drift_schema_text(wrapped)["status"] != "PASS":
            raise AssertionError("valid FVFluxKernel schema evidence did not pass")

        bad_schema = wrapped.replace("boundaries_to_force", "unrelated_parameter")
        if analyze_drift_schema_text(bad_schema)["status"] == "PASS":
            raise AssertionError("missing FVFluxKernel schema control was accepted")
        if analyze_drift_schema_text("{}\n")["status"] == "PASS":
            raise AssertionError("missing MOOSE JSON evidence was accepted")
    except Exception as exc:
        print(f"ISSUE45_INVENTORY_NULLSPACE_SELFTEST: FAIL ({exc})")
        return 1
    print("ISSUE45_INVENTORY_NULLSPACE_SELFTEST: PASS")
    return 0


def _prepare_case(*, exe: Path, results_root: str | None) -> dict[str, Any]:
    repo_root = Path(__file__).resolve().parents[1]
    base_case = repo_root / v2.v1.BASE_CASE_RELATIVE
    if not base_case.is_dir():
        raise ElectronInventoryNullspaceError(f"missing accepted electron control: {base_case}")

    mesh = v2.mesh_stats(base_case / "qvt.msh")
    radial_span = float(mesh["bbox_span_m"]["x"])
    base_text = (base_case / "input.i").read_text()
    text = v5._build_feedback_v5(
        base_text,
        dt=DT_REFERENCE,
        steps=STEPS,
        radial_span=radial_span,
    )
    p1 = audit_closed_electron_structure(text)

    evidence_root = (
        Path(results_root).expanduser().resolve()
        if results_root
        else exe.parent / "temp" / "results"
    )
    root = evidence.ensure_fresh_directory(
        evidence_root / f"issue45_inventory_nullspace_{evidence.utc_timestamp()}"
    )
    case_dir = root / "case"
    v2.v1._copy_case(base_case, case_dir, text)
    v2.v1._validate_assets(case_dir)
    return {
        "root": root,
        "case_dir": case_dir,
        "input_path": case_dir / "input.i",
        "p1": p1,
    }


def _run_p2_check_input(*, exe: Path, prepared: dict[str, Any]) -> dict[str, Any]:
    log_path = prepared["root"] / "p2_check_input.log"
    run = run_qpx(
        exe,
        cwd=prepared["case_dir"],
        input_name="input.i",
        log_path=log_path,
        extra_args=("--check-input", "--color", "off"),
        stream=False,
    )
    return {
        "status": "PASS" if run.returncode == 0 else "HOLD",
        "returncode": run.returncode,
        "wall_seconds": run.wall_seconds,
        "log": str(log_path),
        "failure": v5._classify_p2_failure(log_path, run.returncode),
        "identity": {
            **evidence.identity_record(executable=exe, input_path=prepared["input_path"]),
            "qpx_sha256": evidence.sha256_file(exe),
        },
    }


def _run_p2_schema(*, exe: Path, prepared: dict[str, Any]) -> dict[str, Any]:
    log_path = prepared["root"] / "p2_drift_schema.log"
    run = run_command(
        [str(exe), "--json-search", DRIFT_TYPE],
        cwd=prepared["case_dir"],
        log_path=log_path,
        stream=False,
    )
    analysis = analyze_drift_schema_text(
        log_path.read_text(errors="replace") if log_path.is_file() else "",
        returncode=run.returncode,
    )
    return {
        **analysis,
        "returncode": run.returncode,
        "wall_seconds": run.wall_seconds,
        "log": str(log_path),
        "qpx_realpath": str(exe),
        "qpx_sha256": evidence.sha256_file(exe),
    }


def run_preflight(*, qpx: str | None, results_root: str | None) -> int:
    exe = v2.resolve_executable(qpx)
    v2.validate_executable(exe)
    prepared = _prepare_case(exe=exe, results_root=results_root)

    p1_pass = prepared["p1"]["status"] == "PASS"
    check_input = _run_p2_check_input(exe=exe, prepared=prepared) if p1_pass else {}
    schema = _run_p2_schema(exe=exe, prepared=prepared) if p1_pass else {}
    p2_check_pass = check_input.get("status") == "PASS"
    p2_schema_pass = schema.get("status") == "PASS"
    status = "PASS" if p1_pass and p2_check_pass and p2_schema_pass else "HOLD"

    if status == "PASS":
        decision = {
            "status": "PASS",
            "class": "INVENTORY_LEFT_NULLSPACE_STATIC_PASS",
            "reason": (
                "the generated closed/source-free electron residual satisfies the structural conservation contract, "
                "and user-local QPX schema confirms the custom drift exposes FVFluxKernel conservative boundary-execution semantics"
            ),
            "left_null_vector": "[1^T, 0]",
            "identity": "[1^T,0] J_steady = 0 for the current reduced closed/source-free model",
            "p3_required_for_this_identity": False,
        }
    else:
        decision = {
            "status": "HOLD",
            "class": (
                "CONSERVATION_STRUCTURE_FAIL"
                if not p1_pass
                else schema.get("class", "HARNESS_OR_CONSTRUCTION_FAIL")
                if not p2_schema_pass
                else "HARNESS_OR_CONSTRUCTION_FAIL"
            ),
            "reason": "P0/P1/P2 did not complete the static/framework conservation chain",
            "p3_required_for_this_identity": False,
        }

    summary_path = prepared["root"] / "summary.json"
    v2._write_json(
        summary_path,
        {
            "issue": ISSUE,
            "mode": "inventory-nullspace-preflight",
            "status": status,
            "p3_executed": False,
            "claim": "static/framework proof of the electron-inventory left-null identity for the current closed/source-free reduced model",
            "p1": prepared["p1"],
            "p2": {"check_input": check_input, "drift_schema": schema},
            "decision": decision,
        },
    )

    print(f"ISSUE45_INVENTORY_NULLSPACE_P1: {'PASS' if p1_pass else 'HOLD'}")
    print(f"ISSUE45_INVENTORY_NULLSPACE_P2_CHECK_INPUT: {'PASS' if p2_check_pass else 'HOLD'}")
    print(f"ISSUE45_INVENTORY_NULLSPACE_P2_DRIFT_SCHEMA: {'PASS' if p2_schema_pass else 'HOLD'}")
    print(f"ISSUE45_INVENTORY_NULLSPACE_PREFLIGHT: {status}")
    print(f"ISSUE45_INVENTORY_NULLSPACE_CLASS: {decision['class']}")
    print(f"ISSUE45_INVENTORY_NULLSPACE_REASON: {decision['reason']}")
    print(f"ISSUE45_INVENTORY_NULLSPACE_SUMMARY: {summary_path}")
    return 0 if status == "PASS" else 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run Issue45 electron-inventory nullspace structural/framework preflight"
    )
    parser.add_argument("--qpx", help="path to user-local qpx-opt")
    parser.add_argument("--results-root")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--self-test", action="store_true")
    mode.add_argument("--preflight", action="store_true")
    args = parser.parse_args(argv)

    if args.self_test:
        return self_test()
    if self_test() != 0:
        return 1
    try:
        return run_preflight(qpx=args.qpx, results_root=args.results_root)
    except (ElectronInventoryNullspaceError, MooseInputError) as exc:
        print("ISSUE45_INVENTORY_NULLSPACE_PREFLIGHT: HOLD")
        print("ISSUE45_INVENTORY_NULLSPACE_CLASS: HARNESS_OR_CONSTRUCTION_FAIL")
        print(f"ISSUE45_INVENTORY_NULLSPACE_REASON: {exc}")
        return 2


if __name__ == "__main__":
    import sys

    raise SystemExit(main(sys.argv[1:]))
