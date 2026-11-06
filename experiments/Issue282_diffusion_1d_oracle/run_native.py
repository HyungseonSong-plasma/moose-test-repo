#!/usr/bin/env python3
"""Issue #282: real, pinned QPX/MOOSE run versus independent 1-D cosine oracle.

Track A only: no SOL/adapter package install, no production plasma capability.
Status from this script is NUMERICAL_EVIDENCE, never Physics scientific sign-off.
Always preserve generated input/log/CSV/Exodus, even on check or solve failure.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
import traceback

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
IMAGE = (
    "ghcr.io/hyungseonsong-plasma/physics-runtime@sha256:"
    "cda9f0d09a17aed5fa606e97d1ee5c3450f7280536cec2e5c635402bb07d972c"
)
LENGTH_M = 0.01
END_S = 1.0e-8
AMPLITUDE = 0.25
RELATIVE_TARGET = 1.0e-4
PI = math.pi
DIFFUSIVITIES = (0.0, 100.0)
MESHES = (64, 128, 256)
STEPS = (10, 20, 40)


def render_input(*, nx: int, steps: int, diffusivity: float) -> str:
    if nx < 2 or steps < 1 or diffusivity not in DIFFUSIVITIES:
        raise ValueError("outside bounded Issue282 benchmark")
    dt = END_S / steps
    return f"""# Issue282 independent cosine/zero-Neumann diffusion (not historical 2-D E2a)
[Mesh]
  type = GeneratedMesh
  dim = 1
  nx = {nx}
  xmin = 0
  xmax = {LENGTH_M:.17g}
[]
[Variables]
  [u]
    type = MooseVariableFVReal
  []
[]
[Functions]
  [cosine_initial]
    type = ParsedFunction
    expression = '1 + {AMPLITUDE:.17g}*cos({PI:.17g}*x/{LENGTH_M:.17g})'
  []
[]
[ICs]
  [energy_ic]
    type = FunctionIC
    variable = u
    function = cosine_initial
  []
[]
[FunctorMaterials]
  [controlled_diffusivity]
    type = ADGenericFunctorMaterial
    prop_names = 'controlled_energy_diffusivity'
    prop_values = '{diffusivity:.17g}'
  []
[]
[FVKernels]
  [energy_time]
    type = FVTimeKernel
    variable = u
  []
  [energy_diffusion]
    type = FVDiffusion
    variable = u
    coeff = controlled_energy_diffusivity
  []
[]
# Natural zero flux at each end; no drift, Joule, chemistry or wall energy source.
[Postprocessors]
  [normalized_energy_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = u
    execute_on = 'INITIAL TIMESTEP_END'
  []
[]
[Executioner]
  type = Transient
  # The controlled constant-D PDE is linear; avoid unneeded nonlinear line search.
  solve_type = LINEAR
  petsc_options_iname = '-pc_type'
  petsc_options_value = 'lu'
  dt = {dt:.17g}
  end_time = {END_S:.17g}
  num_steps = {steps}
  l_tol = 1e-12
[]
[Outputs]
  csv = true
  exodus = true
  file_base = out
  execute_on = 'INITIAL TIMESTEP_END'
[]
"""


def cosine_cell_average(lo: float, hi: float, *, diffusivity: float, t: float) -> float:
    """Independent exact *cell average*, not the generated MOOSE IR."""
    k = PI / LENGTH_M
    decay = math.exp(-diffusivity * k * k * t)
    return 1.0 + AMPLITUDE * decay * (
        math.sin(k * hi) - math.sin(k * lo)
    ) / (k * (hi - lo))


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _name(value: object) -> str:
    if hasattr(value, "tobytes"):
        return value.tobytes().decode("utf-8", "replace").strip("\x00 ")
    return "".join(
        p.decode("utf-8", "replace") if isinstance(p, bytes) else str(p)
        for p in value
    ).strip("\x00 ")


def exodus_field(path: Path, *, expected_nx: int):
    """Decode actual FV element values. Never silently treat interpolated nodes as FV cells."""
    from netCDF4 import Dataset  # external evidence reader, CI installs pinned wheel

    with Dataset(str(path)) as ds:
        if "name_elem_var" not in ds.variables:
            raise ValueError("Exodus does not expose elemental FV field: name_elem_var absent")
        names = [_name(row) for row in ds.variables["name_elem_var"][:]]
        if "u" not in names:
            raise ValueError(f"Exodus lacks elemental u: {names!r}")
        var_num = names.index("u") + 1
        if "coordx" not in ds.variables:
            raise ValueError("Exodus lacks coordx")
        coordinates = [float(x) for x in ds.variables["coordx"][:]]
        elements = []
        for key in sorted(ds.variables):
            if not key.startswith("connect"):
                continue
            block = key[len("connect"):]
            values_key = f"vals_elem_var{var_num}eb{block}"
            if values_key not in ds.variables:
                raise ValueError(f"Exodus lacks {values_key}")
            conn = ds.variables[key][:]
            values = ds.variables[values_key][:]
            if len(values) < 2:
                raise ValueError("Exodus needs initial and final FV field snapshots")
            if len(conn) != len(values[-1]):
                raise ValueError("Exodus connectivity/field count mismatch")
            for j, nodes in enumerate(conn):
                xs = sorted(coordinates[int(n) - 1] for n in nodes)
                elements.append((xs[0], xs[-1], float(values[0][j]), float(values[-1][j])))
        elements.sort(key=lambda e: e[0])
        if len(elements) != expected_nx:
            raise ValueError(f"Expected {expected_nx} cells, got {len(elements)}")
        if not math.isclose(elements[0][0], 0.0, abs_tol=1e-12) or not math.isclose(
            elements[-1][1], LENGTH_M, abs_tol=1e-12
        ):
            raise ValueError("Exodus does not cover the expected 1-D domain")
        return elements


def evaluate(elements, *, diffusivity: float) -> dict:
    norm = error = initial_integral = final_integral = 0.0
    strict_control = True
    for x0, x1, initial, final in elements:
        width = x1 - x0
        if width <= 0 or not all(map(math.isfinite, (initial, final))):
            raise ValueError("Nonfinite FV state or invalid cell")
        expected = cosine_cell_average(x0, x1, diffusivity=diffusivity, t=END_S)
        norm += expected * expected * width
        error += (final - expected) ** 2 * width
        initial_integral += initial * width
        final_integral += final * width
        strict_control &= abs(final - initial) <= (1e-12 + 1e-10 * abs(initial))
    relative_l2 = math.sqrt(error / norm)
    conservation = abs(final_integral - initial_integral) / abs(initial_integral)
    result = {
        "normalized_field_relative_l2": relative_l2,
        "normalized_inventory_relative_defect": conservation,
        "normalized_initial_integral_m": initial_integral,
        "normalized_final_integral_m": final_integral,
        "nonnegative": all(e[3] >= -1e-12 for e in elements),
        "d0_strict_cellwise_preservation": strict_control if diffusivity == 0 else None,
        "candidate_target_relative": RELATIVE_TARGET,
    }
    result["numeric_threshold_met"] = (
        relative_l2 <= RELATIVE_TARGET
        and conservation <= RELATIVE_TARGET
        and result["nonnegative"]
        and (diffusivity != 0 or strict_control)
    )
    return result


def call_backend(case_dir: Path, args: list[str], log_name: str) -> int:
    relative = case_dir.relative_to(ROOT).as_posix()
    cmd = [
        "docker", "run", "--rm", "--network", "none",
        "-v", f"{ROOT}:/workspace", "-w", f"/workspace/{relative}",
        IMAGE, *args,
    ]
    try:
        cp = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        text = f"command: {args!r}\nreturncode: {cp.returncode}\n"
        text += "stdout:\n" + cp.stdout + "\nstderr:\n" + cp.stderr
        (case_dir / log_name).write_text(text, encoding="utf-8")
        return cp.returncode
    except Exception:
        (case_dir / log_name).write_text(traceback.format_exc(), encoding="utf-8")
        return -1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", type=Path, default=HERE / "results")
    ap.add_argument("--prepare-only", action="store_true")
    args = ap.parse_args()
    results = args.results.resolve()
    if not results.is_relative_to(ROOT):
        raise ValueError("results must stay under the repository for artifact retention")
    results.mkdir(parents=True, exist_ok=True)
    manifest = {
        "issue": 282, "mode": "TRACK_A_NATIVE_QPX",
        "scientific_acceptance": "PENDING_INDEPENDENT_PHYSICS_VALIDATOR",
        "is_historical_gaussian_e2a": False,
        "source_sha": subprocess.check_output(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True
        ).strip(),
        "image": IMAGE, "length_m": LENGTH_M, "end_time_s": END_S,
        "relative_target": RELATIVE_TARGET, "solver_strategy": "LINEAR / PETSc LU",
        "cases": [],
    }
    bad = 0
    for nx in MESHES:
        for steps in STEPS:
            for diffusivity in DIFFUSIVITIES:
                tag = f"nx{nx}_steps{steps}_D{int(diffusivity)}"
                case = results / tag
                case.mkdir(parents=True, exist_ok=True)
                input_path = case / "input.i"
                input_path.write_text(
                    render_input(nx=nx, steps=steps, diffusivity=diffusivity),
                    encoding="utf-8",
                )
                item = {
                    "case": tag, "nx": nx, "steps": steps, "D_m2_s": diffusivity,
                    "input_sha256": digest(input_path), "status": "PREPARED",
                }
                manifest["cases"].append(item)
                (results / "manifest.json").write_text(
                    json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
                )
                if args.prepare_only:
                    continue
                check = call_backend(case, ["--check-input", "-i", "input.i"], "check.log")
                item["check_returncode"] = check
                if check != 0:
                    item["status"] = "P2_CHECK_FAILED"
                    bad += 1
                    continue
                execute = call_backend(case, ["-i", "input.i"], "run.log")
                item["run_returncode"] = execute
                if execute != 0:
                    item["status"] = "P3_SOLVE_FAILED"
                    bad += 1
                    continue
                files = sorted(case.glob("out.e*"))
                if not files:
                    item["status"] = "EXODUS_MISSING"
                    bad += 1
                    continue
                try:
                    item["exodus_files"] = [
                        {"name": f.name, "sha256": digest(f)} for f in files
                    ]
                    item["numeric"] = evaluate(
                        exodus_field(files[0], expected_nx=nx),
                        diffusivity=diffusivity,
                    )
                    item["status"] = (
                        "NUMERIC_TARGET_MET_NOT_SCIENCE_ACCEPTED"
                        if item["numeric"]["numeric_threshold_met"]
                        else "NUMERIC_TARGET_EXCEEDED"
                    )
                    if not item["numeric"]["numeric_threshold_met"]:
                        bad += 1
                except Exception as exc:
                    item["status"] = "INCONCLUSIVE_FIELD_DECODE"
                    item["evidence_error"] = repr(exc)
                    bad += 1
            (results / "manifest.json").write_text(
                json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
            )
    manifest["run_status"] = (
        "PREPARED_ONLY" if args.prepare_only
        else "ALL_NUMERIC_TARGETS_MET_NOT_SCIENCE_ACCEPTED" if not bad
        else f"UNRESOLVED_OR_FAILED_{bad}_OF_{len(manifest['cases'])}"
    )
    (results / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"status": manifest["run_status"], "case_count": len(manifest["cases"])}))
    return 0 if args.prepare_only or not bad else 1


if __name__ == "__main__":
    sys.exit(main())
