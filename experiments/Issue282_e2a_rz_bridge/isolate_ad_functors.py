#!/usr/bin/env python3
"""Physics #282: bounded RZ AD parsed-material dependency discriminator.

Uses the EXACT historical R4-QF1/E2a D=0 source generator and pinned native
PhysicsApp image. The original input is NEVER edited; substitutions only
modify derived copies and intentionally alter the equations for debugging.
A successful modified solve is NOT scientific parity or Physics acceptance.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import traceback

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.Issue282_e2a_rz_bridge.diagnose_segv import make_case
from experiments.Issue282_e2a_rz_bridge.diagnose_gdb_stack import (
    INPUT_SHA256,
    MESH_SHA256,
)
from experiments.Issue282_e2a_rz_bridge.run_native import (
    IMAGE, PER_CASE_TIMEOUT, run_native,
)
from physics_harness.adapters.moose import blocks as mb
from physics_harness.adapters.moose import parameters as mp

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "functor_isolation_results"
# 10 bounded cases; no broad combinatorial sweep or arbitrary solver changes.
CASES = (
    ("r4_original", "r4_qf1_predecessor", "control"),
    ("r4_rho_generic", "r4_qf1_predecessor", "rho_generic"),
    ("r4_rho_parsed_constant", "r4_qf1_predecessor", "rho_parsed_constant"),
    ("r4_mn_generic", "r4_qf1_predecessor", "mn_generic"),
    ("e2a_original", "e2a_zero_diffusion", "control"),
    ("e2a_rho_generic", "e2a_zero_diffusion", "rho_generic"),
    ("e2a_energy_inventory_off", "e2a_zero_diffusion", "energy_inventory_off"),
    ("e2a_energy_density_generic", "e2a_zero_diffusion", "energy_density_generic"),
    ("e2a_mass_integrals_off", "e2a_zero_diffusion", "mass_integrals_off"),
    ("e2a_all_ad_integrals_off", "e2a_zero_diffusion", "all_ad_integrals_off"),
)
RHO_PATH = "FunctorMaterials/mixture_density"
MN_PATH = "FunctorMaterials/mean_molar_mass"
ENERGY_DENSITY_PATH = "FunctorMaterials/electron_energy_density_J_m3"
ENERGY_PP_PATH = "Postprocessors/electron_energy_inventory_J"
RHO_GENERIC = """  [mixture_density]
    type = ADGenericFunctorMaterial
    prop_names = 'rho_mat'
    prop_values = '1.0'
    block = plasma
  []"""
RHO_PARSED_CONSTANT = """  [mixture_density]
    type = ADParsedFunctorMaterial
    property_name = rho_mat
    expression = '1.0'
    block = plasma
  []"""
MN_GENERIC = """  [mean_molar_mass]
    type = ADGenericFunctorMaterial
    prop_names = 'Mn_mix'
    prop_values = '0.032'
    block = plasma
  []"""
ENERGY_GENERIC = """  [electron_energy_density_J_m3]
    type = ADGenericFunctorMaterial
    prop_names = 'electron_energy_density_J_m3'
    prop_values = '1.192119776885221'
    block = plasma
  []"""


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def transform(text: str, mode: str) -> tuple[str, list[str]]:
    """Exactly enumerate changed root dependencies; do not mutate historical input."""
    if mode == "control":
        return text, []
    if mode == "rho_generic":
        return mb.replace_block(text, RHO_PATH, RHO_GENERIC), [RHO_PATH]
    if mode == "rho_parsed_constant":
        return mb.replace_block(text, RHO_PATH, RHO_PARSED_CONSTANT), [RHO_PATH]
    if mode == "mn_generic":
        return mb.replace_block(text, MN_PATH, MN_GENERIC), [MN_PATH]
    if mode == "energy_inventory_off":
        return mb.remove_block(text, ENERGY_PP_PATH), [ENERGY_PP_PATH]
    if mode == "energy_density_generic":
        return (
            mb.replace_block(text, ENERGY_DENSITY_PATH, ENERGY_GENERIC),
            [ENERGY_DENSITY_PATH],
        )
    if mode in ("mass_integrals_off", "all_ad_integrals_off"):
        removed = []
        for path in mp.direct_children(text, "Postprocessors"):
            if mp.get_parameter(text, path, "type") != "ADElementIntegralFunctorPostprocessor":
                continue
            if mode == "mass_integrals_off" and not (
                path == "Postprocessors/mass_total" or
                path.startswith("Postprocessors/mass_")
            ):
                continue
            removed.append(path)
        if not removed:
            raise ValueError("isolation selected no integral postprocessors")
        for path in removed:
            text = mb.remove_block(text, path)
        return text, removed
    raise ValueError(f"unsupported isolation mode: {mode}")


def persist(out: Path, manifest: dict) -> None:
    (out / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--prepare-only", action="store_true")
    ap.add_argument("--results", type=Path, default=RESULTS)
    args = ap.parse_args()
    out = args.results.resolve()
    if not out.is_relative_to(ROOT):
        raise ValueError("results must stay within checkout for immutable artifact capture")
    out.mkdir(parents=True, exist_ok=True)
    report = {
        "issue": 282,
        "class": "NATIVE_RZ_AD_FUNCTOR_DEPENDENCY_ISOLATION",
        "scientific_acceptance": "NOT_EVALUATED_DIAGNOSTIC_ONLY",
        "source_sha": subprocess.check_output(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True
        ).strip(),
        "pinned_runtime": IMAGE,
        "historical_input_preserved": True,
        "modifications_not_physics_equivalence": True,
        "reference_native_gdb_artifact": 13519757615,
        "cases": {},
    }
    persist(out, report)
    for tag, original_case, mode in CASES:
        case = out / tag
        row = {
            "parent": original_case, "isolation_mode": mode,
            "status": "STAGING",
        }
        report["cases"][tag] = row
        persist(out, report)
        try:
            original = make_case(case, original_case)
            row["original"] = original
            baseline = (case / "input.i").read_text(encoding="utf-8")
            row["baseline_projected_sha256"] = hashlib.sha256(
                baseline.encode("utf-8")
            ).hexdigest()
            row["mesh_sha256"] = digest(case / "qvt.msh")
            expected = INPUT_SHA256[original_case]
            if row["baseline_projected_sha256"] != expected or row["mesh_sha256"] != MESH_SHA256:
                row["status"] = "INPUT_DRIFT_FAIL_CLOSED"
                continue

            mutated, changed = transform(baseline, mode)
            if mode == "control" and mutated != baseline:
                raise ValueError("control must remain byte identical")
            if mode != "control" and mutated == baseline:
                raise ValueError("diagnostic mode did not change the input")
            row["changed_root_blocks"] = changed
            (case / "input.i").write_text(mutated, encoding="utf-8")
            row["diagnostic_sha256"] = digest(case / "input.i")
            row["status"] = "PREPARED_RESEARCH_ONLY"
            persist(out, report)
            if args.prepare_only:
                continue

            p2 = run_native(
                case, ["--check-input", "-i", "input.i"],
                log_name="check.log", timeout=PER_CASE_TIMEOUT,
            )
            row["p2_rc"] = p2
            if p2 != 0:
                row["status"] = "P2_REJECTED_NOT_A_RUNTIME_DISCRIMINATOR"
                continue
            p3 = run_native(
                case, ["-i", "input.i"],
                log_name="run.log", timeout=PER_CASE_TIMEOUT,
            )
            row["p3_rc"] = p3
            row["status"] = (
                "P3_SEGFAULT" if p3 in (139, -11)
                else "P3_SOLVE_COMPLETED_NOT_SCIENCE_ACCEPTED" if p3 == 0
                else "P3_OTHER_FAILURE"
            )
        except Exception as exc:
            row["status"] = "INCONCLUSIVE_EXCEPTION"
            row["error"] = repr(exc)
            row["traceback"] = traceback.format_exc()
        finally:
            persist(out, report)

    if args.prepare_only:
        report["verdict"] = "PREPARED_ONLY_NO_NATIVE_EVIDENCE"
        persist(out, report)
        return 0 if all(v["status"] == "PREPARED_RESEARCH_ONLY" for v in report["cases"].values()) else 1

    controls = [report["cases"][x] for x in ("r4_original", "e2a_original")]
    if not all(x["status"] == "P3_SEGFAULT" for x in controls):
        report["verdict"] = "INCONCLUSIVE_CONTROL_NOT_REPRODUCED"
    else:
        contrasted = [
            tag for tag, row in report["cases"].items()
            if row["isolation_mode"] != "control" and
            row["status"] == "P3_SOLVE_COMPLETED_NOT_SCIENCE_ACCEPTED"
        ]
        report["contrast_cases"] = contrasted
        report["verdict"] = (
            "SOLVE_CONTRAST_FOUND_RESEARCH_ONLY" if contrasted
            else "NO_SOLVE_CONTRAST_OR_NOT_COMPARABLE"
        )
    persist(out, report)
    print(json.dumps({
        "verdict": report["verdict"],
        "cases": {k: v["status"] for k, v in report["cases"].items()},
    }, sort_keys=True))
    return 0 if report["verdict"] == "SOLVE_CONTRAST_FOUND_RESEARCH_ONLY" else 1


if __name__ == "__main__":
    sys.exit(main())
