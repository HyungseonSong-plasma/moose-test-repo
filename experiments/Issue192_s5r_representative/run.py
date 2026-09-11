#!/usr/bin/env python3
"""User-local Stage-5 S5-R representative runtime/evidence harness for issue #192.

This surface executes the canonical representative assembly with the user's real
``physics-opt``. It runs the frozen baseline timestep and a half-timestep case
to expose obvious source-stiffness/timestep sensitivity. A successful invocation
produces governed evidence; it does not by itself declare Stage-5 acceptance or
Integrated Physics Accuracy.
"""
from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import json
import math
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.Issue31_r4_q0_all_ground import run as q0_run  # noqa: E402
from experiments.Issue31_r4_qn0_all_ground import run as qn0_run  # noqa: E402
from experiments.historical_recipe_support.issue31_r4_qf1 import (  # noqa: E402
    CHARGED_HEAVY_C2,
)
from experiments.historical_recipe_support.issue192_s5r import (  # noqa: E402
    ADMITTED_CHANNELS,
    AVOGADRO,
    DEFERRED_TOKENS,
    MOLAR_MASS,
    PROGRESS,
    RATE_TABLES,
    audit_s5r_input,
    build_s5r_input,
)
from physics_harness.adapters.moose import blocks as mb  # noqa: E402
from physics_harness.adapters.moose import parameters as mp  # noqa: E402
from physics_harness.adapters.moose.nonlinear_solver import (  # noqa: E402
    failure_signature,
    runtime_core_facts,
)
from physics_harness.evidence import (  # noqa: E402
    create_collision_safe_directory,
    utc_timestamp,
    write_json_bundle,
)
from physics_harness.execution.cases import (  # noqa: E402
    stage_case,
    validate_case_references,
)
from physics_harness.execution.runtime import (  # noqa: E402
    resolve_executable,
    resolve_results_root,
    run_physics,
    validate_executable,
)

SOURCE = ROOT / "experiments/Issue91_real_qvt_r3/r3_e0"
ELECTRON_DATA = ROOT / "physics_app/data/electron_impact"
HEAVY_DATA = ROOT / "physics_app/data/heavy_reactions"

BASELINE_DT_S = 1.0e-4
HALF_DT_S = 5.0e-5
END_TIME_S = 5.0e-4
LOOKUP_MIN_EV = 1.40991
LOOKUP_MAX_EV = 22.1378
ELEMENTARY_CHARGE_C = 1.602176634e-19

# Reuse already-accepted numerical bookkeeping envelopes; do not invent a new
# science threshold in the first representative runtime.
SPECIES_BALANCE_REL_TOL = 0.05
CONSTRAINED_O2_BALANCE_REL_TOL = 0.12
TOTAL_BALANCE_REL_TOL = 0.08
GENERIC_COUPLED_BALANCE_REL_TOL = 0.12
SUM_W_ABS_TOL = 1.0e-10
SPECIES_BOUND_TOL = 1.0e-10
MASS_PARTITION_REL_TOL = 2.0e-8
MAX_GAUSS_RELATIVE_DEFECT = 1.0e-3
MAX_C2_CARRIER_SCALED_DEFECT = 1.0e-10

ALL_HEAVY = ("O2", "O2s", "O2p", "O", "Om", "Op", "Os")
SOLVED_HEAVY = ("O2s", "O2p", "O", "Om", "Op", "Os")
OXYGEN_ATOMS = {"O2": 2, "O2s": 2, "O2p": 2, "O": 1, "Om": 1, "Op": 1, "Os": 1}
HEAVY_CHARGE = {"O2": 0, "O2s": 0, "O2p": 1, "O": 0, "Om": -1, "Op": 1, "Os": 0}

# Full representative stoichiometry used only for evidence reconstruction.
# Production ownership stays in issue192_s5r.py.
FULL_HEAVY_STOICH: dict[str, dict[str, int]] = {
    "EI01": {"O2": -1, "O": 1, "Om": 1},
    "EI02": {},
    "EI10": {"O2": -1, "O2s": 1},
    "EI16": {"O2": -1, "O2p": 1},
    "EI17": {},
    "EI19": {},
    "EI18_O_TO_OS": {"O": -1, "Os": 1},
    "EI20_O_IONIZATION": {"O": -1, "Op": 1},
    "EDETACH_OM": {"Om": -1, "O": 1},
    "H01_OP_O2_CHARGE_TRANSFER": {"Op": -1, "O2": -1, "O": 1, "O2p": 1},
    "H02_OM_OP_NEUTRALIZATION": {"Om": -1, "Op": -1, "O": 2},
    "H03_OM_O2P_TO_3O": {"Om": -1, "O2p": -1, "O": 3},
    "H04_OM_O2P_TO_O_O2": {"Om": -1, "O2p": -1, "O": 1, "O2": 1},
    "H05_OM_O_DETACHMENT": {"Om": -1, "O": -1, "O2": 1},
}

ENERGY_CHANNELS = (
    "EI10",
    "EI16",
    "EI19",
    "EI18_O_TO_OS",
    "EI20_O_IONIZATION",
    "EDETACH_OM",
)
CASE_SPECS = (("baseline", BASELINE_DT_S), ("half_dt", HALF_DT_S))


class S5RRuntimeError(RuntimeError):
    pass


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _repo_head() -> str | None:
    proc = subprocess.run(
        ["git", "-C", str(ROOT), "rev-parse", "HEAD"],
        text=True,
        capture_output=True,
        check=False,
    )
    return proc.stdout.strip() if proc.returncode == 0 else None


def _num(row: dict[str, str], key: str) -> float:
    if key not in row:
        raise S5RRuntimeError(f"missing CSV column {key}")
    try:
        value = float(row[key])
    except (TypeError, ValueError) as exc:
        raise S5RRuntimeError(f"invalid {key}={row.get(key)!r}") from exc
    if not math.isfinite(value):
        raise S5RRuntimeError(f"non-finite {key}={value}")
    return value


def _rel_defect(lhs: float, rhs: float, *scales: float) -> float:
    scale = max(abs(lhs), abs(rhs), *(abs(value) for value in scales), 1.0e-300)
    return abs(lhs - rhs) / scale


def _insert_runtime_observables(text: str) -> str:
    observables = (
        (
            "s5r_n_epsilon_inventory",
            "ADElementIntegralFunctorPostprocessor",
            "n_epsilon",
            "",
        ),
        (
            "s5r_mean_en_avg",
            "ElementAverageFunctorPostprocessor",
            "mean_en_solved",
            "",
        ),
        (
            "s5r_ei02_elastic_energy_avg",
            "ElementAverageFunctorPostprocessor",
            "S_ei02_elastic_hat",
            "",
        ),
        (
            "s5r_ei17_elastic_energy_avg",
            "ElementAverageFunctorPostprocessor",
            "S_ei17_elastic_hat",
            "",
        ),
    )
    for name, typ, functor, extra in observables:
        mb.require_absent(text, f"Postprocessors/{name}")
        text = mb.insert_child_block(
            text,
            "Postprocessors",
            f"""  [{name}]
    type = {typ}
    functor = {functor}{extra}
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []""",
        )
    return text


def _runtime_input(dt_s: float) -> tuple[str, dict[str, Any]]:
    if dt_s <= 0.0:
        raise S5RRuntimeError("runtime timestep must be positive")
    base = (SOURCE / "heavy_base.i").read_text()
    text, meta = build_s5r_input(base)
    if audit_s5r_input(text)["status"] != "PASS":
        raise S5RRuntimeError("canonical S5-R assembly audit is not PASS")

    text = mp.upsert_parameter(text, "Executioner", "dt", f"{dt_s:.17g}")
    text = mp.upsert_parameter(text, "Executioner", "end_time", f"{END_TIME_S:.17g}")
    text = mp.upsert_parameter(
        text,
        "Postprocessors/r31_charge_integral",
        "execute_on",
        "'INITIAL TIMESTEP_END'",
    )
    text = _insert_runtime_observables(text)

    post_audit = audit_s5r_input(text)
    if post_audit["status"] != "PASS":
        raise S5RRuntimeError(
            f"runtime observables changed S5-R semantics: {post_audit['failed_checks']}"
        )
    for token in DEFERRED_TOKENS:
        if token in text:
            raise S5RRuntimeError(f"deferred channel leaked into runtime input: {token}")

    meta = copy.deepcopy(meta)
    meta["runtime_evidence_surface"] = {
        "dt_s": dt_s,
        "end_time_s": END_TIME_S,
        "representative_runtime_claim": False,
        "wall_see_physics_enabled": False,
    }
    return text, meta


def _copy_runtime_assets(case_dir: Path) -> None:
    for name in sorted(set(RATE_TABLES.values())):
        shutil.copy2(ELECTRON_DATA / name, case_dir / name)
    for name in ("stage5_s5d_oxygen_heavy.txt", "stage5_s5e_h05_oxygen_heavy.txt"):
        shutil.copy2(HEAVY_DATA / name, case_dir / name)


def _stage(target: Path, *, dt_s: float) -> dict[str, Any]:
    text, meta = _runtime_input(dt_s)
    staging = stage_case(
        SOURCE,
        target,
        input_text=text,
        purge_directory_names=(".jitcache", "checkpoint", "checkpoints"),
        purge_patterns=(
            "input_out*",
            "*.log",
            "*.e",
            "*.exo",
            "prepare_evidence.json",
        ),
    )
    _copy_runtime_assets(target)
    references = validate_case_references(target)
    (target / "prepare_evidence.json").write_text(
        json.dumps(meta, indent=2, sort_keys=True) + "\n"
    )
    return {
        "staging": staging,
        "construction": meta,
        "referenced_files": references,
        "dt_s": dt_s,
        "end_time_s": END_TIME_S,
    }


def _read_rows(csv_path: Path) -> list[dict[str, str]]:
    if not csv_path.is_file():
        raise S5RRuntimeError(f"missing runtime CSV: {csv_path}")
    with csv_path.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) < 2:
        raise S5RRuntimeError("runtime CSV needs INITIAL and physical rows")
    return rows


def _write_physical_csv(case_dir: Path, rows: list[dict[str, str]]) -> Path:
    physical = [row for row in rows if _num(row, "time") > 1.0e-15]
    if not physical:
        raise S5RRuntimeError("no positive-time rows in runtime CSV")
    target = case_dir / "input_out.physical.csv"
    fieldnames = list(rows[0])
    with target.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(physical)
    return target


def _progress(row: dict[str, str], channel: str) -> float:
    return _num(row, f"s5r_progress_{channel.lower()}")


def _species_source_density(row: dict[str, str], species: str) -> float:
    total = 0.0
    for channel, stoich in FULL_HEAVY_STOICH.items():
        nu = stoich.get(species, 0)
        if nu:
            total += MOLAR_MASS[species] * nu * _progress(row, channel)
    return total


def _source_invariants(row: dict[str, str]) -> dict[str, float]:
    heavy_mass = 0.0
    oxygen_molar_atoms = 0.0
    heavy_charge_molar = 0.0
    scale_mass = 0.0
    scale_oxygen = 0.0
    scale_charge = 0.0
    for channel, stoich in FULL_HEAVY_STOICH.items():
        rate = _progress(row, channel)
        for species, nu in stoich.items():
            molar_term = nu * rate
            mass_term = MOLAR_MASS[species] * molar_term
            oxygen_term = OXYGEN_ATOMS[species] * molar_term
            charge_term = HEAVY_CHARGE[species] * molar_term
            heavy_mass += mass_term
            oxygen_molar_atoms += oxygen_term
            heavy_charge_molar += charge_term
            scale_mass += abs(mass_term)
            scale_oxygen += abs(oxygen_term)
            scale_charge += abs(charge_term)

    electron_molar = _num(row, "s5r_electron_source_avg") / AVOGADRO
    charge_closure = heavy_charge_molar - electron_molar
    scale_charge += abs(electron_molar)
    return {
        "heavy_mass_source_kg_m3_s": heavy_mass,
        "heavy_mass_relative_closure": abs(heavy_mass) / max(scale_mass, 1.0e-300),
        "oxygen_atom_source_mol_m3_s": oxygen_molar_atoms,
        "oxygen_atom_relative_closure": abs(oxygen_molar_atoms)
        / max(scale_oxygen, 1.0e-300),
        "charge_equivalent_source_mol_m3_s": charge_closure,
        "charge_relative_closure": abs(charge_closure)
        / max(scale_charge, 1.0e-300),
    }


def _energy_coefficients(input_text: str) -> dict[str, float]:
    result: dict[str, float] = {}
    for channel in ENERGY_CHANNELS:
        path = f"FVKernels/s5r_energy_{channel.lower()}"
        if mp.get_parameter(input_text, path, "v") != PROGRESS[channel]:
            raise S5RRuntimeError(f"energy projector does not consume canonical progress: {channel}")
        result[channel] = float(mp.get_parameter(input_text, path, "coef"))
    return result


def _energy_source_density(
    row: dict[str, str],
    energy_coefficients: dict[str, float],
) -> float:
    total = _num(row, "s5r_ei02_elastic_energy_avg")
    total += _num(row, "s5r_ei17_elastic_energy_avg")
    for channel, coefficient in energy_coefficients.items():
        total += coefficient * _progress(row, channel)
    return total


def _state_evidence(rows: list[dict[str, str]]) -> dict[str, Any]:
    hard_failures: list[str] = []
    mass_partition_max = 0.0
    source_closure = {
        "heavy_mass_relative": 0.0,
        "oxygen_relative": 0.0,
        "charge_relative": 0.0,
    }

    for row in rows:
        sum_error = max(
            abs(_num(row, "sum_w_min") - 1.0),
            abs(_num(row, "sum_w_max") - 1.0),
        )
        if sum_error > SUM_W_ABS_TOL:
            hard_failures.append(f"sum(w) closure {sum_error:.6e} at t={_num(row, 'time'):.6e}")

        species_mass_sum = 0.0
        for species in ALL_HEAVY:
            low = _num(row, f"w_{species}_min")
            high = _num(row, f"w_{species}_max")
            if low < -SPECIES_BOUND_TOL or high > 1.0 + SPECIES_BOUND_TOL or high < low:
                hard_failures.append(
                    f"{species} bounds [{low:.6e}, {high:.6e}] at t={_num(row, 'time'):.6e}"
                )
            species_mass_sum += _num(row, f"mass_{species}")
        total_mass = _num(row, "mass_total")
        partition = abs(species_mass_sum - total_mass) / max(abs(total_mass), 1.0e-300)
        mass_partition_max = max(mass_partition_max, partition)
        if partition > MASS_PARTITION_REL_TOL:
            hard_failures.append(
                f"mass partition rel={partition:.6e} at t={_num(row, 'time'):.6e}"
            )

        if _num(row, "n_e_min") < 0.0:
            hard_failures.append(f"negative electron density at t={_num(row, 'time'):.6e}")
        if _num(row, "s5r_n_epsilon_min") <= 0.0:
            hard_failures.append(f"non-positive electron energy at t={_num(row, 'time'):.6e}")
        mean_low = _num(row, "s5r_mean_en_min")
        mean_high = _num(row, "s5r_mean_en_max")
        if (
            mean_low < LOOKUP_MIN_EV
            or mean_high > LOOKUP_MAX_EV
            or mean_high < mean_low
        ):
            hard_failures.append(
                f"mean energy outside strict lookup domain [{mean_low:.6e}, {mean_high:.6e}]"
            )

        for channel in ADMITTED_CHANNELS:
            rate = _progress(row, channel)
            if rate < 0.0:
                hard_failures.append(
                    f"negative canonical progress {channel}={rate:.6e}"
                )

        closure = _source_invariants(row)
        source_closure["heavy_mass_relative"] = max(
            source_closure["heavy_mass_relative"],
            closure["heavy_mass_relative_closure"],
        )
        source_closure["oxygen_relative"] = max(
            source_closure["oxygen_relative"],
            closure["oxygen_atom_relative_closure"],
        )
        source_closure["charge_relative"] = max(
            source_closure["charge_relative"],
            closure["charge_relative_closure"],
        )

    return {
        "status": "MEASURED",
        "hard_pass": not hard_failures,
        "hard_failures": hard_failures,
        "mass_partition_max_relative": mass_partition_max,
        "source_level_closure": source_closure,
        "mean_energy_domain_eV": [LOOKUP_MIN_EV, LOOKUP_MAX_EV],
    }


def _discrete_balances(
    rows: list[dict[str, str]],
    *,
    energy_coefficients: dict[str, float],
) -> dict[str, Any]:
    species_max = {species: 0.0 for species in ALL_HEAVY}
    total_max = 0.0
    electron_max = 0.0
    energy_max = 0.0
    c2_component_max = 0.0
    c2_carrier_max = 0.0
    per_step: list[dict[str, Any]] = []

    for previous, current in zip(rows[:-1], rows[1:]):
        t0 = _num(previous, "time")
        t1 = _num(current, "time")
        dt = t1 - t0
        if dt <= 0.0:
            raise S5RRuntimeError(f"non-positive runtime dt={dt}")
        volume = _num(current, "domain_volume")
        if volume <= 0.0:
            raise S5RRuntimeError("non-positive plasma domain volume")

        current_species: dict[str, Any] = {}
        for species in ALL_HEAVY:
            accumulation = (
                _num(current, f"mass_{species}")
                - _num(previous, f"mass_{species}")
            ) / dt
            inlet = _num(current, "inlet_mdot") if species == "O2" else 0.0
            outlet = _num(current, f"outlet_mdot_{species}")
            reaction = volume * _species_source_density(current, species)
            rhs = inlet - outlet + reaction
            defect = _rel_defect(accumulation, rhs, inlet, outlet, reaction)
            species_max[species] = max(species_max[species], defect)
            current_species[species] = {
                "accumulation_kg_s": accumulation,
                "inlet_kg_s": inlet,
                "outlet_kg_s": outlet,
                "reaction_kg_s": reaction,
                "rhs_kg_s": rhs,
                "relative_defect": defect,
            }

        total_accumulation = (
            _num(current, "mass_total") - _num(previous, "mass_total")
        ) / dt
        total_rhs = _num(current, "inlet_mdot") - _num(current, "outlet_mass_actual")
        total_defect = _rel_defect(
            total_accumulation,
            total_rhs,
            _num(current, "inlet_mdot"),
            _num(current, "outlet_mass_actual"),
        )
        total_max = max(total_max, total_defect)

        electron_accumulation = (
            _num(current, "n_e_inventory") - _num(previous, "n_e_inventory")
        ) / dt
        electron_rhs = _num(current, "s5r_electron_source_avg") * volume
        electron_defect = _rel_defect(electron_accumulation, electron_rhs)
        electron_max = max(electron_max, electron_defect)

        energy_accumulation = (
            _num(current, "s5r_n_epsilon_inventory")
            - _num(previous, "s5r_n_epsilon_inventory")
        ) / dt
        energy_rhs = _energy_source_density(current, energy_coefficients) * volume
        energy_defect = _rel_defect(energy_accumulation, energy_rhs)
        energy_max = max(energy_max, energy_defect)

        total_boundary_current = 0.0
        species_current: dict[str, float] = {}
        for species, contract in CHARGED_HEAVY_C2.items():
            inlet_mdot = 0.0
            outlet_mdot = _num(current, f"outlet_mdot_{species}")
            outward_mass_rate = outlet_mdot - inlet_mdot
            current_amp = (
                ELEMENTARY_CHARGE_C
                * int(contract["z"])
                * outward_mass_rate
                * AVOGADRO
                / float(contract["molar_mass_kg_per_mol"])
            )
            species_current[species] = current_amp
            total_boundary_current += current_amp
        delta_q = _num(current, "r31_charge_integral") - _num(
            previous, "r31_charge_integral"
        )
        q_boundary = dt * total_boundary_current
        charge_residual = delta_q + q_boundary
        component_scale = max(abs(delta_q), abs(q_boundary), 1.0e-300)
        carrier_scale = max(
            ELEMENTARY_CHARGE_C * _num(current, "n_e_inventory"),
            1.0e-300,
        )
        c2_component = abs(charge_residual) / component_scale
        c2_carrier = abs(charge_residual) / carrier_scale
        c2_component_max = max(c2_component_max, c2_component)
        c2_carrier_max = max(c2_carrier_max, c2_carrier)

        per_step.append(
            {
                "time_initial_s": t0,
                "time_final_s": t1,
                "dt_s": dt,
                "species": current_species,
                "total_mass_relative_defect": total_defect,
                "electron_particle_relative_defect": electron_defect,
                "electron_energy_relative_defect": energy_defect,
                "charge": {
                    "delta_Q_C": delta_q,
                    "outward_boundary_current_C_s": total_boundary_current,
                    "boundary_charge_C": q_boundary,
                    "residual_C": charge_residual,
                    "component_relative_defect": c2_component,
                    "carrier_scaled_defect": c2_carrier,
                    "species_boundary_current_C_s": species_current,
                },
            }
        )

    hard_gates = {
        "species_balance": all(
            defect
            <= (
                CONSTRAINED_O2_BALANCE_REL_TOL
                if species == "O2"
                else SPECIES_BALANCE_REL_TOL
            )
            for species, defect in species_max.items()
        ),
        "total_mass_balance": total_max <= TOTAL_BALANCE_REL_TOL,
        "electron_particle_balance": electron_max <= GENERIC_COUPLED_BALANCE_REL_TOL,
        "electron_energy_balance": energy_max <= GENERIC_COUPLED_BALANCE_REL_TOL,
        "global_charge_c2": c2_carrier_max <= MAX_C2_CARRIER_SCALED_DEFECT,
    }
    return {
        "status": "MEASURED",
        "species_max_relative_defect": species_max,
        "total_mass_max_relative_defect": total_max,
        "electron_particle_max_relative_defect": electron_max,
        "electron_energy_max_relative_defect": energy_max,
        "charge_component_max_relative_defect": c2_component_max,
        "charge_carrier_scaled_max_defect": c2_carrier_max,
        "hard_gates": hard_gates,
        "hard_pass": all(hard_gates.values()),
        "tolerances": {
            "species_non_O2": SPECIES_BALANCE_REL_TOL,
            "constrained_O2": CONSTRAINED_O2_BALANCE_REL_TOL,
            "total_mass": TOTAL_BALANCE_REL_TOL,
            "electron_particle": GENERIC_COUPLED_BALANCE_REL_TOL,
            "electron_energy": GENERIC_COUPLED_BALANCE_REL_TOL,
            "global_charge_carrier_scaled": MAX_C2_CARRIER_SCALED_DEFECT,
        },
        "steps": per_step,
    }


def _endpoint(row: dict[str, str]) -> dict[str, float]:
    keys = [
        "mass_total",
        "n_e_inventory",
        "r31_charge_integral",
        "n_e_avg",
        "s5r_n_epsilon_inventory",
        "s5r_mean_en_avg",
    ]
    keys.extend(f"w_{species}_avg" for species in ALL_HEAVY)
    return {key: _num(row, key) for key in keys}


def _timestep_sensitivity(
    baseline: dict[str, float],
    half_dt: dict[str, float],
) -> dict[str, Any]:
    comparison = {}
    for key in baseline:
        a = baseline[key]
        b = half_dt[key]
        comparison[key] = {
            "baseline": a,
            "half_dt": b,
            "symmetric_relative_difference": abs(a - b)
            / max(abs(a), abs(b), 1.0e-300),
        }
    return {
        "status": "MEASURED_UNTHRESHOLDED",
        "reason": (
            "first representative S5-R measurement: report endpoint sensitivity "
            "without inventing a new scientific convergence threshold"
        ),
        "comparison": comparison,
    }


def _runtime(
    executable: Path,
    case_dir: Path,
    log: Path,
    *,
    timeout: float,
) -> dict[str, Any]:
    result = run_physics(
        executable,
        cwd=case_dir,
        input_name="input.i",
        log_path=log,
        extra_args=("-snes_monitor", "-snes_converged_reason", "-ksp_converged_reason"),
        timeout_seconds=timeout,
    )
    text = log.read_text(errors="replace")
    return {
        "returncode": result.returncode,
        "wall_seconds": result.wall_seconds,
        "timed_out": result.timed_out,
        "failure_signature": failure_signature(text),
        "runtime_facts": runtime_core_facts(
            text,
            returncode=result.returncode,
            coupled_scaling_variables=("n_e", "n_epsilon"),
        ),
        "log": str(log),
    }


def _p2(
    executable: Path,
    case_dir: Path,
    log: Path,
    *,
    timeout: float,
) -> dict[str, Any]:
    result = run_physics(
        executable,
        cwd=case_dir,
        input_name="input.i",
        log_path=log,
        extra_args=("--check-input",),
        timeout_seconds=timeout,
    )
    return {
        "returncode": result.returncode,
        "wall_seconds": result.wall_seconds,
        "timed_out": result.timed_out,
        "log": str(log),
    }


def _analyze_case(
    case_dir: Path,
    *,
    input_text: str,
) -> dict[str, Any]:
    rows = _read_rows(case_dir / "input_out.csv")
    physical_path = _write_physical_csv(case_dir, rows)
    physical_rows = [row for row in rows if _num(row, "time") > 1.0e-15]
    state = _state_evidence(physical_rows)
    balances = _discrete_balances(
        rows,
        energy_coefficients=_energy_coefficients(input_text),
    )
    gauss = q0_run._gauss_evidence(physical_path)
    electrostatic_state = qn0_run._state_evidence(physical_path)
    gauss_pass = (
        gauss.get("status") == "MEASURED"
        and float(gauss["relative_defect"]) <= MAX_GAUSS_RELATIVE_DEFECT
    )
    evidence_pass = (
        state["hard_pass"]
        and balances["hard_pass"]
        and gauss_pass
        and electrostatic_state.get("status") == "MEASURED"
    )
    return {
        "state": state,
        "balances": balances,
        "gauss_law": gauss,
        "gauss_gate": {
            "max_relative_defect": MAX_GAUSS_RELATIVE_DEFECT,
            "pass": gauss_pass,
        },
        "electrostatic_state": electrostatic_state,
        "endpoint": _endpoint(physical_rows[-1]),
        "hard_pass": evidence_pass,
    }


def _synthetic_rows(dt_s: float) -> list[dict[str, str]]:
    fractions = {
        "O2": 0.70,
        "O2s": 0.05,
        "O2p": 0.01,
        "O": 0.10,
        "Om": 0.01,
        "Op": 0.01,
        "Os": 0.12,
    }
    rows: list[dict[str, str]] = []
    for step in range(3):
        row: dict[str, str] = {
            "time": str(step * dt_s),
            "domain_volume": "1",
            "mass_total": "1",
            "inlet_mdot": "1e-6",
            "outlet_mass_actual": "1e-6",
            "sum_w_min": "1",
            "sum_w_max": "1",
            "n_e_min": "1e16",
            "n_e_avg": "1e16",
            "n_e_inventory": "1e16",
            "s5r_n_epsilon_min": "1",
            "s5r_n_epsilon_inventory": "1",
            "s5r_mean_en_min": "5.73276",
            "s5r_mean_en_max": "5.73276",
            "s5r_mean_en_avg": "5.73276",
            "s5r_electron_source_avg": "0",
            "s5r_ei02_elastic_energy_avg": "0",
            "s5r_ei17_elastic_energy_avg": "0",
            "r31_charge_integral": "0",
        }
        for species, fraction in fractions.items():
            row[f"w_{species}_avg"] = str(fraction)
            row[f"w_{species}_min"] = str(fraction)
            row[f"w_{species}_max"] = str(fraction)
            row[f"mass_{species}"] = str(fraction)
            row[f"outlet_mdot_{species}"] = "1e-6" if species == "O2" else "0"
        for channel in ADMITTED_CHANNELS:
            row[f"s5r_progress_{channel.lower()}"] = "0"
        rows.append(row)
    return rows


def self_test() -> None:
    assert set(FULL_HEAVY_STOICH) == set(ADMITTED_CHANNELS)
    baseline_text, _ = _runtime_input(BASELINE_DT_S)
    half_text, _ = _runtime_input(HALF_DT_S)
    assert math.isclose(
        float(mp.get_parameter(baseline_text, "Executioner", "dt")),
        BASELINE_DT_S,
    )
    assert math.isclose(
        float(mp.get_parameter(half_text, "Executioner", "dt")),
        HALF_DT_S,
    )
    for text in (baseline_text, half_text):
        assert audit_s5r_input(text)["status"] == "PASS"
        assert mp.get_parameter(
            text, "Postprocessors/r31_charge_integral", "execute_on"
        ) == "'INITIAL TIMESTEP_END'"
        assert mb.has_block(text, "Postprocessors/s5r_n_epsilon_inventory")
        assert mb.has_block(text, "Postprocessors/s5r_mean_en_avg")
        for token in DEFERRED_TOKENS:
            assert token not in text

    rows = _synthetic_rows(BASELINE_DT_S)
    state = _state_evidence(rows[1:])
    balances = _discrete_balances(
        rows,
        energy_coefficients={channel: -1.0 for channel in ENERGY_CHANNELS},
    )
    assert state["hard_pass"]
    assert balances["hard_pass"]

    negative = copy.deepcopy(rows)
    negative[-1]["w_Om_min"] = "-0.1"
    assert not _state_evidence(negative[1:])["hard_pass"]

    broken_species = copy.deepcopy(rows)
    broken_species[-1]["mass_O"] = "0.2"
    assert not _discrete_balances(
        broken_species,
        energy_coefficients={channel: -1.0 for channel in ENERGY_CHANNELS},
    )["hard_pass"]

    broken_electron = copy.deepcopy(rows)
    broken_electron[-1]["n_e_inventory"] = "1.1e16"
    assert not _discrete_balances(
        broken_electron,
        energy_coefficients={channel: -1.0 for channel in ENERGY_CHANNELS},
    )["hard_pass"]

    broken_energy = copy.deepcopy(rows)
    broken_energy[-1]["s5r_n_epsilon_inventory"] = "1.1"
    assert not _discrete_balances(
        broken_energy,
        energy_coefficients={channel: -1.0 for channel in ENERGY_CHANNELS},
    )["hard_pass"]

    print("S5R_REPRESENTATIVE_RUNTIME_HARNESS_SELFTEST_PASS")
    print("representative_runtime=NOT_EXECUTED")


def run(args: argparse.Namespace) -> int:
    executable = resolve_executable(args.physics)
    validate_executable(executable)
    results_root = resolve_results_root(executable, args.results_root)
    results_root.mkdir(parents=True, exist_ok=True)

    stamp = utc_timestamp().replace(":", "").replace("-", "")
    root = create_collision_safe_directory(
        results_root,
        f"issue192_s5r_representative_{stamp}",
    )
    cases_root = root / "cases"
    logs = root / "logs"
    cases_root.mkdir(parents=True, exist_ok=True)
    logs.mkdir(parents=True, exist_ok=True)

    summary: dict[str, Any] = {
        "schema_version": 1,
        "issue": 192,
        "stage": "STAGE_5_S5_R",
        "experiment": "s5r-representative-production-chemistry",
        "repository_head": _repo_head(),
        "physics_opt_realpath": str(executable.resolve()),
        "physics_opt_sha256": _sha256(executable),
        "claim_boundary": {
            "on_green": "Stage-5 S5-R representative coupled chemistry evidence ready for review",
            "not_automatic": [
                "Stage-5 acceptance",
                "Integrated Physics Accuracy",
            ],
        },
        "cases": {},
        "timestep_sensitivity": {},
        "status": "NOT_RUN",
    }

    staged: dict[str, dict[str, Any]] = {}
    input_texts: dict[str, str] = {}
    for case_name, dt_s in CASE_SPECS:
        case_dir = cases_root / case_name
        staged[case_name] = _stage(case_dir, dt_s=dt_s)
        input_texts[case_name] = (case_dir / "input.i").read_text()
        summary["cases"][case_name] = {
            "dt_s": dt_s,
            "end_time_s": END_TIME_S,
            "staged": staged[case_name],
            "p2": {},
            "runtime": {},
            "evidence": {},
        }

    # Fail-fast before representative runtime if either exact staged input does not parse.
    for case_name, _ in CASE_SPECS:
        case_dir = cases_root / case_name
        p2 = _p2(
            executable,
            case_dir,
            logs / f"{case_name}_p2.log",
            timeout=args.timeout,
        )
        summary["cases"][case_name]["p2"] = p2
        if p2["returncode"] != 0:
            summary["status"] = f"P2_FAIL_{case_name.upper()}"
            write_json_bundle(root, {"summary": ("summary.json", summary)})
            print(f"S5R_REPRESENTATIVE_ROOT: {root}")
            print(f"S5R_REPRESENTATIVE_STATUS: {summary['status']}")
            return 2

    runtime_success: dict[str, bool] = {}
    for case_name, _ in CASE_SPECS:
        case_dir = cases_root / case_name
        runtime = _runtime(
            executable,
            case_dir,
            logs / f"{case_name}_runtime.log",
            timeout=args.timeout,
        )
        summary["cases"][case_name]["runtime"] = runtime
        runtime_success[case_name] = runtime["returncode"] == 0
        if runtime_success[case_name]:
            try:
                evidence = _analyze_case(
                    case_dir,
                    input_text=input_texts[case_name],
                )
            except (S5RRuntimeError, AssertionError, KeyError, ValueError) as exc:
                evidence = {
                    "hard_pass": False,
                    "analysis_error": str(exc),
                }
            summary["cases"][case_name]["evidence"] = evidence

    if not runtime_success.get("baseline", False):
        summary["status"] = (
            "TIMESTEP_OR_SOURCE_STIFFNESS_EVIDENCE_READY"
            if runtime_success.get("half_dt", False)
            else "REPRESENTATIVE_RUNTIME_FAIL_BOTH_TIMESTEPS"
        )
        write_json_bundle(root, {"summary": ("summary.json", summary)})
        print(f"S5R_REPRESENTATIVE_ROOT: {root}")
        print(f"S5R_REPRESENTATIVE_STATUS: {summary['status']}")
        print(f"S5R_REPRESENTATIVE_SUMMARY: {root / 'summary.json'}")
        return 1

    if not runtime_success.get("half_dt", False):
        summary["status"] = "HALF_DT_RUNTIME_FAIL"
        write_json_bundle(root, {"summary": ("summary.json", summary)})
        print(f"S5R_REPRESENTATIVE_ROOT: {root}")
        print(f"S5R_REPRESENTATIVE_STATUS: {summary['status']}")
        print(f"S5R_REPRESENTATIVE_SUMMARY: {root / 'summary.json'}")
        return 1

    baseline_evidence = summary["cases"]["baseline"]["evidence"]
    half_evidence = summary["cases"]["half_dt"]["evidence"]
    if not baseline_evidence.get("hard_pass") or not half_evidence.get("hard_pass"):
        summary["status"] = "REPRESENTATIVE_RUNTIME_INVARIANT_FAIL"
        write_json_bundle(root, {"summary": ("summary.json", summary)})
        print(f"S5R_REPRESENTATIVE_ROOT: {root}")
        print(f"S5R_REPRESENTATIVE_STATUS: {summary['status']}")
        print(f"S5R_REPRESENTATIVE_SUMMARY: {root / 'summary.json'}")
        return 1

    summary["timestep_sensitivity"] = _timestep_sensitivity(
        baseline_evidence["endpoint"],
        half_evidence["endpoint"],
    )
    summary["status"] = "S5R_REPRESENTATIVE_EVIDENCE_READY"
    write_json_bundle(root, {"summary": ("summary.json", summary)})
    print(f"S5R_REPRESENTATIVE_ROOT: {root}")
    print(f"S5R_REPRESENTATIVE_STATUS: {summary['status']}")
    print("S5R_REPRESENTATIVE_TIMESTEP_SENSITIVITY: MEASURED_UNTHRESHOLDED")
    print(f"S5R_REPRESENTATIVE_SUMMARY: {root / 'summary.json'}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--physics", help="canonical user-local physics-opt")
    parser.add_argument("--results-root", type=Path)
    parser.add_argument("--timeout", type=float, default=900.0)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.timeout <= 0.0:
        parser.error("--timeout must be positive")
    if args.self_test:
        self_test()
        return 0
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
