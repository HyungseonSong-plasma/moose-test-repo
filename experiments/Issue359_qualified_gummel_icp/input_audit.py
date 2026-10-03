"""Issue359 semantic generated-input audit.

Canonical object/path/type/parameter binding checks are delegated to the central
MOOSE input-contract harness. This module retains only Issue359-specific
cross-object relations, representation invariants, wall-chemistry evidence, and
policy checks that are not yet generic harness semantics.
"""
from __future__ import annotations

from typing import Any

from physics_harness.adapters.moose import (
    PRESENCE_FORBIDDEN,
    MooseInputContract,
    MooseObjectContract,
    audit_declared_input,
)
from physics_harness.adapters.moose import blocks as mb
from physics_harness.adapters.moose import parameters as mp


CHARGED = ("O2p", "Om", "Op")


def _obj(
    object_id: str,
    path: str,
    type_name: str | None,
    **bindings: str,
) -> MooseObjectContract:
    return MooseObjectContract(
        object_id=object_id,
        path=path,
        type_name=type_name,
        parameters=tuple(bindings),
        parameter_values=tuple(bindings.items()),
    )


def _forbidden(object_id: str, path: str, reason: str) -> MooseObjectContract:
    return MooseObjectContract(
        object_id=object_id,
        path=path,
        type_name=None,
        presence=PRESENCE_FORBIDDEN,
        reason=reason,
        source="Issue359 accepted construction policy",
    )


def _outer_contract() -> MooseInputContract:
    objects: list[MooseObjectContract] = [
        _obj(
            "heavy.transport.closure",
            "FunctorMaterials/heavy_transport",
            "PhysicsThermalDiffusionMaterial",
            electron_temperature="T_e_from_gummel_K",
            electron_number_density="electron_density_from_gummel",
        ),
        _forbidden(
            "architecture.plasma_closures.outer",
            "PlasmaClosures",
            "Issue359 uses explicit atomic materials after qualification",
        ),
    ]
    charge = {"O2p": "1", "Om": "-1", "Op": "1"}
    mobility = {"O2p": "mu_O2p", "Om": "mu_Om", "Op": "mu_Op"}
    for sp in CHARGED:
        objects.extend(
            (
                _obj(
                    f"heavy.{sp}.time",
                    f"FVKernels/{sp}_time",
                    "PhysicsFVConservativeMassFractionTimeDerivative",
                    variable=f"w_{sp}",
                    rho="rho_mat",
                ),
                _obj(
                    f"heavy.{sp}.advection",
                    f"FVKernels/{sp}_advection",
                    "PhysicsFVMassFractionAdvection",
                    variable=f"w_{sp}",
                    rho="rho_mat",
                ),
                _obj(
                    f"heavy.{sp}.diffusion",
                    f"FVKernels/{sp}_diffusion",
                    "PhysicsFVMixtureAveragedDiffusion",
                    variable=f"w_{sp}",
                    rho="rho_mat",
                    diffusivity=f"D_mix_{sp}",
                    mean_molar_mass="Mn_mix",
                    include_molar_mass_gradient="true",
                ),
                _obj(
                    f"heavy.{sp}.electrostatic_drift",
                    f"FVKernels/{sp}_electrostatic_drift",
                    "PhysicsFVElectrostaticDrift",
                    variable=f"w_{sp}",
                    potential="potential_from_gummel",
                    mobility=mobility[sp],
                    carrier="rho_mat",
                    charge_number=charge[sp],
                ),
                _obj(
                    f"heavy.{sp}.mass_frame_em_correction",
                    f"FVKernels/{sp}_heavy_mass_em_correction",
                    "PhysicsFVHeavyMassElectromigrationCorrection",
                    variable=f"w_{sp}",
                    potential="potential_from_gummel",
                    rho="rho_mat",
                    ion_mass_fractions="'w_O2p w_Om w_Op'",
                    ion_mobilities="'mu_O2p mu_Om mu_Op'",
                    ion_charges="'1 -1 1'",
                ),
            )
        )
    return MooseInputContract("issue359.outer.v1", objects=tuple(objects))


def _electron_contract() -> MooseInputContract:
    all_b = "'inlet outlet plasma_electrode plasma_metal plasma_right plasma_cover plasma_wafer plasma_focus_ring'"
    return MooseInputContract(
        "issue359.electron.v1",
        objects=(
            _obj("electron.state.log_density", "Variables/log_e", None),
            _obj("electron.state.energy_molar", "Variables/c_epsilon", None),
            _obj(
                "electron.particle.time",
                "FVKernels/electron_time",
                "PhysicsFVLogMolarElectronTimeDerivative",
                variable="log_e",
            ),
            _obj(
                "electron.particle.diffusion",
                "FVKernels/electron_diffusion",
                "PhysicsFVLogMolarElectronDiffusion",
                variable="log_e",
                coeff="electron_diffusion",
                coeff_interp_method="harmonic",
            ),
            _obj(
                "electron.particle.drift",
                "FVKernels/electron_drift",
                "PhysicsFVLogMolarElectrostaticDrift",
                variable="log_e",
                potential="potential_from_poisson",
                mobility="electron_mobility",
                carrier="carrier_one",
                charge_number="-1",
            ),
            _obj(
                "electron.energy.time",
                "FVKernels/energy_time",
                "FVTimeKernel",
                variable="c_epsilon",
            ),
            _obj(
                "electron.energy.diffusion",
                "FVKernels/energy_diffusion",
                "FVDiffusion",
                variable="c_epsilon",
                coeff="electron_energy_diffusion",
            ),
            _obj(
                "electron.energy.drift",
                "FVKernels/energy_drift",
                "PhysicsFVElectrostaticDrift",
                variable="c_epsilon",
                potential="potential_from_poisson",
                mobility="electron_energy_mobility",
                carrier="carrier_one",
                charge_number="-1",
            ),
            _obj(
                "electron.energy.joule",
                "FVKernels/energy_joule",
                "PhysicsFVElectronEnergyJouleHeating",
                variable="c_epsilon",
                electron_density="c_e_molar",
                potential="potential_from_poisson",
                mobility="joule_mobility",
                diffusion="joule_diffusion",
                state_form="molar_eV",
            ),
            _obj(
                "electron.energy.elastic_o2",
                "FVKernels/energy_elastic_o2",
                "FVCoupledForce",
                variable="c_epsilon",
                v="S_elastic_applied_molar",
                coef="1.0",
            ),
            _obj(
                "electron.transport.closure",
                "FunctorMaterials/electron_transport_closure",
                "PhysicsElectronClosureMaterial",
                state_form="physical_eV",
                electron_number_density="electron_density_m3",
                electron_energy_density="electron_energy_density_eV_m3",
            ),
            _obj(
                "electron.kinetics.o2_elastic",
                "FunctorMaterials/electron_o2_elastic_kinetics",
                "PhysicsElectronKineticsMaterial",
                electron_mean_energy="mean_en_solved",
                electron_number_density="electron_density_m3",
            ),
            _obj(
                "electron.wall.particle",
                "FVBCs/electron_wall_collection",
                "PhysicsFVElectronGroundedSheathCollectionBC",
                variable="log_e",
                boundary=all_b,
                potential="potential_from_poisson",
                log_molar_state="true",
            ),
            _obj(
                "electron.wall.energy",
                "FVBCs/electron_energy_wall_loss",
                "PhysicsFVElectronGroundedSheathEnergyBC",
                variable="c_epsilon",
                boundary=all_b,
                electron_density="c_e_molar",
                potential="potential_from_poisson",
                molar_energy_state="true",
            ),
            _forbidden(
                "electron.normalized_density.material",
                "FunctorMaterials/electron_density_normalized",
                "T1/T2 accepted representation uses log molar density directly",
            ),
            _forbidden(
                "architecture.plasma_closures.electron",
                "PlasmaClosures",
                "Issue359 uses explicit atomic materials after qualification",
            ),
        ),
    )


def _driver_contract() -> MooseInputContract:
    return MooseInputContract(
        "issue359.driver.v1",
        objects=(
            _obj(
                "gummel.siblings",
                "GummelIteration/electron_poisson",
                None,
                electron_input_file="electron_sub.i",
                poisson_input_file="poisson_sub.i",
                potential_transfer_mode="through_parent",
                parent_potential_variable="potential_from_poisson",
            ),
            _forbidden(
                "architecture.plasma_closures.driver",
                "PlasmaClosures",
                "driver coordinates siblings and owns no plasma closure Action",
            ),
        ),
    )


def _poisson_contract() -> MooseInputContract:
    return MooseInputContract(
        "issue359.poisson.v1",
        objects=(
            _obj("poisson.state.log_density_frozen", "AuxVariables/log_e_frozen", None),
            _obj("poisson.state.energy_molar_frozen", "AuxVariables/c_epsilon_frozen", None),
            _obj(
                "poisson.electron.mean_energy_bridge",
                "FunctorMaterials/gummel_mean_energy",
                "ADParsedFunctorMaterial",
                functor_names="'c_epsilon_frozen log_e_frozen'",
                functor_symbols="'ceps loge'",
                expression="'ceps/max(exp(loge),1.0e-300)'",
            ),
            _obj(
                "poisson.charge.closure",
                "FunctorMaterials/plasma_charge_density",
                "PhysicsPlasmaChargeDensityMaterial",
            ),
            _obj(
                "poisson.electron_response.topology",
                "FVKernels/electron_response_topology_correction",
                "FVElectronResponseTopologyCorrection",
                variable="potential_plasma",
                anchor="phi_anchor_frozen",
                beta="electron_response_beta",
            ),
            _forbidden(
                "poisson.electron_response.banded_1d",
                "FVKernels/electron_response_banded_correction",
                "geometry-specific 1D banded response was retired for RZ topology",
            ),
            _forbidden(
                "architecture.plasma_closures.poisson",
                "PlasmaClosures",
                "Issue359 uses explicit atomic materials after qualification",
            ),
        ),
    )


def _row(
    label: str,
    group: str,
    term: str,
    scope: str,
    expected: str,
    passed: bool,
    evidence: str,
) -> dict[str, Any]:
    return {
        "label": label,
        "group": group,
        "term": term,
        "scope": scope,
        "expected": expected,
        "status": "PASS" if passed else "FAIL",
        "evidence": evidence,
    }


def _contract_row(scope: str, text: str, contract: MooseInputContract) -> dict[str, Any]:
    result = audit_declared_input(contract, text)
    return _row(
        f"contract.{scope}",
        "Central Input Contract",
        f"{scope} generated-input semantic object/binding contract",
        scope,
        contract.contract_id,
        result.status == "PASS",
        str(result.to_dict()),
    )


def audit(
    outer: str,
    driver: str,
    electron: str,
    poisson: str,
    continuity: dict[str, Any],
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = [
        _contract_row("outer", outer, _outer_contract()),
        _contract_row("driver", driver, _driver_contract()),
        _contract_row("electron", electron, _electron_contract()),
        _contract_row("poisson", poisson, _poisson_contract()),
    ]

    src = mp.words(
        mp.get_parameter(outer, "Transfers/gummel_state_to_heavy", "source_variable") or ""
    )
    dst = mp.words(
        mp.get_parameter(outer, "Transfers/gummel_state_to_heavy", "variable") or ""
    )
    mapped = dict(zip(src, dst)) if len(src) == len(dst) else {}
    ion_paths = [
        f"FVKernels/{sp}_electrostatic_drift" for sp in CHARGED
    ] + [
        f"FVKernels/{sp}_heavy_mass_em_correction" for sp in CHARGED
    ] + [
        f"FunctorMaterials/{sp}_wall_flux" for sp in CHARGED
    ]
    ion_potential_ok = (
        mapped.get("potential_from_poisson") == "potential_from_gummel"
        and all(
            mb.has_block(outer, path)
            and mp.get_parameter(outer, path, "potential") == "potential_from_gummel"
            for path in ion_paths
        )
    )
    rows.append(_row(
        "coupling.heavy.potential",
        "Coupled Variable",
        "Poisson potential -> charged-heavy transport/wall flux",
        "outer heavy",
        "potential_from_poisson -> potential_from_gummel",
        ion_potential_ok,
        f"transfer={mapped.get('potential_from_poisson')}; consumers={len(ion_paths)}",
    ))

    wall_map = {
        "wall.O.recombination": "O",
        "wall.O2s.quench": "O2s",
        "wall.Os.recombination": "Os",
        "wall.O2p.neutralization": "O2p",
        "wall.Om.neutralization": "Om",
        "wall.Op.neutralization": "Op",
    }
    for object_id, species in wall_map.items():
        item = continuity["wall_reactions"].get(species, {})
        rows.append(_row(
            object_id,
            "Boundary Condition",
            item.get("reaction") or species,
            species,
            "species-specific surface reaction on all plasma walls",
            bool(item.get("ok")),
            f"reaction={item.get('reaction')}; sticking={item.get('sticking')}",
        ))
    rows.append(_row(
        "wall.charged_neutralization.O_return",
        "Boundary Condition",
        "O+/O- neutralization return flux -> O",
        "O return",
        "explicit O return flux on all plasma walls",
        bool(continuity.get("charged_neutralization_O_return")),
        "FVBCs/ion_neutralization_O_return",
    ))

    scientific_names_only = all(
        "issue359_" not in text for text in (outer, driver, electron, poisson)
    )
    rows.append(_row(
        "architecture.scientific_object_names",
        "Architecture",
        "generated input object names are scientific and issue-agnostic",
        "all generated inputs",
        "no issue-local issue359_* object names",
        scientific_names_only,
        "outer/driver/electron/poisson scanned for issue359_ prefix",
    ))

    energy_state_ok = (
        "n_epsilon" not in electron
        and "n_epsilon" not in driver
        and "n_epsilon" not in poisson
        and not mb.has_block(electron, "Variables/mean_en")
        and not mb.has_block(poisson, "AuxVariables/mean_en_frozen")
        and mb.has_block(electron, "Variables/c_epsilon")
        and mb.has_block(poisson, "AuxVariables/c_epsilon_frozen")
    )
    rows.append(_row(
        "representation.electron.energy_state",
        "Representation",
        "electron energy solved state is conservative c_epsilon; mean energy is derived",
        "electron/driver/poisson",
        "c_epsilon + c_epsilon_frozen; legacy n_epsilon absent",
        energy_state_ok,
        "generated electron, driver and Poisson inputs scanned",
    ))

    normalization_absent = (
        "electron_density_hat" not in electron
        and "state_form = normalized" not in electron
        and "energy_reference_eV" not in electron
        and "electron_energy_reference_eV" not in electron
    )
    rows.append(_row(
        "representation.electron.normalization_absent",
        "Representation",
        "T1/T2 electron particle/energy normalization is absent",
        "electron subapp",
        "log_e + c_epsilon; no reference-density/energy scaling",
        normalization_absent,
        "active electron input scanned for legacy normalization symbols",
    ))

    reaction_disabled = (
        "PhysicsFVSpeciesReactionSource" not in outer and "s5r_source_" not in outer
    )
    rows.append(_row(
        "policy.heavy.volumetric_chemistry_disabled",
        "Policy",
        "volumetric reaction source disabled",
        "heavy species",
        "no PhysicsFVSpeciesReactionSource in current stage",
        reaction_disabled,
        "reaction-source coupling intentionally deferred",
    ))

    failed = [row["label"] for row in rows if row["status"] != "PASS"]
    return {
        "status": "PASS" if not failed else "FAIL",
        "failed_labels": failed,
        "rows": rows,
    }


def to_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Issue359 Input Audit",
        "",
        "| Semantic ID | Group | Term | Scope | Status |",
        "|---|---|---|---|---|",
    ]
    for row in report["rows"]:
        lines.append(
            f"| {row['label']} | {row['group']} | {row['term']} | "
            f"{row['scope']} | **{row['status']}** |"
        )
    lines.extend(["", "## Evidence", ""])
    for row in report["rows"]:
        lines.append(f"- {row['label']} {row['status']}: {row['evidence']}")
    return "\n".join(lines) + "\n"


def status_lines(report: dict[str, Any]) -> list[str]:
    return [
        f"INPUT_AUDIT {row['label']} {row['status']} :: {row['term']}"
        for row in report["rows"]
    ]
