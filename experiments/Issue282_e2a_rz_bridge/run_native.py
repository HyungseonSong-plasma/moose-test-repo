#!/usr/bin/env python3
"""Physics #282: *actual* historical 2-D RZ E2a bridge, not the 1-D oracle.

Uses the immutable published PhysicsApp image and the actual historical
Issue26 E2a generator + qvt.msh geometry. Does not construct a new 2-D
rectangle and falsely claim equivalence with the historical RZ apparatus.

Evidence classes:
  - P2_CHECK / P3_SOLVE / measured CSV / stored Exodus: real backend facts;
  - physical J conversion and independent initial Gaussian reference: audit;
  - final D100 reference on irregular RZ geometry: NOT YET ESTABLISHED;
  - Physics scientific acceptance and SOL/Adapter contract: PENDING.
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
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.Issue26_electron_energy.E2a_controlled_diffusion.run import (
    CASE_DIFFUSIVITIES,
    _stage_case,
    _read_state,
    _case_evidence,
    _cross_case_evidence,
)
from experiments.Issue282_e2a_rz_bridge.research_type_bridge import (
    project_historical_registration_only,
)
from experiments.historical_recipe_support.issue26_e1 import (
    ELEMENTARY_CHARGE_C,
    ENERGY_INVENTORY_PP,
    ENERGY_NORM_AVG_PP,
    ENERGY_NORM_MAX_PP,
    ENERGY_NORM_MIN_PP,
    ENERGY_REFERENCE_EV,
)

HERE = Path(__file__).resolve().parent
IMAGE = (
    "ghcr.io/hyungseonsong-plasma/physics-runtime@sha256:"
    "cda9f0d09a17aed5fa606e97d1ee5c3450f7280536cec2e5c635402bb07d972c"
)
RELATIVE_TOLERANCE = 1e-4
D0_RANGE_RTOL = 1e-10
D0_RANGE_ATOL = 1e-12
EXPRESSION = "1.0 + 0.5*exp(-800.0*(x-0.12)^2 - 80.0*(y-0.22)^2)"
PER_CASE_TIMEOUT = 420


def digest(path: Path) -> str:
    sha = hashlib.sha256()
    with path.open("rb") as source:
        for buffer in iter(lambda: source.read(1 << 20), b""):
            sha.update(buffer)
    return sha.hexdigest()


def analytic_initial(x_m: float, r_m: float) -> float:
    """Independent transcription of frozen E2a Gaussian, not the MOOSE code."""
    return 1.0 + 0.5 * math.exp(
        -800.0 * (x_m - 0.12) ** 2 - 80.0 * (r_m - 0.22) ** 2
    )


def physical_energy_density_j_m3(u: float, n_ref_m3: float) -> float:
    """u is dimensionless; n_ref and E_ref are fixed E2a references."""
    if not all(math.isfinite(v) for v in (u, n_ref_m3)) or n_ref_m3 <= 0:
        raise ValueError("finite u and positive n_ref required")
    return u * n_ref_m3 * ENERGY_REFERENCE_EV * ELEMENTARY_CHARGE_C


def r_z_cell_volume_m3(vertices: list[tuple[float, float]]) -> tuple[float, float, float]:
    """RZ axis=Y: exact volume of revolution of linear-edge triangle/quad.

    The radial coordinate is y, and volume = 2*pi*int_A y dA.
    Polygon area/centroid integral is exact for polygonal cells.
    """
    if len(vertices) < 3:
        raise ValueError("RZ cell needs >=3 ordered vertices")
    signed_area2 = 0.0
    cx6a = 0.0
    cy6a = 0.0
    for (x1, y1), (x2, y2) in zip(vertices, vertices[1:] + vertices[:1]):
        cross = x1 * y2 - x2 * y1
        signed_area2 += cross
        cx6a += (x1 + x2) * cross
        cy6a += (y1 + y2) * cross
    if abs(signed_area2) < 1e-20:
        raise ValueError("degenerate RZ polygon")
    area_m2 = abs(signed_area2) / 2
    cx = cx6a / (3 * signed_area2)
    radius = cy6a / (3 * signed_area2)
    if radius < -1e-12:
        raise ValueError("negative radius in RZ mesh")
    return 2.0 * math.pi * area_m2 * max(0.0, radius), cx, radius


def _field_names(chars) -> list[str]:
    names = []
    for entry in chars:
        if hasattr(entry, "tobytes"):
            names.append(entry.tobytes().decode("utf-8", "replace").strip("\x00 "))
        else:
            names.append("".join(
                (x.decode("utf-8", "replace") if isinstance(x, bytes) else str(x))
                for x in entry
            ).strip("\x00 "))
    return names


def exodus_2d_rz_audit(path: Path, *, n_ref_m3: float) -> dict:
    """Independent mesh-aware initial profile/energy check, no final field oracle.

    Exodus FV field can be block-scoped. Missing/ambiguous block values fail
    closed; never fill unavailable plasma values with zeros.
    """
    from netCDF4 import Dataset
    with Dataset(str(path)) as ds:
        variables = ds.variables
        needed = {"coordx", "coordy", "name_elem_var"}
        missing = needed.difference(variables)
        if missing:
            raise ValueError(f"missing Exodus RZ fields: {sorted(missing)}")
        x = list(map(float, variables["coordx"][:]))
        y = list(map(float, variables["coordy"][:]))
        names = _field_names(variables["name_elem_var"][:])
        if "n_epsilon" not in names:
            raise ValueError(f"Exodus lacks FV n_epsilon: {names!r}")
        j = names.index("n_epsilon") + 1
        elements = []
        for key in sorted(variables):
            if not key.startswith("connect"):
                continue
            block = key[len("connect"):]
            values_key = f"vals_elem_var{j}eb{block}"
            if values_key not in variables:
                continue  # Variable exists in plasma block only.
            data = variables[values_key][:]
            if len(data) < 2:
                raise ValueError(f"missing initial/final states for {values_key}")
            cells = variables[key][:]
            if len(cells) != len(data[0]):
                raise ValueError(f"cell/field length mismatch for {values_key}")
            for row, u_initial, u_final in zip(cells, data[0], data[-1]):
                ids = [int(q) - 1 for q in row]
                vertices = [(x[k], y[k]) for k in ids]
                volume, cx, radius = r_z_cell_volume_m3(vertices)
                if volume <= 0:
                    raise ValueError("RZ plasma cell with zero volume")
                initial, final = float(u_initial), float(u_final)
                if not math.isfinite(initial) or not math.isfinite(final):
                    raise ValueError("nonfinite plasma field value")
                elements.append((volume, cx, radius, initial, final))
        if not elements:
            raise ValueError("Exodus contains no plasma FV n_epsilon cells")
        expected2 = error2 = initial_j = final_j = total_volume = 0.0
        for vol, cx, r, u0, uf in elements:
            expected = analytic_initial(cx, r)
            expected2 += vol * expected**2
            error2 += vol * (u0 - expected)**2
            initial_j += vol * physical_energy_density_j_m3(u0, n_ref_m3)
            final_j += vol * physical_energy_density_j_m3(uf, n_ref_m3)
            total_volume += vol
        return {
            "cell_count": len(elements),
            "RZ_axis": "Y (radial coordinate y)",
            "RZ_volume_m3": total_volume,
            "initial_gaussian_weighted_relative_l2": math.sqrt(error2 / expected2),
            "independent_initial_inventory_J": initial_j,
            "independent_final_inventory_J": final_j,
            "independent_inventory_relative_defect": abs(final_j - initial_j) / abs(initial_j),
            "reference_kind": "historical input Gaussian at FV polygon centroid; initial only",
            "final_D100_analytic_oracle_available": False,
        }


def run_native(case: Path, extra: list[str], *, log_name: str, timeout: int) -> int:
    relative = case.relative_to(ROOT).as_posix()
    command = [
        "docker", "run", "--rm", "--network", "none",
        "-v", f"{ROOT}:/workspace",
        "-w", f"/workspace/{relative}", IMAGE, *extra,
    ]
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, timeout=timeout,
        )
        (case / log_name).write_text(
            f"args={extra!r}\nreturncode={result.returncode}\n"
            + "stdout:\n" + result.stdout + "\nstderr:\n" + result.stderr,
            encoding="utf-8",
        )
        return result.returncode
    except Exception:
        (case / log_name).write_text(traceback.format_exc(), encoding="utf-8")
        return -1


def independent_scalar_checks(cases: dict) -> dict:
    if len(cases) != 2 or any(
        row.get("state_status") != "MEASURED" for row in cases.values()
    ):
        return {"status": "INCONCLUSIVE_DATA_MISSING"}
    output = {}
    energy_start = []
    for label, row in cases.items():
        initial = row["state"]["initial"]
        final = row["state"]["final"]
        a = initial[ENERGY_INVENTORY_PP]
        b = final[ENERGY_INVENTORY_PP]
        defect = abs(a - b) / abs(a) if a else math.inf
        output[label] = {
            "initial_energy_inventory_J": a,
            "final_energy_inventory_J": b,
            "independent_csv_conservation_defect": defect,
            "candidate_conservation_pass": defect <= RELATIVE_TOLERANCE,
            "profile_range_initial": initial[ENERGY_NORM_MAX_PP] - initial[ENERGY_NORM_MIN_PP],
            "profile_range_final": final[ENERGY_NORM_MAX_PP] - final[ENERGY_NORM_MIN_PP],
        }
        energy_start.append(a)
    control = output["zero_diffusion"]
    treatment = output["diffusion"]
    range_ok = math.isclose(
        control["profile_range_initial"], control["profile_range_final"],
        rel_tol=D0_RANGE_RTOL, abs_tol=D0_RANGE_ATOL,
    )
    smooth = treatment["profile_range_final"] < treatment["profile_range_initial"]
    initial_defect = abs(energy_start[0] - energy_start[1]) / max(
        abs(energy_start[0]), abs(energy_start[1]), 1e-300
    )
    output["cross_case"] = {
        "initial_energy_inventory_relative_difference": initial_defect,
        "strict_zero_D_range_preservation": range_ok,
        "positive_D_profile_range_contract": smooth,
    }
    accepted = (
        all(output[k]["candidate_conservation_pass"] for k in ("zero_diffusion", "diffusion"))
        and initial_defect <= RELATIVE_TOLERANCE
        and range_ok and smooth
    )
    output["candidate_scalar_gates_met"] = accepted
    output["status"] = (
        "SCALAR_GATES_MET_NOT_SCIENCE_ACCEPTED" if accepted
        else "SCALAR_GATES_EXCEEDED_NOT_SCIENCE_ACCEPTED"
    )
    return output


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--diagnostic-jit-off", action="store_true",
                        help="research-only: disable parser JIT on projected input, not historical source")
    parser.add_argument("--results", type=Path, default=HERE / "results")
    args = parser.parse_args()
    results = args.results.resolve()
    if not results.is_relative_to(ROOT):
        raise ValueError("results must remain inside checkout for retention")
    results.mkdir(parents=True, exist_ok=True)
    report = {
        "issue": 282, "track": "REAL_HISTORICAL_E2A_2D_RZ",
        "scientific_acceptance": "PENDING_INDEPENDENT_PHYSICS_VALIDATOR",
        "numerical_1D_success": "NOT_TRANSFERABLE_TO_2D_RZ",
        "independent_final_2D_field_oracle": "NOT_YET_ESTABLISHED",
        "image": IMAGE, "candidate_relative_target": RELATIVE_TOLERANCE,
        "diagnostic_jit_off": args.diagnostic_jit_off,
        "research_only_not_physics_parity": True,
        "source_commit": subprocess.check_output(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True
        ).strip(),
        "cases": {},
    }
    exit_failures = 0
    def persist() -> None:
        (results / "manifest.json").write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    for mode, D in CASE_DIFFUSIVITIES.items():
        case = results / mode
        item: dict = {"D_m2_s": D, "status": "STAGING"}
        report["cases"][mode] = item
        persist()
        try:
            meta = _stage_case(case, diffusivity_m2_s=D)
            # Preserve untouched historical input and produce a strictly reversible
            # modern *registration-name only* copy for exploratory P2/P3.
            historical_input = case / "input.historical.i"
            historical_input.write_bytes((case / "input.i").read_bytes())
            projected, bridge_report = project_historical_registration_only(
                historical_input.read_text(encoding="utf-8")
            )
            if args.diagnostic_jit_off:
                # Research-only runtime setting; do not edit the historical file.
                # It changes parser compilation, NOT its mathematical expression.
                from physics_harness.adapters.moose import parameters as mp
                projected = mp.upsert_parameter(
                    projected, "GlobalParams", "enable_jit", "false"
                )
                # Preserve output field evidence for independent RZ audit.
                projected = mp.upsert_parameter(
                    projected, "Outputs", "exodus", "true"
                )
            (case / "input.i").write_text(projected, encoding="utf-8")
            item["historical_input_sha256"] = digest(historical_input)
            item["registration_type_projection"] = bridge_report
            item["projection_not_scientific_parity"] = True
            item["staging_audit"] = meta["construction"]["audit"]["status"]
            item["normalization_reference_eV"] = ENERGY_REFERENCE_EV
            item["normalization_n_ref_m3"] = float(
                meta["construction"]["predecessor"]["electron_reference_density_m3"]
            )
            item["input_sha256"] = digest(case / "input.i")
            item["mesh_sha256"] = digest(case / "qvt.msh")
            item["status"] = "STAGED"
            persist()
            if args.prepare_only:
                continue
            p2 = run_native(
                case, ["--check-input", "-i", "input.i"],
                log_name="check.log", timeout=PER_CASE_TIMEOUT,
            )
            item["P2_returncode"] = p2
            if p2:
                item["status"] = "P2_CHECK_FAILED"
                exit_failures += 1
                continue
            p3 = run_native(case, ["-i", "input.i"],
                            log_name="run.log", timeout=PER_CASE_TIMEOUT)
            item["P3_returncode"] = p3
            if p3:
                item["status"] = "P3_SOLVE_FAILED"
                exit_failures += 1
                continue
            item["state"] = _read_state(case / "input_out.csv")
            item["state_status"] = item["state"]["status"]
            item["e2a_historical_observation"] = _case_evidence(
                item["state"], diffusivity_m2_s=D
            )
            exodus = sorted(case.glob("*.e*"))
            item["exodus"] = [
                {"filename": x.name, "sha256": digest(x)} for x in exodus
            ]
            if not exodus:
                item["status"] = "INCONCLUSIVE_EXODUS_MISSING"
                exit_failures += 1
                continue
            try:
                item["RZ_exodus_independent_audit"] = exodus_2d_rz_audit(
                    exodus[0],
                    n_ref_m3=item["normalization_n_ref_m3"],
                )
            except Exception as exc:
                item["RZ_exodus_audit_status"] = "INCONCLUSIVE"
                item["RZ_exodus_audit_error"] = repr(exc)
            if item["state_status"] != "MEASURED":
                item["status"] = "INCONCLUSIVE_CSV_MEASUREMENTS"
                exit_failures += 1
            else:
                item["status"] = "SOLVED_2D_RZ_AWAITING_INDEPENDENT_SCIENCE"
        except Exception as exc:
            item["status"] = "INCONCLUSIVE_PREPARATION"
            item["error"] = repr(exc)
            item["traceback"] = traceback.format_exc()
            exit_failures += 1
        finally:
            persist()
    if not args.prepare_only:
        report["independent_scalar_audit"] = independent_scalar_checks(
            report["cases"]
        )
        if report["independent_scalar_audit"]["status"] != "SCALAR_GATES_MET_NOT_SCIENCE_ACCEPTED":
            exit_failures += 1
    report["run_status"] = (
        "PREPARED_ONLY" if args.prepare_only
        else "BOTH_E2A_RZ_SOLVES_NUMERICAL_SCALARS_MET_NOT_SCIENCE_ACCEPTED"
        if not exit_failures
        else f"INCONCLUSIVE_OR_FAILED_{exit_failures}"
    )
    persist()
    print(json.dumps({
        "status": report["run_status"],
        "cases": {k: v["status"] for k, v in report["cases"].items()},
    }))
    return 0 if args.prepare_only or not exit_failures else 1


if __name__ == "__main__":
    sys.exit(main())
