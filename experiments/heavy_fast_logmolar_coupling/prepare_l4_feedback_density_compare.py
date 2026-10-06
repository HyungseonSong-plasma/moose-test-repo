#!/usr/bin/env python3
from __future__ import annotations

import argparse
import math
import re
from pathlib import Path

import prepare_l4_dt_compare as base

HERE = Path(__file__).resolve().parent
NA = 6.02214076e23
MEAN_E0 = 5.73276
TARGET_NE = 1.0e15
TOTAL_TIME = 1.0e-9  # 1 ns

# eta_O2p chosen so that the inherited simplex startup state gives
# n_O2p = 1e15 m^-3 at p=1.33322 Pa, T_g=600 K while all other eta_s=0.
ETA_O2P_INITIAL = -2.3026410159253476
LOG_NE_INITIAL = math.log(TARGET_NE / NA)
LOG_ENERGY_INITIAL = math.log((TARGET_NE / NA) * MEAN_E0)

ION_COLLECTION_BOUNDARIES = (
    "inlet outlet plasma_electrode plasma_metal plasma_right "
    "plasma_cover plasma_wafer plasma_focus_ring"
)

CASES = {
    "dt1ns_1step": (1.0e-9, 1),
    "dt0p1ns_10steps": (1.0e-10, 10),
    "dt0p01ns_100steps": (1.0e-11, 100),
}


def set_initial_neutrality(text: str) -> str:
    text = base.set_child_parameter(
        text, "eta_O2p", "initial_condition", f"{ETA_O2P_INITIAL:.17g}"
    )
    text = base.set_child_parameter(
        text, "log_ne", "initial_condition", f"{LOG_NE_INITIAL:.17g}"
    )
    text = base.set_child_parameter(
        text, "log_energy", "initial_condition", f"{LOG_ENERGY_INITIAL:.17g}"
    )
    return text


def add_density_diagnostics(text: str) -> str:
    payload = """
  [O2p_n_min_feedback]
    type = ADElementExtremeFunctorValue
    functor = n_O2p_monolithic
    value_type = min
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [O2p_n_max_feedback]
    type = ADElementExtremeFunctorValue
    functor = n_O2p_monolithic
    value_type = max
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
"""
    return base.append_to_section(text, "Postprocessors", payload)


def build(case: str) -> Path:
    if case not in CASES:
        raise ValueError(case)
    dt, num_steps = CASES[case]

    # Reuse the accepted L4 construction, but extend ion collection to inlet/outlet.
    base.ION_WALL_BOUNDARIES = ION_COLLECTION_BOUNDARIES

    level_matrix = base.load_level_matrix_module()
    generated = level_matrix.build(4)
    text = generated.read_text(encoding="utf-8")

    # 20 sccm total mixture inflow, pure O2 composition, 10 mTorr outlet.
    text = base.set_flow_and_pure_o2_inlet(text)

    # O2+, O+, O-: surface reaction + migration on inlet, outlet, and six walls.
    text = base.configure_ion_wall_physics(text)

    # Lower the initial charged-particle density while preserving neutrality.
    text = set_initial_neutrality(text)
    text = add_density_diagnostics(text)

    start, end = base.executioner_bounds(text)
    section = text[start:end]
    for name, value in (
        ("dt", f"{dt:.17g}"),
        ("dtmin", f"{dt:.17g}"),
        ("dtmax", f"{dt:.17g}"),
        ("end_time", f"{TOTAL_TIME:.17g}"),
        ("num_steps", str(num_steps)),
    ):
        section = base.set_top_level_parameter(section, name, value)
    text = text[:start] + section + text[end:]

    required = (
        "Q_sccm = 20.0",
        "outlet_pressure = 1.33322",
        "M_inlet = 0.032",
        f"boundary = '{ION_COLLECTION_BOUNDARIES}'",
        f"initial_condition = {ETA_O2P_INITIAL:.17g}",
        f"initial_condition = {LOG_NE_INITIAL:.17g}",
        f"initial_condition = {LOG_ENERGY_INITIAL:.17g}",
        "functor = ion_surface_mass_flux_O2p",
        "functor = ion_migration_mass_flux_O2p",
        "functor = ion_surface_mass_flux_Op",
        "functor = ion_migration_mass_flux_Op",
        "functor = ion_surface_mass_flux_Om",
        "functor = ion_migration_mass_flux_Om",
    )
    for token in required:
        if token not in text:
            raise RuntimeError(f"feedback-density contract missing: {token}")

    # Electron sheath remains the existing six-wall model; only ions additionally
    # collect on inlet/outlet as requested.
    electron_sheath = base.child_block(text, "electron_sheath_loss")
    if "inlet" in electron_sheath or "outlet" in electron_sheath:
        raise RuntimeError("electron sheath boundary set unexpectedly changed")

    for name in (
        "O2p_surface_wall_loss",
        "O2p_migration_wall_loss",
        "Op_surface_wall_loss",
        "Op_migration_wall_loss",
        "Om_surface_wall_loss",
        "Om_migration_wall_loss",
    ):
        body = base.child_block(text, name)
        if "inlet" not in body or "outlet" not in body:
            raise RuntimeError(f"{name} is missing inlet/outlet ion collection")

    exec_start, exec_end = base.executioner_bounds(text)
    exec_section = text[exec_start:exec_end]
    for expected in (
        f"  dt = {dt:.17g}",
        f"  dtmin = {dt:.17g}",
        f"  dtmax = {dt:.17g}",
        f"  end_time = {TOTAL_TIME:.17g}",
        f"  num_steps = {num_steps}",
    ):
        if expected not in exec_section:
            raise RuntimeError(f"time contract missing: {expected}")

    out = HERE / f"full_monolithic_l4_feedback_{case}.i"
    out.write_text(text, encoding="utf-8")
    print(f"wrote {out}")
    print(f"case={case} dt={dt:.17g} num_steps={num_steps} end_time={TOTAL_TIME:.17g}")
    print(f"initial ne={TARGET_NE:.17g} m^-3; initial nO2p={TARGET_NE:.17g} m^-3")
    print(f"eta_O2p_initial={ETA_O2P_INITIAL:.17g}")
    print("total inlet flow=20 sccm pure O2; outlet pressure=10 mTorr")
    print(f"ion surface+migration boundaries={ION_COLLECTION_BOUNDARIES}")
    print("electron sheath remains on the six plasma walls")
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", choices=tuple(CASES), required=True)
    args = parser.parse_args()
    build(args.case)


if __name__ == "__main__":
    main()
