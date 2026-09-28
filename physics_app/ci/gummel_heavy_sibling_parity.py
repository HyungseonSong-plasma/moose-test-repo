#!/usr/bin/env python3
"""Prepare and compare the production heavy->Gummel sibling architecture.

Source input is the already-qualified Issue337 PlasmaClosures case.  This tool
changes ownership only:
  heavy MAIN -> Gummel coordinator -> {electron, Poisson} sibling MultiApps.

The electron energy state rename n_epsilon -> mean_en is symbol-only.  Its
normalization, equations, initial state, and physical interpretation are kept
identical to the qualified input.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import re
import shutil
from pathlib import Path

from physics_harness.adapters.moose.input import MooseInput


FIXED_POINT_PARAMS = (
    "fixed_point_algorithm",
    "transformed_variables",
    "multiapp_fixed_point_convergence",
    "fixed_point_min_its",
    "fixed_point_max_its",
    "fixed_point_rel_tol",
    "fixed_point_abs_tol",
    "accept_on_max_fixed_point_iteration",
)


def _block(text: str, path: str) -> str:
    span = MooseInput(text).unique(path)
    return text[span.start:span.end]


def _remove_if(text: str, path: str) -> str:
    doc = MooseInput(text)
    found = doc.find(path)
    if not found:
        return text
    if len(found) != 1:
        raise RuntimeError(f"ambiguous block {path}: {len(found)}")
    span = found[0]
    return text[:span.start] + text[span.end:]


def _remove_matching(text: str, prefix: str) -> str:
    paths = [b.path for b in MooseInput(text).blocks if b.path.startswith(prefix)]
    for path in sorted(paths, key=len, reverse=True):
        text = _remove_if(text, path)
    return text


def _remove_optional_parameters(text: str, path: str, names: tuple[str, ...]) -> str:
    span = MooseInput(text).unique(path)
    block = text[span.start:span.end]
    for name in names:
        pattern = re.compile(
            rf"(?m)^\s*{re.escape(name)}\s*=\s*[^#\r\n]*\s*(?:#.*)?(?:\r?\n|$)"
        )
        block, count = pattern.subn("", block, count=1)
        if count > 1:
            raise RuntimeError(f"duplicate parameter {name} in {path}")
    return text[:span.start] + block + text[span.end:]


def _append_child(text: str, parent: str, payload: str) -> str:
    return MooseInput(text).insert_before_close(parent, payload.rstrip())[0]


def _append_top(text: str, payload: str) -> str:
    if not text.endswith("\n"):
        text += "\n"
    return text + "\n" + payload.strip("\n") + "\n"


def _initial_child_blocks(fast: str) -> str:
    names = (
        "w_O2p_h",
        "w_Om_h",
        "w_Op_h",
        "potential_from_poisson",
        "electron_density_out",
        "mean_energy_out",
    )
    return "\n".join(_block(fast, f"AuxVariables/{name}").rstrip() for name in names)


def _coordinator(fast: str) -> str:
    mesh = _block(fast, "Mesh").rstrip()
    executioner = _block(fast, "Executioner").rstrip()
    outputs = _block(fast, "Outputs").rstrip()
    aux = _initial_child_blocks(fast)

    return f"""# Production Gummel coordinator.
# Physics equations live only in electron.i and poisson.i.
{mesh}

[Problem]
  solve = false
  kernel_coverage_check = false
[]

[AuxVariables]
{aux}
[]

[GummelIteration]
  [electron_poisson]
    electron_multiapp = electron_state
    electron_input_file = electron.i
    electron_multiapp_type = TransientMultiApp

    poisson_multiapp = poisson
    poisson_input_file = poisson.i
    poisson_multiapp_type = TransientMultiApp

    # Core sibling exchange.
    electron_density_variable = log_e
    poisson_electron_density_variable = log_e_frozen
    poisson_potential_variable = potential_plasma
    electron_potential_variable = potential_from_poisson

    electron_state_variables = 'log_e mean_en'

    # Frozen heavy state from MAIN -> coordinator -> electron.
    coordinator_to_electron_source_variables = 'w_O2p_h w_Om_h w_Op_h'
    coordinator_to_electron_variables = 'w_O2p_h w_Om_h w_Op_h'

    # Electron -> Poisson at TIMESTEP_END, before the Poisson solve.
    electron_to_poisson_source_variables =
      'mean_en potential_from_poisson w_O2p_h w_Om_h w_Op_h'
    electron_to_poisson_variables =
      'mean_en_frozen phi_anchor_frozen w_O2p_frozen w_Om_frozen w_Op_frozen'

    # Latest converged state mirrored to the coordinator.
    electron_to_coordinator_source_variables = 'electron_density_out mean_energy_out'
    electron_to_coordinator_variables = 'electron_density_out mean_energy_out'
    poisson_to_coordinator_source_variables = 'potential_plasma'
    poisson_to_coordinator_variables = 'potential_from_poisson'

    poisson_transformed_variables = 'potential_plasma'
    relaxation_factor = 0.45
    no_restore = true

    manage_convergence = true
    convergence_name = gummel_delta_phi
    # In sibling mode this postprocessor is read directly from the Poisson subapp.
    delta_phi_postprocessor = fp_delta_phi_max
    delta_phi_abs_tol = 1.0e-6
  []
[]

[Postprocessors]
  [fixed_point_iterations]
    type = NumFixedPointIterations
    execute_on = 'TIMESTEP_END'
  []
  [cumulative_fixed_point_iterations]
    type = CumulativeValuePostprocessor
    postprocessor = fixed_point_iterations
    execute_on = 'TIMESTEP_END'
  []
[]

{executioner}

{outputs}
"""


def _electron(fast: str) -> str:
    text = fast
    text = _remove_if(text, "GummelIteration")
    text = _remove_if(text, "FunctorMaterials/fp_delta_phi_abs")
    text = _remove_if(text, "Postprocessors/fp_delta_phi_max")
    text = _remove_if(text, "Postprocessors/fixed_point_iterations")
    text = _remove_if(text, "Postprocessors/cumulative_fixed_point_iterations")
    text = _remove_if(text, "AuxVariables/fp_phi_anchor_diag")
    text = _remove_matching(text, "Postprocessors/fp_phi_current_")
    text = _remove_matching(text, "Postprocessors/fp_phi_anchor_")
    text = _remove_optional_parameters(text, "Executioner", FIXED_POINT_PARAMS)

    # Pure symbol migration: do not change state convention or scaling.
    text = text.replace("n_epsilon", "mean_en")
    return text


def _poisson(poisson: str) -> str:
    text = poisson.replace("n_epsilon_frozen", "mean_en_frozen")
    text = text.replace("PhysicsFVGummelBandedCorrection", "FVElectronResponseBandedCorrection")

    material = """  [fp_delta_phi_abs]
    type = ADParsedFunctorMaterial
    property_name = fp_delta_phi_abs
    functor_names = 'potential_plasma phi_anchor_frozen'
    functor_symbols = 'phi phi0'
    expression = 'abs(phi-phi0)'
  []"""
    text = _append_child(text, "FunctorMaterials", material)

    pp = """[Postprocessors]
  [fp_delta_phi_max]
    type = ADElementExtremeFunctorValue
    functor = fp_delta_phi_abs
    value_type = max
    execute_on = 'TIMESTEP_END'
  []
[]"""
    if MooseInput(text).find("Postprocessors"):
        text = _append_child(
            text,
            "Postprocessors",
            """  [fp_delta_phi_max]
    type = ADElementExtremeFunctorValue
    functor = fp_delta_phi_abs
    value_type = max
    execute_on = 'TIMESTEP_END'
  []""",
        )
    else:
        text = _append_top(text, pp)
    return text


def prepare(source: Path, output: Path) -> None:
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)

    parent = (source / "input.i").read_text()
    fast = (source / "fast_sub.i").read_text()
    poisson = (source / "poisson_sub.i").read_text()

    # Preserve the qualified heavy parent byte-for-byte except for the subapp input filename.
    parent, _ = MooseInput(parent).replace_parameters(
        "MultiApps/electron", {"input_files": "'gummel.i'"}
    )

    (output / "input.i").write_text(parent)
    (output / "gummel.i").write_text(_coordinator(fast))
    (output / "electron.i").write_text(_electron(fast))
    (output / "poisson.i").write_text(_poisson(poisson))

    for name in ("electron_moments.txt", "o2_elastic.txt", "transport_data.txt", "case.json"):
        src = source / name
        if src.exists():
            shutil.copy2(src, output / name)

    # Static scientific contract.
    p = (output / "input.i").read_text()
    g = (output / "gummel.i").read_text()
    e = (output / "electron.i").read_text()
    q = (output / "poisson.i").read_text()

    assert "input_files = 'gummel.i'" in p
    assert "[PlasmaClosures]" in p and "[heavy]" in p
    assert "[PlasmaClosures]" in e and "[electron]" in e
    assert "[PlasmaClosures]" in q and "[charge]" in q
    assert "[GummelIteration]" in g
    assert "electron_input_file = electron.i" in g
    assert "poisson_input_file = poisson.i" in g
    assert "fixed_point_algorithm = 'steffensen'" in g
    assert "transformed_variables = 'potential_from_poisson'" in g
    assert "relaxation_factor = 0.45" in g
    assert "delta_phi_abs_tol = 1.0e-6" in g
    assert "type = FVElectronResponseBandedCorrection" in q
    assert "bandwidth = 5" in q
    assert "n_epsilon" not in e
    assert "n_epsilon_frozen" not in q
    assert "mean_en" in e and "mean_en_frozen" in q

    print(f"GUMMEL_HEAVY_SIBLING_PREPARED {output}")


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def _find_one(root: Path, patterns: tuple[str, ...]) -> Path:
    hits: list[Path] = []
    for pat in patterns:
        hits.extend(root.glob(pat))
    hits = sorted(set(hits))
    if len(hits) != 1:
        raise AssertionError(f"expected one file for {patterns}, got {hits}")
    return hits[0]


def _profile_from_csv(case: Path) -> list[dict[str, float]]:
    path = _find_one(case, ("input_final_csv_parent_profile_*.csv",))
    rows = _read_csv(path)
    out = []
    for r in rows:
        out.append(
            {
                "x": float(r["x"]),
                "electron_density": float(r["electron_density_fast"]),
                "mean_energy_eV": float(r["mean_energy_fast"]),
                "potential": float(r["potential_fast"]),
                "w_O2p": float(r["w_O2p"]),
                "w_Om": float(r["w_Om"]),
                "w_Op": float(r["w_Op"]),
                "heavy_charge_C_m3": float(r["heavy_charge_out"]),
                "net_charge_C_m3": float(r["net_charge_out"]),
            }
        )
    out.sort(key=lambda x: x["x"])
    return out


def _potential_series(case: Path) -> list[dict[str, float]]:
    rows = _read_csv(case / "input_step_csv.csv")
    return [
        {
            "time_s": float(r["time"]),
            "phi_avg_V": float(r["phi_avg"]),
            "phi_min_V": float(r["phi_min"]),
            "phi_max_V": float(r["phi_max"]),
        }
        for r in rows
    ]


def _fp_series(case: Path) -> list[dict[str, float]]:
    path = case / "input_out_electron0_step_csv.csv"
    if not path.exists():
        candidates = sorted(
            p for p in case.glob("*electron0*step_csv.csv")
            if "electron_state" not in p.name and "poisson" not in p.name
        )
        if len(candidates) != 1:
            raise AssertionError(f"cannot locate coordinator step CSV: {candidates}")
        path = candidates[0]
    rows = _read_csv(path)
    return [
        {
            "time_s": float(r["time"]),
            "fixed_point_iterations": int(float(r["fixed_point_iterations"])),
            "cumulative_fixed_point_iterations": int(
                float(r["cumulative_fixed_point_iterations"])
            ),
        }
        for r in rows
    ]


def _rel_err(a: list[dict[str, float]], b: list[dict[str, float]], key: str) -> float:
    scale = max(max(abs(float(x[key])) for x in a), 1.0e-30)
    return max(abs(float(x[key]) - float(y[key])) for x, y in zip(a, b, strict=True)) / scale


def _max_abs(a: list[dict[str, float]], b: list[dict[str, float]], key: str) -> float:
    return max(abs(float(x[key]) - float(y[key])) for x, y in zip(a, b, strict=True))


def compare(case: Path, golden_json: Path, output_json: Path | None) -> None:
    golden_bundle = json.loads(golden_json.read_text())
    golden = golden_bundle["runs"]["plasma_closures"]

    profile = _profile_from_csv(case)
    fp = _fp_series(case)
    potential = _potential_series(case)

    gp = list(golden["final_profile"])
    gf = list(golden["fixed_point_time_series"])
    gt = list(golden["potential_time_series"])

    if len(profile) != len(gp):
        raise AssertionError(f"profile point mismatch {len(profile)} != {len(gp)}")
    if len(fp) != len(gf):
        raise AssertionError(f"FP point mismatch {len(fp)} != {len(gf)}")
    if len(potential) != len(gt):
        raise AssertionError(f"trajectory point mismatch {len(potential)} != {len(gt)}")

    profile_keys = (
        "electron_density",
        "mean_energy_eV",
        "potential",
        "w_O2p",
        "w_Om",
        "w_Op",
        "heavy_charge_C_m3",
        "net_charge_C_m3",
    )
    profile_exact = all(
        float(a[k]) == float(b[k])
        for a, b in zip(profile, gp, strict=True)
        for k in profile_keys + ("x",)
    )

    fp_exact = all(
        int(a["fixed_point_iterations"]) == int(b["fixed_point_iterations"])
        and int(a["cumulative_fixed_point_iterations"]) == int(b["cumulative_fixed_point_iterations"])
        and float(a["time_s"]) == float(b["time_s"])
        for a, b in zip(fp, gf, strict=True)
    )

    trajectory_exact = all(
        float(a[k]) == float(b[k])
        for a, b in zip(potential, gt, strict=True)
        for k in ("time_s", "phi_avg_V", "phi_min_V", "phi_max_V")
    )

    metrics = {
        f"{k}_einf": _rel_err(gp, profile, k)
        for k in profile_keys
    }
    metrics.update(
        {
            "trajectory_phi_avg_max_abs_V": _max_abs(gt, potential, "phi_avg_V"),
            "trajectory_phi_min_max_abs_V": _max_abs(gt, potential, "phi_min_V"),
            "trajectory_phi_max_max_abs_V": _max_abs(gt, potential, "phi_max_V"),
            "trajectory_time_max_abs_s": _max_abs(gt, potential, "time_s"),
            "fp_total_golden": int(gf[-1]["cumulative_fixed_point_iterations"]),
            "fp_total_trial": int(fp[-1]["cumulative_fixed_point_iterations"]),
        }
    )

    finite = all(math.isfinite(float(v)) for v in metrics.values())
    numerical_parity = (
        finite
        and metrics["electron_density_einf"] <= 1.0e-10
        and metrics["mean_energy_eV_einf"] <= 1.0e-10
        and metrics["potential_einf"] <= 1.0e-10
        and metrics["w_O2p_einf"] <= 1.0e-10
        and metrics["w_Om_einf"] <= 1.0e-10
        and metrics["w_Op_einf"] <= 1.0e-10
        and metrics["heavy_charge_C_m3_einf"] <= 1.0e-10
        and metrics["net_charge_C_m3_einf"] <= 1.0e-10
        and metrics["trajectory_phi_avg_max_abs_V"] <= 1.0e-9
        and metrics["trajectory_phi_min_max_abs_V"] <= 1.0e-9
        and metrics["trajectory_phi_max_max_abs_V"] <= 1.0e-9
        and metrics["fp_total_trial"] == metrics["fp_total_golden"]
    )

    result = {
        "classification": (
            "GUMMEL_HEAVY_SIBLING_EXACT_PARITY"
            if profile_exact and fp_exact and trajectory_exact
            else (
                "GUMMEL_HEAVY_SIBLING_NUMERICAL_PARITY"
                if numerical_parity and fp_exact
                else "GUMMEL_HEAVY_SIBLING_PARITY_FAIL"
            )
        ),
        "profile_exact": profile_exact,
        "fixed_point_history_exact": fp_exact,
        "potential_trajectory_exact": trajectory_exact,
        "metrics": metrics,
        "profile_points": len(profile),
        "fixed_point_points": len(fp),
        "potential_points": len(potential),
    }

    if output_json:
        output_json.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print("GUMMEL_HEAVY_SIBLING_PARITY", json.dumps(result, sort_keys=True))
    if result["classification"] == "GUMMEL_HEAVY_SIBLING_PARITY_FAIL":
        raise SystemExit(2)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--prepare", nargs=2, metavar=("SOURCE", "OUTPUT"))
    ap.add_argument("--compare", nargs=2, metavar=("CASE", "GOLDEN_JSON"))
    ap.add_argument("--output-json", type=Path)
    args = ap.parse_args()

    if args.prepare:
        prepare(Path(args.prepare[0]), Path(args.prepare[1]))
    elif args.compare:
        compare(Path(args.compare[0]), Path(args.compare[1]), args.output_json)
    else:
        ap.error("choose --prepare SOURCE OUTPUT or --compare CASE GOLDEN_JSON")


if __name__ == "__main__":
    main()
