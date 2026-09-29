#!/usr/bin/env python3
"""Issue #357: current 10 mTorr Oxygen state/data on the real-QVT ICP geometry."""
from __future__ import annotations

import argparse
import csv
import json
import math
import re
from pathlib import Path
from statistics import fmean
from typing import Any

from experiments.Issue192_s5r_representative import run as s5r_run
from experiments.historical_recipe_support.issue192_s5r import (
    ENERGY_REFERENCE_EV,
    audit_s5r_input,
    build_s5r_input,
)
from physics_harness.adapters.moose import blocks as mb
from physics_harness.adapters.moose import parameters as mp
from physics_harness.execution.cases import stage_case, validate_case_references
from physics_harness.execution.runtime import resolve_executable, run_physics, validate_executable

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "experiments/Issue91_real_qvt_r3/r3_e0"
CANONICAL_HEAVY = ROOT / "physics_app/ci/plasma_closures_oxygen_transport.txt"
SMOKE_ELECTRON = ROOT / "physics_app/ci/plasma_closures_transport_table.txt"

PRESSURE_PA = 1.333223684
TG_K = 300.0
NREF_M3 = 1.0e16
DT_S = 5.6650790022617894e-11
NUM_STEPS = 8
END_TIME_S = DT_S * NUM_STEPS
CURRENT_MASS_FRACTIONS = {
    "O2": 0.99994,
    "O2s": 1.0e-5,
    "O2p": 1.0e-5,
    "O": 1.0e-5,
    "Om": 1.0e-5,
    "Op": 1.0e-5,
    "Os": 1.0e-5,
}
AVOGADRO = 6.02214076e23
R_GAS = 8.31446261815324
K_B = 1.380649e-23
E_CHARGE = 1.602176634e-19
MASS = {
    "O2": 0.032,
    "O2s": 0.032,
    "O2p": 0.032,
    "O": 0.016,
    "Om": 0.016,
    "Op": 0.016,
    "Os": 0.016,
}
WALL_BOUNDARIES = (
    "plasma_electrode",
    "plasma_metal",
    "plasma_right",
    "plasma_cover",
    "plasma_wafer",
    "plasma_focus_ring",
)
TE_REFERENCE_K = (2.0 / 3.0) * ENERGY_REFERENCE_EV * E_CHARGE / K_B


class ICPProfileError(RuntimeError):
    pass


def _replace_top_level(text: str, name: str, value: str) -> str:
    pattern = rf"(?m)^(?!\s){re.escape(name)}\s*=\s*.*$"
    replaced, count = re.subn(pattern, f"{name} = {value}", text, count=1)
    if count != 1:
        raise ICPProfileError(f"expected exactly one top-level {name}, found {count}")
    return replaced


def _couple_solved_electron_temperature(text: str) -> str:
    """Remove the historical fixed Te and make solved mean energy the sole electron thermal state."""
    text = mp.upsert_parameter(
        text,
        "FunctorMaterials/state_constants",
        "prop_names",
        "'T_g mu_flow'",
    )
    text = mp.upsert_parameter(
        text,
        "FunctorMaterials/state_constants",
        "prop_values",
        "'${T_g_value} ${mu_const}'",
    )

    path = "FunctorMaterials/issue357_solved_electron_temperature"
    mb.require_absent(text, path)
    text = mb.insert_child_block(
        text,
        "FunctorMaterials",
        f"""  [issue357_solved_electron_temperature]
    type = ADParsedFunctorMaterial
    property_name = electron_temperature_solved_K
    functor_names = 'mean_en_solved'
    functor_symbols = 'mean_ev'
    expression = '{(2.0 / 3.0) * E_CHARGE / K_B:.17g}*mean_ev'
    block = plasma
  []""",
    )
    text = mp.upsert_parameter(
        text,
        "FunctorMaterials/heavy_transport",
        "electron_temperature",
        "electron_temperature_solved_K",
    )
    text = mp.upsert_parameter(
        text,
        "FunctorMaterials/heavy_transport",
        "electron_number_density",
        "n_e_physical",
    )
    return text


def _add_full_electron_energy_transport(text: str) -> str:
    """Add the qualified drift/Joule terms missing from the historical S5-R energy PDE."""
    for path in (
        "FVKernels/issue357_energy_drift",
        "FVKernels/issue357_energy_joule",
    ):
        mb.require_absent(text, path)

    boundaries = "'" + " ".join(("inlet", "outlet") + WALL_BOUNDARIES) + "'"
    text = mb.insert_child_block(
        text,
        "FVKernels",
        f"""  [issue357_energy_drift]
    type = PhysicsFVElectrostaticDrift
    variable = mean_en
    potential = potential_plasma
    mobility = electron_energy_mobility
    carrier = carrier_one
    charge_number = -1
    advected_interp_method = upwind
    boundaries_to_avoid = {boundaries}
    block = plasma
  []""",
    )
    text = mb.insert_child_block(
        text,
        "FVKernels",
        f"""  [issue357_energy_joule]
    type = PhysicsFVElectronEnergyJouleHeating
    variable = mean_en
    electron_density = n_e
    potential = potential_plasma
    mobility = electron_mobility
    diffusion = electron_diffusion
    energy_reference_eV = {ENERGY_REFERENCE_EV:.17g}
    block = plasma
  []""",
    )
    return text


def _audit_solved_energy_transplant(text: str) -> dict[str, Any]:
    checks = {
        "energy_state_is_solver_variable": (
            mp.get_parameter(text, "Variables/mean_en", "type") == "MooseVariableFVReal"
        ),
        "energy_accumulation": (
            mp.get_parameter(text, "FVKernels/s5r_mean_en_time", "variable") == "mean_en"
        ),
        "energy_diffusion": (
            mp.get_parameter(text, "FVKernels/s5r_mean_en_diffusion", "coeff")
            == "electron_energy_diffusion"
        ),
        "energy_drift": (
            mp.get_parameter(text, "FVKernels/issue357_energy_drift", "potential")
            == "potential_plasma"
            and mp.get_parameter(text, "FVKernels/issue357_energy_drift", "mobility")
            == "electron_energy_mobility"
        ),
        "energy_joule": (
            mp.get_parameter(text, "FVKernels/issue357_energy_joule", "type")
            == "PhysicsFVElectronEnergyJouleHeating"
            and mp.get_parameter(text, "FVKernels/issue357_energy_joule", "electron_density")
            == "n_e"
        ),
        "reaction_energy_sources_present": all(
            mb.has_block(text, path)
            for path in (
                "FVKernels/s5r_ei02_elastic_energy",
                "FVKernels/s5r_ei17_elastic_energy",
                "FVKernels/s5r_energy_ei10",
                "FVKernels/s5r_energy_ei16",
                "FVKernels/s5r_energy_ei19",
                "FVKernels/s5r_energy_ei18_o_to_os",
                "FVKernels/s5r_energy_ei20_o_ionization",
                "FVKernels/s5r_energy_edetach_om",
            )
        ),
        "transport_uses_solved_mean_energy": (
            mp.get_parameter(text, "FunctorMaterials/electron_transport", "mean_energy")
            == "mean_en_solved"
        ),
        "heavy_uses_solved_electron_temperature": (
            mp.get_parameter(
                text, "FunctorMaterials/heavy_transport", "electron_temperature"
            )
            == "electron_temperature_solved_K"
        ),
        "heavy_uses_physical_electron_density": (
            mp.get_parameter(
                text, "FunctorMaterials/heavy_transport", "electron_number_density"
            )
            == "n_e_physical"
        ),
        "fixed_Te_removed": (
            "T_e" not in mp.words(
                mp.get_parameter(text, "FunctorMaterials/state_constants", "prop_names")
                or ""
            )
            and "electron_temperature = T_e" not in text
        ),
        "strict_lookup": (
            mp.get_parameter(text, "FunctorMaterials/electron_transport", "bounds_policy")
            == "error"
        ),
    }
    failed = sorted(name for name, passed in checks.items() if not passed)
    return {
        "status": "PASS" if not failed else "FAIL",
        "checks": checks,
        "failed_checks": failed,
        "electron_temperature_reference_K": TE_REFERENCE_K,
        "temperature_ownership": {
            "heavy_gas": "T_g",
            "electron": "electron_temperature_solved_K(mean_en_solved)",
        },
        "wall_energy_model": "closed electron-energy wall for first volume discriminator",
    }


def _add_profile_sampler(text: str) -> str:
    profile_block = """  [profile_samples]
    type = ElementValueSampler
    variable = 'p n_e mean_en potential_plasma w_O2s w_O2p w_O w_Om w_Op w_Os'
    block = plasma
    sort_by = id
    execute_on = 'INITIAL TIMESTEP_END'
  []"""
    if mb.has_block(text, "VectorPostprocessors"):
        mb.require_absent(text, "VectorPostprocessors/profile_samples")
        text = mb.insert_child_block(text, "VectorPostprocessors", profile_block)
    else:
        text += "\n[VectorPostprocessors]\n" + profile_block + "\n[]\n"

    output_block = """  [profile_csv]
    type = CSV
    execute_on = 'INITIAL TIMESTEP_END'
    execute_vector_postprocessors_on = 'INITIAL TIMESTEP_END'
  []"""
    if mb.has_block(text, "Outputs"):
        mb.require_absent(text, "Outputs/profile_csv")
        text = mb.insert_child_block(text, "Outputs", output_block)
    else:
        text += "\n[Outputs]\n" + output_block + "\n[]\n"
    return text


def _build_input() -> tuple[str, dict[str, Any]]:
    base = (SOURCE / "heavy_base.i").read_text()
    text, meta = build_s5r_input(base)

    # S5-R owns the normalized electron-energy state. Keep only the dimensionless
    # carrier helper from the historical prescribed-energy layer.
    text = mp.upsert_parameter(
        text,
        "FunctorMaterials/electron_constants",
        "prop_names",
        "'carrier_one'",
    )
    text = mp.upsert_parameter(
        text,
        "FunctorMaterials/electron_constants",
        "prop_values",
        "'1.0'",
    )
    text = _couple_solved_electron_temperature(text)
    text = _add_full_electron_energy_transport(text)

    # No fixed electron-temperature scalar remains after solved-Te coupling.
    text, removed_te = re.subn(
        r"(?m)^T_e_value\s*=\s*.*\n",
        "",
        text,
        count=1,
    )
    if removed_te != 1:
        raise ICPProfileError(f"expected one historical T_e_value assignment, removed {removed_te}")

    # R4-QF1/S5-R intentionally removed the historical Yin_O2 and Yin_O
    # aliases: O2 is the constrained remainder and O has a dedicated uniform
    # FunctionIC. Patch only the still-live initial-state aliases here.
    replacements = {
        "outlet_pressure": f"{PRESSURE_PA:.17g}",
        "T_g_value": f"{TG_K:.17g}",
        "n_e_value": f"{NREF_M3:.17g}",
        "Yin_O2s": f"{CURRENT_MASS_FRACTIONS['O2s']:.17g}",
        "Yin_O2p": f"{CURRENT_MASS_FRACTIONS['O2p']:.17g}",
        "Yin_Om": f"{CURRENT_MASS_FRACTIONS['Om']:.17g}",
        "Yin_Op": f"{CURRENT_MASS_FRACTIONS['Op']:.17g}",
        "Yin_Os": f"{CURRENT_MASS_FRACTIONS['Os']:.17g}",
    }
    for name, value in replacements.items():
        text = _replace_top_level(text, name, value)

    text = mp.upsert_parameter(
        text,
        "Functions/ic_w_O_transient",
        "expression",
        f"'{CURRENT_MASS_FRACTIONS['O']:.17g}'",
    )
    text = mp.upsert_parameter(text, "Executioner", "dt", f"{DT_S:.17g}")
    text = mp.upsert_parameter(text, "Executioner", "end_time", f"{END_TIME_S:.17g}")

    # Numerical globalization only: keep the physical residual unchanged while
    # preventing the first Newton full step from crossing the strict-positive
    # electron-energy domain.
    text = mp.upsert_parameter(text, "Executioner", "line_search", "basic")
    text = mp.upsert_parameter(
        text,
        "Executioner",
        "petsc_options_iname",
        "'-pc_type -pc_factor_shift_type -snes_linesearch_damping'",
    )
    text = mp.upsert_parameter(
        text,
        "Executioner",
        "petsc_options_value",
        "'lu NONZERO 0.25'",
    )
    text = _add_profile_sampler(text)

    audit = audit_s5r_input(text)
    if audit["status"] != "PASS":
        raise ICPProfileError(f"current real-QVT assembly audit failed: {audit['failed_checks']}")
    energy_audit = _audit_solved_energy_transplant(text)
    if energy_audit["status"] != "PASS":
        raise ICPProfileError(
            f"solved-energy transplant audit failed: {energy_audit['failed_checks']}"
        )

    meta = dict(meta)
    meta["solved_energy_transplant_audit"] = energy_audit
    meta["issue357"] = {
        "pressure_Pa": PRESSURE_PA,
        "T_g_K": TG_K,
        "electron_temperature_reference_K": TE_REFERENCE_K,
        "electron_temperature_owner": "derived from solved mean_en_solved",
        "electron_reference_density_m3": NREF_M3,
        "electron_energy_reference_eV": ENERGY_REFERENCE_EV,
        "mass_fractions": CURRENT_MASS_FRACTIONS,
        "dt_s": DT_S,
        "num_steps": NUM_STEPS,
        "end_time_s": END_TIME_S,
        "flow_sccm": 20.0,
        "electron_energy_equation": (
            "time + diffusion + electrostatic drift + Joule + elastic/reaction sources"
        ),
        "electron_energy_wall_model": "closed for first volume discriminator",
        "nonlinear_globalization": {
            "line_search": "basic",
            "damping": 0.25,
            "physics_residual_changed": False,
        },
        "geometry": "real-QVT RZ ICP reactor",
        "claim": "bounded geometry/profile sanity only",
    }
    return text, meta


def _stage(case_dir: Path) -> dict[str, Any]:
    text, meta = _build_input()
    staged = stage_case(
        SOURCE,
        case_dir,
        input_text=text,
        purge_directory_names=(".jitcache", "checkpoint", "checkpoints"),
        purge_patterns=("input_out*", "*.log", "*.e", "*.exo", "prepare_evidence.json"),
    )
    s5r_run._copy_runtime_assets(case_dir)

    staged_heavy = case_dir / "transport_data.txt"
    if staged_heavy.read_bytes() != CANONICAL_HEAVY.read_bytes():
        raise ICPProfileError(
            "real-QVT heavy transport data differs from current canonical Oxygen data"
        )
    staged_electron = case_dir / "electron_moments.txt"
    if staged_electron.read_bytes() == SMOKE_ELECTRON.read_bytes():
        raise ICPProfileError(
            "scientific ICP run accidentally selected the 3-point CI smoke electron table"
        )
    if len(staged_electron.read_text().splitlines()) < 50:
        raise ICPProfileError("real-QVT electron moment table unexpectedly short")

    refs = validate_case_references(case_dir)
    (case_dir / "prepare_evidence.json").write_text(
        json.dumps(meta, indent=2, sort_keys=True) + "\n"
    )
    return {
        "staging": staged,
        "references": refs,
        "canonical_heavy_data_byte_identical": True,
        "scientific_electron_table": "electron_moments.txt",
        "ci_smoke_electron_table_excluded": True,
        "construction": meta,
    }


def _read_profile(case_dir: Path) -> tuple[Path, list[dict[str, str]]]:
    matches = sorted(case_dir.glob("input_out_profile_samples*.csv"))
    if not matches:
        matches = sorted(case_dir.glob("*profile_samples*.csv"))
    if not matches:
        raise ICPProfileError("missing ElementValueSampler profile CSV")
    path = matches[-1]
    with path.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ICPProfileError(f"empty profile CSV: {path.name}")
    return path, rows


def _electron_table(case_dir: Path) -> list[tuple[float, float, float]]:
    table = []
    for raw in (case_dir / "electron_moments.txt").read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) >= 3:
            table.append((float(parts[0]), float(parts[1]), float(parts[2])))
    if len(table) < 2:
        raise ICPProfileError("electron moment table has fewer than two rows")
    return table


def _interp(table: list[tuple[float, float, float]], x: float) -> tuple[float, float]:
    if x < table[0][0] or x > table[-1][0]:
        raise ICPProfileError(
            f"mean energy {x} eV outside electron table [{table[0][0]}, {table[-1][0]}]"
        )
    for a, b in zip(table[:-1], table[1:]):
        if a[0] <= x <= b[0]:
            t = 0.0 if b[0] == a[0] else (x - a[0]) / (b[0] - a[0])
            return a[1] + t * (b[1] - a[1]), a[2] + t * (b[2] - a[2])
    return table[-1][1], table[-1][2]


def _derive(case_dir: Path, rows: list[dict[str, str]]) -> list[dict[str, float]]:
    table = _electron_table(case_dir)
    out: list[dict[str, float]] = []
    keys = (
        "id",
        "x",
        "y",
        "p",
        "n_e",
        "mean_en",
        "potential_plasma",
        "w_O2s",
        "w_O2p",
        "w_O",
        "w_Om",
        "w_Op",
        "w_Os",
    )
    for row in rows:
        vals = {k: float(row[k]) for k in keys}
        fractions = {
            s: vals[f"w_{s}"] for s in ("O2s", "O2p", "O", "Om", "Op", "Os")
        }
        fractions["O2"] = 1.0 - sum(fractions.values())
        mean_molar_mass = 1.0 / sum(fractions[s] / MASS[s] for s in MASS)
        rho = vals["p"] * mean_molar_mass / (R_GAS * TG_K)
        ne = NREF_M3 * vals["n_e"]
        mean_e = (
            ENERGY_REFERENCE_EV * vals["mean_en"] / vals["n_e"]
            if vals["n_e"] > 0.0
            else float("nan")
        )
        ion_number = (
            rho * fractions["O2p"] / MASS["O2p"] * AVOGADRO
            - rho * fractions["Om"] / MASS["Om"] * AVOGADRO
            + rho * fractions["Op"] / MASS["Op"] * AVOGADRO
        )
        charge_density = E_CHARGE * (ion_number - ne)
        mu_n, d_n = _interp(table, mean_e)
        neutral_n = vals["p"] / (K_B * TG_K)
        out.append(
            {
                "id": vals["id"],
                "r_m": vals["x"],
                "z_m": vals["y"],
                "pressure_Pa": vals["p"],
                "electron_density_m3": ne,
                "mean_energy_eV": mean_e,
                "potential_V": vals["potential_plasma"],
                "w_O2": fractions["O2"],
                "w_O2s": fractions["O2s"],
                "w_O2p": fractions["O2p"],
                "w_O": fractions["O"],
                "w_Om": fractions["Om"],
                "w_Op": fractions["Op"],
                "w_Os": fractions["Os"],
                "rho_kg_m3": rho,
                "charge_density_C_m3": charge_density,
                "electron_mobility_m2_Vs": mu_n / neutral_n,
                "electron_diffusion_m2_s": d_n / neutral_n,
            }
        )
    return out


def _write_csv(path: Path, rows: list[dict[str, float]]) -> None:
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _bins(
    rows: list[dict[str, float]], coord: str, nbin: int = 12
) -> list[dict[str, float]]:
    lo = min(row[coord] for row in rows)
    hi = max(row[coord] for row in rows)
    width = (hi - lo) / nbin if hi > lo else 1.0
    fields = (
        "electron_density_m3",
        "mean_energy_eV",
        "potential_V",
        "charge_density_C_m3",
        "w_O2p",
        "w_Om",
        "w_Op",
    )
    result = []
    for i in range(nbin):
        a = lo + i * width
        b = hi if i == nbin - 1 else lo + (i + 1) * width
        chosen = [
            row
            for row in rows
            if (a <= row[coord] <= b if i == nbin - 1 else a <= row[coord] < b)
        ]
        if not chosen:
            continue
        item: dict[str, float] = {
            coord: fmean(row[coord] for row in chosen),
            "count": float(len(chosen)),
        }
        for field in fields:
            item[field] = fmean(row[field] for row in chosen)
        result.append(item)
    return result


def _stats(values: list[float]) -> dict[str, float]:
    return {"min": min(values), "max": max(values), "avg": fmean(values)}


def _summarize(rows: list[dict[str, float]]) -> dict[str, Any]:
    finite = all(math.isfinite(value) for row in rows for value in row.values())
    species = ("w_O2", "w_O2s", "w_O2p", "w_O", "w_Om", "w_Op", "w_Os")
    species_bounds = all(
        -1.0e-12 <= row[s] <= 1.0 + 1.0e-12 for row in rows for s in species
    )
    sum_w_error = max(abs(sum(row[s] for s in species) - 1.0) for row in rows)
    ne = [row["electron_density_m3"] for row in rows]
    mean_e = [row["mean_energy_eV"] for row in rows]
    phi = [row["potential_V"] for row in rows]
    return {
        "elements": len(rows),
        "finite": finite,
        "species_bounds": species_bounds,
        "max_sum_w_error": sum_w_error,
        "electron_density_m3": _stats(ne),
        "mean_energy_eV": _stats(mean_e),
        "potential_V": {**_stats(phi), "span": max(phi) - min(phi)},
        "charge_density_C_m3": _stats([row["charge_density_C_m3"] for row in rows]),
        "electron_mobility_m2_Vs": _stats(
            [row["electron_mobility_m2_Vs"] for row in rows]
        ),
        "electron_diffusion_m2_s": _stats(
            [row["electron_diffusion_m2_s"] for row in rows]
        ),
        "w_O2p": _stats([row["w_O2p"] for row in rows]),
        "w_Om": _stats([row["w_Om"] for row in rows]),
        "w_Op": _stats([row["w_Op"] for row in rows]),
        "hard_sanity_pass": (
            finite
            and species_bounds
            and min(ne) >= 0.0
            and min(mean_e) > 0.0
            and sum_w_error <= 1.0e-8
        ),
    }


def run(args: argparse.Namespace) -> int:
    exe = resolve_executable(args.physics)
    validate_executable(exe)
    root = args.results_root
    root.mkdir(parents=True, exist_ok=True)
    case_dir = root / "case"
    logs = root / "logs"
    logs.mkdir(parents=True, exist_ok=True)

    staged = _stage(case_dir)
    check = run_physics(
        exe,
        cwd=case_dir,
        input_name="input.i",
        log_path=logs / "check_input.log",
        extra_args=("--check-input",),
        timeout_seconds=args.timeout,
    )
    if check.returncode != 0:
        raise ICPProfileError("ICP profile input failed --check-input")

    runtime = run_physics(
        exe,
        cwd=case_dir,
        input_name="input.i",
        log_path=logs / "runtime.log",
        extra_args=("-snes_converged_reason", "-ksp_converged_reason"),
        timeout_seconds=args.timeout,
    )
    if runtime.returncode != 0:
        raise ICPProfileError(
            f"ICP profile runtime failed with return code {runtime.returncode}"
        )

    sampler, raw = _read_profile(case_dir)
    derived = _derive(case_dir, raw)
    _write_csv(root / "element_profile.csv", derived)
    radial = _bins(derived, "r_m")
    axial = _bins(derived, "z_m")
    _write_csv(root / "radial_profile.csv", radial)
    _write_csv(root / "axial_profile.csv", axial)

    summary = {
        "issue": 357,
        "status": "ICP_PROFILE_SANITY_PASS",
        "geometry": "real-QVT RZ ICP reactor",
        "current_state": staged["construction"]["issue357"],
        "data_guards": {
            "canonical_heavy_data_byte_identical": staged[
                "canonical_heavy_data_byte_identical"
            ],
            "scientific_electron_table": staged["scientific_electron_table"],
            "ci_smoke_electron_table_excluded": staged[
                "ci_smoke_electron_table_excluded"
            ],
        },
        "check_input": {
            "returncode": check.returncode,
            "wall_seconds": check.wall_seconds,
        },
        "runtime": {
            "returncode": runtime.returncode,
            "wall_seconds": runtime.wall_seconds,
        },
        "sampler_csv": sampler.name,
        "final_profile": _summarize(derived),
        "radial_profile": radial,
        "axial_profile": axial,
        "energy_equation": staged["construction"]["solved_energy_transplant_audit"],
        "interpretation_scope": (
            "solved-electron-energy volume profile sanity only; no ICP coil RF power "
            "deposition and no final wall/sheath/SEE validation claim"
        ),
    }
    if not summary["final_profile"]["hard_sanity_pass"]:
        summary["status"] = "ICP_PROFILE_SANITY_FAIL"

    (root / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n"
    )
    print("ISSUE357_ICP_PROFILE_SUMMARY " + json.dumps(summary, sort_keys=True))
    print("ISSUE357_RADIAL_PROFILE " + json.dumps(radial, sort_keys=True))
    print("ISSUE357_AXIAL_PROFILE " + json.dumps(axial, sort_keys=True))
    return 0 if summary["status"] == "ICP_PROFILE_SANITY_PASS" else 2


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--physics", required=True)
    parser.add_argument("--results-root", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=1200.0)
    args = parser.parse_args()
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
