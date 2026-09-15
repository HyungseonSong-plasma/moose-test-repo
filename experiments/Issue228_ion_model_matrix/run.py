#!/usr/bin/env python3
"""Issue #228 ion transport-law discriminator on the axis-free 10-step reactor case.

All cases keep the same mesh, electron transport, grounded-sheath model, chemistry,
FV Poisson discretization, timestep, and axis-free electrostatic boundary policy.
Only the charged-heavy diffusion law changes.

Cases
-----
mixture
    Production QPXFVMixtureAveragedDiffusion for O2+, O-, O+.
no_molar_grad
    Same mixture-averaged kernel and transport coefficients, but disables only
    the mean-molar-mass-gradient contribution for the charged species.
fickian_charged
    Replaces charged-species mixture diffusion with the bounded diagnostic flux
        J_diff,k = -rho * D_mix,k * grad(w_k)
    while preserving the existing electrostatic drift kernels, mobilities,
    wall owners, chemistry, and all neutral-species transport.

The Fickian case is a controlled drift-diffusion proxy in the current
mass-fraction formulation. It is not claimed to be mathematically identical to
an older FE number-density drift-diffusion model.
"""
from __future__ import annotations

import argparse
import json
import math
import shutil
from pathlib import Path
from typing import Any

from experiments.Issue192_s5r_representative import run as s5r
from experiments.Issue211_science_factorial import run as sci
from experiments.Issue228_axis_bc_10step import run as axis
from physics_harness.adapters.moose import blocks as mb
from physics_harness.adapters.moose import parameters as mp

MODES = ("mixture", "no_molar_grad", "fickian_charged")
CHARGED = (
    ("O2p", "w_O2p", "D_mix_O2p", "mu_O2p", 1),
    ("Om", "w_Om", "D_mix_Om", "mu_Om", -1),
    ("Op", "w_Op", "D_mix_Op", "mu_Op", 1),
)


def _write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _diff_path(species: str) -> str:
    return f"FVKernels/{species}_diffusion"


def _drift_path(species: str) -> str:
    return f"FVKernels/{species}_electrostatic_drift"


def _require_production_charged_contract(text: str) -> None:
    for species, variable, diffusivity, mobility, charge in CHARGED:
        dpath = _diff_path(species)
        if not mb.has_block(text, dpath):
            raise RuntimeError(f"missing production charged diffusion block: {dpath}")
        if mp.get_parameter(text, dpath, "type") != "QPXFVMixtureAveragedDiffusion":
            raise RuntimeError(f"unexpected production diffusion type at {dpath}")
        if mp.get_parameter(text, dpath, "variable") != variable:
            raise RuntimeError(f"unexpected production variable at {dpath}")
        if mp.get_parameter(text, dpath, "diffusivity") != diffusivity:
            raise RuntimeError(f"unexpected production diffusivity at {dpath}")

        drift = _drift_path(species)
        if not mb.has_block(text, drift):
            raise RuntimeError(f"missing production charged drift block: {drift}")
        dtype = mp.get_parameter(text, drift, "type")
        if dtype not in ("QPXFVElectrostaticDrift", "PhysicsFVElectrostaticDrift"):
            raise RuntimeError(f"unexpected charged drift type at {drift}: {dtype}")
        if mp.get_parameter(text, drift, "variable") != variable:
            raise RuntimeError(f"unexpected drift variable at {drift}")
        if mp.get_parameter(text, drift, "mobility") != mobility:
            raise RuntimeError(f"unexpected mobility at {drift}")
        if int(float(mp.get_parameter(text, drift, "charge_number") or "nan")) != charge:
            raise RuntimeError(f"unexpected charge_number at {drift}")
        if mp.get_parameter(text, drift, "potential") != "potential_plasma":
            raise RuntimeError(f"charged drift is not coupled to potential_plasma at {drift}")


def _disable_charged_molar_gradient(text: str) -> str:
    for species, *_ in CHARGED:
        text = mp.upsert_parameter(
            text,
            _diff_path(species),
            "include_molar_mass_gradient",
            "false",
        )
    return text


def _replace_charged_with_fickian(text: str) -> str:
    for species, variable, diffusivity, _mobility, _charge in CHARGED:
        dpath = _diff_path(species)
        mat_name = f"r228_rhoD_{species}"
        mat_path = f"FunctorMaterials/{mat_name}"
        mb.require_absent(text, mat_path)

        text = mb.remove_block(text, dpath)
        text = mb.insert_child_block(
            text,
            "FunctorMaterials",
            f"""  [{mat_name}]
    type = ADParsedFunctorMaterial
    property_name = {mat_name}
    functor_names = 'rho_mat {diffusivity}'
    functor_symbols = 'rho_s d_s'
    expression = 'rho_s*d_s'
    block = plasma
  []""",
        )
        text = mb.insert_child_block(
            text,
            "FVKernels",
            f"""  [{species}_diffusion]
    type = FVDiffusion
    variable = {variable}
    coeff = {mat_name}
    block = plasma
  []""",
        )
    return text


def build_case(mode: str) -> tuple[str, dict[str, Any]]:
    if mode not in MODES:
        raise ValueError(mode)

    text, meta = axis.build_case()
    _require_production_charged_contract(text)

    if mode == "no_molar_grad":
        text = _disable_charged_molar_gradient(text)
    elif mode == "fickian_charged":
        text = _replace_charged_with_fickian(text)

    return text, {
        **meta,
        "issue": 228,
        "claim": "charged_ion_transport_law_10step_discriminator",
        "diagnostic_only": True,
        "mode": mode,
        "axis_grounding_removed": True,
        "mesh_geometry_changed": False,
        "mesh_topology_changed": False,
        "electron_transport_changed": False,
        "electron_sheath_law_changed": False,
        "chemistry_changed": False,
        "poisson_discretization_changed": False,
        "charged_ion_drift_changed": False,
        "charged_ion_mobility_changed": False,
        "charged_ion_diffusivity_values_changed": False,
        "charged_ion_diffusion_law": mode,
        "neutral_species_transport_changed": False,
    }


def self_test() -> dict[str, Any]:
    checks: dict[str, bool] = {}
    for mode in MODES:
        text, meta = build_case(mode)
        checks[f"{mode}:axis_free"] = meta["diagnostic_ground_boundary"] == axis.GROUND_NONAXIS
        checks[f"{mode}:ten_steps"] = int(meta["expected_steps"]) == axis.EXPECTED_STEPS
        checks[f"{mode}:end_time"] = math.isclose(
            float(meta["end_time_s"]), axis.END_TIME_S, rel_tol=0.0, abs_tol=1.0e-24
        )
        checks[f"{mode}:electron_drift_unchanged"] = (
            mp.get_parameter(text, "FVKernels/n_e_drift", "type") == "PhysicsFVElectrostaticDrift"
        )
        checks[f"{mode}:poisson_diffusion_fv"] = (
            mp.get_parameter(text, "FVKernels/r31_phi_diffusion", "type") == "FVDiffusion"
        )
        checks[f"{mode}:poisson_source_unchanged"] = (
            mp.get_parameter(text, "FVKernels/r31_phi_charge_source", "type") == "FVCoupledForce"
        )

        for species, variable, diffusivity, mobility, charge in CHARGED:
            dpath = _diff_path(species)
            drift = _drift_path(species)
            checks[f"{mode}:{species}:drift_present"] = mb.has_block(text, drift)
            checks[f"{mode}:{species}:drift_variable"] = mp.get_parameter(text, drift, "variable") == variable
            checks[f"{mode}:{species}:drift_mobility"] = mp.get_parameter(text, drift, "mobility") == mobility
            checks[f"{mode}:{species}:drift_charge"] = int(float(mp.get_parameter(text, drift, "charge_number") or "nan")) == charge
            checks[f"{mode}:{species}:drift_potential"] = mp.get_parameter(text, drift, "potential") == "potential_plasma"

            if mode == "mixture":
                checks[f"{mode}:{species}:diff_type"] = mp.get_parameter(text, dpath, "type") == "QPXFVMixtureAveragedDiffusion"
                checks[f"{mode}:{species}:molar_grad"] = mp.get_parameter(text, dpath, "include_molar_mass_gradient") == "true"
            elif mode == "no_molar_grad":
                checks[f"{mode}:{species}:diff_type"] = mp.get_parameter(text, dpath, "type") == "QPXFVMixtureAveragedDiffusion"
                checks[f"{mode}:{species}:molar_grad_off"] = mp.get_parameter(text, dpath, "include_molar_mass_gradient") == "false"
            else:
                mat_name = f"r228_rhoD_{species}"
                checks[f"{mode}:{species}:diff_type"] = mp.get_parameter(text, dpath, "type") == "FVDiffusion"
                checks[f"{mode}:{species}:diff_coeff"] = mp.get_parameter(text, dpath, "coeff") == mat_name
                checks[f"{mode}:{species}:rhoD_material"] = mb.has_block(text, f"FunctorMaterials/{mat_name}")
                checks[f"{mode}:{species}:same_D_source"] = diffusivity in (mp.get_parameter(text, f"FunctorMaterials/{mat_name}", "functor_names") or "")

    failed = sorted(k for k, value in checks.items() if not value)
    return {"status": "PASS" if not failed else "FAIL", "checks": checks, "failed_checks": failed}


def run_case(args: argparse.Namespace) -> int:
    mode = args.mode
    exe = args.physics_opt.resolve()
    out = args.results_root.resolve()
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)

    p0 = self_test()
    _write(out / "self_test.json", p0)
    if p0["status"] != "PASS":
        raise RuntimeError(p0)

    text, meta = build_case(mode)
    case_dir = out / "case"
    logs = out / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    summary: dict[str, Any] = {"status": "RUNNING", "meta": meta}

    try:
        summary["stage"] = sci._stage(case_dir, text, meta)
    except Exception as exc:
        summary["status"] = "HARNESS_FAIL"
        summary["harness_error"] = f"{type(exc).__name__}: {exc}"
        _write(out / "summary.json", summary)
        return 1

    p2 = s5r._p2(exe, case_dir, logs / "p2.log", timeout=min(float(args.timeout), 300.0))
    summary["p2"] = p2
    if p2.get("returncode") != 0:
        summary["status"] = "P2_FAIL"
        _write(out / "summary.json", summary)
        return 1

    runtime = sci._runtime(exe, case_dir, logs / "runtime.log", logs / "time_v.log", float(args.timeout))
    summary["runtime"] = runtime
    try:
        result = axis._analyse(case_dir, text, meta, runtime)
        summary["result"] = result
        good = (
            result["runtime_returncode"] == 0
            and not result["timed_out"]
            and result["physical_steps"] == axis.EXPECTED_STEPS
            and result["all_steps_hard_pass"]
        )
        summary["status"] = "PASS" if good else "FAIL"
    except Exception as exc:
        summary["status"] = "ANALYSIS_FAIL"
        summary["analysis_error"] = f"{type(exc).__name__}: {exc}"
        good = False

    _write(out / "summary.json", summary)
    return 0 if good else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=MODES)
    parser.add_argument("--physics-opt", type=Path)
    parser.add_argument("--results-root", type=Path, default=Path("issue228-ion-model-results"))
    parser.add_argument("--timeout", type=float, default=1800.0)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        result = self_test()
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result["status"] == "PASS" else 1
    if args.mode is None:
        parser.error("--mode is required unless --self-test is used")
    if args.physics_opt is None:
        parser.error("--physics-opt is required unless --self-test is used")
    return run_case(args)


if __name__ == "__main__":
    raise SystemExit(main())
