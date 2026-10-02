"""Stable label registry for Issue359 generated-input audits.

The labels are intentionally semantic and stable.  MOOSE block names may evolve,
but CI reports these labels so comparisons remain readable across refactors.
"""
from __future__ import annotations

from typing import Any

from experiments.Issue359_qualified_gummel_icp import heavy_continuity as hc
from physics_harness.adapters.moose import blocks as mb
from physics_harness.adapters.moose import parameters as mp


ION_KERNEL_LABELS = {
    "ion_fvkernel_01": "time derivative",
    "ion_fvkernel_02": "advection",
    "ion_fvkernel_03": "diffusion",
    "ion_fvkernel_04": "electrostatic drift",
    "ion_fvkernel_05": "mixture electromigration correction",
}
ELECTRON_KERNEL_LABELS = {
    "electron_fvkernel_01": "time derivative",
    "electron_fvkernel_02": "diffusion",
    "electron_fvkernel_03": "electrostatic drift",
}
MEAN_EN_KERNEL_LABELS = {
    "mean_en_fvkernel_01": "time derivative",
    "mean_en_fvkernel_02": "diffusion",
    "mean_en_fvkernel_03": "electrostatic drift",
    "mean_en_fvkernel_04": "Joule heating",
    "mean_en_fvkernel_05": "elastic energy loss",
}
COUPLED_VARIABLE_LABELS = {
    "ion_potential_poisson": "Poisson potential -> charged-heavy transport/wall flux",
    "electron_potential_poisson": "Poisson potential -> electron drift",
    "mean_en_potential_poisson": "Poisson potential -> energy drift/Joule heating",
}
ION_BC_LABELS = {
    "ion_bc_01": "O2+ -> O2 surface neutralization + one-sided migration",
    "ion_bc_02": "O- -> O surface neutralization + one-sided migration",
    "ion_bc_03": "O+ -> O surface neutralization + one-sided migration",
    "ion_bc_04": "O+/O- neutralization return flux -> O",
}
NEUTRAL_BC_LABELS = {
    "neutral_bc_01": "O -> 0.5 O2",
    "neutral_bc_02": "O2s -> O2",
    "neutral_bc_03": "Os -> 0.5 O2",
}

CHARGED = ("O2p", "Om", "Op")


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


def _kernel_ok(
    text: str,
    path: str,
    expected_type: str,
    expected_variable: str,
    expected: dict[str, str] | None = None,
) -> tuple[bool, str]:
    if not mb.has_block(text, path):
        return False, f"{path}: missing"
    actual_type = mp.get_parameter(text, path, "type")
    variable = mp.get_parameter(text, path, "variable")
    checks = [
        actual_type == expected_type,
        variable == expected_variable,
    ]
    details = [f"path={path}", f"type={actual_type}", f"variable={variable}"]
    for name, value in (expected or {}).items():
        actual = mp.get_parameter(text, path, name)
        checks.append(actual == value)
        details.append(f"{name}={actual}")
    return all(checks), "; ".join(details)


def _aggregate_kernel(
    text: str,
    species: tuple[str, ...],
    path_suffix: str,
    expected_type: str,
    expected_params,
) -> tuple[bool, str]:
    evidence: list[str] = []
    passed = True
    for sp in species:
        path = f"FVKernels/{sp}_{path_suffix}"
        params = expected_params(sp)
        ok, detail = _kernel_ok(text, path, expected_type, f"w_{sp}", params)
        passed = passed and ok
        evidence.append(f"{sp}: {'PASS' if ok else 'FAIL'} ({detail})")
    return passed, " | ".join(evidence)


def audit(
    outer: str,
    driver: str,
    electron: str,
    continuity: dict[str, Any],
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []

    ok, ev = _aggregate_kernel(
        outer,
        CHARGED,
        "time",
        "PhysicsFVConservativeMassFractionTimeDerivative",
        lambda _sp: {"rho": "rho_mat"},
    )
    rows.append(_row(
        "ion_fvkernel_01", "FVKernel", ION_KERNEL_LABELS["ion_fvkernel_01"],
        "O2p, Om, Op", "PhysicsFVConservativeMassFractionTimeDerivative(rho=rho_mat)", ok, ev,
    ))

    ok, ev = _aggregate_kernel(
        outer,
        CHARGED,
        "advection",
        "PhysicsFVMassFractionAdvection",
        lambda _sp: {"rho": "rho_mat"},
    )
    rows.append(_row(
        "ion_fvkernel_02", "FVKernel", ION_KERNEL_LABELS["ion_fvkernel_02"],
        "O2p, Om, Op", "PhysicsFVMassFractionAdvection(rho=rho_mat)", ok, ev,
    ))

    ok, ev = _aggregate_kernel(
        outer,
        CHARGED,
        "diffusion",
        "PhysicsFVMixtureAveragedDiffusion",
        lambda sp: {
            "rho": "rho_mat",
            "diffusivity": f"D_mix_{sp}",
            "mean_molar_mass": "Mn_mix",
            "include_molar_mass_gradient": "true",
        },
    )
    rows.append(_row(
        "ion_fvkernel_03", "FVKernel", ION_KERNEL_LABELS["ion_fvkernel_03"],
        "O2p, Om, Op", "mixture-averaged diffusion with species D_mix", ok, ev,
    ))

    charge = {"O2p": "1", "Om": "-1", "Op": "1"}
    mobility = {"O2p": "mu_O2p", "Om": "mu_Om", "Op": "mu_Op"}
    ok, ev = _aggregate_kernel(
        outer,
        CHARGED,
        "electrostatic_drift",
        "PhysicsFVElectrostaticDrift",
        lambda sp: {
            "potential": "potential_from_gummel",
            "mobility": mobility[sp],
            "carrier": "rho_mat",
            "charge_number": charge[sp],
        },
    )
    rows.append(_row(
        "ion_fvkernel_04", "FVKernel", ION_KERNEL_LABELS["ion_fvkernel_04"],
        "O2p, Om, Op", "charged-heavy drift driven by potential_from_gummel", ok, ev,
    ))

    ok, ev = _aggregate_kernel(
        outer,
        CHARGED,
        "heavy_mass_em_correction",
        "PhysicsFVHeavyMassElectromigrationCorrection",
        lambda _sp: {
            "potential": "potential_from_gummel",
            "rho": "rho_mat",
            "ion_mass_fractions": "'w_O2p w_Om w_Op'",
            "ion_mobilities": "'mu_O2p mu_Om mu_Op'",
            "ion_charges": "'1 -1 1'",
        },
    )
    rows.append(_row(
        "ion_fvkernel_05", "FVKernel", ION_KERNEL_LABELS["ion_fvkernel_05"],
        "O2p, Om, Op", "mixture electromigration correction driven by potential_from_gummel", ok, ev,
    ))

    electron_specs = (
        (
            "electron_fvkernel_01", "electron_time",
            "PhysicsFVLogMolarElectronTimeDerivative", {},
        ),
        (
            "electron_fvkernel_02", "electron_diffusion",
            "PhysicsFVLogMolarElectronDiffusion",
            {"coeff": "electron_diffusion", "coeff_interp_method": "harmonic"},
        ),
        (
            "electron_fvkernel_03", "electron_drift",
            "PhysicsFVLogMolarElectrostaticDrift",
            {
                "potential": "potential_from_poisson",
                "mobility": "electron_mobility",
                "carrier": "carrier_one",
                "charge_number": "-1",
            },
        ),
    )
    for label, name, typ, params in electron_specs:
        ok, ev = _kernel_ok(electron, f"FVKernels/{name}", typ, "log_e", params)
        rows.append(_row(
            label, "FVKernel", ELECTRON_KERNEL_LABELS[label],
            "electron/log_e", f"{typ}", ok, ev,
        ))

    mean_specs = (
        ("mean_en_fvkernel_01", "energy_time", "FVTimeKernel", {}),
        (
            "mean_en_fvkernel_02", "energy_diffusion", "FVDiffusion",
            {"coeff": "electron_energy_diffusion"},
        ),
        (
            "mean_en_fvkernel_03", "energy_drift", "PhysicsFVElectrostaticDrift",
            {
                "potential": "potential_from_poisson",
                "mobility": "electron_energy_mobility",
                "carrier": "carrier_one",
                "charge_number": "-1",
            },
        ),
        (
            "mean_en_fvkernel_04", "energy_joule", "PhysicsFVElectronEnergyJouleHeating",
            {
                "electron_density": "electron_density_hat",
                "potential": "potential_from_poisson",
                "mobility": "joule_mobility",
                "diffusion": "joule_diffusion",
            },
        ),
        (
            "mean_en_fvkernel_05", "energy_elastic_o2", "FVCoupledForce",
            {"v": "S_elastic_applied_hat", "coef": "1.0"},
        ),
    )
    for label, name, typ, params in mean_specs:
        ok, ev = _kernel_ok(electron, f"FVKernels/{name}", typ, "n_epsilon", params)
        rows.append(_row(
            label, "FVKernel", MEAN_EN_KERNEL_LABELS[label],
            "electron energy/n_epsilon", typ, ok, ev,
        ))

    src = mp.words(
        mp.get_parameter(outer, "Transfers/issue359_fast_to_heavy", "source_variable") or ""
    )
    dst = mp.words(
        mp.get_parameter(outer, "Transfers/issue359_fast_to_heavy", "variable") or ""
    )
    mapped = dict(zip(src, dst)) if len(src) == len(dst) else {}
    ion_paths = [
        f"FVKernels/{sp}_electrostatic_drift" for sp in CHARGED
    ] + [
        f"FVKernels/{sp}_heavy_mass_em_correction" for sp in CHARGED
    ] + [
        f"FunctorMaterials/issue359_{sp}_wall_flux" for sp in CHARGED
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
        "ion_potential_poisson", "Coupled Variable",
        COUPLED_VARIABLE_LABELS["ion_potential_poisson"],
        "outer heavy", "potential_from_poisson -> potential_from_gummel", ion_potential_ok,
        f"transfer={mapped.get('potential_from_poisson')}; consumers={len(ion_paths)}",
    ))

    electron_potential_ok = (
        mp.get_parameter(electron, "FVKernels/electron_drift", "potential")
        == "potential_from_poisson"
    )
    rows.append(_row(
        "electron_potential_poisson", "Coupled Variable",
        COUPLED_VARIABLE_LABELS["electron_potential_poisson"],
        "electron/log_e", "potential_from_poisson", electron_potential_ok,
        f"electron_drift.potential={mp.get_parameter(electron, 'FVKernels/electron_drift', 'potential')}",
    ))

    mean_potential_ok = all(
        mp.get_parameter(electron, path, "potential") == "potential_from_poisson"
        for path in ("FVKernels/energy_drift", "FVKernels/energy_joule")
    )
    rows.append(_row(
        "mean_en_potential_poisson", "Coupled Variable",
        COUPLED_VARIABLE_LABELS["mean_en_potential_poisson"],
        "electron energy/n_epsilon", "potential_from_poisson", mean_potential_ok,
        "energy_drift and energy_joule use potential_from_poisson",
    ))

    wall_map = {
        "neutral_bc_01": "O",
        "neutral_bc_02": "O2s",
        "neutral_bc_03": "Os",
        "ion_bc_01": "O2p",
        "ion_bc_02": "Om",
        "ion_bc_03": "Op",
    }
    for label, species in wall_map.items():
        item = continuity["wall_reactions"].get(species, {})
        description = (
            NEUTRAL_BC_LABELS[label] if label.startswith("neutral_") else ION_BC_LABELS[label]
        )
        rows.append(_row(
            label, "Boundary Condition", description, species,
            f"species-specific surface reaction on all plasma walls",
            bool(item.get("ok")),
            f"reaction={item.get('reaction')}; sticking={item.get('sticking')}",
        ))
    rows.append(_row(
        "ion_bc_04", "Boundary Condition", ION_BC_LABELS["ion_bc_04"],
        "O return", "explicit O return flux on all plasma walls",
        bool(continuity.get("charged_neutralization_O_return")),
        "FVBCs/issue359_O_return",
    ))

    reaction_disabled = (
        "PhysicsFVSpeciesReactionSource" not in outer
        and "s5r_source_" not in outer
    )
    rows.append(_row(
        "policy_reaction_source_disabled", "Policy", "volumetric reaction source disabled",
        "heavy species", "no PhysicsFVSpeciesReactionSource in current stage",
        reaction_disabled, "reaction-source coupling intentionally deferred",
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
        "| Label | Group | Term | Scope | Status |",
        "|---|---|---|---|---|",
    ]
    for row in report["rows"]:
        lines.append(
            f"| `{row['label']}` | {row['group']} | {row['term']} | "
            f"{row['scope']} | **{row['status']}** |"
        )
    lines.extend(["", "## Evidence", ""])
    for row in report["rows"]:
        lines.append(f"- `{row['label']}` {row['status']}: {row['evidence']}")
    return "\n".join(lines) + "\n"


def status_lines(report: dict[str, Any]) -> list[str]:
    return [
        f"INPUT_AUDIT {row['label']} {row['status']} :: {row['term']}"
        for row in report["rows"]
    ]
