#!/usr/bin/env python3
from __future__ import annotations

import json
import math
import re
import shutil
import sys
from pathlib import Path

from physics_harness.adapters.moose import blocks as mb
from physics_harness.adapters.moose import parameters as mp
from experiments.Issue359_qualified_gummel_icp import heavy_continuity as hc

ROOT = Path(__file__).resolve().parents[4]
POISSON_DIR = ROOT / "experiments/2d-icp-poisson-experiment"
HEAVY_DIR = ROOT / "experiments/Issue91_real_qvt_r3/r3_e0"
BASE_INPUT = POISSON_DIR / "input.i"
HEAVY_INPUT = HEAVY_DIR / "heavy_base.i"

DT = 1.0e-9
FLOW_SCCM = 20.0
PRESSURE_PA = 1.333223684
TG_K = 300.0
AVOGADRO = 6.02214076e23
ELEMENTARY_CHARGE = 1.602176634e-19
R_GAS = 8.31446261815324
MEAN_ENERGY_EV = 5.73276
MASS_FRACTIONS = {
    "O2": 0.99994,
    "O2s": 1.0e-5,
    "O2p": 1.0e-5,
    "O": 1.0e-5,
    "Om": 1.0e-5,
    "Op": 1.0e-5,
    "Os": 1.0e-5,
}
ALL_B = {
    "inlet", "outlet", "plasma_electrode", "plasma_metal",
    "plasma_right", "plasma_cover", "plasma_wafer", "plasma_focus_ring",
}


def replace_top(text: str, name: str, value: str) -> str:
    out, n = re.subn(
        rf"(?m)^(?!\s){re.escape(name)}\s*=\s*.*$",
        f"{name} = {value}",
        text,
        count=1,
    )
    if n != 1:
        raise RuntimeError(f"expected one top-level assignment for {name}, got {n}")
    return out


def remove_top(text: str, name: str) -> str:
    return re.sub(rf"(?m)^(?!\s){re.escape(name)}\s*=\s*.*\n", "", text, count=1)


def extract_top_block(text: str, name: str) -> str:
    lines = text.splitlines(keepends=True)
    target = f"[{name}]"
    start = None
    for i, line in enumerate(lines):
        if line == target + "\n" or line.rstrip("\r\n") == target:
            start = i
            break
    if start is None:
        raise RuntimeError(f"missing top-level block {name}")
    depth = 0
    for j in range(start, len(lines)):
        s = lines[j].strip()
        if not (s.startswith("[") and s.endswith("]")):
            continue
        if s == "[]":
            depth -= 1
            if depth == 0:
                return "".join(lines[start:j + 1]).rstrip() + "\n"
        else:
            depth += 1
    raise RuntimeError(f"unterminated top-level block {name}")


def direct_children(text: str, parent: str) -> list[tuple[str, str]]:
    block = extract_top_block(text, parent)
    lines = block.splitlines(keepends=True)
    out: list[tuple[str, str]] = []
    i = 1
    while i < len(lines) - 1:
        line = lines[i]
        s = line.strip()
        if line.startswith("  [") and s != "[]" and s.startswith("[") and s.endswith("]"):
            name = s[1:-1]
            start = i
            depth = 1
            i += 1
            while i < len(lines) - 1 and depth:
                q = lines[i].strip()
                if q.startswith("[") and q.endswith("]"):
                    if q == "[]":
                        depth -= 1
                    else:
                        depth += 1
                i += 1
            if depth:
                raise RuntimeError(f"unterminated child {parent}/{name}")
            out.append((name, "".join(lines[start:i]).rstrip()))
            continue
        i += 1
    return out


def merge_children(base: str, donor: str, parent: str) -> str:
    for name, raw in direct_children(donor, parent):
        path = f"{parent}/{name}"
        if mb.has_block(base, path):
            raise RuntimeError(f"monolithic merge collision: {path}")
        base = mb.insert_child_block(base, parent, raw)
    return base


def set_one_step(text: str) -> str:
    for key, value in (
        ("dt", f"{DT:.17g}"),
        ("dtmin", f"{DT:.17g}"),
        ("dtmax", f"{DT:.17g}"),
        ("end_time", f"{DT:.17g}"),
        ("num_steps", "1"),
        ("timestep_tolerance", "1.0e-18"),
        ("nl_rel_tol", "1.0e-8"),
        ("nl_abs_tol", "1.0e-11"),
        ("nl_max_its", "80"),
        ("automatic_scaling", "true"),
        ("off_diagonals_in_auto_scaling", "true"),
        ("compute_scaling_once", "false"),
    ):
        text = mp.upsert_parameter(text, "Executioner", key, value)
    return text


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: prepare.py <case-dir>")
    case = Path(sys.argv[1]).resolve()
    if case.exists():
        shutil.rmtree(case)
    case.mkdir(parents=True)

    base = BASE_INPUT.read_text()
    heavy = HEAVY_INPUT.read_text()

    # Build the heavy-flow donor only. No MultiApps, transfers, or Gummel objects
    # are created anywhere in this probe.
    heavy = hc.promote_current_types(heavy)
    for name, value in (
        ("Q_sccm", FLOW_SCCM),
        ("outlet_pressure", PRESSURE_PA),
        ("T_g_value", TG_K),
        ("Yin_O2", MASS_FRACTIONS["O2"]),
        ("Yin_O2s", MASS_FRACTIONS["O2s"]),
        ("Yin_O2p", MASS_FRACTIONS["O2p"]),
        ("Yin_O", MASS_FRACTIONS["O"]),
        ("Yin_Om", MASS_FRACTIONS["Om"]),
        ("Yin_Op", MASS_FRACTIONS["Op"]),
        ("Yin_Os", MASS_FRACTIONS["Os"]),
    ):
        heavy = replace_top(heavy, name, f"{value:.17g}")
    for name in ("T_e_value", "n_e_value", "E0_migration"):
        heavy = remove_top(heavy, name)
    for path in ("Functions/phi_prescribed", "Functions/ic_w_O_transient", "ICs/ic_w_O"):
        if mb.has_block(heavy, path):
            heavy = mb.remove_block(heavy, path)
    for species in hc.SOLVED_HEAVY:
        heavy = mp.upsert_parameter(
            heavy, f"Variables/w_{species}", "initial_condition",
            f"{MASS_FRACTIONS[species]:.17g}",
        )

    heavy = mp.upsert_parameter(
        heavy, "FunctorMaterials/state_constants", "prop_names", "'T_g mu_flow'"
    )
    heavy = mp.upsert_parameter(
        heavy, "FunctorMaterials/state_constants", "prop_values", "'${T_g_value} ${mu_const}'"
    )
    # In the monolithic system heavy transport sees the live electron state directly.
    heavy = mp.upsert_parameter(
        heavy, "FunctorMaterials/heavy_transport", "electron_temperature", "electron_temperature_K"
    )
    heavy = mp.upsert_parameter(
        heavy, "FunctorMaterials/heavy_transport", "electron_number_density", "electron_density_m3"
    )
    heavy = hc.insert_surface_reactions(heavy, potential="phi")

    # User-requested discriminator: no bulk E-drift / heavy EM correction.
    for species in hc.CHARGED_HEAVY:
        path = f"FVKernels/{species}_electrostatic_drift"
        if mb.has_block(heavy, path):
            heavy = mb.remove_block(heavy, path)
    for species in hc.SOLVED_HEAVY:
        path = f"FVKernels/{species}_heavy_mass_em_correction"
        if mb.has_block(heavy, path):
            heavy = mb.remove_block(heavy, path)

    # Heavy-flow scalar controls are imported atomically into the Poisson base.
    controls = """# --- monolithic heavy-flow donor controls ---
Q_sccm = 20
Vm_std = 0.0224136
outlet_pressure = 1.333223684
T_g_value = 300
mu_const = 2e-05
e_over_kB_K_per_V = 11604.518121550082
Yin_O2 = 0.99994
Yin_O2s = 1e-05
Yin_O2p = 1e-05
Yin_O = 1e-05
Yin_Om = 1e-05
Yin_Op = 1e-05
Yin_Os = 1e-05
M_inlet = ${fparse 1.0/(Yin_O2/0.032+Yin_O2s/0.032+Yin_O2p/0.032+Yin_O/0.016+Yin_Om/0.016+Yin_Op/0.016+Yin_Os/0.016)}
Q_std = ${fparse Q_sccm * 1e-6 / 60.0}
inlet_mdot_value = ${fparse Q_std * M_inlet / Vm_std}
inlet_mdot_O2s_value = ${fparse inlet_mdot_value * Yin_O2s}
inlet_mdot_O2p_value = ${fparse inlet_mdot_value * Yin_O2p}
inlet_mdot_O_value = ${fparse inlet_mdot_value * Yin_O}
inlet_mdot_Om_value = ${fparse inlet_mdot_value * Yin_Om}
inlet_mdot_Op_value = ${fparse inlet_mdot_value * Yin_Op}
inlet_mdot_Os_value = ${fparse inlet_mdot_value * Yin_Os}
# --- end monolithic heavy-flow donor controls ---

"""
    base = controls + base

    # Rhie-Chow and flow variables/kernels live in the same application/system.
    for parent in ("GlobalParams", "UserObjects"):
        if mb.has_block(base, parent):
            raise RuntimeError(f"base unexpectedly already owns {parent}")
        base += "\n" + extract_top_block(heavy, parent)
    for parent in ("Variables", "FunctorMaterials", "FVKernels", "FVBCs", "Postprocessors"):
        base = merge_children(base, heavy, parent)

    # Charge-neutral initialization from the heavy charged species.
    rho0 = PRESSURE_PA * 0.032 / (R_GAS * TG_K)
    ni0 = rho0 * AVOGADRO * (
        MASS_FRACTIONS["O2p"] / 0.032
        - MASS_FRACTIONS["Om"] / 0.016
        + MASS_FRACTIONS["Op"] / 0.016
    )
    ce0 = ni0 / AVOGADRO
    base = mp.upsert_parameter(base, "Variables/log_e", "initial_condition", f"{math.log(ce0):.17g}")
    base = mp.upsert_parameter(
        base, "Variables/c_epsilon", "initial_condition", f"{ce0 * MEAN_ENERGY_EV:.17g}"
    )
    base = mp.upsert_parameter(
        base, "AuxVariables/electron_density", "initial_condition", f"{ni0:.17g}"
    )

    # Electron transport reads the live flow pressure and the heavy T_g functor.
    base = mp.upsert_parameter(base, "FunctorMaterials/electron_transport", "gas_pressure", "p")
    base = mp.upsert_parameter(base, "FunctorMaterials/electron_transport", "gas_temperature", "T_g")
    base = mp.upsert_parameter(
        base,
        "FunctorMaterials/constants",
        "prop_names",
        "'zero_phi energy_wall_te_factor relative_permittivity'",
    )
    base = mp.upsert_parameter(
        base, "FunctorMaterials/constants", "prop_values", "'0.0 2.5 1.0'"
    )

    # Replace frozen-ion Poisson source by the live heavy charged species.
    base = mp.upsert_parameter(
        base,
        "FunctorMaterials/space_charge_density",
        "functor_names",
        "'rho_mat w_O2p w_Om w_Op electron_density_m3'",
    )
    base = mp.upsert_parameter(
        base,
        "FunctorMaterials/space_charge_density",
        "functor_symbols",
        "'rho wp wm wo ne'",
    )
    base = mp.upsert_parameter(
        base,
        "FunctorMaterials/space_charge_density",
        "expression",
        "'1.602176634e-19*(6.02214076e23*rho*(wp/0.032-wm/0.016+wo/0.016)-ne)'",
    )

    # Remove the obsolete frozen-ion diagnostic so the output cannot be misread.
    for path in ("AuxVariables/frozen_ion_density_out", "AuxKernels/frozen_ion_density_copy"):
        if mb.has_block(base, path):
            base = mb.remove_block(base, path)

    base = mp.upsert_parameter(
        base,
        "VectorPostprocessors/final_profile",
        "variable",
        "'u v p w_O2s w_O2p w_O w_Om w_Op w_Os electron_density c_epsilon mean_energy_out electron_temperature_eV diffusion_out charge_density_out poisson_source_out phi'",
    )
    base = mp.upsert_parameter(
        base,
        "Outputs/exodus",
        "show",
        "'u v p w_O2s w_O2p w_O w_Om w_Op w_Os electron_density electron_temperature_eV charge_density_out poisson_source_out phi'",
    )
    base = set_one_step(base)

    # Contract: single application, one nonlinear system, no Gummel/MultiApp/transfer.
    solved = {
        "u", "v", "p", "w_O2s", "w_O2p", "w_O", "w_Om", "w_Op", "w_Os",
        "log_e", "c_epsilon", "phi",
    }
    checks = {
        "single_app_no_multiapps": not mb.has_block(base, "MultiApps"),
        "single_app_no_transfers": not mb.has_block(base, "Transfers"),
        "no_gummel_objects": "Gummel" not in base and "gummel" not in base,
        "all_monolithic_variables_present": all(mb.has_block(base, f"Variables/{v}") for v in solved),
        "dt_1ns_one_step": (
            float(mp.get_parameter(base, "Executioner", "dt") or "nan") == DT
            and float(mp.get_parameter(base, "Executioner", "end_time") or "nan") == DT
            and int(mp.get_parameter(base, "Executioner", "num_steps") or "0") == 1
        ),
        "inlet_20_sccm": re.search(r"(?m)^Q_sccm\s*=\s*20(?:\.0+)?\s*$", base) is not None,
        "outlet_10_mTorr": re.search(r"(?m)^outlet_pressure\s*=\s*1\.333223684\s*$", base) is not None,
        "poisson_all_ground": set(mp.words(
            mp.get_parameter(base, "FVBCs/phi_grounded_walls", "boundary") or ""
        )) == ALL_B,
        "electron_bulk_drift_off": (
            not mb.has_block(base, "FVKernels/electron_drift")
            and not mb.has_block(base, "FVKernels/energy_drift")
            and not mb.has_block(base, "FVKernels/energy_joule")
        ),
        "heavy_bulk_drift_off": all(
            not mb.has_block(base, f"FVKernels/{s}_electrostatic_drift")
            for s in hc.CHARGED_HEAVY
        ) and all(
            not mb.has_block(base, f"FVKernels/{s}_heavy_mass_em_correction")
            for s in hc.SOLVED_HEAVY
        ),
        "live_heavy_charge_to_poisson": (
            mp.get_parameter(base, "FunctorMaterials/space_charge_density", "functor_names")
            == "'rho_mat w_O2p w_Om w_Op electron_density_m3'"
        ),
        "electron_transport_reads_live_flow_pressure": (
            mp.get_parameter(base, "FunctorMaterials/electron_transport", "gas_pressure") == "p"
            and mp.get_parameter(base, "FunctorMaterials/electron_transport", "gas_temperature") == "T_g"
        ),
        "surface_reactions_preserved": all(
            mb.has_block(base, path)
            for path in (
                "FVBCs/O_wall_loss",
                "FVBCs/O2s_wall_loss",
                "FVBCs/Os_wall_loss",
                "FunctorMaterials/O2p_wall_flux",
                "FunctorMaterials/Om_wall_flux",
                "FunctorMaterials/Op_wall_flux",
                "FVBCs/O2p_surface_plasma_electrode",
                "FVBCs/Om_surface_plasma_electrode",
                "FVBCs/Op_surface_plasma_electrode",
                "FVBCs/ion_neutralization_O_return",
            )
        ),
    }
    failed = sorted(k for k, ok in checks.items() if not ok)
    contract = {
        "probe": "poisson-base-plus-heavy-flow-monolithic-1ns",
        "architecture": "single-app monolithic Newton",
        "dt_s": DT,
        "num_steps": 1,
        "flow_sccm": FLOW_SCCM,
        "outlet_pressure_Pa": PRESSURE_PA,
        "outlet_pressure_mTorr": 10.0,
        "all_electrostatic_boundaries_grounded": True,
        "bulk_drift": False,
        "electron_joule_heating": False,
        "surface_reactions": hc.SURFACE_REACTIONS,
        "surface_sticking": hc.WALL_STICKING,
        "initial_electron_density_m3": ni0,
        "checks": checks,
        "failed_checks": failed,
        "status": "PASS" if not failed else "FAIL",
    }
    (case / "input.i").write_text(base)
    (case / "probe_contract.json").write_text(json.dumps(contract, indent=2, sort_keys=True) + "\n")

    for src in (
        POISSON_DIR / "qvt.msh",
        POISSON_DIR / "electron_moments.txt",
        HEAVY_DIR / "transport_data.txt",
    ):
        if not src.is_file():
            raise RuntimeError(f"required donor file missing: {src}")
        shutil.copy2(src, case / src.name)

    print(json.dumps(contract, indent=2, sort_keys=True))
    if failed:
        raise SystemExit(f"monolithic contract failed: {failed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
