#!/usr/bin/env python3
"""Code4 PR-B: bounded constant-coefficient drift vs standard FVAdvection.

The only tested hypothesis is c*z*mu*(-grad phi) = constant velocity
for a RAW scalar FV variable, identical upwind and excluded exterior faces.
No general candidate approval, Native science acceptance, or C++ retirement.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path

N_CELLS = 12
DT = 0.005
N_STEPS = 3
CASES = {
    "charge_plus": dict(z=1, mu=0.01, carrier=1.0, grad_phi=-100.0),
    "charge_minus": dict(z=-1, mu=0.01, carrier=1.0, grad_phi=-100.0),
    "electric_zero": dict(z=1, mu=0.01, carrier=1.0, grad_phi=0.0),
    "mobility_zero": dict(z=1, mu=0.0, carrier=1.0, grad_phi=-100.0),
    "carrier_two": dict(z=1, mu=0.01, carrier=2.0, grad_phi=-100.0),
}


def constant_velocity(case: dict) -> float:
    if case["z"] == 0 or case["carrier"] <= 0 or case["mu"] < 0:
        raise ValueError("INVALID_BOUNDED_DRIFT_CONTRACT")
    return -case["z"] * case["mu"] * case["carrier"] * case["grad_phi"]


def old_face_flux(u_elem: float, u_neighbor: float, case: dict,
                  normal: float = 1.0) -> float:
    drift_normal = -case["z"] * case["mu"] * case["grad_phi"] * normal
    upwind = u_elem if drift_normal >= 0 else u_neighbor
    return case["carrier"] * upwind * drift_normal


def candidate_face_flux(u_elem: float, u_neighbor: float, case: dict,
                        normal: float = 1.0) -> float:
    vnormal = constant_velocity(case) * normal
    upwind = u_elem if vnormal >= 0 else u_neighbor
    return upwind * vnormal


def face_oracle() -> None:
    for name, case in CASES.items():
        for normal in (-1.0, 1.0):
            for left, right in ((1.0, 2.0), (4.0, 1.0), (0.3, 0.7)):
                a = old_face_flux(left, right, case, normal)
                b = candidate_face_flux(left, right, case, normal)
                if not math.isclose(a, b, abs_tol=1e-13, rel_tol=1e-13):
                    raise AssertionError((name, a, b))
    plus, minus = (CASES[k] for k in ("charge_plus", "charge_minus"))
    assert old_face_flux(2.0, 5.0, plus) > 0.0
    assert old_face_flux(2.0, 5.0, minus) < 0.0
    assert constant_velocity(CASES["electric_zero"]) == 0
    assert constant_velocity(CASES["mobility_zero"]) == 0
    assert constant_velocity(CASES["carrier_two"]) == 2 * constant_velocity(plus)
    # Negative controls: wrong electric-field sign or missing carrier changes flux.
    assert not math.isclose(old_face_flux(2, 5, plus), -candidate_face_flux(2, 5, plus))
    assert not math.isclose(old_face_flux(2, 5, CASES["carrier_two"]),
                            candidate_face_flux(2, 5, plus))
    # Heavy-species correction is conditional: sum(w)=1 and exact matching
    # provisional flux reconstructs -J; intentionally missing species fails.
    weights = (0.2, 0.3, 0.5)
    j_direct = sum((1, -1, 1)[i] * weights[i] for i in range(3))
    correction = -j_direct * sum(weights)
    assert math.isclose(j_direct + correction, 0, abs_tol=1e-14)
    assert not math.isclose(j_direct - j_direct * sum(weights[:-1]), 0, abs_tol=1e-14)


def render(case: dict, implementation: str) -> str:
    vel = constant_velocity(case)
    name = "old" if implementation == "old" else "candidate"
    if name == "old":
        flux_kernel = f"""    type = PhysicsFVElectrostaticDrift
    variable = u
    potential = potential_linear
    mobility = mobility
    carrier = carrier
    charge_number = {case['z']}
    advected_interp_method = upwind
    boundaries_to_avoid = 'left right'"""
    else:
        flux_kernel = f"""    type = FVAdvection
    variable = u
    velocity = '{vel:.17g} 0 0'
    advected_interp_method = upwind
    boundaries_to_avoid = 'left right'"""
    return f"""# code4 bounded A/B, no general retirement implication.
[Mesh]
  type = GeneratedMesh
  dim = 1
  nx = {N_CELLS}
  xmin = 0
  xmax = 1
[]
[Variables]
  [u]
    type = MooseVariableFVReal
  []
[]
[Functions]
  [potential_linear]
    type = ParsedFunction
    expression = '{case['grad_phi']:.17g}*x'
  []
  [initial_profile]
    type = ParsedFunction
    expression = '1+0.4*x'
  []
[]
[ICs]
  [u_initial]
    type = FunctionIC
    variable = u
    function = initial_profile
  []
[]
[FunctorMaterials]
  [constant_coefficients]
    type = ADGenericFunctorMaterial
    prop_names = 'mobility carrier'
    prop_values = '{case['mu']:.17g} {case['carrier']:.17g}'
  []
[]
[FVKernels]
  [time]
    type = FVTimeKernel
    variable = u
  []
  [drift]
{flux_kernel}
  []
[]
[Postprocessors]
  [u_min]
    type = ElementExtremeFunctorValue
    functor = u
    value_type = min
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [u_max]
    type = ElementExtremeFunctorValue
    functor = u
    value_type = max
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [u_integral]
    type = ElementIntegralFunctorPostprocessor
    functor = u
    execute_on = 'INITIAL TIMESTEP_END'
  []
[]
[Executioner]
  type = Transient
  solve_type = NEWTON
  automatic_scaling = true
  dt = {DT}
  end_time = {DT*N_STEPS}
  nl_abs_tol = 1e-12
  nl_rel_tol = 1e-11
  nl_max_its = 30
[]
[Outputs]
  csv = true
  execute_on = 'INITIAL TIMESTEP_END'
[]
"""


def prepare(output: Path, source_sha: str) -> dict:
    face_oracle()
    output.mkdir(parents=True, exist_ok=True)
    runs = []
    for name, case in CASES.items():
        for variant in ("old", "candidate"):
            path = output / f"{name}_{variant}.i"
            contents = render(case, variant)
            path.write_text(contents, encoding="utf-8")
            runs.append(dict(case=name, variant=variant, input=path.name,
                             input_sha256=hashlib.sha256(contents.encode()).hexdigest(),
                             physical_velocity=constant_velocity(case)))
    manifest = dict(schema="code4.pr_b.bounded_native.v0.1", source_sha=source_sha,
                    classification="UNEXECUTED_BOUNDED_FIXTURE", runs=runs,
                    conditions=dict(raw_state=True, constant_mobility=True,
                                    constant_carrier=True, linear_potential=True,
                                    upwind=True, external_faces_excluded=True),
                    excluded=["variable_functors", "nonlinear_potential", "log_molar",
                              "wall_bc", "heavy_mass_correction", "full_ad_parity"])
    (output / "inputs_manifest.json").write_text(
        json.dumps(manifest, sort_keys=True, indent=2)+"\n", encoding="utf-8")
    return manifest


def step_reference(previous: list[float], velocity: float) -> list[float]:
    r = abs(velocity) * DT * N_CELLS
    n = len(previous)
    current = [0.0] * n
    if velocity >= 0:
        current[0] = previous[0] / (1 + r) if r else previous[0]
        for i in range(1, n):
            diagonal = 1.0 if i == n-1 else 1.0+r
            current[i] = (previous[i] + r*current[i-1]) / diagonal
    else:
        current[-1] = previous[-1] / (1+r)
        for i in range(n-2, -1, -1):
            diagonal = 1.0 if i == 0 else 1.0+r
            current[i] = (previous[i] + r*current[i+1]) / diagonal
    return current


def independent_reference(velocity: float, steps: int) -> dict:
    values = [1+0.4*(i+0.5)/N_CELLS for i in range(N_CELLS)]
    for _ in range(steps):
        values = step_reference(values, velocity)
    return {"u_min": min(values), "u_max": max(values),
            "u_integral": sum(values)/N_CELLS}


def read_csv(path: Path) -> list[dict]:
    if not path.is_file():
        raise FileNotFoundError(f"MISSING_NATIVE_OUTPUT:{path}")
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if not rows or not {"time", "u_min", "u_max", "u_integral"}.issubset(rows[0]):
        raise ValueError(f"INCOMPLETE_NATIVE_OBSERVABLES:{path}")
    return rows


def near(a: float, b: float, *, relative: float = 1e-6,
         absolute: float = 1e-9) -> bool:
    return abs(a-b) <= absolute + relative*max(abs(a), abs(b))


def analyze(directory: Path, expected_sha: str, binary_sha256: str) -> dict:
    manifest = json.loads((directory / "inputs_manifest.json").read_text())
    if manifest["source_sha"] != expected_sha or not binary_sha256:
        raise ValueError("NATIVE_EXACT_SOURCE_BINARY_MISMATCH")
    for item in manifest["runs"]:
        actual = hashlib.sha256((directory/item["input"]).read_bytes()).hexdigest()
        if actual != item["input_sha256"]:
            raise ValueError(f"INPUT_MUTATED:{item['input']}")
    records = []
    failures = []
    for name, case in CASES.items():
        rows = {v: read_csv(directory / f"{name}_{v}_out.csv")
                for v in ("old", "candidate")}
        if len(rows["old"]) != len(rows["candidate"]) or len(rows["old"]) < N_STEPS+1:
            failures.append(f"{name}:MISSING_TIMESTEPS")
            continue
        observations = []
        for old_row, candidate_row in zip(rows["old"], rows["candidate"]):
            t_old, t_candidate = float(old_row["time"]), float(candidate_row["time"])
            index = round(t_old / DT)
            if not near(t_old, t_candidate, relative=0, absolute=1e-12) or index < 0 or index > N_STEPS:
                failures.append(f"{name}:TIME_GRID_MISMATCH")
                continue
            reference = independent_reference(constant_velocity(case), index)
            for metric in ("u_min", "u_max", "u_integral"):
                a, b = float(old_row[metric]), float(candidate_row[metric])
                target = reference[metric]
                # Exact old-vs-new Native comparison is narrower than the
                # independent one-dimensional implicit-Euler reference.
                if not near(a, b, relative=3e-5, absolute=1e-8):
                    failures.append(f"{name}:{metric}:NATIVE_AB_MISMATCH:t={t_old}")
                if not near(a, target, relative=2e-3, absolute=1e-5):
                    failures.append(f"{name}:{metric}:INDEPENDENT_ORACLE_MISMATCH:t={t_old}")
                observations.append(dict(time=t_old, metric=metric, old=a,
                                         candidate=b, independent=target))
        records.append(dict(case=name, velocity=constant_velocity(case),
                            observations=observations))
    return dict(schema="code4.pr_b.native_ab.v0.1", source_sha=expected_sha,
                binary_sha256=binary_sha256, cases=records, failures=sorted(set(failures)),
                bounded_native=("PASS" if not failures else "FAIL"),
                general_replacement="NOT_APPROVED",
                coupled_heavy_mass_parity="NOT_EVALUATED",
                wall_bc_parity="NOT_EVALUATED",
                general_ad_jacobian_parity="NOT_EVALUATED",
                safe_delete="HOLD")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--prepare", action="store_true")
    p.add_argument("--analyze", action="store_true")
    p.add_argument("--directory", required=True, type=Path)
    p.add_argument("--expected-head", required=True)
    p.add_argument("--binary-sha256")
    a = p.parse_args()
    if a.prepare == a.analyze:
        p.error("choose exactly one of --prepare/--analyze")
    if a.prepare:
        info = prepare(a.directory, a.expected_head)
        print(f"CODE4_PR_B_PREPARED={len(info['runs'])}")
        return 0
    report = analyze(a.directory, a.expected_head, a.binary_sha256 or "")
    (a.directory / "native_ab_result.json").write_text(
        json.dumps(report, indent=2, sort_keys=True)+"\n", encoding="utf-8")
    print("CODE4_PR_B_BOUNDED_NATIVE_AB=" + report["bounded_native"])
    print("CODE4_PR_B_SAFE_DELETE=HOLD")
    for failure in report["failures"]:
        print("CODE4_PR_B_FAILURE=" + failure)
    return 0 if report["bounded_native"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
