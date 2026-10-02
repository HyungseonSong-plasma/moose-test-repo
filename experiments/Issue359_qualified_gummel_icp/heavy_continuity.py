"""Issue359 heavy-species transient continuity and wall-chemistry assembly/audit."""
from __future__ import annotations

import math
from typing import Any

from experiments.historical_recipe_support import issue192_s5r as s5r
from experiments.Issue27_surface_reactions.controlled_wall import combined as wall27
from physics_harness.adapters.moose import blocks as mb
from physics_harness.adapters.moose import parameters as mp

SOLVED_HEAVY = tuple(s5r.SOLVED_HEAVY)
CHARGED_HEAVY = ("O2p", "Om", "Op")
NEUTRAL_WALL_SPECIES = ("O", "O2s", "Os")
PLASMA_WALLS = tuple(wall27.PLASMA_WALLS)
ALL_BOUNDARIES = ("inlet", "outlet", *PLASMA_WALLS)

WALL_STICKING = {
    "O": 0.2,
    "O2s": 1.0,
    "Os": 0.2,
    "O2p": 1.0,
    "Om": 1.0,
    "Op": 1.0,
}
SURFACE_REACTIONS = {
    "O": "O -> 0.5 O2",
    "O2s": "O2s -> O2",
    "Os": "Os -> 0.5 O2",
    "O2p": "O2p -> O2",
    "Om": "Om -> O",
    "Op": "Op -> O",
}

CURRENT_TYPES = {
    "QPXFVConservativeMassFractionTimeDerivative": "PhysicsFVConservativeMassFractionTimeDerivative",
    "QPXFVMassFractionAdvection": "PhysicsFVMassFractionAdvection",
    "QPXFVMixtureAveragedDiffusion": "PhysicsFVMixtureAveragedDiffusion",
    "QPXFVElectrostaticDrift": "PhysicsFVElectrostaticDrift",
    "QPXFVHeavyMassElectromigrationCorrection": "PhysicsFVHeavyMassElectromigrationCorrection",
}


class HeavyContinuityError(RuntimeError):
    pass


def promote_current_types(text: str) -> str:
    for old, new in CURRENT_TYPES.items():
        text = text.replace(f"type = {old}", f"type = {new}")
    return text


def bind_gummel_potential(text: str, potential: str = "potential_from_gummel") -> str:
    for species in CHARGED_HEAVY:
        path = f"FVKernels/{species}_electrostatic_drift"
        if not mb.has_block(text, path):
            raise HeavyContinuityError(f"missing charged drift owner: {path}")
        text = mp.upsert_parameter(text, path, "potential", potential)
    for species in SOLVED_HEAVY:
        path = f"FVKernels/{species}_heavy_mass_em_correction"
        if not mb.has_block(text, path):
            raise HeavyContinuityError(f"missing heavy EM-correction owner: {path}")
        text = mp.upsert_parameter(text, path, "potential", potential)
    return text


def insert_volumetric_chemistry(text: str) -> str:
    """Reuse the accepted Stage-5 S5-R-v1 heavy reaction ledger."""
    for path in (
        "FunctorMaterials/issue359_n_e_physical",
        "FunctorMaterials/issue359_mean_en_solved",
    ):
        mb.require_absent(text, path)

    text = mb.insert_child_block(
        text,
        "FunctorMaterials",
        """  [issue359_n_e_physical]
    type = ADParsedFunctorMaterial
    property_name = n_e_physical
    functor_names = 'electron_density_from_gummel'
    functor_symbols = 'ne'
    expression = 'ne'
    block = plasma
  []""",
    )
    text = mb.insert_child_block(
        text,
        "FunctorMaterials",
        """  [issue359_mean_en_solved]
    type = ADParsedFunctorMaterial
    property_name = mean_en_solved
    functor_names = 'mean_energy_from_gummel'
    functor_symbols = 'mean_ev'
    expression = 'mean_ev'
    block = plasma
  []""",
    )
    text = s5r._insert_concentrations(text)
    text = s5r._insert_kinetic_owners(text)
    text = s5r._insert_species_sources(text)
    return text


def insert_surface_reactions(
    text: str, potential: str = "potential_from_gummel"
) -> str:
    """Install accepted species-specific wall chemistry on all six plasma walls."""
    wall_list = "'" + " ".join(PLASMA_WALLS) + "'"

    # Neutral thermal-sticking reactions:
    # O -> 0.5 O2, O2s -> O2, Os -> 0.5 O2.
    for species in NEUTRAL_WALL_SPECIES:
        cfg = wall27.NEUTRALS[species]
        material = f"issue359_{species}_wall_flux_material"
        functor = f"issue359_{species}_wall_flux_outward"
        bc_name = f"issue359_{species}_wall_loss"
        pp_name = f"issue359_{species}_wall_rate"
        symbol = species.lower()
        expression = wall27._neutral_flux_expression(
            WALL_STICKING[species], float(cfg["molar_mass"]), symbol
        )
        for path in (
            f"FunctorMaterials/{material}",
            f"FVBCs/{bc_name}",
            f"Postprocessors/{pp_name}",
        ):
            mb.require_absent(text, path)
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
    factor = -1.0
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

    # Charged species use the accepted COMSOL-style split:
    # thermal surface neutralization + one-sided electric migration.
    for species in CHARGED_HEAVY:
        cfg = wall27.CHARGED[species]
        density_property = f"issue359_n_{species}"
        density_material = f"issue359_{species}_number_density"
        flux_material = f"issue359_{species}_wall_flux"
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
    expression = 'rho*w*{wall27.AVOGADRO:.17g}/{float(cfg['molar_mass']):.17g}'
    block = plasma
  []""",
        )
        text = mb.insert_child_block(
            text,
            "FunctorMaterials",
            f"""  [{flux_material}]
    type = PhysicsIonWallFluxMaterial
    ion_number_density = {density_property}
    potential = {potential}
    mobility = {cfg['mobility']}
    gas_temperature = T_g
    charge_number = {int(cfg['charge'])}
    molar_mass = {float(cfg['molar_mass']):.17g}
    sticking = {WALL_STICKING[species]:.17g}
    declare_suffix = {species}
    block = plasma
  []""",
        )

        for wall in PLASMA_WALLS:
            surface_bc = f"issue359_{species}_surface_{wall}"
            migration_bc = f"issue359_{species}_migration_{wall}"
            surface_pp = f"{surface_bc}_rate"
            migration_pp = f"{migration_bc}_rate"
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
    factor = -1.0
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
    factor = -1.0
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

    # O+/O- neutralization returns equal mass as atomic O.
    # O2+ removal is returned through constrained O2 = 1 - sum(solved species).
    mb.require_absent(text, "FunctorMaterials/issue359_O_return_material")
    mb.require_absent(text, "FVBCs/issue359_O_return")
    text = mb.insert_child_block(
        text,
        "FunctorMaterials",
        """  [issue359_O_return_material]
    type = ADParsedFunctorMaterial
    property_name = issue359_O_return_mass_flux_inward
    functor_names = 'ion_surface_mass_flux_Op ion_migration_mass_flux_Op ion_surface_mass_flux_Om ion_migration_mass_flux_Om'
    functor_symbols = 'sop mop som mom'
    expression = 'sop+mop+som+mom'
    block = plasma
  []""",
    )
    text = mb.insert_child_block(
        text,
        "FVBCs",
        f"""  [issue359_O_return]
    type = FVFunctorNeumannBC
    variable = w_O
    boundary = {wall_list}
    functor = issue359_O_return_mass_flux_inward
    factor = 1.0
  []""",
    )
    return text


def _kernel_record(
    text: str,
    species: str,
    path: str,
    expected_type: str,
    **expected: str,
) -> dict[str, Any]:
    exists = mb.has_block(text, path)
    actual_type = mp.get_parameter(text, path, "type") if exists else None
    variable = mp.get_parameter(text, path, "variable") if exists else None
    values = {
        name: (mp.get_parameter(text, path, name) if exists else None)
        for name in expected
    }
    ok = exists and actual_type == expected_type and variable == f"w_{species}"
    ok = ok and all(values[name] == value for name, value in expected.items())
    return {
        "path": path,
        "expected_type": expected_type,
        "actual_type": actual_type,
        "variable": variable,
        "parameters": values,
        "ok": ok,
    }


def audit(text: str, potential: str = "potential_from_gummel") -> dict[str, Any]:
    """Term-by-term continuity + species-specific surface-reaction audit."""
    checks: dict[str, bool] = {}
    species_report: dict[str, Any] = {}

    for species in SOLVED_HEAVY:
        terms: dict[str, Any] = {}
        terms["time"] = _kernel_record(
            text,
            species,
            f"FVKernels/{species}_time",
            "PhysicsFVConservativeMassFractionTimeDerivative",
            rho="rho_mat",
        )
        terms["advection"] = _kernel_record(
            text,
            species,
            f"FVKernels/{species}_advection",
            "PhysicsFVMassFractionAdvection",
            rho="rho_mat",
        )
        terms["diffusion"] = _kernel_record(
            text,
            species,
            f"FVKernels/{species}_diffusion",
            "PhysicsFVMixtureAveragedDiffusion",
            rho="rho_mat",
            diffusivity=f"D_mix_{species}",
            mean_molar_mass="Mn_mix",
            include_molar_mass_gradient="true",
        )
        terms["em_correction"] = _kernel_record(
            text,
            species,
            f"FVKernels/{species}_heavy_mass_em_correction",
            "PhysicsFVHeavyMassElectromigrationCorrection",
            potential=potential,
            rho="rho_mat",
            ion_mass_fractions="'w_O2p w_Om w_Op'",
            ion_mobilities="'mu_O2p mu_Om mu_Op'",
            ion_charges="'1 -1 1'",
        )
        terms["reaction_source"] = _kernel_record(
            text,
            species,
            f"FVKernels/s5r_source_{species}",
            "PhysicsFVSpeciesReactionSource",
            source=f"S_{species}_s5r",
        )

        if species in CHARGED_HEAVY:
            cfg = wall27.CHARGED[species]
            terms["electrostatic_drift"] = _kernel_record(
                text,
                species,
                f"FVKernels/{species}_electrostatic_drift",
                "PhysicsFVElectrostaticDrift",
                potential=potential,
                mobility=str(cfg["mobility"]),
                charge_number=str(int(cfg["charge"])),
                carrier="rho_mat",
            )
            drift_path = f"FVKernels/{species}_electrostatic_drift"
            avoided = set(
                mp.words(mp.get_parameter(text, drift_path, "boundaries_to_avoid") or "")
            )
            terms["electrostatic_drift"]["boundaries_to_avoid"] = sorted(avoided)
            terms["electrostatic_drift"]["ok"] = (
                terms["electrostatic_drift"]["ok"]
                and avoided == set(ALL_BOUNDARIES)
            )
        else:
            path = f"FVKernels/{species}_electrostatic_drift"
            terms["electrostatic_drift"] = {
                "path": path,
                "expected": "not_applicable_for_neutral",
                "ok": not mb.has_block(text, path),
            }

        for term, record in terms.items():
            checks[f"continuity:{species}:{term}"] = bool(record["ok"])
        species_report[species] = {"variable": f"w_{species}", "terms": terms}

    wall_report: dict[str, Any] = {}
    for species in NEUTRAL_WALL_SPECIES:
        path = f"FVBCs/issue359_{species}_wall_loss"
        exists = mb.has_block(text, path)
        boundaries = (
            set(mp.words(mp.get_parameter(text, path, "boundary") or ""))
            if exists
            else set()
        )
        ok = (
            exists
            and mp.get_parameter(text, path, "type") == "FVFunctorNeumannBC"
            and mp.get_parameter(text, path, "variable") == f"w_{species}"
            and boundaries == set(PLASMA_WALLS)
            and math.isclose(
                float(mp.get_parameter(text, path, "factor") or "nan"),
                -1.0,
                rel_tol=0.0,
                abs_tol=1.0e-15,
            )
        )
        checks[f"wall:{species}:surface_reaction"] = ok
        wall_report[species] = {
            "reaction": SURFACE_REACTIONS[species],
            "sticking": WALL_STICKING[species],
            "bc": path,
            "walls": sorted(boundaries),
            "ok": ok,
        }

    for species in CHARGED_HEAVY:
        cfg = wall27.CHARGED[species]
        material = f"FunctorMaterials/issue359_{species}_wall_flux"
        material_ok = (
            mb.has_block(text, material)
            and mp.get_parameter(text, material, "type") == "PhysicsIonWallFluxMaterial"
            and mp.get_parameter(text, material, "potential") == potential
            and mp.get_parameter(text, material, "mobility") == cfg["mobility"]
            and int(mp.get_parameter(text, material, "charge_number") or "0")
            == int(cfg["charge"])
            and math.isclose(
                float(mp.get_parameter(text, material, "sticking") or "nan"),
                WALL_STICKING[species],
                rel_tol=0.0,
                abs_tol=1.0e-15,
            )
        )
        side_checks: dict[str, bool] = {}
        for wall in PLASMA_WALLS:
            surface = f"FVBCs/issue359_{species}_surface_{wall}"
            migration = f"FVBCs/issue359_{species}_migration_{wall}"
            side_checks[wall] = (
                mb.has_block(text, surface)
                and mb.has_block(text, migration)
                and mp.get_parameter(text, surface, "boundary") == wall
                and mp.get_parameter(text, migration, "boundary") == wall
                and mp.get_parameter(text, surface, "variable") == f"w_{species}"
                and mp.get_parameter(text, migration, "variable") == f"w_{species}"
            )
        ok = material_ok and all(side_checks.values())
        checks[f"wall:{species}:surface_plus_migration"] = ok
        wall_report[species] = {
            "reaction": SURFACE_REACTIONS[species],
            "sticking": WALL_STICKING[species],
            "material": material,
            "side_checks": side_checks,
            "ok": ok,
        }

    o_return = "FVBCs/issue359_O_return"
    o_return_ok = (
        mb.has_block(text, o_return)
        and mp.get_parameter(text, o_return, "variable") == "w_O"
        and set(mp.words(mp.get_parameter(text, o_return, "boundary") or ""))
        == set(PLASMA_WALLS)
    )
    checks["wall:charged_neutralization:O_return"] = o_return_ok

    failed = sorted(name for name, ok in checks.items() if not ok)
    return {
        "status": "PASS" if not failed else "FAIL",
        "checks": checks,
        "failed_checks": failed,
        "species": species_report,
        "wall_reactions": wall_report,
        "charged_neutralization_O_return": o_return_ok,
        "constrained_O2_wall_return": (
            "O2p -> O2 is represented by the N-1 constrained O2 closure"
        ),
    }
