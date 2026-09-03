#!/usr/bin/env python3
"""Run Issue #27 A1 prescribed-flux O -> 0.5 O2 wall discriminator.

This runner intentionally isolates finite-volume boundary-flux sign and the N-1
constrained-O2 bookkeeping contract. It does not implement a sticking law and
is not a reactor-scale validation.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
from typing import Any, Mapping

from qpx_harness.evidence import create_collision_safe_directory, utc_timestamp
from qpx_harness.execution.runtime import resolve_executable, run_qpx, validate_executable

ROOT = Path(__file__).resolve().parents[3]
SOURCE_INPUT = Path(__file__).with_name("input.i")

M_O_KG_PER_MOL = 0.016
M_O2_KG_PER_MOL = 0.032
DEFAULT_EVENT_FLUX_MOL_M2_S = 0.1
DEFAULT_DT_S = 0.1
DEFAULT_RHO_KG_M3 = 1.0
DEFAULT_INITIAL_W_O = 0.1

MAX_FLUX_RELATIVE_DEFECT = 1.0e-6
MAX_STOICH_RELATIVE_DEFECT = 1.0e-8
MAX_TOTAL_MASS_RELATIVE_DEFECT = 1.0e-10
MAX_O_ATOM_RELATIVE_DEFECT = 1.0e-10
MIN_ALLOWED_MASS_FRACTION = -1.0e-12


class Issue27A1Error(RuntimeError):
    pass


def _float_parameter(parameters: Mapping[str, Any], name: str, default: float) -> float:
    raw = parameters.get(name, default)
    try:
        value = float(raw)
    except (TypeError, ValueError) as exc:
        raise Issue27A1Error(f"parameters.{name} must be numeric") from exc
    if not math.isfinite(value):
        raise Issue27A1Error(f"parameters.{name} must be finite")
    return value


def _validated_parameters(parameters: Mapping[str, Any]) -> dict[str, float | str]:
    reaction_id = str(parameters.get("reaction_id", "O_to_half_O2"))
    if reaction_id != "O_to_half_O2":
        raise Issue27A1Error(
            "A1 controlled-wall runner currently accepts only reaction_id='O_to_half_O2'; "
            "extend the protocol only after A1 freezes the FVBC sign/bookkeeping contract"
        )
    event_flux = _float_parameter(
        parameters, "event_flux_mol_m2_s", DEFAULT_EVENT_FLUX_MOL_M2_S
    )
    dt = _float_parameter(parameters, "dt_seconds", DEFAULT_DT_S)
    rho = _float_parameter(parameters, "rho_kg_m3", DEFAULT_RHO_KG_M3)
    initial_w_o = _float_parameter(parameters, "initial_w_O", DEFAULT_INITIAL_W_O)
    if event_flux <= 0.0:
        raise Issue27A1Error("event_flux_mol_m2_s must be positive")
    if dt <= 0.0:
        raise Issue27A1Error("dt_seconds must be positive")
    if rho <= 0.0:
        raise Issue27A1Error("rho_kg_m3 must be positive")
    if not 0.0 < initial_w_o < 1.0:
        raise Issue27A1Error("initial_w_O must lie strictly between 0 and 1")
    return {
        "reaction_id": reaction_id,
        "event_flux_mol_m2_s": event_flux,
        "dt_seconds": dt,
        "rho_kg_m3": rho,
        "initial_w_O": initial_w_o,
        "initial_w_O2": 1.0 - initial_w_o,
        "outward_O_mass_flux_kg_m2_s": event_flux * M_O_KG_PER_MOL,
    }


def _replace_assignment(text: str, name: str, value: float) -> str:
    pattern = re.compile(rf"(?m)^(\s*{re.escape(name)}\s*=\s*)[^#\r\n]+")
    matches = list(pattern.finditer(text))
    if len(matches) != 1:
        raise Issue27A1Error(f"expected one top-level assignment for {name}, found {len(matches)}")
    match = matches[0]
    return text[: match.start()] + match.group(1) + f"{value:.17g}" + text[match.end() :]


def _stage(case_dir: Path, parameters: Mapping[str, Any]) -> dict[str, Any]:
    frozen = _validated_parameters(parameters)
    text = SOURCE_INPUT.read_text(encoding="utf-8")
    text = _replace_assignment(text, "rho_value", float(frozen["rho_kg_m3"]))
    text = _replace_assignment(text, "initial_w_O", float(frozen["initial_w_O"]))
    text = _replace_assignment(
        text, "wall_mass_flux_O", float(frozen["outward_O_mass_flux_kg_m2_s"])
    )
    text = _replace_assignment(text, "dt_value", float(frozen["dt_seconds"]))
    case_dir.mkdir(parents=True, exist_ok=False)
    (case_dir / "input.i").write_text(text, encoding="utf-8")
    (case_dir / "construction.json").write_text(
        json.dumps(frozen, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return frozen


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _repo_head() -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return result.stdout.strip() or None


def _run_stage(
    exe: Path,
    *,
    case_dir: Path,
    log_path: Path,
    timeout: float,
    check_input: bool,
) -> dict[str, Any]:
    extra = ("--check-input",) if check_input else (
        "-snes_monitor",
        "-snes_converged_reason",
        "-ksp_converged_reason",
    )
    result = run_qpx(
        exe,
        cwd=case_dir,
        input_name="input.i",
        log_path=log_path,
        extra_args=extra,
        timeout_seconds=timeout,
    )
    return {
        "returncode": result.returncode,
        "wall_seconds": result.wall_seconds,
        "timed_out": result.timed_out,
        "log": str(log_path),
    }


def _read_inventory(csv_path: Path, frozen: Mapping[str, Any]) -> dict[str, Any]:
    if not csv_path.is_file():
        return {"status": "MISSING", "error": f"missing {csv_path.name}"}
    with csv_path.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) < 2:
        return {"status": "MISSING", "error": "expected INITIAL and TIMESTEP_END CSV rows"}

    required = (
        "time",
        "wall_area",
        "O_mass",
        "O2_mass",
        "total_oxygen_mass",
        "w_O_min",
        "w_O2_min",
    )
    missing = [name for name in required if name not in rows[0] or name not in rows[-1]]
    if missing:
        return {"status": "MISSING", "error": f"missing CSV columns: {missing}"}
    try:
        initial = {name: float(rows[0][name]) for name in required}
        final = {name: float(rows[-1][name]) for name in required}
    except (TypeError, ValueError) as exc:
        return {"status": "INVALID", "error": str(exc)}

    dt = float(frozen["dt_seconds"])
    flux = float(frozen["outward_O_mass_flux_kg_m2_s"])
    area = final["wall_area"]
    expected_o_loss = flux * area * dt
    measured_o_loss = initial["O_mass"] - final["O_mass"]
    measured_o2_gain = final["O2_mass"] - initial["O2_mass"]
    scale = max(abs(expected_o_loss), 1.0e-300)

    flux_relative_defect = abs(measured_o_loss - expected_o_loss) / scale
    stoich_relative_defect = abs(measured_o_loss - measured_o2_gain) / scale
    initial_total = initial["total_oxygen_mass"]
    final_total = final["total_oxygen_mass"]
    total_mass_relative_defect = abs(final_total - initial_total) / max(abs(initial_total), 1.0e-300)

    initial_atom_mol = initial["O_mass"] / M_O_KG_PER_MOL + 2.0 * initial["O2_mass"] / M_O2_KG_PER_MOL
    final_atom_mol = final["O_mass"] / M_O_KG_PER_MOL + 2.0 * final["O2_mass"] / M_O2_KG_PER_MOL
    atom_relative_defect = abs(final_atom_mol - initial_atom_mol) / max(abs(initial_atom_mol), 1.0e-300)

    acceptance = {
        "positive_outward_flux_decreases_O": measured_o_loss > 0.0,
        "imposed_flux_closure": flux_relative_defect <= MAX_FLUX_RELATIVE_DEFECT,
        "O_to_half_O2_mass_stoichiometry": stoich_relative_defect <= MAX_STOICH_RELATIVE_DEFECT,
        "total_oxygen_mass_conservation": total_mass_relative_defect <= MAX_TOTAL_MASS_RELATIVE_DEFECT,
        "oxygen_atom_conservation": atom_relative_defect <= MAX_O_ATOM_RELATIVE_DEFECT,
        "nonnegative_mass_fractions": (
            final["w_O_min"] >= MIN_ALLOWED_MASS_FRACTION
            and final["w_O2_min"] >= MIN_ALLOWED_MASS_FRACTION
        ),
    }
    return {
        "status": "MEASURED",
        "initial": initial,
        "final": final,
        "expected_O_loss_kg": expected_o_loss,
        "measured_O_loss_kg": measured_o_loss,
        "measured_O2_gain_kg": measured_o2_gain,
        "flux_relative_defect": flux_relative_defect,
        "stoich_relative_defect": stoich_relative_defect,
        "total_mass_relative_defect": total_mass_relative_defect,
        "oxygen_atom_relative_defect": atom_relative_defect,
        "acceptance": acceptance,
        "pass": all(acceptance.values()),
    }


def run_controlled_wall(
    *,
    qpx: str | Path | None,
    results_root: Path,
    timeout: float,
    parameters: Mapping[str, Any],
) -> int:
    if timeout <= 0.0:
        raise Issue27A1Error("timeout must be positive")
    exe = resolve_executable(qpx)
    validate_executable(exe)
    stamp = utc_timestamp().replace(":", "").replace("-", "")
    root = create_collision_safe_directory(
        results_root,
        f"issue27_a1_o_recombination_{stamp}",
    )
    case_dir = root / "case"
    logs = root / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    frozen = _stage(case_dir, parameters)

    summary: dict[str, Any] = {
        "issue": 27,
        "experiment": "A1_o_recombination_prescribed_flux",
        "scientific_scope": "controlled FV wall-flux sign and constrained-O2 bookkeeping only",
        "repository_head": _repo_head(),
        "qpx_realpath": str(exe.resolve()),
        "qpx_sha256": _sha256(exe),
        "parameters": frozen,
        "tolerances": {
            "max_flux_relative_defect": MAX_FLUX_RELATIVE_DEFECT,
            "max_stoich_relative_defect": MAX_STOICH_RELATIVE_DEFECT,
            "max_total_mass_relative_defect": MAX_TOTAL_MASS_RELATIVE_DEFECT,
            "max_oxygen_atom_relative_defect": MAX_O_ATOM_RELATIVE_DEFECT,
            "min_allowed_mass_fraction": MIN_ALLOWED_MASS_FRACTION,
        },
        "p2": {},
        "runtime": {},
        "inventory": {},
        "status": "NOT_RUN",
    }

    summary["p2"] = _run_stage(
        exe,
        case_dir=case_dir,
        log_path=logs / "a1_p2.log",
        timeout=timeout,
        check_input=True,
    )
    if summary["p2"]["returncode"] != 0:
        summary["status"] = "A1_P2_FAIL"
        (root / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
        print(f"ISSUE27_A1_STATUS: {summary['status']}")
        print(f"EVIDENCE_DIR: {root}")
        return 2

    summary["runtime"] = _run_stage(
        exe,
        case_dir=case_dir,
        log_path=logs / "a1_runtime.log",
        timeout=timeout,
        check_input=False,
    )
    if summary["runtime"]["returncode"] != 0:
        summary["status"] = "A1_RUNTIME_FAIL"
        (root / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
        print(f"ISSUE27_A1_STATUS: {summary['status']}")
        print(f"EVIDENCE_DIR: {root}")
        return 1

    inventory = _read_inventory(case_dir / "input_out.csv", frozen)
    summary["inventory"] = inventory
    if inventory.get("status") != "MEASURED":
        summary["status"] = "A1_EVIDENCE_MISSING"
    elif inventory.get("pass") is True:
        summary["status"] = "A1_PASS_READY_FOR_STICKING_LAW"
    else:
        summary["status"] = "A1_EVIDENCE_READY_NOT_ACCEPTED"

    (root / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(f"ISSUE27_A1_STATUS: {summary['status']}")
    if inventory.get("status") == "MEASURED":
        print(f"O_LOSS_KG: {inventory['measured_O_loss_kg']}")
        print(f"O2_GAIN_KG: {inventory['measured_O2_gain_kg']}")
        print(f"FLUX_RELATIVE_DEFECT: {inventory['flux_relative_defect']}")
        print(f"STOICH_RELATIVE_DEFECT: {inventory['stoich_relative_defect']}")
        print(f"O_ATOM_RELATIVE_DEFECT: {inventory['oxygen_atom_relative_defect']}")
    print(f"EVIDENCE_DIR: {root}")
    return 0 if summary["status"] == "A1_PASS_READY_FOR_STICKING_LAW" else 1


__all__ = [
    "Issue27A1Error",
    "run_controlled_wall",
    "_validated_parameters",
]
