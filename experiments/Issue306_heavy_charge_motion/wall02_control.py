#!/usr/bin/env python3
"""Issue #306 Sequence 02: COMSOL-style left charged-heavy wall-loss discriminator.

This sequence preserves the successful Sequence-01 heavy-release construction
and changes one heavy-species boundary axis only:

  bulk mode:
    left remains the Sequence-01 heavy-flow outlet for species transport.

  wall mode:
    O2+, O-, and O+ receive a COMSOL-style absorbing wall flux on left:
      Gamma_wall = s * 1/4 n_i v_th + n_i mu_i max(z_i E_n, 0)

The existing PhysicsIonWallFluxMaterial is the canonical repository owner of
that surface + signed one-sided migration contract.  Bulk electrostatic drift
and heavy-mass electromigration correction continue to avoid left/right, so
wall migration is not double counted.

The INSFV pressure outlet is retained only as the hydrodynamic pressure anchor.
It is not the charged-heavy species boundary condition in wall mode.
"""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from experiments.Issue306_heavy_charge_motion import control as base

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
GENERATED = ROOT / "generated_wall02"
RESULTS = ROOT / "results_wall02"

CHI_H = base.CHI_H
HEAVY_CYCLES = base.HEAVY_CYCLES
FINAL_TAU = base.FINAL_TAU
CASE_SPECS = tuple(
    {
        "name": f"{mode}_chi{int(chi)}",
        "mode": mode,
        "chi": chi,
        "fp_max": {1.0: 100, 10.0: 300, 20.0: 600}[chi],
    }
    for mode in ("bulk", "wall")
    for chi in (1.0, 10.0, 20.0)
)
CASE_NAMES = tuple(str(x["name"]) for x in CASE_SPECS)

WALL = "left"
WALL_SPECIES = {
    "O2p": {
        "variable": "w_O2p",
        "mobility": "mu_O2p",
        "charge": 1,
        "molar_mass": 0.032,
    },
    "Om": {
        "variable": "w_Om",
        "mobility": "mu_Om",
        "charge": -1,
        "molar_mass": 0.016,
    },
    "Op": {
        "variable": "w_Op",
        "mobility": "mu_Op",
        "charge": 1,
        "molar_mass": 0.016,
    },
}


def _params(spec: dict[str, object]) -> dict[str, object]:
    """Return the existing Sequence-01 timing contract with a wall-mode label."""
    p = base._params(spec)
    p["mode"] = str(spec["mode"])
    p["left_charged_wall_loss"] = str(spec["mode"]) == "wall"
    p["left_wall_model"] = (
        "surface_plus_signed_one_sided_migration"
        if p["left_charged_wall_loss"]
        else "none"
    )
    return p


def _wall_material_blocks() -> str:
    """Build current Physics ion-wall materials for O2+, O-, and O+."""
    blocks: list[str] = []
    for species, cfg in WALL_SPECIES.items():
        blocks.append(
            f"""
  [wall_n_{species}]
    type = ADParsedFunctorMaterial
    property_name = wall_n_{species}
    functor_names = 'rho_const {cfg['variable']}'
    functor_symbols = 'rho wf'
    expression = 'rho*wf*{base.prepare.NA:.17g}/{float(cfg['molar_mass']):.17g}'
  []
  [left_wall_flux_{species}]
    type = PhysicsIonWallFluxMaterial
    ion_number_density = wall_n_{species}
    potential = potential_fast
    mobility = {cfg['mobility']}
    gas_temperature = T_g
    charge_number = {int(cfg['charge'])}
    molar_mass = {float(cfg['molar_mass']):.17g}
    sticking = 1.0
    declare_suffix = left_{species}
  []
"""
        )
    return "".join(blocks)


def _wall_bc_blocks() -> str:
    """Build separate surface and migration BCs so each contribution is auditable."""
    blocks: list[str] = []
    for species, cfg in WALL_SPECIES.items():
        blocks.append(
            f"""
  [left_{species}_surface_loss]
    type = FVFunctorNeumannBC
    variable = {cfg['variable']}
    boundary = {WALL}
    functor = ion_surface_mass_flux_left_{species}
    factor = -1.0
  []
  [left_{species}_migration_loss]
    type = FVFunctorNeumannBC
    variable = {cfg['variable']}
    boundary = {WALL}
    functor = ion_migration_mass_flux_left_{species}
    factor = -1.0
  []
"""
        )
    return "".join(blocks)


def _wall_pp_blocks() -> str:
    """Expose signed wall-loss rates for surface and migration components."""
    blocks: list[str] = []
    for species in WALL_SPECIES:
        blocks.append(
            f"""
  [left_{species}_surface_rate]
    type = SideFVFluxBCIntegral
    boundary = {WALL}
    fvbcs = 'left_{species}_surface_loss'
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [left_{species}_migration_rate]
    type = SideFVFluxBCIntegral
    boundary = {WALL}
    fvbcs = 'left_{species}_migration_loss'
    execute_on = 'INITIAL TIMESTEP_END'
  []
"""
        )
    return "".join(blocks)


def _wall_parent(p: dict[str, object]) -> str:
    """Add left COMSOL-style charged-heavy wall loss to the Sequence-01 parent."""
    text = base._released_parent(p)

    material_anchor = """  [charge_state]
    type = ADParsedFunctorMaterial
"""
    if text.count(material_anchor) != 1:
        raise RuntimeError("released-parent material anchor changed")
    text = text.replace(
        material_anchor,
        _wall_material_blocks() + material_anchor,
        1,
    )

    bc_anchor = """  [outlet_p]
    type = INSFVOutletPressureBC
"""
    if text.count(bc_anchor) != 1:
        raise RuntimeError("released-parent outlet anchor changed")
    text = text.replace(
        bc_anchor,
        _wall_bc_blocks() + bc_anchor,
        1,
    )

    pp_anchor = """  [heavy_charge_integral]
    type = ADElementIntegralFunctorPostprocessor
"""
    if text.count(pp_anchor) != 1:
        raise RuntimeError("released-parent postprocessor anchor changed")
    text = text.replace(
        pp_anchor,
        _wall_pp_blocks() + pp_anchor,
        1,
    )

    text = text.replace(
        "# right 20 sccm pure-O2 inlet, left absolute-pressure outlet.\n"
        "# The pressure value is held at the Sequence-12 gas state (0.66661 Pa) so the\n"
        "# fast physics state is not changed while heavy motion is released.",
        "# right 20 sccm pure-O2 inlet.  On left, O2+/O-/O+ use the accepted\n"
        "# COMSOL-style surface + signed one-sided migration wall-loss law.\n"
        "# INSFVOutletPressureBC remains only as the hydrodynamic pressure anchor;",
        1,
    )
    return text


def build(clean: bool = True) -> list[dict[str, object]]:
    """Generate bulk-control and left-wall-loss cases at identical clocks."""
    if clean and GENERATED.exists():
        shutil.rmtree(GENERATED)
    GENERATED.mkdir(parents=True, exist_ok=True)

    poisson = base._poisson_child()
    built: list[dict[str, object]] = []
    fast_by_chi: dict[float, str] = {}

    for spec in CASE_SPECS:
        p = _params(spec)
        case_dir = GENERATED / str(p["name"])
        case_dir.mkdir(parents=True, exist_ok=True)

        fast = base._fast_child(p)
        parent = base._released_parent(p) if p["mode"] == "bulk" else _wall_parent(p)

        (case_dir / "input.i").write_text(parent, encoding="utf-8")
        (case_dir / "fast_sub.i").write_text(fast, encoding="utf-8")
        (case_dir / "poisson_sub.i").write_text(poisson, encoding="utf-8")
        shutil.copy2(base.ELECTRON_MOMENTS, case_dir / "electron_moments.txt")
        shutil.copy2(base.ELASTIC_DATA, case_dir / "o2_elastic.txt")
        shutil.copy2(base.HEAVY_TRANSPORT_DATA, case_dir / "transport_data.txt")
        (case_dir / "case.json").write_text(
            json.dumps(p, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        chi = float(p["chi_e"])
        if chi in fast_by_chi and fast_by_chi[chi] != fast:
            raise RuntimeError(f"fast child changed between wall modes for chi={chi}")
        fast_by_chi[chi] = fast
        built.append(p)

    (GENERATED / "matrix.json").write_text(
        json.dumps(
            {
                "issue": 306,
                "sequence": 2,
                "objective": (
                    "COMSOL-style left charged-heavy wall-loss discriminator at "
                    "fixed chi_h=40 and two heavy cycles"
                ),
                "chi_h": CHI_H,
                "heavy_cycles": HEAVY_CYCLES,
                "total_time_tau": FINAL_TAU,
                "fast_physics": "Issue253 Sequence12 unchanged",
                "control": "bulk released-heavy Sequence01 topology",
                "wall_case": (
                    "left O2+/O-/O+ surface loss plus signed one-sided migration; "
                    "flow pressure outlet retained only as hydrodynamic anchor"
                ),
                "wall_sticking": {"O2p": 1.0, "Om": 1.0, "Op": 1.0},
                "chemistry": False,
                "rf_heating": False,
                "cases": built,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return built


def static_contract() -> dict[str, object]:
    """Verify that wall mode changes only the registered charged-wall axis."""
    built = build()
    by = {str(x["name"]): x for x in built}
    if set(by) != set(CASE_NAMES):
        raise RuntimeError("case set mismatch")

    for chi in (1.0, 10.0, 20.0):
        bulk = by[f"bulk_chi{int(chi)}"]
        wall = by[f"wall_chi{int(chi)}"]
        assert bulk["dt_e_s"] == wall["dt_e_s"]
        assert bulk["dt_h_s"] == wall["dt_h_s"]
        assert bulk["end_time_s"] == wall["end_time_s"]
        assert bulk["fast_steps_per_heavy_cycle"] == int(CHI_H / chi)

        bulk_dir = GENERATED / str(bulk["name"])
        wall_dir = GENERATED / str(wall["name"])
        assert (bulk_dir / "fast_sub.i").read_text() == (wall_dir / "fast_sub.i").read_text()
        assert (bulk_dir / "poisson_sub.i").read_text() == (wall_dir / "poisson_sub.i").read_text()

        bulk_parent = (bulk_dir / "input.i").read_text()
        wall_parent = (wall_dir / "input.i").read_text()
        assert "type = PhysicsIonWallFluxMaterial" not in bulk_parent
        assert wall_parent.count("type = PhysicsIonWallFluxMaterial") == 3
        assert wall_parent.count("boundary = left\n    functor = ion_surface_mass_flux_left_") == 3
        assert wall_parent.count("boundary = left\n    functor = ion_migration_mass_flux_left_") == 3
        assert wall_parent.count("type = SideFVFluxBCIntegral") >= 6
        assert "charge_number = -1" in wall_parent
        assert wall_parent.count("sticking = 1.0") == 3

        # Interior drift and mass-frame correction must not also own the wall.
        assert wall_parent.count("boundaries_to_avoid = 'left right'") == 9

        # Hydrodynamic closure is distinct from the heavy-species wall law.
        assert "type = INSFVOutletPressureBC" in wall_parent
        assert "variable = p" in wall_parent

    return {
        "status": "PASS",
        "issue": 306,
        "sequence": 2,
        "tau_epsilon_initial_s": base.prepare.tau_epsilon(),
        "chi_h": CHI_H,
        "heavy_cycles": HEAVY_CYCLES,
        "total_time_tau": FINAL_TAU,
        "matrix": built,
        "wall_contract": (
            "Gamma_i,w = sticking*0.25*n_i*v_th + "
            "n_i*mu_i*max(z_i*E_n,0) on left for O2+/O-/O+"
        ),
    }


def p0() -> None:
    """Run the static construction gate."""
    summary = static_contract()
    print("ISSUE306_WALL02_P0: PASS")
    print(json.dumps(summary, indent=2, sort_keys=True))


def _docker(script: str) -> None:
    base._docker(script)


def p1() -> None:
    """Run repository physics preflight on all generated parent cases."""
    build()
    commands = "; ".join(
        "python3 /workspace/bin/physics.py preflight "
        f"/workspace/{ROOT.relative_to(REPO)}/generated_wall02/{name}/input.i"
        for name in CASE_NAMES
    )
    script = (
        "set -euo pipefail; source /environment; export PYTHONPATH=/workspace; "
        "uv pip install --system --python \"$(command -v python3)\" "
        "-r /workspace/requirements-evidence-engine.txt; "
        "python3 /workspace/bin/physics.py preflight --self-test; " + commands
    )
    _docker(script)
    print("ISSUE306_WALL02_P1: PASS")


def p2() -> None:
    """Build Physics and run --check-input for every parent and fast child."""
    if not GENERATED.exists():
        build()
    rel = ROOT.relative_to(REPO)
    checks: list[str] = []
    for name in CASE_NAMES:
        checks.append(
            f"cd /workspace/{rel}/generated_wall02/{name} && "
            f"/workspace/physics_app/physics-opt --check-input -i input.i "
            f"> /workspace/{rel}/results_wall02/{name}_parent_p2.log 2>&1"
        )
        checks.append(
            f"cd /workspace/{rel}/generated_wall02/{name} && "
            f"/workspace/physics_app/physics-opt --check-input -i fast_sub.i "
            f"> /workspace/{rel}/results_wall02/{name}_fast_p2.log 2>&1"
        )
    script = (
        "set -euo pipefail; source /environment; "
        "export MOOSE_DIR=/opt/physics_vendor/moose; export CRANE_DIR=/opt/physics_vendor/crane; "
        "export SQUIRREL_DIR=/opt/physics_vendor/squirrel; export ZAPDOS_DIR=/opt/physics_vendor/zapdos; "
        "export METHOD=opt; "
        f"mkdir -p /workspace/{rel}/results_wall02; "
        "make -C /workspace/physics_app -j2; test -x /workspace/physics_app/physics-opt; "
        + "; ".join(checks)
    )
    _docker(script)
    print("ISSUE306_WALL02_P2: PASS")


def inner_run(case_name: str) -> int:
    """Execute one generated case inside the build-base container."""
    if case_name not in CASE_NAMES:
        raise SystemExit(f"unknown case {case_name}")
    RESULTS.mkdir(parents=True, exist_ok=True)
    case_dir = GENERATED / case_name
    log = RESULTS / f"{case_name}_runtime.log"
    started = time.perf_counter()
    with log.open("w", encoding="utf-8") as handle:
        completed = subprocess.run(
            [str(REPO / "physics_app" / "physics-opt"), "-i", "input.i"],
            cwd=case_dir,
            stdout=handle,
            stderr=subprocess.STDOUT,
            check=False,
        )
    elapsed = time.perf_counter() - started
    (RESULTS / f"{case_name}_returncode.txt").write_text(
        f"{completed.returncode}\n", encoding="utf-8"
    )
    (RESULTS / f"{case_name}_elapsed_seconds.txt").write_text(
        f"{elapsed:.9f}\n", encoding="utf-8"
    )
    return 0


def _analyze_case(case_name: str) -> tuple[dict[str, object], int]:
    """Reuse Sequence-01 analysis and append left wall-flux decomposition."""
    old_generated, old_results = base.GENERATED, base.RESULTS
    try:
        base.GENERATED = GENERATED
        base.RESULTS = RESULTS
        result, code = base.analyze_case(case_name)
    finally:
        base.GENERATED = old_generated
        base.RESULTS = old_results

    p = json.loads((GENERATED / case_name / "case.json").read_text(encoding="utf-8"))
    result["mode"] = p["mode"]
    result["left_charged_wall_loss"] = p["left_charged_wall_loss"]

    if code == 0 and p["mode"] == "wall":
        rows = base._rows(GENERATED / case_name / "input_step_csv.csv")
        if rows:
            final = rows[-1]
            wall_rates: dict[str, dict[str, float]] = {}
            for species in WALL_SPECIES:
                wall_rates[species] = {
                    "surface_rate_signed": float(final[f"left_{species}_surface_rate"]),
                    "migration_rate_signed": float(final[f"left_{species}_migration_rate"]),
                }
            result["left_wall_rates"] = wall_rates

    return result, code


def run_case(case_name: str) -> None:
    """Run and analyze one wall02 matrix case."""
    if not (REPO / "physics_app" / "physics-opt").exists():
        raise SystemExit("physics-opt missing")
    rel = ROOT.relative_to(REPO)
    script = (
        "set -euo pipefail; source /environment; "
        "export MOOSE_DIR=/opt/physics_vendor/moose; export CRANE_DIR=/opt/physics_vendor/crane; "
        "export SQUIRREL_DIR=/opt/physics_vendor/squirrel; export ZAPDOS_DIR=/opt/physics_vendor/zapdos; "
        "export METHOD=opt; export PYTHONPATH=/workspace; "
        f"python3 /workspace/{rel}/wall02_control.py --inner-run {case_name}"
    )
    _docker(script)
    result, code = _analyze_case(case_name)
    (RESULTS / f"{case_name}_result.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print("ISSUE306_WALL02_CASE:", case_name, result["classification"])
    if code:
        raise SystemExit(code)


def _load_results(root: Path) -> dict[str, dict[str, object]]:
    found: dict[str, dict[str, object]] = {}
    for path in root.rglob("*_result.json"):
        item = json.loads(path.read_text(encoding="utf-8"))
        name = str(item.get("case", ""))
        if name in CASE_NAMES:
            found[name] = item
    missing = [name for name in CASE_NAMES if name not in found]
    if missing:
        raise RuntimeError(f"missing wall02 result(s): {missing}")
    return found


def aggregate(root: Path) -> dict[str, object]:
    """Compare chi dependence with and without the left charged-wall law."""
    found = _load_results(root)
    if not all(bool(found[name].get("evidence_valid")) for name in CASE_NAMES):
        return {
            "issue": 306,
            "sequence": 2,
            "classification": "WALL02_INVALID_EVIDENCE",
            "evidence_valid": False,
            "cases": found,
        }

    comparisons: dict[str, object] = {}
    for mode in ("bulk", "wall"):
        anchor = found[f"{mode}_chi1"]
        ap = anchor["final_profile"]
        for chi in (10, 20):
            item = found[f"{mode}_chi{chi}"]
            pp = item["final_profile"]
            comparisons[f"{mode}_chi{chi}_vs_{mode}_chi1"] = {
                "electron_density_einf": base._profile_error(ap, pp, "electron_density"),
                "mean_energy_einf": base._profile_error(ap, pp, "mean_energy_eV"),
                "raw_potential_einf": base._profile_error(ap, pp, "potential"),
                "net_charge_einf": base._profile_error(ap, pp, "net_charge_C_m3"),
                **base._offset_shape(ap, pp),
            }

    contraction: dict[str, object] = {}
    for chi in (10, 20):
        b = comparisons[f"bulk_chi{chi}_vs_bulk_chi1"]
        w = comparisons[f"wall_chi{chi}_vs_wall_chi1"]
        bshift = abs(float(b["mean_potential_shift_V"]))
        wshift = abs(float(w["mean_potential_shift_V"]))
        bcharge = abs(float(b["net_charge_einf"]))
        wcharge = abs(float(w["net_charge_einf"]))
        contraction[f"chi{chi}"] = {
            "bulk_offset_V": b["mean_potential_shift_V"],
            "wall_offset_V": w["mean_potential_shift_V"],
            "offset_magnitude_ratio_wall_over_bulk": wshift / max(bshift, 1.0e-30),
            "offset_contraction_fraction": 1.0 - wshift / max(bshift, 1.0e-30),
            "net_charge_ratio_wall_over_bulk": wcharge / max(bcharge, 1.0e-30),
            "net_charge_contraction_fraction": 1.0 - wcharge / max(bcharge, 1.0e-30),
        }

    return {
        "issue": 306,
        "sequence": 2,
        "classification": "COMSOL_LEFT_WALL_2CYCLE_EVIDENCE_COMPLETE",
        "evidence_valid": True,
        "chi_h": CHI_H,
        "heavy_cycles": HEAVY_CYCLES,
        "total_time_tau": FINAL_TAU,
        "cases": found,
        "mode_comparisons": comparisons,
        "wall_contraction": contraction,
        "interpretation_guard": (
            "The pressure outlet is retained only for incompressible-flow closure. "
            "Scientific attribution concerns the charged-heavy species flux: "
            "surface loss plus signed one-sided migration on left."
        ),
    }


def p3() -> None:
    """Run all six cases sequentially and aggregate the wall discriminator."""
    build()
    RESULTS.mkdir(parents=True, exist_ok=True)
    rel = ROOT.relative_to(REPO)
    inner = "; ".join(
        f"python3 /workspace/{rel}/wall02_control.py --inner-run {name}"
        for name in CASE_NAMES
    )
    script = (
        "set -euo pipefail; source /environment; "
        "export MOOSE_DIR=/opt/physics_vendor/moose; export CRANE_DIR=/opt/physics_vendor/crane; "
        "export SQUIRREL_DIR=/opt/physics_vendor/squirrel; export ZAPDOS_DIR=/opt/physics_vendor/zapdos; "
        "export METHOD=opt; export PYTHONPATH=/workspace; "
        + inner
    )
    _docker(script)

    invalid: list[str] = []
    for name in CASE_NAMES:
        result, code = _analyze_case(name)
        (RESULTS / f"{name}_result.json").write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print("ISSUE306_WALL02_CASE:", name, result["classification"])
        if code:
            invalid.append(name)

    summary = aggregate(RESULTS)
    (RESULTS / "issue306_wall02_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print("ISSUE306_WALL02_P3:", summary["classification"])
    print(json.dumps(summary, indent=2, sort_keys=True))
    if invalid or not bool(summary.get("evidence_valid")):
        raise SystemExit(2)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=("p0", "p1", "p2", "p3"))
    parser.add_argument("--case", choices=CASE_NAMES)
    parser.add_argument("--inner-run", choices=CASE_NAMES)
    parser.add_argument("--aggregate", action="store_true")
    args = parser.parse_args()
    RESULTS.mkdir(parents=True, exist_ok=True)

    if args.inner_run:
        return inner_run(args.inner_run)
    if args.case:
        run_case(args.case)
        return 0
    if args.aggregate:
        root = os.environ.get("CHATGPT_MATRIX_EVIDENCE_ROOT")
        if not root:
            raise SystemExit("CHATGPT_MATRIX_EVIDENCE_ROOT is required")
        summary = aggregate(Path(root))
        (RESULTS / "issue306_wall02_summary.json").write_text(
            json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print("ISSUE306_WALL02_CLASSIFICATION:", summary["classification"])
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 0 if bool(summary["evidence_valid"]) else 2
    if args.phase:
        {"p0": p0, "p1": p1, "p2": p2, "p3": p3}[args.phase]()
        return 0
    parser.error("one action is required")


if __name__ == "__main__":
    raise SystemExit(main())
