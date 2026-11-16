#!/usr/bin/env python3
"""Issue #541 task 3: real, bounded PhysicsApp FEM signed-charge discriminator.

This is a synthetic P3 solver/residual-response test, NOT S6 scientific parity.
The electron ID "e" is deliberately never assigned +1: Chemistry rejects it.
Instead the same FEM species ID O2p is run with charge +1 and -1 in ephemeral
JSON, with identical remaining inputs, to isolate the signed FEM drift term.
A zero-mobility control distinguishes charge-independent solver changes.
"""
from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
SOURCE_JSON = ROOT / "experiments/Issue402_plasma_dsl_g1/plasma_species_initial_p2.json"
MIN_EFFECT = 1.0e-4
ZERO_TOL = 2.0e-5
FIELD_MIN = 0.1
FIELD_TOL = 1.0e-8
CASES = (("positive", 1, 1.0), ("negative", -1, 1.0), ("zero_drift", 1, 0.0))

INPUT = """# Synthetic JSON-signed FEM charge response; one real implicit timestep.
# No historical S6/P3 inputs, production model, or rate data are modified.
[Mesh]
  type = GeneratedMesh
  dim = 1
  nx = 8
  xmin = 0
  xmax = 1
[]
[Variables]
  [potential]
    family = LAGRANGE
    order = FIRST
  []
[]
[Kernels]
  [potential_laplace]
    type = Diffusion
    variable = potential
  []
  [potential_source]
    type = BodyForce
    variable = potential
    value = 8
  []
[]
[BCs]
  [potential_left]
    type = DirichletBC
    variable = potential
    boundary = left
    value = 0
  []
  [potential_right]
    type = DirichletBC
    variable = potential
    boundary = right
    value = 0
  []
[]
[Physics]
  [Plasmas]
    files = mechanism.json
    [Transport]
      [DriftDiffusion]
        [Continuity]
          fem_species = O2p
          fem_potential = potential
        []
      []
    []
  []
[]
[Postprocessors]
  [center_log]
    type = PointValue
    variable = log_O2p
    point = '0.5 0 0'
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [center_potential]
    type = PointValue
    variable = potential
    point = '0.5 0 0'
    execute_on = 'INITIAL TIMESTEP_END'
  []
[]
[Executioner]
  type = Transient
  dt = 0.02
  num_steps = 1
  solve_type = NEWTON
  nl_rel_tol = 1e-10
  nl_abs_tol = 1e-12
  nl_max_its = 30
  abort_on_solve_fail = true
[]
[Outputs]
  file_base = result
  csv = true
  exodus = false
[]
"""


class EvidenceError(RuntimeError):
    pass


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def check_response(measured: dict[str, dict[str, float]]) -> dict[str, float]:
    if set(measured) != {name for name, _, _ in CASES}:
        raise EvidenceError("Missing, extra or duplicated signed-charge control")
    for name in measured:
        record = measured[name]
        if set(record) != {"center_log", "center_potential", "time"}:
            raise EvidenceError("Incomplete source-bound FEM observation: " + name)
        if any(not math.isfinite(float(v)) for v in record.values()):
            raise EvidenceError("Non-finite FEM observation: " + name)
        if abs(record["time"] - 0.02) > 1.0e-10:
            raise EvidenceError("No real 0.02 s timestep observation: " + name)
        if record["center_potential"] < FIELD_MIN:
            raise EvidenceError("Prescribed nonzero FEM field not established: " + name)
    positive = measured["positive"]["center_log"]
    negative = measured["negative"]["center_log"]
    reference = measured["zero_drift"]["center_log"]
    fields = [measured[name]["center_potential"] for name, _, _ in CASES]
    if max(fields) - min(fields) > FIELD_TOL:
        raise EvidenceError("Electric field changed with the JSON charge")
    if abs(reference) > ZERO_TOL:
        raise EvidenceError("Zero-mobility solver control did not preserve uniform state")
    # The imposed Poisson potential is concave, phi(x)=4*x*(1-x).
    # The weak FEM flux is grad(test).(D grad(c) + z mu c grad(phi)).
    # With initial c=1 mol/m3, positive z depletes x=0.5; negative z
    # enriches it. This observes the signed assembled residual via a real solve.
    if not (positive < reference - MIN_EFFECT and
            negative > reference + MIN_EFFECT):
        raise EvidenceError("JSON charge sign did not reverse FEM drift response")
    return {
        "positive_center_log": positive,
        "negative_center_log": negative,
        "zero_drift_center_log": reference,
        "positive_minus_zero": positive - reference,
        "negative_minus_zero": negative - reference,
        "center_potential": fields[0],
    }


def self_test() -> None:
    valid = {
        "positive": {"center_log": -0.12, "center_potential": 1.0, "time": 0.02},
        "negative": {"center_log": 0.13, "center_potential": 1.0, "time": 0.02},
        "zero_drift": {"center_log": 0.0, "center_potential": 1.0, "time": 0.02},
    }
    check_response(valid)
    mutations = [
        lambda v: v["negative"].update(center_log=-0.13),
        lambda v: v["positive"].update(center_log=0.12),
        lambda v: v["positive"].update(center_log=0.0),
        lambda v: v["zero_drift"].update(center_log=0.01),
        lambda v: v["negative"].update(center_potential=0.0),
        lambda v: v["negative"].update(center_potential=1.1),
        lambda v: v["negative"].update(time=0.0),
        lambda v: v["negative"].update(center_log=float("nan")),
        lambda v: v.pop("negative"),
    ]
    for index, mutate in enumerate(mutations):
        broken = copy.deepcopy(valid)
        mutate(broken)
        try:
            check_response(broken)
        except (EvidenceError, ValueError):
            continue
        raise AssertionError("Validator accepted negative mutation " + str(index))
    print("ISSUE541_TASK3_SIGNED_FEM_RESIDUAL_P0_SELFTEST_PASS")


def make_case(directory: Path, charge: int, mobility: float) -> None:
    directory.mkdir(parents=True, exist_ok=False)
    mechanism = json.loads(SOURCE_JSON.read_text(encoding="utf-8"))
    if mechanism["species"]["e"]["charge_number"] != -1:
        raise EvidenceError("The canonical electron sign changed")
    species = mechanism["species"]["O2p"]
    if species["charge_number"] != 1:
        raise EvidenceError("Unexpected canonical heavy-ion charge")
    species.update(
        charge_number=charge,
        mobility=mobility,
        diffusivity=0.05,
        initial_number_density=602214076000000000000000,
    )
    (directory / "mechanism.json").write_text(
        json.dumps(mechanism, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (directory / "input.i").write_text(INPUT, encoding="utf-8")


def execute(binary: Path, directory: Path, *, check_input: bool, timeout: int) -> None:
    args = [str(binary), "--check-input", "-i", "input.i"] if check_input else [
        str(binary), "-i", "input.i"
    ]
    label = "p2" if check_input else "p3"
    try:
        result = subprocess.run(
            args, cwd=directory, capture_output=True, text=True, timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise EvidenceError(label + " timed out for " + directory.name) from exc
    (directory / (label + ".log")).write_text(
        result.stdout + "\n" + result.stderr, encoding="utf-8"
    )
    if result.returncode != 0:
        raise EvidenceError(label + " physics-opt exit " + str(result.returncode) +
                            " for " + directory.name)
    if check_input and "Syntax OK" not in result.stdout + result.stderr:
        raise EvidenceError("No actual Native syntax success: " + directory.name)


def read_observation(directory: Path) -> dict[str, float]:
    path = directory / "result.csv"
    if not path.is_file():
        raise EvidenceError("Native solved output missing: " + str(path))
    with path.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    if not rows:
        raise EvidenceError("No solver measurements: " + directory.name)
    try:
        result = {key: float(rows[-1][key]) for key in (
            "time", "center_log", "center_potential"
        )}
    except (KeyError, TypeError, ValueError) as exc:
        raise EvidenceError("Malformed solver CSV: " + directory.name) from exc
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--executable", type=Path)
    parser.add_argument("--p1-identity", type=Path)
    parser.add_argument("--expected-head")
    parser.add_argument("--oci-image")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--timeout", type=int, default=120)
    args = parser.parse_args()

    self_test()
    if args.self_test:
        return 0
    if any(x is None for x in (
        args.executable, args.p1_identity, args.expected_head,
        args.oci_image, args.output_dir
    )):
        parser.error("P1 identity, exact head, OCI image, output and binary required")

    binary = args.executable.resolve(strict=True)
    identity = json.loads(args.p1_identity.read_text(encoding="utf-8"))
    if identity.get("P1") != "PASS" or identity.get("source_sha") != args.expected_head:
        raise EvidenceError("Untrusted source-bound P1 identity")
    if identity.get("oci_image") != args.oci_image:
        raise EvidenceError("OCI identity mismatch")
    if identity.get("binary_sha256") != digest(binary):
        raise EvidenceError("Built executable SHA-256 mismatch")
    if subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip() != args.expected_head:
        raise EvidenceError("Checkout no longer matches source HEAD")
    if args.output_dir.exists():
        raise EvidenceError("Refusing to overwrite existing task3 evidence")
    args.output_dir.mkdir(parents=True)
    # All P2 construction checks finish before any real P3 timestep starts.
    for name, charge, mobility in CASES:
        make_case(args.output_dir / name, charge, mobility)
    for name, _, _ in CASES:
        execute(binary, args.output_dir / name, check_input=True, timeout=args.timeout)
    measurements = {}
    for name, _, _ in CASES:
        directory = args.output_dir / name
        execute(binary, directory, check_input=False, timeout=args.timeout)
        measurements[name] = read_observation(directory)
    result = check_response(measurements)
    receipt = {
        "schema": "issue541.task3.real_native_fem_sign.v1",
        "source_sha": args.expected_head,
        "binary_sha256": digest(binary),
        "oci_image": args.oci_image,
        "canonical_json_sha256": digest(SOURCE_JSON),
        "synthetic_charge_target": "O2p",
        "only_charge_differs_between_positive_and_negative": True,
        "measured": measurements,
        "discriminator": result,
        "P0": "PASS",
        "P1": "PASS_SOURCE_BOUND_BINARY",
        "P2": "PASS",
        "P3": "PASS_SYNTHETIC_FEM_DISCRIMINATOR",
        "S6_SCIENCE": "HOLD",
    }
    (args.output_dir / "receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print("ISSUE541_TASK3_JSON_SIGNED_FEM_RESIDUAL_NATIVE_PASS")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (EvidenceError, OSError, subprocess.CalledProcessError) as exc:
        print("ISSUE541_TASK3_JSON_SIGNED_FEM_RESIDUAL_HOLD: " + str(exc), file=sys.stderr)
        sys.exit(1)
