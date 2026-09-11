"""Issue #192 Stage-5 S5-R representative production chemistry assembly.

This module composes the accepted #31 R4-QF1 solved-electrostatic execution topology
with the accepted Stage-4 solved-electron-energy bridge and the frozen S5-R-v1
volumetric chemistry ledger. It deliberately does not add wall/SEE physics, does
not invent deferred reactions, and does not independently re-evaluate kinetics
inside any downstream projection.
"""
from __future__ import annotations

import math
from typing import Any

from physics_harness.adapters.moose import blocks as mb
from physics_harness.adapters.moose import parameters as mp
from experiments.historical_recipe_support.issue31_r4_qf1 import (
    ELECTROSTATIC_BOUNDARIES_TO_AVOID,
    FEEDBACK_POTENTIAL,
    build_r4_qf1_input,
)

AVOGADRO = 6.02214076e23
ELECTRON_MASS_KG = 9.1093837139e-31
K_B_OVER_E_EV_PER_K = 8.617333262145e-5
ENERGY_REFERENCE_EV = 5.73276
M_O2 = 0.032
M_O = 0.016

ADMITTED_CHANNELS = (
    "EI01",
    "EI02",
    "EI10",
    "EI16",
    "EI17",
    "EI19",
    "EI18_O_TO_OS",
    "EI20_O_IONIZATION",
    "EDETACH_OM",
    "H01_OP_O2_CHARGE_TRANSFER",
    "H02_OM_OP_NEUTRALIZATION",
    "H03_OM_O2P_TO_3O",
    "H04_OM_O2P_TO_O_O2",
    "H05_OM_O_DETACHMENT",
)

PROGRESS = {
    "EI01": "R_attachment",
    "EI02": "R_elastic_O2",
    "EI10": "R_O2s",
    "EI16": "R_ion_O2",
    "EI17": "R_elastic_O",
    "EI19": "R_excitation_O_4p192",
    "EI18_O_TO_OS": "R_excitation_O_1p968",
    "EI20_O_IONIZATION": "R_ion_O",
    "EDETACH_OM": "R_detach_Om",
    "H01_OP_O2_CHARGE_TRANSFER": "reaction_rate_H01_Op_O2_charge_transfer",
    "H02_OM_OP_NEUTRALIZATION": "reaction_rate_H02_Om_Op_neutralization",
    "H03_OM_O2P_TO_3O": "reaction_rate_H03_Om_O2p_to_3O",
    "H04_OM_O2P_TO_O_O2": "reaction_rate_H04_Om_O2p_to_O_O2",
    "H05_OM_O_DETACHMENT": "reaction_rate_H05_Om_O_to_O2_electron",
}

OWNER_BLOCKS = {
    "EI01": "FunctorMaterials/s5r_ei01_rate",
    "EI02": "FunctorMaterials/s5r_ei02_rate",
    "EI10": "FunctorMaterials/s5r_ei10_rate",
    "EI16": "FunctorMaterials/s5r_ei16_rate",
    "EI17": "FunctorMaterials/s5r_ei17_rate",
    "EI19": "FunctorMaterials/s5r_ei19_rate",
    "EI18_O_TO_OS": "FunctorMaterials/s5r_ei18_rate",
    "EI20_O_IONIZATION": "FunctorMaterials/s5r_ei20_rate",
    "EDETACH_OM": "FunctorMaterials/s5r_edetach_rate",
    "H01_OP_O2_CHARGE_TRANSFER": "FunctorMaterials/s5r_h01_h04_rates",
    "H02_OM_OP_NEUTRALIZATION": "FunctorMaterials/s5r_h01_h04_rates",
    "H03_OM_O2P_TO_3O": "FunctorMaterials/s5r_h01_h04_rates",
    "H04_OM_O2P_TO_O_O2": "FunctorMaterials/s5r_h01_h04_rates",
    "H05_OM_O_DETACHMENT": "FunctorMaterials/s5r_h05_rate",
}

RATE_TABLES = {
    "EI01": "o2_attachment.txt",
    "EI02": "o2_elastic.txt",
    "EI16": "o2_ionization.txt",
    "EI17": "o_elastic.txt",
    "EI19": "o_excitation_1s.txt",
    "EI18_O_TO_OS": "o_excitation_1d.txt",
    "EI20_O_IONIZATION": "o_ionization.txt",
}

H01_H04_ACTIVE = (
    "H01_Op_O2_charge_transfer",
    "H02_Om_Op_neutralization",
    "H03_Om_O2p_to_3O",
    "H04_Om_O2p_to_O_O2",
)
H05_ACTIVE = "H05_Om_O_to_O2_electron"

DEFERRED_TOKENS = (
    "e + O2 -> e + O + O",
    "e + O2 -> e + O + Os",
    "Om + Arp -> O + Ar",
)

ENERGY_LOSS_EV = {
    "EI10": 0.977,
    "EI16": 12.06,
    "EI19": 4.192,
    "EI18_O_TO_OS": 1.968,
    "EI20_O_IONIZATION": 13.618,
    "EDETACH_OM": 12.0,
}

SOLVED_HEAVY = ("O2s", "O2p", "O", "Om", "Op", "Os")
MOLAR_MASS = {
    "O2": M_O2,
    "O2s": M_O2,
    "O2p": M_O2,
    "O": M_O,
    "Om": M_O,
    "Op": M_O,
    "Os": M_O,
}

# Stoichiometric projection for channels without inherited dedicated projectors.
HEAVY_STOICH = {
    "EI01": {"O2": -1, "O": 1, "Om": 1},
    "EI18_O_TO_OS": {"O": -1, "Os": 1},
    "EI20_O_IONIZATION": {"O": -1, "Op": 1},
    "EDETACH_OM": {"Om": -1, "O": 1},
    "H01_OP_O2_CHARGE_TRANSFER": {"Op": -1, "O2": -1, "O": 1, "O2p": 1},
    "H02_OM_OP_NEUTRALIZATION": {"Om": -1, "Op": -1, "O": 2},
    "H03_OM_O2P_TO_3O": {"Om": -1, "O2p": -1, "O": 3},
    "H04_OM_O2P_TO_O_O2": {"Om": -1, "O2p": -1, "O": 1, "O2": 1},
    "H05_OM_O_DETACHMENT": {"Om": -1, "O": -1, "O2": 1},
}
ELECTRON_STOICH = {
    "EI01": -1,
    "EI16": 1,
    "EI20_O_IONIZATION": 1,
    "EDETACH_OM": 1,
    "H05_OM_O_DETACHMENT": 1,
}


class Issue192S5RError(RuntimeError):
    pass


def _top_level_float(text: str, name: str) -> float:
    import re

    matches = re.findall(rf"(?m)^\s*{re.escape(name)}\s*=\s*([^#\r\n]+)", text)
    if len(matches) != 1:
        raise Issue192S5RError(f"cannot resolve unique top-level scalar {name}")
    value = float(matches[0].strip())
    if not math.isfinite(value):
        raise Issue192S5RError(f"non-finite top-level scalar {name}={value}")
    return value


def _insert_material(text: str, name: str, body: str) -> str:
    mb.require_absent(text, f"FunctorMaterials/{name}")
    return mb.insert_child_block(
        text,
        "FunctorMaterials",
        f"  [{name}]\n{body}\n  []",
    )


def _insert_kernel(text: str, name: str, body: str) -> str:
    mb.require_absent(text, f"FVKernels/{name}")
    return mb.insert_child_block(text, "FVKernels", f"  [{name}]\n{body}\n  []")


def _insert_energy_state(text: str) -> str:
    for path in (
        "Variables/n_epsilon",
        "FunctorMaterials/s5r_mean_energy",
        "FVKernels/s5r_n_epsilon_time",
        "FVKernels/s5r_n_epsilon_diffusion",
    ):
        mb.require_absent(text, path)

    text = mb.insert_child_block(
        text,
        "Variables",
        """  [n_epsilon]
    type = MooseVariableFVReal
    initial_condition = 1.0
    block = plasma
  []""",
    )
    text = _insert_material(
        text,
        "s5r_mean_energy",
        f"""    type = PhysicsElectronMeanEnergyMaterial
    electron_energy_density = n_epsilon
    electron_density = n_e
    energy_reference_eV = {ENERGY_REFERENCE_EV:.17g}
    block = plasma""",
    )

    # Promote the accepted R4 particle-transport lookup to the accepted Stage-4
    # solved-energy lookup owner. Particle property names remain unchanged.
    text = mp.upsert_parameter(
        text,
        "FunctorMaterials/electron_transport",
        "type",
        "PhysicsElectronTransportLookupMaterial",
    )
    text = mp.upsert_parameter(
        text,
        "FunctorMaterials/electron_transport",
        "mean_energy",
        "mean_en_solved",
    )
    text = mp.upsert_parameter(
        text,
        "FunctorMaterials/electron_transport",
        "bounds_policy",
        "error",
    )
    text = _insert_kernel(
        text,
        "s5r_n_epsilon_time",
        """    type = FVTimeKernel
    variable = n_epsilon
    block = plasma""",
    )
    text = _insert_kernel(
        text,
        "s5r_n_epsilon_diffusion",
        """    type = FVDiffusion
    variable = n_epsilon
    coeff = electron_energy_diffusion
    block = plasma""",
    )
    return text


def _insert_concentrations(text: str) -> str:
    text = _insert_material(
        text,
        "s5r_c_O2",
        f"""    type = ADParsedFunctorMaterial
    property_name = c_O2
    functor_names = 'rho_mat w_O2_constraint'
    functor_symbols = 'rho wo2'
    expression = 'rho*wo2/{M_O2:.17g}'
    block = plasma""",
    )
    text = _insert_material(
        text,
        "s5r_c_O",
        f"""    type = ADParsedFunctorMaterial
    property_name = c_O
    functor_names = 'rho_mat w_O'
    functor_symbols = 'rho wo'
    expression = 'rho*wo/{M_O:.17g}'
    block = plasma""",
    )
    text = _insert_material(
        text,
        "s5r_c_Om",
        f"""    type = ADParsedFunctorMaterial
    property_name = c_Om
    functor_names = 'rho_mat w_Om'
    functor_symbols = 'rho wom'
    expression = 'rho*wom/{M_O:.17g}'
    block = plasma""",
    )
    text = _insert_material(
        text,
        "s5r_c_electron",
        f"""    type = ADParsedFunctorMaterial
    property_name = c_electron
    functor_names = 'n_e_physical'
    functor_symbols = 'nephys'
    expression = 'nephys/{AVOGADRO:.17g}'
    block = plasma""",
    )
    text = _insert_material(
        text,
        "s5r_Te_eV",
        """    type = ADParsedFunctorMaterial
    property_name = Te_eV
    functor_names = 'mean_en_solved'
    functor_symbols = 'meanen'
    expression = '(2.0/3.0)*meanen'
    block = plasma""",
    )
    return text


def _insert_kinetic_owners(text: str) -> str:
    # Inherited Stage-3/4 channels.
    for name, table, target, progress in (
        ("s5r_ei01_rate", RATE_TABLES["EI01"], "c_O2", PROGRESS["EI01"]),
        ("s5r_ei02_rate", RATE_TABLES["EI02"], "c_O2", PROGRESS["EI02"]),
        ("s5r_ei17_rate", RATE_TABLES["EI17"], "c_O", PROGRESS["EI17"]),
        ("s5r_ei19_rate", RATE_TABLES["EI19"], "c_O", PROGRESS["EI19"]),
        ("s5r_ei18_rate", RATE_TABLES["EI18_O_TO_OS"], "c_O", PROGRESS["EI18_O_TO_OS"]),
        ("s5r_ei20_rate", RATE_TABLES["EI20_O_IONIZATION"], "c_O", PROGRESS["EI20_O_IONIZATION"]),
    ):
        text = _insert_material(
            text,
            name,
            f"""    type = PhysicsElectronImpactRateMaterial
    rate_table_file = {table}
    mean_energy = mean_en_solved
    electron_number_density = n_e_physical
    target_molar_concentration = {target}
    reaction_progress = {progress}
    block = plasma""",
        )

    text = _insert_material(
        text,
        "s5r_ei10_rate",
        """    type = PhysicsElectronImpactO2sExcitationMaterial
    electron_number_density = n_e_physical
    o2_molar_concentration = c_O2
    block = plasma""",
    )
    text = _insert_material(
        text,
        "s5r_ei10_projection",
        """    type = PhysicsO2sExcitationSourceMaterial
    reaction_progress = R_O2s
    o2_molar_mass = 0.031998
    block = plasma""",
    )

    text = _insert_material(
        text,
        "s5r_ei16_rate",
        f"""    type = PhysicsElectronImpactIonizationMaterial
    rate_table_file = {RATE_TABLES["EI16"]}
    mean_energy = mean_en_solved
    electron_number_density = n_e_physical
    o2_molar_concentration = c_O2
    block = plasma""",
    )
    text = _insert_material(
        text,
        "s5r_ei16_projection",
        """    type = PhysicsO2IonizationSourceMaterial
    reaction_progress = R_ion_O2
    o2_molar_mass = 0.031998
    block = plasma""",
    )

    # Accepted S5-C electron detachment law.
    text = _insert_material(
        text,
        "s5r_edetach_rate",
        f"""    type = ADParsedFunctorMaterial
    property_name = {PROGRESS["EDETACH_OM"]}
    functor_names = 'c_electron c_Om Te_eV'
    functor_symbols = 'celec comneg teev'
    expression = '{5.47e-14 * AVOGADRO:.17g}*celec*comneg*exp(-2.98/teev)*(teev^0.324)'
    block = plasma""",
    )

    text = _insert_material(
        text,
        "s5r_h01_h04_rates",
        f"""    type = PhysicsReactionRateMaterial
    chemistry_file = stage5_s5d_oxygen_heavy.txt
    density = rho_mat
    temperature = T_g
    species = 'O2 O2p O Om Op'
    mass_fractions = 'w_O2_constraint w_O2p w_O w_Om w_Op'
    active_reactions = '{' '.join(H01_H04_ACTIVE)}'
    block = plasma""",
    )
    text = _insert_material(
        text,
        "s5r_h05_rate",
        f"""    type = PhysicsReactionRateMaterial
    chemistry_file = stage5_s5e_h05_oxygen_heavy.txt
    density = rho_mat
    temperature = T_g
    species = 'O2 O Om'
    mass_fractions = 'w_O2_constraint w_O w_Om'
    active_reactions = '{H05_ACTIVE}'
    block = plasma""",
    )
    return text


def _term(coef: float, functor: str, symbol: str) -> str:
    if coef == 1.0:
        return symbol
    if coef == -1.0:
        return f"-{symbol}"
    return f"{coef:.17g}*{symbol}"


def _insert_species_sources(text: str) -> str:
    # Inherited dedicated EI10/EI16 projectors are reused rather than rebuilt.
    dedicated = {
        "O2": [
            ("O2_o2s_excitation_mass_source", "ei10_o2"),
            ("O2_ionization_mass_source", "ei16_o2"),
        ],
        "O2s": [("O2s_excitation_mass_source", "ei10_o2s")],
        "O2p": [("O2p_ionization_mass_source", "ei16_o2p")],
    }

    for species in ("O2",) + SOLVED_HEAVY:
        functors: list[str] = []
        symbols: list[str] = []
        terms: list[str] = []

        for functor, symbol in dedicated.get(species, []):
            functors.append(functor)
            symbols.append(symbol)
            terms.append(symbol)

        for channel, stoich in HEAVY_STOICH.items():
            nu = stoich.get(species, 0)
            if not nu:
                continue
            progress = PROGRESS[channel]
            symbol = f"r{len(symbols)}"
            functors.append(progress)
            symbols.append(symbol)
            terms.append(_term(MOLAR_MASS[species] * float(nu), progress, symbol))

        property_name = (
            "S_O2_s5r_expected" if species == "O2" else f"S_{species}_s5r"
        )
        expression = "+".join(terms).replace("+-", "-") if terms else "0"
        text = _insert_material(
            text,
            f"s5r_source_{species}",
            f"""    type = ADParsedFunctorMaterial
    property_name = {property_name}
    functor_names = '{' '.join(functors)}'
    functor_symbols = '{' '.join(symbols)}'
    expression = '{expression}'
    block = plasma""",
        )

    # One downstream mass-source kernel per solved heavy species.
    for species in SOLVED_HEAVY:
        text = _insert_kernel(
            text,
            f"s5r_source_{species}",
            f"""    type = PhysicsFVSpeciesReactionSource
    variable = w_{species}
    source = S_{species}_s5r
    block = plasma""",
        )
    return text


def _insert_electron_source(text: str, *, n_ref: float) -> str:
    functors = [
        PROGRESS["EI01"],
        "electron_ionization_number_source",
        PROGRESS["EI20_O_IONIZATION"],
        PROGRESS["EDETACH_OM"],
        PROGRESS["H05_OM_O_DETACHMENT"],
    ]
    text = _insert_material(
        text,
        "s5r_electron_source",
        f"""    type = ADParsedFunctorMaterial
    property_name = S_e_s5r
    functor_names = '{' '.join(functors)}'
    functor_symbols = 'rattach sei16 rei20 rdetach rh05'
    expression = '{AVOGADRO:.17g}*(-rattach+rei20+rdetach+rh05)+sei16'
    block = plasma""",
    )
    text = _insert_kernel(
        text,
        "s5r_electron_source",
        f"""    type = PhysicsFVElectronReactionSource
    variable = n_e
    number_source = S_e_s5r
    n_ref = {n_ref:.17g}
    block = plasma""",
    )
    return text


def _insert_energy_sources(text: str, *, n_ref: float) -> str:
    # EI02/EI17 elastic exchange: one strict kinetic progress each, then only
    # state-dependent energy algebra downstream using the canonical T_g.
    for suffix, channel, mass in (
        ("ei02", "EI02", M_O2),
        ("ei17", "EI17", M_O),
    ):
        particle_mass = mass / AVOGADRO
        factor = (
            (3.0 * ELECTRON_MASS_KG / particle_mass)
            * AVOGADRO
            / (n_ref * ENERGY_REFERENCE_EV)
        )
        text = _insert_material(
            text,
            f"s5r_{suffix}_elastic_energy",
            f"""    type = ADParsedFunctorMaterial
    property_name = S_{suffix}_elastic_hat
    functor_names = 'mean_en_solved T_g {PROGRESS[channel]}'
    functor_symbols = 'meanE tgas rprog'
    expression = '-{factor:.17g}*(0.66666666666666663*meanE-{K_B_OVER_E_EV_PER_K:.17g}*tgas)*rprog'
    block = plasma""",
        )
        text = _insert_kernel(
            text,
            f"s5r_{suffix}_elastic_energy",
            f"""    type = FVCoupledForce
    variable = n_epsilon
    v = S_{suffix}_elastic_hat
    coef = 1
    block = plasma""",
        )

    for channel in (
        "EI10",
        "EI16",
        "EI19",
        "EI18_O_TO_OS",
        "EI20_O_IONIZATION",
        "EDETACH_OM",
    ):
        coef = -(ENERGY_LOSS_EV[channel] * AVOGADRO / (n_ref * ENERGY_REFERENCE_EV))
        text = _insert_kernel(
            text,
            f"s5r_energy_{channel.lower()}",
            f"""    type = FVCoupledForce
    variable = n_epsilon
    v = {PROGRESS[channel]}
    coef = {coef:.17g}
    block = plasma""",
        )
    return text


def _insert_observables(text: str) -> str:
    for channel in ADMITTED_CHANNELS:
        name = "s5r_progress_" + channel.lower()
        mb.require_absent(text, f"Postprocessors/{name}")
        text = mb.insert_child_block(
            text,
            "Postprocessors",
            f"""  [{name}]
    type = ElementAverageFunctorPostprocessor
    functor = {PROGRESS[channel]}
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []""",
        )
    for name, functor in (
        ("s5r_n_epsilon_min", "n_epsilon"),
        ("s5r_mean_en_min", "mean_en_solved"),
        ("s5r_mean_en_max", "mean_en_solved"),
        ("s5r_O2_source_expected_avg", "S_O2_s5r_expected"),
        ("s5r_electron_source_avg", "S_e_s5r"),
    ):
        typ = "ElementAverageFunctorPostprocessor"
        extra = ""
        if name.endswith("_min"):
            typ = "ADElementExtremeFunctorValue"
            extra = "\n    value_type = min"
        elif name.endswith("_max"):
            typ = "ADElementExtremeFunctorValue"
            extra = "\n    value_type = max"
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


def _owner_paths_by_type(text: str) -> set[str]:
    kinetic_types = {
        "PhysicsElectronImpactRateMaterial",
        "PhysicsElectronImpactO2sExcitationMaterial",
        "PhysicsElectronImpactIonizationMaterial",
        "PhysicsReactionRateMaterial",
    }
    paths = set()
    for path in mp.direct_children(text, "FunctorMaterials"):
        if mp.get_parameter(text, path, "type") in kinetic_types:
            paths.add(path)
    # EDETACH is deliberately an ADParsed owner, identified by its property.
    for path in mp.direct_children(text, "FunctorMaterials"):
        if (
            mp.get_parameter(text, path, "type") == "ADParsedFunctorMaterial"
            and mp.get_parameter(text, path, "property_name") == PROGRESS["EDETACH_OM"]
        ):
            paths.add(path)
    return paths


def audit_s5r_input(text: str) -> dict[str, Any]:
    checks: dict[str, bool] = {}

    checks["solved_energy_variable"] = mb.has_block(text, "Variables/n_epsilon")
    checks["mean_energy_bridge"] = (
        mp.get_parameter(text, "FunctorMaterials/s5r_mean_energy", "type")
        == "PhysicsElectronMeanEnergyMaterial"
        and mp.get_parameter(
            text, "FunctorMaterials/s5r_mean_energy", "electron_energy_density"
        )
        == "n_epsilon"
        and mp.get_parameter(
            text, "FunctorMaterials/s5r_mean_energy", "electron_density"
        )
        == "n_e"
    )
    checks["strict_solved_energy_transport"] = (
        mp.get_parameter(text, "FunctorMaterials/electron_transport", "type")
        == "PhysicsElectronTransportLookupMaterial"
        and mp.get_parameter(text, "FunctorMaterials/electron_transport", "mean_energy")
        == "mean_en_solved"
        and mp.get_parameter(text, "FunctorMaterials/electron_transport", "gas_temperature")
        == "T_g"
        and mp.get_parameter(text, "FunctorMaterials/electron_transport", "bounds_policy")
        == "error"
    )
    checks["solved_poisson_feedback_preserved"] = (
        mp.get_parameter(text, "FVKernels/n_e_drift", "potential") == FEEDBACK_POTENTIAL
        and mp.get_parameter(text, "FVKernels/O2p_electrostatic_drift", "potential")
        == FEEDBACK_POTENTIAL
    )

    expected_owner_paths = set(OWNER_BLOCKS.values())
    checks["exact_kinetic_owner_block_set"] = _owner_paths_by_type(text) == expected_owner_paths

    # Generic electron-impact owners.
    for channel in ("EI01", "EI02", "EI17", "EI19", "EI18_O_TO_OS", "EI20_O_IONIZATION"):
        path = OWNER_BLOCKS[channel]
        checks[f"owner:{channel}"] = (
            mp.get_parameter(text, path, "type") == "PhysicsElectronImpactRateMaterial"
            and mp.get_parameter(text, path, "rate_table_file") == RATE_TABLES[channel]
            and mp.get_parameter(text, path, "mean_energy") == "mean_en_solved"
            and mp.get_parameter(text, path, "electron_number_density") == "n_e_physical"
            and mp.get_parameter(text, path, "reaction_progress") == PROGRESS[channel]
        )

    checks["owner:EI10"] = (
        mp.get_parameter(text, OWNER_BLOCKS["EI10"], "type")
        == "PhysicsElectronImpactO2sExcitationMaterial"
        and mp.get_parameter(text, OWNER_BLOCKS["EI10"], "electron_number_density")
        == "n_e_physical"
        and mp.get_parameter(text, OWNER_BLOCKS["EI10"], "o2_molar_concentration")
        == "c_O2"
    )
    checks["owner:EI16"] = (
        mp.get_parameter(text, OWNER_BLOCKS["EI16"], "type")
        == "PhysicsElectronImpactIonizationMaterial"
        and mp.get_parameter(text, OWNER_BLOCKS["EI16"], "rate_table_file")
        == RATE_TABLES["EI16"]
        and mp.get_parameter(text, OWNER_BLOCKS["EI16"], "mean_energy")
        == "mean_en_solved"
        and mp.get_parameter(text, OWNER_BLOCKS["EI16"], "electron_number_density")
        == "n_e_physical"
        and mp.get_parameter(text, OWNER_BLOCKS["EI16"], "o2_molar_concentration")
        == "c_O2"
    )
    checks["owner:EDETACH_OM"] = (
        mp.get_parameter(text, OWNER_BLOCKS["EDETACH_OM"], "type")
        == "ADParsedFunctorMaterial"
        and mp.get_parameter(text, OWNER_BLOCKS["EDETACH_OM"], "property_name")
        == PROGRESS["EDETACH_OM"]
        and "Te_eV" in mp.words(
            mp.get_parameter(text, OWNER_BLOCKS["EDETACH_OM"], "functor_names")
        )
    )
    checks["owner:H01_H04"] = (
        mp.get_parameter(text, OWNER_BLOCKS["H01_OP_O2_CHARGE_TRANSFER"], "type")
        == "PhysicsReactionRateMaterial"
        and mp.words(
            mp.get_parameter(
                text, OWNER_BLOCKS["H01_OP_O2_CHARGE_TRANSFER"], "active_reactions"
            )
        )
        == list(H01_H04_ACTIVE)
        and mp.get_parameter(
            text, OWNER_BLOCKS["H01_OP_O2_CHARGE_TRANSFER"], "temperature"
        )
        == "T_g"
    )
    checks["owner:H05"] = (
        mp.get_parameter(text, OWNER_BLOCKS["H05_OM_O_DETACHMENT"], "type")
        == "PhysicsReactionRateMaterial"
        and mp.words(
            mp.get_parameter(text, OWNER_BLOCKS["H05_OM_O_DETACHMENT"], "active_reactions")
        )
        == [H05_ACTIVE]
        and mp.get_parameter(text, OWNER_BLOCKS["H05_OM_O_DETACHMENT"], "temperature")
        == "T_g"
    )

    checks["ei10_projection_reused"] = (
        mp.get_parameter(text, "FunctorMaterials/s5r_ei10_projection", "type")
        == "PhysicsO2sExcitationSourceMaterial"
        and mp.get_parameter(
            text, "FunctorMaterials/s5r_ei10_projection", "reaction_progress"
        )
        == PROGRESS["EI10"]
    )
    checks["ei16_projection_reused"] = (
        mp.get_parameter(text, "FunctorMaterials/s5r_ei16_projection", "type")
        == "PhysicsO2IonizationSourceMaterial"
        and mp.get_parameter(
            text, "FunctorMaterials/s5r_ei16_projection", "reaction_progress"
        )
        == PROGRESS["EI16"]
    )

    for species in SOLVED_HEAVY:
        checks[f"heavy_projection:{species}"] = (
            mp.get_parameter(text, f"FVKernels/s5r_source_{species}", "type")
            == "PhysicsFVSpeciesReactionSource"
            and mp.get_parameter(text, f"FVKernels/s5r_source_{species}", "source")
            == f"S_{species}_s5r"
        )
    checks["electron_projection"] = (
        mp.get_parameter(text, "FVKernels/s5r_electron_source", "type")
        == "PhysicsFVElectronReactionSource"
        and mp.get_parameter(text, "FVKernels/s5r_electron_source", "number_source")
        == "S_e_s5r"
    )

    for suffix in ("ei02", "ei17"):
        checks[f"elastic_common_Tg:{suffix}"] = (
            "T_g"
            in mp.words(
                mp.get_parameter(
                    text,
                    f"FunctorMaterials/s5r_{suffix}_elastic_energy",
                    "functor_names",
                )
            )
            and mp.get_parameter(
                text, f"FVKernels/s5r_{suffix}_elastic_energy", "type"
            )
            == "FVCoupledForce"
        )
    for channel in (
        "EI10",
        "EI16",
        "EI19",
        "EI18_O_TO_OS",
        "EI20_O_IONIZATION",
        "EDETACH_OM",
    ):
        path = f"FVKernels/s5r_energy_{channel.lower()}"
        checks[f"energy_projection:{channel}"] = (
            mp.get_parameter(text, path, "type") == "FVCoupledForce"
            and mp.get_parameter(text, path, "v") == PROGRESS[channel]
            and float(mp.get_parameter(text, path, "coef") or "0") < 0.0
        )
    checks["no_H05_energy_source"] = not any(
        "h05" in path.lower() and mp.get_parameter(text, path, "type") == "FVCoupledForce"
        for path in mp.direct_children(text, "FVKernels")
    )
    checks["no_custom_reaction_energy_projector"] = (
        "PhysicsFVElectronReactionEnergySource" not in text
    )

    # Every admitted progress is observable, giving the assembled surface an
    # explicit zero-missing ledger witness.
    for channel in ADMITTED_CHANNELS:
        checks[f"progress_observable:{channel}"] = (
            mp.get_parameter(
                text,
                f"Postprocessors/s5r_progress_{channel.lower()}",
                "functor",
            )
            == PROGRESS[channel]
        )

    checks["deferred_channels_absent"] = all(token not in text for token in DEFERRED_TOKENS)
    checks["no_clamp_or_floor"] = (
        "bounds_policy = clamp" not in text
        and "bounds_policy = floor" not in text
    )
    checks["common_production_Tg"] = (
        mp.get_parameter(text, "FunctorMaterials/s5r_h01_h04_rates", "temperature")
        == "T_g"
        and mp.get_parameter(text, "FunctorMaterials/s5r_h05_rate", "temperature")
        == "T_g"
        and mp.get_parameter(text, "FunctorMaterials/electron_transport", "gas_temperature")
        == "T_g"
    )

    failed = sorted(name for name, passed in checks.items() if not passed)
    return {
        "status": "PASS" if not failed else "FAIL",
        "checks": checks,
        "failed_checks": failed,
        "admitted_channels": list(ADMITTED_CHANNELS),
        "progress_map": dict(PROGRESS),
        "owner_map": dict(OWNER_BLOCKS),
    }


def build_s5r_input(base_text: str) -> tuple[str, dict[str, Any]]:
    text, predecessor = build_r4_qf1_input(base_text)
    if predecessor["audit"]["status"] != "PASS":
        raise Issue192S5RError("R4-QF1 predecessor audit is not PASS")

    n_ref = _top_level_float(text, "n_e_value")
    text = _insert_energy_state(text)
    text = _insert_concentrations(text)
    text = _insert_kinetic_owners(text)
    text = _insert_species_sources(text)
    text = _insert_electron_source(text, n_ref=n_ref)
    text = _insert_energy_sources(text, n_ref=n_ref)
    text = _insert_observables(text)

    audit = audit_s5r_input(text)
    if audit["status"] != "PASS":
        raise Issue192S5RError(f"S5-R assembly audit failed: {audit['failed_checks']}")

    return text, {
        "issue": 192,
        "controller_issue": 176,
        "stage": "STAGE_5_S5_R_REPRESENTATIVE_REAL_QVT",
        "model": "R4_QF1_PLUS_SOLVED_ENERGY_PLUS_S5R_V1_CHEMISTRY",
        "predecessor": predecessor,
        "electron_reference_density_m3": n_ref,
        "admitted_ledger": list(ADMITTED_CHANNELS),
        "progress_map": dict(PROGRESS),
        "owner_map": dict(OWNER_BLOCKS),
        "common_heavy_temperature": "T_g",
        "solved_mean_energy": "mean_en_solved",
        "electron_transport_bounds_policy": "error",
        "deferred_channels": list(DEFERRED_TOKENS),
        "wall_see_physics_enabled": False,
        "representative_runtime_claim": False,
        "audit": audit,
    }


__all__ = [
    "ADMITTED_CHANNELS",
    "DEFERRED_TOKENS",
    "H01_H04_ACTIVE",
    "H05_ACTIVE",
    "Issue192S5RError",
    "OWNER_BLOCKS",
    "PROGRESS",
    "RATE_TABLES",
    "audit_s5r_input",
    "build_s5r_input",
]
