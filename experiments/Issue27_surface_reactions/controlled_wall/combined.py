#!/usr/bin/env python3
"""Run Issue #27 A5+A6 combined COMSOL-style wall integration on accepted R4-QF1.

A5 is an in-run structural/N-1 preflight. A6 then compares a surface-only
control with the COMSOL-style charged-wall extension

    ion wall flux = surface-reaction flux + one-sided electric migration flux

using the already validated QPXIonWallFluxMaterial. SEE remains disabled.
"""
from __future__ import annotations

import csv
import json
import math
import re
from pathlib import Path
from typing import Any, Mapping

from experiments.Issue31_r4_q0_all_ground import run as q0_run
from experiments.Issue91_real_qvt_r3 import run as issue91_run
from qpx_harness.evidence import create_collision_safe_directory, utc_timestamp, write_json_bundle
from qpx_harness.execution.cases import stage_case
from qpx_harness.execution.runtime import resolve_executable, validate_executable
from qpx_harness.moose import blocks as mb
from qpx_harness.moose import parameters as mp
from recipes.issue31_r4_qf1 import build_r4_qf1_input

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / "experiments" / "Issue91_real_qvt_r3" / "r3_e0"

AVOGADRO = 6.02214076e23
ELEMENTARY_CHARGE_C = 1.602176634e-19
FARADAY_C_PER_MOL = AVOGADRO * ELEMENTARY_CHARGE_C
GAS_CONSTANT_J_PER_MOL_K = 8.31446
M_O2_KG_PER_MOL = 0.032
M_O_KG_PER_MOL = 0.016
PLASMA_WALLS = (
    "plasma_electrode",
    "plasma_metal",
    "plasma_right",
    "plasma_cover",
    "plasma_wafer",
    "plasma_focus_ring",
)
PHYSICAL_BOUNDARIES = ("inlet", "outlet", *PLASMA_WALLS)
CASE_MODES = ("control", "surface_only", "comsol_wall")
CHARGED = {
    "O2p": {"variable": "w_O2p", "mobility": "mu_O2p", "charge": 1, "molar_mass": M_O2_KG_PER_MOL},
    "Om": {"variable": "w_Om", "mobility": "mu_Om", "charge": -1, "molar_mass": M_O_KG_PER_MOL},
    "Op": {"variable": "w_Op", "mobility": "mu_Op", "charge": 1, "molar_mass": M_O_KG_PER_MOL},
}
NEUTRALS = {
    "O": {"variable": "w_O", "molar_mass": M_O_KG_PER_MOL},
    "O2s": {"variable": "w_O2s", "molar_mass": M_O2_KG_PER_MOL},
    "Os": {"variable": "w_Os", "molar_mass": M_O_KG_PER_MOL},
}
AREA_PP = "issue27_a6_wall_area"
O_RETURN_FUNCTOR = "issue27_a6_O_return_mass_flux_inward"
O_RETURN_BC = "issue27_a6_O_return"
O_RETURN_PP = "issue27_a6_O_return_rate"
ELECTRON_FUNCTOR = "issue27_a6_electron_ledger_normalized_flux_outward"
ELECTRON_BC = "issue27_a6_electron_charge_ledger"
ELECTRON_PP = "issue27_a6_electron_ledger_rate"


class Issue27CombinedWallError(RuntimeError):
    pass


def _top_level_float(text: str, name: str) -> float:
    matches = re.findall(rf"(?m)^\s*{re.escape(name)}\s*=\s*([^#\r\n]+)", text)
    if len(matches) != 1:
        raise Issue27CombinedWallError(f"cannot resolve unique top-level scalar {name}")
    value = float(matches[0].strip())
    if not math.isfinite(value):
        raise Issue27CombinedWallError(f"non-finite scalar {name}={value}")
    return value


def _float_parameter(parameters: Mapping[str, Any], name: str, default: float) -> float:
    raw = parameters.get(name, default)
    try:
        value = float(raw)
    except (TypeError, ValueError) as exc:
        raise Issue27CombinedWallError(f"parameters.{name} must be numeric") from exc
    if not math.isfinite(value):
        raise Issue27CombinedWallError(f"parameters.{name} must be finite")
    return value


def _validated_parameters(parameters: Mapping[str, Any]) -> dict[str, Any]:
    wall_model = str(parameters.get("wall_model", ""))
    if wall_model != "combined_comsol_wall_control":
        raise Issue27CombinedWallError("A6 requires wall_model='combined_comsol_wall_control'")
    if str(parameters.get("wall_scope", "")) != "all_plasma_walls":
        raise Issue27CombinedWallError("A6 requires wall_scope='all_plasma_walls'")
    if str(parameters.get("gas_temperature_functor", "T_g")) != "T_g":
        raise Issue27CombinedWallError("A6 gas_temperature_functor is frozen to T_g")
    if parameters.get("motz_wise_correction", False) is not False:
        raise Issue27CombinedWallError("A6 is frozen to Motz-Wise OFF")
    if str(parameters.get("electron_wall_mode", "")) != "matched_signed_charge_ledger":
        raise Issue27CombinedWallError(
            "A6 electron wall mode is frozen to matched_signed_charge_ledger"
        )

    expected = {
        "O_sticking_coefficient": 0.2,
        "O2s_sticking_coefficient": 1.0,
        "Os_sticking_coefficient": 0.2,
        "O2p_sticking_coefficient": 1.0,
        "Om_sticking_coefficient": 1.0,
        "Op_sticking_coefficient": 1.0,
        "secondary_emission_coefficient": 0.0,
    }
    frozen: dict[str, Any] = {
        "wall_model": wall_model,
        "wall_scope": "all_plasma_walls",
        "wall_boundaries": list(PLASMA_WALLS),
        "excluded_boundaries": ["inlet", "outlet"],
        "gas_temperature_functor": "T_g",
        "motz_wise_correction": False,
        "electron_wall_mode": "matched_signed_charge_ledger",
    }
    for name, target in expected.items():
        value = _float_parameter(parameters, name, target)
        if not math.isclose(value, target, rel_tol=0.0, abs_tol=0.0):
            raise Issue27CombinedWallError(f"A6 freezes {name}={target}, got {value}")
        frozen[name] = value
    frozen["comsol_charged_wall_contract"] = (
        "QPXIonWallFluxMaterial: surface mass flux plus one-sided migration mass flux; "
        "migration uses the accepted signed outward-normal clamp from Issue #1"
    )
    frozen["secondary_emission"] = False
    frozen["production_electron_sheath"] = False
    return frozen


def _neutral_flux_expression(sticking: float, molar_mass: float, variable_symbol: str) -> str:
    thermal = (
        f"sqrt(8.0*{GAS_CONSTANT_J_PER_MOL_K:.17g}*tg/"
        f"(3.14159265358979323846*{molar_mass:.17g}))"
    )
    return f"{sticking:.17g}*0.25*{thermal}*rho*{variable_symbol}"


def _neutral_names(species: str) -> tuple[str, str, str, str]:
    return (
        f"issue27_a6_{species}_flux_material",
        f"issue27_a6_{species}_wall_flux_outward",
        f"issue27_a6_{species}_wall_loss",
        f"issue27_a6_{species}_wall_rate",
    )


def _charged_names(species: str, wall: str) -> tuple[str, str, str, str]:
    surface_bc = f"issue27_a6_{species}_surface_{wall}"
    migration_bc = f"issue27_a6_{species}_migration_{wall}"
    surface_pp = f"{surface_bc}_rate"
    migration_pp = f"{migration_bc}_rate"
    return surface_bc, migration_bc, surface_pp, migration_pp


def _mode_flags(mode: str) -> tuple[bool, bool, bool]:
    if mode not in CASE_MODES:
        raise Issue27CombinedWallError(f"unsupported A6 mode {mode!r}")
    return mode != "control", mode == "comsol_wall", mode != "control"


def _build_a6_case_input(
    base_text: str,
    *,
    parameters: Mapping[str, Any],
    mode: str,
) -> tuple[str, dict[str, Any]]:
    frozen = _validated_parameters(parameters)
    surface_on, migration_on, electron_on = _mode_flags(mode)
    text, predecessor = build_r4_qf1_input(base_text)
    if predecessor["audit"]["status"] != "PASS":
        raise Issue27CombinedWallError("R4-QF1 predecessor audit is not PASS")

    n_ref = _top_level_float(text, "n_e_value")
    wall_list = "'" + " ".join(PLASMA_WALLS) + "'"

    if mb.has_block(text, "Variables/w_O2"):
        raise Issue27CombinedWallError("A5 preflight forbids an independent w_O2 variable")

    # Neutral Phase-A reactions: O -> 0.5 O2, O2s -> O2, Os -> 0.5 O2.
    neutral_sticking = {
        "O": float(frozen["O_sticking_coefficient"]),
        "O2s": float(frozen["O2s_sticking_coefficient"]),
        "Os": float(frozen["Os_sticking_coefficient"]),
    }
    for species, cfg in NEUTRALS.items():
        material, functor, bc_name, pp_name = _neutral_names(species)
        for path in (
            f"FunctorMaterials/{material}",
            f"FVBCs/{bc_name}",
            f"Postprocessors/{pp_name}",
        ):
            mb.require_absent(text, path)
        symbol = species.lower()
        expression = _neutral_flux_expression(
            neutral_sticking[species], float(cfg["molar_mass"]), symbol
        )
        text = mb.insert_child_block(
            text,
            "FunctorMaterials",
            f"""  [{material}]
    type = ADParsedFunctorMaterial
    property_name = {functor}
    functor_names = 'rho_mat {cfg['variable']} T_g'
    functor_symbols = 'rho {symbol} tg'
    expression = '{expression}'
    block = plasma
  []""",
        )
        text = mb.insert_child_block(
            text,
            "FVBCs",
            f"""  [{bc_name}]
    type = FVFunctorNeumannBC
    variable = {cfg['variable']}
    boundary = {wall_list}
    functor = {functor}
    factor = {-1.0 if surface_on else 0.0:.17g}
  []""",
        )
        text = mb.insert_child_block(
            text,
            "Postprocessors",
            f"""  [{pp_name}]
    type = SideFVFluxBCIntegral
    boundary = {wall_list}
    fvbcs = '{bc_name}'
    execute_on = 'INITIAL TIMESTEP_END'
  []""",
        )

    # Charged Phase-A wall transport. QPXIonWallFluxMaterial is the already
    # validated Issue #1 implementation of the COMSOL surface + signed/clamped
    # normal migration decomposition. declare_suffix lets all three ions coexist.
    for species, cfg in CHARGED.items():
        density_property = f"issue27_a6_n_{species}"
        density_material = f"issue27_a6_{species}_number_density"
        flux_material = f"issue27_a6_{species}_wall_flux"
        for path in (
            f"FunctorMaterials/{density_material}",
            f"FunctorMaterials/{flux_material}",
        ):
            mb.require_absent(text, path)
        text = mb.insert_child_block(
            text,
            "FunctorMaterials",
            f"""  [{density_material}]
    type = ADParsedFunctorMaterial
    property_name = {density_property}
    functor_names = 'rho_mat {cfg['variable']}'
    functor_symbols = 'rho w'
    expression = 'rho*w*{AVOGADRO:.17g}/{float(cfg['molar_mass']):.17g}'
    block = plasma
  []""",
        )
        text = mb.insert_child_block(
            text,
            "FunctorMaterials",
            f"""  [{flux_material}]
    type = QPXIonWallFluxMaterial
    ion_number_density = {density_property}
    potential = potential_plasma
    mobility = {cfg['mobility']}
    gas_temperature = T_g
    charge_number = {int(cfg['charge'])}
    molar_mass = {float(cfg['molar_mass']):.17g}
    sticking = {float(frozen[f'{species}_sticking_coefficient']):.17g}
    declare_suffix = {species}
    block = plasma
  []""",
        )
        for wall in PLASMA_WALLS:
            surface_bc, migration_bc, surface_pp, migration_pp = _charged_names(species, wall)
            for path in (
                f"FVBCs/{surface_bc}",
                f"FVBCs/{migration_bc}",
                f"Postprocessors/{surface_pp}",
                f"Postprocessors/{migration_pp}",
            ):
                mb.require_absent(text, path)
            text = mb.insert_child_block(
                text,
                "FVBCs",
                f"""  [{surface_bc}]
    type = FVFunctorNeumannBC
    variable = {cfg['variable']}
    boundary = {wall}
    functor = ion_surface_mass_flux_{species}
    factor = {-1.0 if surface_on else 0.0:.17g}
  []""",
            )
            text = mb.insert_child_block(
                text,
                "FVBCs",
                f"""  [{migration_bc}]
    type = FVFunctorNeumannBC
    variable = {cfg['variable']}
    boundary = {wall}
    functor = ion_migration_mass_flux_{species}
    factor = {-1.0 if migration_on else 0.0:.17g}
  []""",
            )
            text = mb.insert_child_block(
                text,
                "Postprocessors",
                f"""  [{surface_pp}]
    type = SideFVFluxBCIntegral
    boundary = {wall}
    fvbcs = '{surface_bc}'
    execute_on = 'INITIAL TIMESTEP_END'
  []""",
            )
            text = mb.insert_child_block(
                text,
                "Postprocessors",
                f"""  [{migration_pp}]
    type = SideFVFluxBCIntegral
    boundary = {wall}
    fvbcs = '{migration_bc}'
    execute_on = 'INITIAL TIMESTEP_END'
  []""",
            )

    def ion_flux_terms(species: str, include_migration: bool) -> str:
        terms = [f"ion_surface_mass_flux_{species}"]
        if include_migration:
            terms.append(f"ion_migration_mass_flux_{species}")
        return "+".join(terms)

    include_migration = migration_on
    op_total = ion_flux_terms("Op", include_migration)
    om_total = ion_flux_terms("Om", include_migration)
    o2p_total = ion_flux_terms("O2p", include_migration)

    # Neutralization products. Op and Om return equal mass as O. O2p is returned
    # through the accepted constrained-O2 N-1 representation.
    mb.require_absent(text, "FunctorMaterials/issue27_a6_O_return_material")
    mb.require_absent(text, f"FVBCs/{O_RETURN_BC}")
    mb.require_absent(text, f"Postprocessors/{O_RETURN_PP}")
    return_expression = f"({op_total})+({om_total})" if surface_on else "0"
    text = mb.insert_child_block(
        text,
        "FunctorMaterials",
        f"""  [issue27_a6_O_return_material]
    type = ADParsedFunctorMaterial
    property_name = {O_RETURN_FUNCTOR}
    functor_names = 'ion_surface_mass_flux_Op ion_migration_mass_flux_Op ion_surface_mass_flux_Om ion_migration_mass_flux_Om'
    functor_symbols = 'sop mop som mom'
    expression = '{return_expression.replace('ion_surface_mass_flux_Op', 'sop').replace('ion_migration_mass_flux_Op', 'mop').replace('ion_surface_mass_flux_Om', 'som').replace('ion_migration_mass_flux_Om', 'mom')}'
    block = plasma
  []""",
    )
    text = mb.insert_child_block(
        text,
        "FVBCs",
        f"""  [{O_RETURN_BC}]
    type = FVFunctorNeumannBC
    variable = w_O
    boundary = {wall_list}
    functor = {O_RETURN_FUNCTOR}
    factor = {1.0 if surface_on else 0.0:.17g}
  []""",
    )
    text = mb.insert_child_block(
        text,
        "Postprocessors",
        f"""  [{O_RETURN_PP}]
    type = SideFVFluxBCIntegral
    boundary = {wall_list}
    fvbcs = '{O_RETURN_BC}'
    execute_on = 'INITIAL TIMESTEP_END'
  []""",
    )

    # A3e-approved charge ledger, now driven by the actual A6 ion wall fluxes.
    # It remains a bounded signed ledger control, not the production electron
    # sheath law. Finite SEE remains Phase C-owned.
    mb.require_absent(text, "FunctorMaterials/issue27_a6_electron_ledger_material")
    mb.require_absent(text, f"FVBCs/{ELECTRON_BC}")
    mb.require_absent(text, f"Postprocessors/{ELECTRON_PP}")
    if electron_on:
        charge_expression = (
            f"{AVOGADRO / n_ref:.17g}*((({o2p_total})/{M_O2_KG_PER_MOL:.17g})"
            f"+(({op_total})/{M_O_KG_PER_MOL:.17g})"
            f"-(({om_total})/{M_O_KG_PER_MOL:.17g}))"
        )
    else:
        charge_expression = "0"
    symbol_map = {
        "ion_surface_mass_flux_O2p": "s2p",
        "ion_migration_mass_flux_O2p": "m2p",
        "ion_surface_mass_flux_Op": "sop",
        "ion_migration_mass_flux_Op": "mop",
        "ion_surface_mass_flux_Om": "som",
        "ion_migration_mass_flux_Om": "mom",
    }
    for original, symbol in symbol_map.items():
        charge_expression = charge_expression.replace(original, symbol)
    text = mb.insert_child_block(
        text,
        "FunctorMaterials",
        f"""  [issue27_a6_electron_ledger_material]
    type = ADParsedFunctorMaterial
    property_name = {ELECTRON_FUNCTOR}
    functor_names = 'ion_surface_mass_flux_O2p ion_migration_mass_flux_O2p ion_surface_mass_flux_Op ion_migration_mass_flux_Op ion_surface_mass_flux_Om ion_migration_mass_flux_Om'
    functor_symbols = 's2p m2p sop mop som mom'
    expression = '{charge_expression}'
    block = plasma
  []""",
    )
    text = mb.insert_child_block(
        text,
        "FVBCs",
        f"""  [{ELECTRON_BC}]
    type = FVFunctorNeumannBC
    variable = n_e
    boundary = {wall_list}
    functor = {ELECTRON_FUNCTOR}
    factor = {-1.0 if electron_on else 0.0:.17g}
  []""",
    )
    text = mb.insert_child_block(
        text,
        "Postprocessors",
        f"""  [{ELECTRON_PP}]
    type = SideFVFluxBCIntegral
    boundary = {wall_list}
    fvbcs = '{ELECTRON_BC}'
    execute_on = 'INITIAL TIMESTEP_END'
  []""",
    )

    mb.require_absent(text, f"Postprocessors/{AREA_PP}")
    text = mb.insert_child_block(
        text,
        "Postprocessors",
        f"""  [{AREA_PP}]
    type = AreaPostprocessor
    boundary = {wall_list}
    execute_on = 'INITIAL TIMESTEP_END'
  []""",
    )

    observed_pps = (
        "mass_total",
        "mass_O2",
        "mass_O2s",
        "mass_O2p",
        "mass_O",
        "mass_Om",
        "mass_Op",
        "mass_Os",
        "w_O2_min",
        "w_O2s_min",
        "w_O2p_min",
        "w_O_min",
        "w_Om_min",
        "w_Op_min",
        "w_Os_min",
        "sum_w_min",
        "sum_w_max",
        "n_e_inventory",
        "n_e_min",
        "r31_charge_integral",
        "r31_gauss_flux_charge",
    )
    for pp in observed_pps:
        text = mp.upsert_parameter(
            text,
            f"Postprocessors/{pp}",
            "execute_on",
            "'INITIAL TIMESTEP_END'",
        )

    return text, {
        "issue": 27,
        "experiment": "A5_A6_COMBINED_COMSOL_WALL_INTEGRATION",
        "mode": mode,
        "predecessor": predecessor,
        "validated_parameters": frozen,
        "wall_boundaries": list(PLASMA_WALLS),
        "excluded_boundaries": ["inlet", "outlet"],
        "electron_reference_density_m3": n_ref,
        "surface_enabled": surface_on,
        "migration_enabled": migration_on,
        "electron_ledger_enabled": electron_on,
        "charged_wall_material": "QPXIonWallFluxMaterial",
        "charged_wall_contract": (
            "COMSOL parity: surface reaction flux + one-sided signed normal electric migration; "
            "interior QPXFVElectrostaticDrift remains excluded from physical walls"
        ),
        "n_minus_1_contract": (
            "O2 is constrained; O/O2s/Os/O2p wall neutralization products are represented "
            "without an independent w_O2 equation"
        ),
        "frozen_phase": {
            "R4_QF1_preserved": True,
            "volumetric_reactions": False,
            "secondary_emission": False,
            "surface_accumulated_charge": False,
            "production_electron_sheath": False,
        },
    }


def _a5_preflight(text: str, meta: Mapping[str, Any]) -> dict[str, Any]:
    failures: list[str] = []
    if mb.has_block(text, "Variables/w_O2"):
        failures.append("independent w_O2 variable exists")
    if tuple(meta["wall_boundaries"]) != PLASMA_WALLS:
        failures.append("wall set differs from canonical six-wall set")
    if list(meta["excluded_boundaries"]) != ["inlet", "outlet"]:
        failures.append("inlet/outlet exclusion changed")

    for kernel in ("O2p_electrostatic_drift", "Om_electrostatic_drift", "Op_electrostatic_drift"):
        words = tuple(
            mp.words(mp.get_parameter(text, f"FVKernels/{kernel}", "boundaries_to_avoid"))
        )
        for boundary in PHYSICAL_BOUNDARIES:
            if boundary not in words:
                failures.append(f"{kernel} does not avoid {boundary}")

    for species in CHARGED:
        path = f"FunctorMaterials/issue27_a6_{species}_wall_flux"
        if mp.get_parameter(text, path, "type") != "QPXIonWallFluxMaterial":
            failures.append(f"{species} wall material is not QPXIonWallFluxMaterial")
        if mp.get_parameter(text, path, "potential") != "potential_plasma":
            failures.append(f"{species} wall material does not use solved potential_plasma")
        if mp.get_parameter(text, path, "declare_suffix") != species:
            failures.append(f"{species} wall material suffix is not isolated")

    # Algebraic A5 reaction bookkeeping: each reaction conserves oxygen mass.
    mass_checks = {
        "O_to_half_O2": abs(M_O_KG_PER_MOL - 0.5 * M_O2_KG_PER_MOL),
        "O2s_to_O2": abs(M_O2_KG_PER_MOL - M_O2_KG_PER_MOL),
        "O2p_to_O2": abs(M_O2_KG_PER_MOL - M_O2_KG_PER_MOL),
        "Om_to_O": abs(M_O_KG_PER_MOL - M_O_KG_PER_MOL),
        "Op_to_O": abs(M_O_KG_PER_MOL - M_O_KG_PER_MOL),
        "Os_to_half_O2": abs(M_O_KG_PER_MOL - 0.5 * M_O2_KG_PER_MOL),
    }
    if any(value != 0.0 for value in mass_checks.values()):
        failures.append("reaction molar-mass bookkeeping is not exact")

    return {
        "status": "PASS" if not failures else "FAIL",
        "failures": failures,
        "independent_O2_variable": False,
        "constrained_O2": True,
        "wall_boundaries": list(PLASMA_WALLS),
        "reaction_mass_checks_kg_per_mol": mass_checks,
        "charged_interior_wall_double_counting_avoided": not any(
            "does not avoid" in item for item in failures
        ),
        "comsol_wall_object": "QPXIonWallFluxMaterial",
    }


def _stage_case(
    target: Path,
    *,
    parameters: Mapping[str, Any],
    mode: str,
) -> dict[str, Any]:
    base = (SOURCE / "heavy_base.i").read_text(encoding="utf-8")
    input_text, meta = _build_a6_case_input(base, parameters=parameters, mode=mode)
    preflight = _a5_preflight(input_text, meta)
    if preflight["status"] != "PASS":
        raise Issue27CombinedWallError(f"A5 preflight failed for {mode}: {preflight['failures']}")
    staging = stage_case(
        SOURCE,
        target,
        input_text=input_text,
        purge_directory_names=(".jitcache", "checkpoint", "checkpoints"),
        purge_patterns=("input_out*", "*.log", "*.e", "*.exo", "prepare_evidence.json"),
    )
    expected_path = target / "expected.json"
    if expected_path.is_file():
        expected = json.loads(expected_path.read_text(encoding="utf-8"))
        expected["field_strength"] = 0.0
        expected["n0"] = float(meta["electron_reference_density_m3"])
        expected_path.write_text(json.dumps(expected, indent=2, sort_keys=True) + "\n")
    evidence = {**meta, "a5_preflight": preflight}
    (target / "prepare_evidence.json").write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return {
        "source": str(SOURCE.resolve()),
        "staging": staging,
        "construction": meta,
        "a5_preflight": preflight,
    }


def _required_columns() -> tuple[str, ...]:
    names = [
        "time",
        AREA_PP,
        "mass_total",
        "mass_O2",
        "mass_O2s",
        "mass_O2p",
        "mass_O",
        "mass_Om",
        "mass_Op",
        "mass_Os",
        "w_O2_min",
        "w_O2s_min",
        "w_O2p_min",
        "w_O_min",
        "w_Om_min",
        "w_Op_min",
        "w_Os_min",
        "sum_w_min",
        "sum_w_max",
        "n_e_inventory",
        "n_e_min",
        "r31_charge_integral",
        "r31_gauss_flux_charge",
        O_RETURN_PP,
        ELECTRON_PP,
    ]
    for species in NEUTRALS:
        names.append(_neutral_names(species)[3])
    for species in CHARGED:
        for wall in PLASMA_WALLS:
            _, _, surface_pp, migration_pp = _charged_names(species, wall)
            names.extend((surface_pp, migration_pp))
    return tuple(names)


def _read_final_state(csv_path: Path) -> dict[str, Any]:
    if not csv_path.is_file():
        return {"status": "MISSING", "error": f"missing {csv_path.name}"}
    with csv_path.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) < 2:
        return {"status": "MISSING", "error": "need INITIAL and TIMESTEP_END rows"}
    row = rows[-1]
    required = _required_columns()
    missing = [name for name in required if name not in row]
    if missing:
        return {"status": "MISSING", "error": f"missing CSV columns: {missing}"}
    try:
        values = {name: float(row[name]) for name in required}
    except (TypeError, ValueError) as exc:
        return {"status": "INVALID", "error": str(exc)}
    if not all(math.isfinite(value) for value in values.values()):
        return {"status": "INVALID", "error": "non-finite final-state value"}
    return {"status": "MEASURED", **values}


def _rel_defect(measured: float, expected: float) -> float:
    return abs(measured - expected) / max(abs(expected), 1.0e-300)


def _physical_rate(value: float) -> float:
    # SideFVFluxBCIntegral follows the BC residual sign convention; the A-series
    # scientific convention is outward-positive magnitude.
    return abs(float(value))


def _case_fluxes(state: Mapping[str, Any]) -> dict[str, Any]:
    neutral = {
        species: _physical_rate(float(state[_neutral_names(species)[3]]))
        for species in NEUTRALS
    }
    charged: dict[str, Any] = {}
    for species in CHARGED:
        by_wall: dict[str, Any] = {}
        surface_total = 0.0
        migration_total = 0.0
        for wall in PLASMA_WALLS:
            _, _, surface_pp, migration_pp = _charged_names(species, wall)
            surface = _physical_rate(float(state[surface_pp]))
            migration = _physical_rate(float(state[migration_pp]))
            by_wall[wall] = {
                "surface_mass_rate_kg_s": surface,
                "migration_mass_rate_kg_s": migration,
                "total_mass_rate_kg_s": surface + migration,
            }
            surface_total += surface
            migration_total += migration
        charged[species] = {
            "surface_mass_rate_kg_s": surface_total,
            "migration_mass_rate_kg_s": migration_total,
            "total_mass_rate_kg_s": surface_total + migration_total,
            "by_wall": by_wall,
        }
    return {
        "neutral_mass_rates_kg_s": neutral,
        "charged": charged,
        "O_return_mass_rate_kg_s": _physical_rate(float(state[O_RETURN_PP])),
        "electron_ledger_raw_integral": float(state[ELECTRON_PP]),
    }


def _differential_evidence(
    states: Mapping[str, Mapping[str, Any]],
    *,
    n_ref_m3: float,
) -> dict[str, Any]:
    if any(states[name].get("status") != "MEASURED" for name in CASE_MODES):
        return {"status": "MISSING", "error": "one or more A6 states are not measured"}
    control = states["control"]
    times = [float(states[name]["time"]) for name in CASE_MODES]
    if times[0] <= 0.0 or any(
        not math.isclose(times[0], value, rel_tol=0.0, abs_tol=1.0e-18)
        for value in times[1:]
    ):
        return {"status": "INVALID", "error": f"inconsistent final times: {times}"}
    dt = times[0]

    def delta(case: Mapping[str, Any], key: str) -> float:
        return float(case[key]) - float(control[key])

    cases: dict[str, Any] = {}
    for mode in ("surface_only", "comsol_wall"):
        state = states[mode]
        fluxes = _case_fluxes(state)
        charged = fluxes["charged"]
        r_o2p = float(charged["O2p"]["total_mass_rate_kg_s"])
        r_op = float(charged["Op"]["total_mass_rate_kg_s"])
        r_om = float(charged["Om"]["total_mass_rate_kg_s"])
        r_o = float(fluxes["neutral_mass_rates_kg_s"]["O"])
        r_o2s = float(fluxes["neutral_mass_rates_kg_s"]["O2s"])
        r_os = float(fluxes["neutral_mass_rates_kg_s"]["Os"])
        r_o_return = float(fluxes["O_return_mass_rate_kg_s"])

        expected_mass_delta = {
            "mass_O2s": -r_o2s * dt,
            "mass_O2p": -r_o2p * dt,
            "mass_Om": -r_om * dt,
            "mass_Op": -r_op * dt,
            "mass_Os": -r_os * dt,
            "mass_O": (-r_o + r_o_return) * dt,
            "mass_O2": (r_o + r_o2s + r_os + r_o2p) * dt,
            "mass_total": 0.0,
        }
        measured_mass_delta = {
            key: delta(state, key) for key in expected_mass_delta
        }
        transfer_scale = max(
            sum(abs(value) for key, value in expected_mass_delta.items() if key != "mass_total"),
            1.0e-300,
        )
        mass_defects = {
            key: (
                abs(measured_mass_delta[key]) / transfer_scale
                if key == "mass_total"
                else _rel_defect(measured_mass_delta[key], expected_mass_delta[key])
            )
            for key in expected_mass_delta
        }

        net_heavy_molar_rate = (
            r_o2p / M_O2_KG_PER_MOL
            + r_op / M_O_KG_PER_MOL
            - r_om / M_O_KG_PER_MOL
        )
        expected_electron_inventory_change = -AVOGADRO * net_heavy_molar_rate * dt
        measured_electron_inventory_change = delta(state, "n_e_inventory")
        charge_scale = max(abs(FARADAY_C_PER_MOL * net_heavy_molar_rate * dt), 1.0e-300)
        charge_delta = delta(state, "r31_charge_integral")
        gauss_residual_delta = (
            (float(state["r31_gauss_flux_charge"]) - float(state["r31_charge_integral"]))
            - (
                float(control["r31_gauss_flux_charge"])
                - float(control["r31_charge_integral"])
            )
        )
        minima = (
            "w_O2_min",
            "w_O2s_min",
            "w_O2p_min",
            "w_O_min",
            "w_Om_min",
            "w_Op_min",
            "w_Os_min",
            "n_e_min",
        )
        composition_error = max(
            abs(float(state["sum_w_min"]) - 1.0),
            abs(float(state["sum_w_max"]) - 1.0),
        )
        positive_migration = (
            float(charged["O2p"]["migration_mass_rate_kg_s"])
            + float(charged["Op"]["migration_mass_rate_kg_s"])
        )
        negative_migration = float(charged["Om"]["migration_mass_rate_kg_s"])
        cases[mode] = {
            "flux_decomposition": fluxes,
            "expected_mass_delta_vs_control_kg": expected_mass_delta,
            "measured_mass_delta_vs_control_kg": measured_mass_delta,
            "mass_relative_defects": mass_defects,
            "net_heavy_charge_molar_rate_mol_s": net_heavy_molar_rate,
            "expected_electron_inventory_change": expected_electron_inventory_change,
            "measured_electron_inventory_change": measured_electron_inventory_change,
            "electron_inventory_relative_defect": _rel_defect(
                measured_electron_inventory_change,
                expected_electron_inventory_change,
            ),
            "delta_volume_charge_vs_control_C": charge_delta,
            "charge_restoration_ratio": abs(charge_delta) / charge_scale,
            "gauss_residual_delta_C": gauss_residual_delta,
            "composition_max_abs_error": composition_error,
            "nonnegative_state": all(float(state[key]) >= -1.0e-12 for key in minima),
            "migration_gate_diagnostic": {
                "positive_ion_migration_mass_rate_kg_s": positive_migration,
                "negative_ion_migration_mass_rate_kg_s": negative_migration,
                "all_side_rates_are_outward_magnitudes": True,
                "interpretation": (
                    "QPXIonWallFluxMaterial owns the COMSOL one-sided z*(n.E) clamp; "
                    "side-resolved rates expose which walls activate it"
                ),
            },
        }

    return {
        "status": "MEASURED",
        "final_time_s": dt,
        "combined_wall_area_m2": float(states["comsol_wall"][AREA_PP]),
        "wall_boundaries": list(PLASMA_WALLS),
        "excluded_boundaries": ["inlet", "outlet"],
        "electron_reference_density_m3": n_ref_m3,
        "cases": cases,
        "scientific_acceptance": "UNSET_EVIDENCE_ONLY",
        "acceptance_contract": (
            "A5 preflight must pass; A6 must preserve N-1 composition and positivity, "
            "show side-resolved COMSOL surface+migration fluxes, close reaction mass bookkeeping, "
            "and restore the charged-heavy/electron volume-charge ledger with Gauss consistency"
        ),
    }


def run_combined_comsol_wall_control(
    *,
    qpx: str | Path | None,
    results_root: Path,
    timeout: float,
    parameters: Mapping[str, Any],
) -> int:
    if timeout <= 0.0:
        raise Issue27CombinedWallError("timeout must be positive")
    exe = resolve_executable(qpx)
    validate_executable(exe)
    frozen = _validated_parameters(parameters)
    stamp = utc_timestamp().replace(":", "").replace("-", "")
    root = create_collision_safe_directory(
        results_root,
        f"issue27_a6_r4_qf1_combined_comsol_wall_{stamp}",
    )
    cases_root = root / "cases"
    logs = root / "logs"
    cases_root.mkdir(parents=True, exist_ok=True)
    logs.mkdir(parents=True, exist_ok=True)

    staged: dict[str, Any] = {}
    for mode in CASE_MODES:
        staged[mode] = _stage_case(cases_root / mode, parameters=parameters, mode=mode)
    n_ref = float(staged["control"]["construction"]["electron_reference_density_m3"])
    a5 = {
        mode: staged[mode]["a5_preflight"] for mode in CASE_MODES
    }
    if any(item["status"] != "PASS" for item in a5.values()):
        raise Issue27CombinedWallError(f"A5 preflight failed: {a5}")

    summary: dict[str, Any] = {
        "issue": 27,
        "experiment": "A5_A6_combined_comsol_wall_integration",
        "scientific_scope": (
            "one-shot A5 constrained-O2 preflight plus A6 all-six-wall Phase-A chemistry; "
            "charged walls use QPXIonWallFluxMaterial COMSOL surface+one-sided migration, SEE=0"
        ),
        "repository_head": issue91_run._repo_head(),
        "qpx_realpath": str(exe.resolve()),
        "qpx_sha256": issue91_run._sha256(exe),
        "parameters": frozen,
        "a5_preflight": a5,
        "staged": staged,
        "p2": {},
        "cases": {},
        "differential": {},
        "status": "NOT_RUN",
    }

    for mode in CASE_MODES:
        p2 = q0_run._p2(exe, cases_root / mode, logs / f"a6_{mode}_p2.log", timeout)
        summary["p2"][mode] = p2
        if p2["returncode"] != 0:
            summary["status"] = f"A6_P2_FAIL_{mode.upper()}"
            write_json_bundle(root, {"summary": ("summary.json", summary)})
            print(f"ISSUE27_A6_STATUS: {summary['status']}")
            print(f"EVIDENCE_DIR: {root}")
            return 2

    states: dict[str, Mapping[str, Any]] = {}
    for mode in CASE_MODES:
        case_dir = cases_root / mode
        runtime = q0_run._runtime(exe, case_dir, logs / f"a6_{mode}_runtime.log", timeout)
        state = _read_final_state(case_dir / "input_out.csv")
        summary["cases"][mode] = {"runtime": runtime, "state": state}
        if runtime["returncode"] != 0:
            summary["status"] = f"A6_RUNTIME_FAIL_{mode.upper()}"
            write_json_bundle(root, {"summary": ("summary.json", summary)})
            print(f"ISSUE27_A6_STATUS: {summary['status']}")
            print(f"EVIDENCE_DIR: {root}")
            return 1
        states[mode] = state

    evidence = _differential_evidence(states, n_ref_m3=n_ref)
    summary["differential"] = evidence
    summary["status"] = (
        "A5_A6_COMBINED_COMSOL_WALL_EVIDENCE_READY_NOT_ACCEPTED"
        if evidence.get("status") == "MEASURED"
        else "A6_EVIDENCE_MISSING"
    )
    write_json_bundle(root, {"summary": ("summary.json", summary)})
    print(f"ISSUE27_A6_STATUS: {summary['status']}")
    print("A5_PREFLIGHT: PASS")
    if evidence.get("status") == "MEASURED":
        for mode in ("surface_only", "comsol_wall"):
            item = evidence["cases"][mode]
            print(f"{mode.upper()}_DELTA_Q_C: {item['delta_volume_charge_vs_control_C']}")
            print(f"{mode.upper()}_CHARGE_RESTORATION_RATIO: {item['charge_restoration_ratio']}")
            print(f"{mode.upper()}_COMPOSITION_ERROR: {item['composition_max_abs_error']}")
            print(
                f"{mode.upper()}_POSITIVE_ION_MIGRATION_KG_S: "
                f"{item['migration_gate_diagnostic']['positive_ion_migration_mass_rate_kg_s']}"
            )
            print(
                f"{mode.upper()}_NEGATIVE_ION_MIGRATION_KG_S: "
                f"{item['migration_gate_diagnostic']['negative_ion_migration_mass_rate_kg_s']}"
            )
    print(f"EVIDENCE_DIR: {root}")
    return 0 if evidence.get("status") == "MEASURED" else 1


__all__ = [
    "PLASMA_WALLS",
    "Issue27CombinedWallError",
    "_build_a6_case_input",
    "_a5_preflight",
    "_validated_parameters",
    "run_combined_comsol_wall_control",
]
