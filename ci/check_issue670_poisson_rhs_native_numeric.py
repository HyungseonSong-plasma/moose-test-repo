#!/usr/bin/env python3
"""#670 P4-D4: real PhysicsApp Poisson RHS Functor numerical evaluation.

This is a *controlled Native material/Kernel evaluation*, not an S6-417/941
production plasma solve. Numerical densities are synthetic; the exact
ADParsedFunctorMaterial charge chain and FunctorKernel RHS type/expression
follow the S6 C0 canonical contract. No protected EI rate tables are used.

Usage:
    python3 ci/check_issue670_poisson_rhs_native_numeric.py prepare --dir /tmp/poisson
    # run each generated *.i in the pinned PhysicsApp OCI, capturing <case>.exit
    python3 ci/check_issue670_poisson_rhs_native_numeric.py verify --dir /tmp/poisson
"""
from __future__ import annotations

import argparse
import csv
from decimal import Decimal
import hashlib
import json
import math
from pathlib import Path

AVOGADRO = Decimal("6.02214076e23")
ELEMENTARY_CHARGE = Decimal("1.602176634e-19")
POISSON_COEFFICIENT = Decimal("1.8095128179727827e-08")
BASE = Decimal("2e14")
STEP = Decimal("1e14")
SOURCE_HEAD = "74a2b0fbeaf411d9c76cb82a69de1629fa55fa7f"
SOURCE_C0_BLOB = "793f3f24bc95bf71d0b2537288cb2ecc8a5f74fa"
SOURCE_C0_CHARGE_EXPRESSION = "ni+nop-ne-nm"
SOURCE_C0_RHS_EXPRESSION = "1.8095128179727827e-08*nq"
CASES = {
    "balanced": {"O2p": BASE, "Op": BASE, "e": BASE, "Om": BASE},
    "O2p_plus": {"O2p": BASE + STEP, "Op": BASE, "e": BASE, "Om": BASE},
    "Op_plus": {"O2p": BASE, "Op": BASE + STEP, "e": BASE, "Om": BASE},
    "electron_plus": {"O2p": BASE, "Op": BASE, "e": BASE + STEP, "Om": BASE},
    "Om_plus": {"O2p": BASE, "Op": BASE, "e": BASE, "Om": BASE + STEP},
}


def sha(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def scalar_log_molar(number_density: Decimal) -> str:
    return format(math.log(float(number_density / AVOGADRO)), ".17g")


def make_input(case: str, densities: dict[str, Decimal]) -> str:
    # All material expressions below copy the actual S6 C0 charge chain,
    # with selected canonical log_O2p/Om/Op names and no plasma-only block
    # limiter, since this controlled GeneratedMesh contains one unnamed block.
    log_values = " ".join(
        scalar_log_molar(densities[name]) for name in ("O2p", "Op", "e", "Om")
    )
    return f"""# P4-D4 Native RHS numerical sample, controlled synthetic state
# source_head={SOURCE_HEAD}; source_C0_git_blob={SOURCE_C0_BLOB}
# case={case}; no S6 science / no private rates
[Mesh]
  [gen]
    type = GeneratedMeshGenerator
    dim = 1
    nx = 8
    xmin = 0
    xmax = 1
  []
[]

[Variables]
  [potential]
    initial_condition = 0
  []
[]

[FunctorMaterials]
  [synthetic_log_molar_inputs]
    type = ADGenericFunctorMaterial
    prop_names = 'log_O2p log_Op log_ne log_Om'
    prop_values = '{log_values}'
  []
  [electron_molar_density]
    type = ADParsedFunctorMaterial
    property_name = electron_molar_density
    functor_names = 'log_ne'
    functor_symbols = 'u'
    expression = 'exp(u)'
  []
  [ion_molar_density]
    type = ADParsedFunctorMaterial
    property_name = ion_molar_density
    functor_names = 'log_O2p'
    functor_symbols = 'u'
    expression = 'exp(u)'
  []
  [electron_physical_density]
    type = ADParsedFunctorMaterial
    property_name = n_e_physical
    functor_names = 'electron_molar_density'
    functor_symbols = 'ce'
    expression = '6.02214076e23*ce'
  []
  [ion_physical_density]
    type = ADParsedFunctorMaterial
    property_name = n_i_physical
    functor_names = 'ion_molar_density'
    functor_symbols = 'ci'
    expression = '6.02214076e23*ci'
  []
  [negative_ion_molar_density]
    type = ADParsedFunctorMaterial
    property_name = negative_ion_molar_density
    functor_names = 'log_Om'
    functor_symbols = 'u'
    expression = 'exp(u)'
  []
  [negative_ion_physical_density]
    type = ADParsedFunctorMaterial
    property_name = n_m_physical
    functor_names = 'negative_ion_molar_density'
    functor_symbols = 'cm'
    expression = '6.02214076e23*cm'
  []
  [atomic_positive_ion_molar_density]
    type = ADParsedFunctorMaterial
    property_name = atomic_positive_ion_molar_density
    functor_names = 'log_Op'
    functor_symbols = 'u'
    expression = 'exp(u)'
  []
  [atomic_positive_ion_physical_density]
    type = ADParsedFunctorMaterial
    property_name = n_op_physical
    functor_names = 'atomic_positive_ion_molar_density'
    functor_symbols = 'cop'
    expression = '6.02214076e23*cop'
  []
  [charge_number_density]
    type = ADParsedFunctorMaterial
    property_name = charge_number_density
    functor_names = 'n_i_physical n_op_physical n_e_physical n_m_physical'
    functor_symbols = 'ni nop ne nm'
    expression = 'ni+nop-ne-nm'
  []
  [charge_density]
    type = ADParsedFunctorMaterial
    property_name = charge_density_C_m3
    functor_names = 'charge_number_density'
    functor_symbols = 'nq'
    expression = '1.602176634e-19*nq'
  []
  [poisson_source]
    type = ADParsedFunctorMaterial
    property_name = poisson_source
    functor_names = 'charge_number_density'
    functor_symbols = 'nq'
    expression = '1.8095128179727827e-08*nq'
  []
[]

# ADMatDiffusion requests an AD material property (not a Functor).
# Match archived S6 C0's [Materials]/eps_plasma type exactly.
[Materials]
  [eps_plasma]
    type = ADGenericConstantMaterial
    prop_names = 'relative_permittivity'
    prop_values = '1.0'
  []
[]

[Kernels]
  [phi_diffusion]
    type = ADMatDiffusion
    variable = potential
    diffusivity = relative_permittivity
  []
  [phi_source]
    type = FunctorKernel
    variable = potential
    functor = poisson_source
    functor_on_rhs = true
  []
[]

[BCs]
  [left]
    type = DirichletBC
    variable = potential
    boundary = left
    value = 0
  []
  [right]
    type = DirichletBC
    variable = potential
    boundary = right
    value = 0
  []
[]

[Postprocessors]
  [nq_observed]
    type = ElementAverageFunctorPostprocessor
    functor = charge_number_density
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [rho_observed]
    type = ElementAverageFunctorPostprocessor
    functor = charge_density_C_m3
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [rhs_observed]
    type = ElementAverageFunctorPostprocessor
    functor = poisson_source
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [potential_avg]
    type = ElementAverageValue
    variable = potential
    execute_on = 'INITIAL TIMESTEP_END'
  []
[]

[Executioner]
  type = Steady
  solve_type = NEWTON
  nl_rel_tol = 1e-10
  nl_abs_tol = 1e-8
  nl_max_its = 30
[]

[Outputs]
  csv = true
  file_base = {case}
[]
"""


def expected(densities: dict[str, Decimal]) -> dict:
    nq = densities["O2p"] + densities["Op"] - densities["e"] - densities["Om"]
    return {"nq_observed": str(nq),
            "rho_observed": str(ELEMENTARY_CHARGE * nq),
            "rhs_observed": str(POISSON_COEFFICIENT * nq)}


def prepare(folder: Path) -> dict:
    folder.mkdir(parents=True, exist_ok=True)
    report = {"schema": "issue670.poisson_rhs.native_numeric_fixture.v1",
              "source_head": SOURCE_HEAD, "source_C0_blob": SOURCE_C0_BLOB,
              "source_equations": {
                  "charge_number_density": SOURCE_C0_CHARGE_EXPRESSION,
                  "poisson_source": SOURCE_C0_RHS_EXPRESSION},
              "scope": "controlled synthetic log-molar states, real PhysicsApp ADParsedFunctorMaterial and FunctorKernel; not a live S6 nonlinear solve",
              "cases": {}}
    for name, densities in CASES.items():
        text = make_input(name, densities)
        file = folder / (name + ".i")
        file.write_text(text)
        report["cases"][name] = {
            "densities_m3": {k: str(v) for k, v in densities.items()},
            "input_sha256": sha(text.encode()),
            "expected": expected(densities)}
    (folder / "expected.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


def verify(folder: Path) -> dict:
    report = json.loads((folder / "expected.json").read_text())
    all_cases = report["cases"]
    for name in CASES:
        info = all_cases[name]
        input_file = folder / (name + ".i")
        if sha(input_file.read_bytes()) != info["input_sha256"]:
            raise AssertionError(f"INPUT_SHA_CHANGED:{name}")
        exit_file = folder / (name + ".exit")
        if not exit_file.is_file():
            raise AssertionError(f"NO_NATIVE_EXIT_CODE:{name}")
        exit_code = int(exit_file.read_text().strip())
        if exit_code != 0:
            raise AssertionError(f"NATIVE_EXIT_{exit_code}:{name}")
        output = folder / (name + ".csv")
        if not output.is_file():
            raise AssertionError(f"NO_NATIVE_CSV:{name}")
        with output.open(newline="") as handle:
            rows = list(csv.DictReader(handle))
        if not rows:
            raise AssertionError(f"EMPTY_NATIVE_CSV:{name}")
        observed = rows[-1]
        values = {}
        for key, exp_txt in info["expected"].items():
            if key not in observed or not observed[key]:
                raise AssertionError(f"NO_NUMERICAL_FUNCTOR_VALUE:{name}:{key}")
            actual = float(observed[key])
            expected_value = float(Decimal(exp_txt))
            if not math.isfinite(actual):
                raise AssertionError(f"NONFINITE:{name}:{key}")
            # 17-digit parsed exp(log(n/N_A)) undergoes a few ULPs;
            # the net neutral charge is the strongest cancellation case.
            absolute_tolerance = {
                "nq_observed": 8.0,
                "rho_observed": 1e-17,
                "rhs_observed": 2e-7,
            }[key]
            tolerance = max(absolute_tolerance, abs(expected_value) * 1e-9)
            if abs(actual - expected_value) > tolerance:
                raise AssertionError(
                    f"NUMERIC_MISMATCH:{name}:{key} measured={actual:.17g} "
                    f"oracle={expected_value:.17g} tolerance={tolerance:.6g}")
            values[key] = {
                "actual": actual, "independent_oracle": expected_value,
                "absolute_error": abs(actual - expected_value),
                "acceptance_tolerance": tolerance}
        p = float(observed.get("potential_avg", "nan"))
        if not math.isfinite(p):
            raise AssertionError(f"POISSON_CONSUMER_NOT_EVALUATED:{name}")
        source = float(Decimal(info["expected"]["rhs_observed"]))
        if source > 0 and p <= 0:
            raise AssertionError(f"POISSON_KERNEL_RHS_SIGN_WRONG:{name} potential={p}")
        if source < 0 and p >= 0:
            raise AssertionError(f"POISSON_KERNEL_RHS_SIGN_WRONG:{name} potential={p}")
        info["native_stdout_sha256"] = sha((folder / (name + ".stdout.log")).read_bytes())
        info["native_csv_sha256"] = sha(output.read_bytes())
        info["native_exit_code"] = exit_code
        info["actual"] = values
        info["potential_avg"] = p
        info["outcome"] = "PASS_ACTUAL_CPP_FUNCTOR_NUMERIC"
    report["observed_count"] = len(CASES)
    report["all_numerical_cases_pass"] = len(all_cases) == len(CASES) and all(
        x.get("outcome") == "PASS_ACTUAL_CPP_FUNCTOR_NUMERIC"
        for x in all_cases.values())
    report["native_solver_scope"] = "controlled 1D steady Poisson, not full S6 plasma timestep"
    report["native_S6_full_rhs_evaluation"] = "NOT_RUN"
    report["SCIENCE_HOLD"] = True
    (folder / "native_numeric_receipt.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n")
    if not report["all_numerical_cases_pass"]:
        raise AssertionError("INCOMPLETE_CASES")
    return report


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("command", choices=("prepare", "verify"))
    p.add_argument("--dir", type=Path, required=True)
    args = p.parse_args()
    print(json.dumps(
        prepare(args.dir) if args.command == "prepare" else verify(args.dir),
        sort_keys=True))
