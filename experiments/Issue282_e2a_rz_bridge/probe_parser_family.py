#!/usr/bin/env python3
"""Issue #282: distinguish native AD parser failure from coupled RZ dependency.

Research-only numerical-disabling controls; no historical Physics equivalence.
Every RZ control stays pinned against the prior GDB artifact; standalone
controls use the actual *previously passing* 1D PhysicsApp FV diffusion input.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import traceback

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.Issue282_diffusion_1d_oracle.run_native import render_input
from experiments.Issue282_e2a_rz_bridge.diagnose_segv import make_case
from experiments.Issue282_e2a_rz_bridge.diagnose_gdb_stack import INPUT_SHA256, MESH_SHA256
from experiments.Issue282_e2a_rz_bridge.run_native import IMAGE, PER_CASE_TIMEOUT, run_native
from physics_harness.adapters.moose import blocks as mb
from physics_harness.adapters.moose import parameters as mp

HERE = Path(__file__).resolve().parent
CASES = (
    ("mini_fv_base", None, "mini_base"),
    ("mini_generic_integral", None, "mini_generic"),
    ("mini_ad_integral_default", None, "mini_ad"),
    ("mini_ad_integral_jitoff", None, "mini_ad_jitoff"),
    ("mini_nested_ad_jitoff", None, "mini_nested_jitoff"),
    ("r4_original", "r4_qf1_predecessor", "control"),
    ("r4_all_parsed_generic", "r4_qf1_predecessor", "all_parsed_generic"),
    ("e2a_original", "e2a_zero_diffusion", "control"),
    ("e2a_all_parsed_generic", "e2a_zero_diffusion", "all_parsed_generic"),
)
MATERIAL_CONST = {
    "Mn_mix": 0.032,
    "rho_mat": 1.0,
    "w_O2_constraint": 1.0,
    "sum_w_functor": 1.0,
    "dMn_dt_model": 0.0,
    "drho_dt_model": 0.0,
    "n_e_physical": 1.0e16,
    "electron_energy_density_J_m3": 1.0,
    "n_epsilon_physical_eV_m3": 1.0,
    "mean_en_solved": 5.73276,
}
DEFAULT_CONST = 0.1


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def mini_input(mode: str) -> str:
    """Derived only from independently validated 1-D D=0 native FV case."""
    src = render_input(nx=64, steps=10, diffusivity=0.0)
    if mode == "mini_base":
        return src
    if mode == "mini_generic":
        parsed = """  [ad_probe]
    type = ADGenericFunctorMaterial
    prop_names = 'ad_probe'
    prop_values = '2.0'
  []"""
    else:
        parsed = """  [ad_probe]
    type = ADParsedFunctorMaterial
    property_name = ad_probe
    functor_names = 'u'
    functor_symbols = 'uval'
    expression = '2.0*uval'
  []"""
    src = mb.insert_child_block(src, "FunctorMaterials", parsed)
    target = "ad_probe"
    if mode == "mini_nested_jitoff":
        src = mb.insert_child_block(src, "FunctorMaterials", """  [ad_probe_outer]
    type = ADParsedFunctorMaterial
    property_name = ad_probe_outer
    functor_names = 'ad_probe'
    functor_symbols = 'inner'
    expression = '1.0+inner'
  []""")
        target = "ad_probe_outer"
    src = mb.insert_child_block(src, "Postprocessors", f"""  [ad_probe_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = {target}
    execute_on = 'INITIAL TIMESTEP_END'
  []""")
    if mode.endswith("jitoff"):
        src = mb.append_top_level_block(src, """[GlobalParams]
  enable_jit = false
[]""")
    return src


def all_parsed_to_generics(text: str) -> tuple[str, list[dict]]:
    """Replace only AD parsed material BLOCKS; never change historic input."""
    rows: list[dict] = []
    for path in mp.direct_children(text, "FunctorMaterials"):
        if mp.get_parameter(text, path, "type") != "ADParsedFunctorMaterial":
            continue
        name = path.split("/", 1)[1]
        property_name = mp.unquote(mp.get_parameter(text, path, "property_name"))
        if not property_name or any(ch.isspace() for ch in property_name):
            raise ValueError(f"cannot safely replace property at {path}")
        value = MATERIAL_CONST.get(property_name, DEFAULT_CONST)
        replacement = (
            f"  [{name}]\n"
            "    type = ADGenericFunctorMaterial\n"
            f"    prop_names = '{property_name}'\n"
            f"    prop_values = '{value:.17g}'\n"
            "    block = plasma\n"
            "  []"
        )
        text = mb.replace_block(text, path, replacement)
        rows.append({"block": path, "property": property_name, "constant": value})
    if len(rows) < 10:
        raise ValueError(f"expected >=10 AD parsed materials, found {len(rows)}")
    if any(
        mp.get_parameter(text, path, "type") == "ADParsedFunctorMaterial"
        for path in mp.direct_children(text, "FunctorMaterials")
    ):
        raise ValueError("AD parsed family substitution incomplete")
    return text, rows


def save(root: Path, report: dict) -> None:
    (root / "manifest.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--prepare-only", action="store_true")
    ap.add_argument("--results", type=Path, default=HERE / "parser_family_results")
    args = ap.parse_args()
    root = args.results.resolve()
    if not root.is_relative_to(ROOT):
        raise ValueError("results directory must be inside checkout")
    root.mkdir(parents=True, exist_ok=True)
    report = {
        "issue": 282, "class": "NATIVE_AD_PARSER_FAMILY_AND_MINIMAL_POSITIVE_CONTROL",
        "scientific_acceptance": "PENDING_NOT_EVALUATED",
        "exact_source_sha": subprocess.check_output(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True
        ).strip(),
        "image": IMAGE,
        "model_perturbations_not_science_equivalence": True,
        "cases": {},
    }
    save(root, report)
    for name, original_name, mode in CASES:
        case = root / name
        row = {
            "kind": "MINIMAL_1D_CONTROL" if original_name is None else "HISTORICAL_RZ",
            "original_case": original_name,
            "mode": mode, "status": "STAGING",
        }
        report["cases"][name] = row
        save(root, report)
        try:
            if original_name is None:
                case.mkdir()
                src = mini_input(mode)
                (case / "input.i").write_text(src, encoding="utf-8")
            else:
                provenance = make_case(case, original_name)
                src = (case / "input.i").read_text(encoding="utf-8")
                if digest(case / "input.i") != INPUT_SHA256[original_name] or (
                    digest(case / "qvt.msh") != MESH_SHA256
                ):
                    row["status"] = "HISTORICAL_INPUT_DRIFT_FAIL_CLOSED"
                    continue
                row["baseline_sha256"] = digest(case / "input.i")
                row["source_provenance"] = provenance
                if mode == "all_parsed_generic":
                    src, changed = all_parsed_to_generics(src)
                    row["changed_ad_materials"] = changed
                    (case / "input.i").write_text(src, encoding="utf-8")
            row["input_sha256"] = digest(case / "input.i")
            row["status"] = "PREPARED_NOT_SCIENCE"
            save(root, report)
            if args.prepare_only:
                continue
            p2 = run_native(
                case, ["--check-input", "-i", "input.i"],
                log_name="check.log", timeout=PER_CASE_TIMEOUT,
            )
            row["p2_rc"] = p2
            if p2 != 0:
                row["status"] = "P2_REJECTED_INCOMPARABLE"
                continue
            p3 = run_native(
                case, ["-i", "input.i"],
                log_name="run.log", timeout=PER_CASE_TIMEOUT,
            )
            row["p3_rc"] = p3
            row["status"] = (
                "P3_SEGFAULT" if p3 in (139, -11)
                else "P3_COMPLETED_NOT_SCIENCE" if p3 == 0
                else "P3_OTHER_FAILURE"
            )
        except Exception as exc:
            row["status"] = "INCONCLUSIVE_EXCEPTION"
            row["error"] = repr(exc)
            row["traceback"] = traceback.format_exc()
        finally:
            save(root, report)

    if args.prepare_only:
        report["verdict"] = "PREPARED_ONLY"
        save(root, report)
        return 0 if all(r["status"] == "PREPARED_NOT_SCIENCE" for r in report["cases"].values()) else 1

    rows = report["cases"]
    base = rows["mini_fv_base"]["status"] == "P3_COMPLETED_NOT_SCIENCE"
    r4 = rows["r4_original"]["status"] == "P3_SEGFAULT"
    e2a = rows["e2a_original"]["status"] == "P3_SEGFAULT"
    report["reference_controls_reproduced"] = bool(base and r4 and e2a)
    report["results_ready_for_independent_diagnosis"] = bool(base and r4 and e2a)
    report["verdict"] = (
        "CONTROLLED_PARSER_FAMILY_EVIDENCE_CAPTURED_NOT_SCIENCE"
        if base and r4 and e2a else "INCONCLUSIVE_REQUIRED_CONTROLS"
    )
    save(root, report)
    print(json.dumps({
        "verdict": report["verdict"],
        "cases": {k: v["status"] for k, v in rows.items()},
    }, sort_keys=True))
    # A mixed success/failure run is a valid *diagnostic*, NOT a science PASS.
    return 0 if base and r4 and e2a else 1


if __name__ == "__main__":
    sys.exit(main())
