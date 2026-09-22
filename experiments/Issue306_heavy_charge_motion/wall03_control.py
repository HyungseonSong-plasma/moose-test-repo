#!/usr/bin/env python3
"""Issue #306 Sequence 03: COMSOL-parity right-wall closure.

Boundary topology fixed by the registered discriminator:

LEFT:
  * 20 sccm pure-O2 heavy-flow inlet
  * solved heavy-species inlet fluxes are zero; constrained O2 carries the feed

RIGHT:
  * hydrodynamic pressure reference only for INSFV closure
  * electron particle wall loss remains right-only:
      Gamma_e = 0.5 * n_e * v_e,th
  * electron energy wall loss remains right-only:
      Gamma_eps = (5/6) * v_e,th * n_eps
  * O2+ and O+ use Bohm surface loss
  * O- uses thermal sticking surface loss
  * O2+, O-, O+ all use signed one-sided migration wall loss

The comparison matrix uses a thermal-ion control with the identical left/right
topology and identical electron wall model, so the controlled change is only
the positive-ion surface law: thermal sticking -> Bohm.
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
GENERATED = ROOT / "generated_wall03"
RESULTS = ROOT / "results_wall03"

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
    for mode in ("thermal", "comsol")
    for chi in (1.0, 10.0, 20.0)
)
CASE_NAMES = tuple(str(x["name"]) for x in CASE_SPECS)

POSITIVE = {
    "O2p": {"variable": "w_O2p", "mobility": "mu_O2p", "molar_mass": 0.032},
    "Op": {"variable": "w_Op", "mobility": "mu_Op", "molar_mass": 0.016},
}
NEGATIVE = {
    "Om": {"variable": "w_Om", "mobility": "mu_Om", "molar_mass": 0.016},
}
ALL_CHARGED = {**POSITIVE, **NEGATIVE}


def _params(spec: dict[str, object]) -> dict[str, object]:
    p = base._params(spec)
    p["mode"] = str(spec["mode"])
    p["flow_inlet"] = "left"
    p["wall_boundary"] = "right"
    p["electron_wall_boundary"] = "right"
    p["electron_particle_wall_coefficient"] = 0.5
    p["electron_energy_wall_coefficient"] = 5.0 / 6.0
    p["positive_ion_surface_model"] = (
        "bohm" if p["mode"] == "comsol" else "thermal_sticking"
    )
    p["negative_ion_surface_model"] = "thermal_sticking"
    return p


def _swap_flow_topology(text: str) -> str:
    """Reverse Sequence-01 flow: left inlet, right pressure reference."""
    if "boundary = right" not in text or "boundary = left" not in text:
        raise RuntimeError("released-parent boundary anchors changed")

    # Only the generated parent uses explicit single-boundary lines for the
    # flow/scalar inlet and pressure outlet.  Drift ownership is expressed by
    # boundaries_to_avoid='left right' and is intentionally untouched.
    text = text.replace("boundary = right", "boundary = __SWAP_LEFT__")
    text = text.replace("boundary = left", "boundary = right")
    text = text.replace("boundary = __SWAP_LEFT__", "boundary = left")
    text = text.replace("direction = '-1 0 0'", "direction = '1 0 0'")

    text = text.replace(
        "# right 20 sccm pure-O2 inlet, left absolute-pressure outlet.\n"
        "# The pressure value is held at the Sequence-12 gas state (0.66661 Pa) so the\n"
        "# fast physics state is not changed while heavy motion is released.",
        "# left 20 sccm pure-O2 inlet; right is the charged-particle wall.\n"
        "# The right INSFV pressure condition is retained only as the flow-pressure\n"
        "# reference and does not own the heavy-species wall flux.",
        1,
    )
    return text


def _number_density_material(species: str, variable: str, molar_mass: float) -> str:
    return f"""
  [wall_n_{species}]
    type = ADParsedFunctorMaterial
    property_name = wall_n_{species}
    functor_names = 'rho_const {variable}'
    functor_symbols = 'rho wf'
    expression = 'rho*wf*{base.prepare.NA:.17g}/{molar_mass:.17g}'
  []
"""


def _thermal_wall_materials() -> str:
    blocks: list[str] = []
    for species, cfg in ALL_CHARGED.items():
        mass = float(cfg["molar_mass"])
        charge = 1 if species in POSITIVE else -1
        blocks.append(_number_density_material(species, str(cfg["variable"]), mass))
        blocks.append(
            f"""
  [right_wall_flux_{species}]
    type = PhysicsIonWallFluxMaterial
    ion_number_density = wall_n_{species}
    potential = potential_fast
    mobility = {cfg['mobility']}
    gas_temperature = T_g
    charge_number = {charge}
    molar_mass = {mass:.17g}
    sticking = 1.0
    declare_suffix = right_{species}
  []
"""
        )
    return "".join(blocks)


def _comsol_wall_materials() -> str:
    blocks = [
        """
  [electron_temperature_wall_eV]
    type = ADParsedFunctorMaterial
    property_name = electron_temperature_wall_eV
    functor_names = 'mean_energy_fast'
    functor_symbols = 'mean_ev'
    expression = '(2.0/3.0)*mean_ev'
  []
"""
    ]

    for species, cfg in POSITIVE.items():
        mass = float(cfg["molar_mass"])
        blocks.append(_number_density_material(species, str(cfg["variable"]), mass))
        # sticking=0 suppresses the thermal surface component; this object owns
        # only the signed one-sided migration term for positive ions.
        blocks.append(
            f"""
  [right_migration_flux_{species}]
    type = PhysicsIonWallFluxMaterial
    ion_number_density = wall_n_{species}
    potential = potential_fast
    mobility = {cfg['mobility']}
    gas_temperature = T_g
    charge_number = 1
    molar_mass = {mass:.17g}
    sticking = 0.0
    declare_suffix = right_{species}
  []
  [right_bohm_surface_{species}]
    type = ADParsedFunctorMaterial
    property_name = bohm_surface_mass_flux_{species}
    functor_names = 'wall_n_{species} electron_temperature_wall_eV'
    functor_symbols = 'ni te'
    expression = 'ni*sqrt({base.prepare.E_CHARGE:.17g}*{base.prepare.NA:.17g}*te/{mass:.17g})*{mass:.17g}/{base.prepare.NA:.17g}'
  []
"""
        )

    species = "Om"
    cfg = NEGATIVE[species]
    mass = float(cfg["molar_mass"])
    blocks.append(_number_density_material(species, str(cfg["variable"]), mass))
    blocks.append(
        f"""
  [right_wall_flux_Om]
    type = PhysicsIonWallFluxMaterial
    ion_number_density = wall_n_Om
    potential = potential_fast
    mobility = mu_Om
    gas_temperature = T_g
    charge_number = -1
    molar_mass = {mass:.17g}
    sticking = 1.0
    declare_suffix = right_Om
  []
"""
    )
    return "".join(blocks)


def _thermal_wall_bcs() -> str:
    blocks: list[str] = []
    for species, cfg in ALL_CHARGED.items():
        blocks.append(
            f"""
  [right_{species}_surface_loss]
    type = FVFunctorNeumannBC
    variable = {cfg['variable']}
    boundary = right
    functor = ion_surface_mass_flux_right_{species}
    factor = -1.0
  []
  [right_{species}_migration_loss]
    type = FVFunctorNeumannBC
    variable = {cfg['variable']}
    boundary = right
    functor = ion_migration_mass_flux_right_{species}
    factor = -1.0
  []
"""
        )
    return "".join(blocks)


def _comsol_wall_bcs() -> str:
    blocks: list[str] = []
    for species, cfg in POSITIVE.items():
        blocks.append(
            f"""
  [right_{species}_surface_loss]
    type = FVFunctorNeumannBC
    variable = {cfg['variable']}
    boundary = right
    functor = bohm_surface_mass_flux_{species}
    factor = -1.0
  []
  [right_{species}_migration_loss]
    type = FVFunctorNeumannBC
    variable = {cfg['variable']}
    boundary = right
    functor = ion_migration_mass_flux_right_{species}
    factor = -1.0
  []
"""
        )
    blocks.append(
        """
  [right_Om_surface_loss]
    type = FVFunctorNeumannBC
    variable = w_Om
    boundary = right
    functor = ion_surface_mass_flux_right_Om
    factor = -1.0
  []
  [right_Om_migration_loss]
    type = FVFunctorNeumannBC
    variable = w_Om
    boundary = right
    functor = ion_migration_mass_flux_right_Om
    factor = -1.0
  []
"""
    )
    return "".join(blocks)


def _wall_postprocessors() -> str:
    blocks: list[str] = []
    for species in ALL_CHARGED:
        blocks.append(
            f"""
  [right_{species}_surface_rate]
    type = SideFVFluxBCIntegral
    boundary = right
    fvbcs = 'right_{species}_surface_loss'
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [right_{species}_migration_rate]
    type = SideFVFluxBCIntegral
    boundary = right
    fvbcs = 'right_{species}_migration_loss'
    execute_on = 'INITIAL TIMESTEP_END'
  []
"""
        )
    return "".join(blocks)


def _parent(p: dict[str, object]) -> str:
    text = _swap_flow_topology(base._released_parent(p))
    mode = str(p["mode"])
    materials = _thermal_wall_materials() if mode == "thermal" else _comsol_wall_materials()
    bcs = _thermal_wall_bcs() if mode == "thermal" else _comsol_wall_bcs()

    material_anchor = """  [charge_state]
    type = ADParsedFunctorMaterial
"""
    if text.count(material_anchor) != 1:
        raise RuntimeError("released-parent material anchor changed")
    text = text.replace(material_anchor, materials + material_anchor, 1)

    bc_anchor = """  [outlet_p]
    type = INSFVOutletPressureBC
"""
    if text.count(bc_anchor) != 1:
        raise RuntimeError("released-parent pressure anchor changed")
    text = text.replace(bc_anchor, bcs + bc_anchor, 1)

    pp_anchor = """  [heavy_charge_integral]
    type = ADElementIntegralFunctorPostprocessor
"""
    if text.count(pp_anchor) != 1:
        raise RuntimeError("released-parent postprocessor anchor changed")
    text = text.replace(pp_anchor, _wall_postprocessors() + pp_anchor, 1)
    return text


def _fast(p: dict[str, object]) -> str:
    """Use the accepted right-only COMSOL electron wall closure unchanged."""
    text = base._fast_child(p)

    required = (
        "expression = '0.5*exp(loge)*sqrt(16.0*1.602176634e-19*mean_ev/"
        "(3.0*pi*9.1093837139e-31))'"
    )
    if required not in text:
        raise RuntimeError("electron particle wall coefficient is not COMSOL 0.5")
    if "[right_thermal_surface_loss]" not in text or "boundary = right" not in text:
        raise RuntimeError("electron particle wall is not right-only")
    if "[right_energy_surface_loss]" not in text:
        raise RuntimeError("electron energy wall is not right-only")
    if "type = PhysicsFVElectronEnergyWallFluxBC" not in text:
        raise RuntimeError("electron 5/6 energy wall owner missing")
    return text


def build(clean: bool = True) -> list[dict[str, object]]:
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

        fast = _fast(p)
        parent = _parent(p)

        (case_dir / "input.i").write_text(parent, encoding="utf-8")
        (case_dir / "fast_sub.i").write_text(fast, encoding="utf-8")
        (case_dir / "poisson_sub.i").write_text(poisson, encoding="utf-8")
        shutil.copy2(base.ELECTRON_MOMENTS, case_dir / "electron_moments.txt")
        shutil.copy2(base.ELASTIC_DATA, case_dir / "o2_elastic.txt")
        shutil.copy2(base.HEAVY_TRANSPORT_DATA, case_dir / "transport_data.txt")
        (case_dir / "case.json").write_text(
            json.dumps(p, indent=2, sort_keys=True) + "\n", encoding="utf-8"
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
                "sequence": 3,
                "objective": (
                    "right-wall COMSOL parity with left 20 sccm inlet: "
                    "electron half-thermal wall loss; positive-ion Bohm surface "
                    "loss; O- thermal sticking; signed ion migration"
                ),
                "chi_h": CHI_H,
                "heavy_cycles": HEAVY_CYCLES,
                "total_time_tau": FINAL_TAU,
                "left": "20 sccm pure-O2 inlet",
                "right": "particle wall plus hydrodynamic pressure reference",
                "electron_wall": {
                    "boundary": "right",
                    "particle_coefficient": 0.5,
                    "energy_coefficient": 5.0 / 6.0,
                    "see": False,
                },
                "thermal_control": "all charged heavy: thermal sticking s=1 + migration",
                "comsol_case": "O2+/O+: Bohm + migration; O-: thermal sticking + migration",
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
    built = build()
    by = {str(x["name"]): x for x in built}
    if set(by) != set(CASE_NAMES):
        raise RuntimeError("case set mismatch")

    for chi in (1.0, 10.0, 20.0):
        t = by[f"thermal_chi{int(chi)}"]
        c = by[f"comsol_chi{int(chi)}"]
        assert t["dt_e_s"] == c["dt_e_s"]
        assert t["dt_h_s"] == c["dt_h_s"]
        assert t["end_time_s"] == c["end_time_s"]
        assert t["fast_steps_per_heavy_cycle"] == int(CHI_H / chi)

        td = GENERATED / str(t["name"])
        cd = GENERATED / str(c["name"])
        tf = (td / "fast_sub.i").read_text()
        cf = (cd / "fast_sub.i").read_text()
        assert tf == cf
        assert "0.5*exp(loge)" in tf
        assert "[right_thermal_surface_loss]" in tf
        assert "[right_energy_surface_loss]" in tf
        assert "boundary = 'left right'" not in tf

        tp = (td / "input.i").read_text()
        cp = (cd / "input.i").read_text()

        # Left inlet / right wall topology.
        assert "type = WCNSFVMassFluxBC\n    variable = p\n    boundary = left" in tp
        assert "type = INSFVOutletPressureBC\n    variable = p\n    boundary = right" in tp
        assert "direction = '1 0 0'" in tp
        assert tp.count("boundaries_to_avoid = 'left right'") == 9
        assert cp.count("boundaries_to_avoid = 'left right'") == 9

        # Thermal control: all three charged species use thermal surface + migration.
        assert tp.count("type = PhysicsIonWallFluxMaterial") == 3
        assert tp.count("sticking = 1.0") == 3
        assert tp.count("boundary = right\n    functor = ion_surface_mass_flux_right_") == 3
        assert tp.count("boundary = right\n    functor = ion_migration_mass_flux_right_") == 3

        # COMSOL case: O2+/O+ Bohm, O- thermal, all with migration.
        assert cp.count("bohm_surface_mass_flux_") >= 4
        assert cp.count("sticking = 0.0") == 2
        assert cp.count("sticking = 1.0") == 1
        assert "charge_number = -1" in cp
        assert cp.count("boundary = right\n    functor = ion_migration_mass_flux_right_") == 3

    return {
        "status": "PASS",
        "issue": 306,
        "sequence": 3,
        "tau_epsilon_initial_s": base.prepare.tau_epsilon(),
        "chi_h": CHI_H,
        "heavy_cycles": HEAVY_CYCLES,
        "total_time_tau": FINAL_TAU,
        "matrix": built,
        "electron_wall_contract": "right only: 0.5*n_e*v_th particle; 5/6 energy",
        "ion_wall_contract": "right: O2+/O+ Bohm + migration; O- thermal sticking + migration",
        "flow_contract": "left 20 sccm inlet; right pressure reference",
    }


def p0() -> None:
    summary = static_contract()
    print("ISSUE306_WALL03_P0: PASS")
    print(json.dumps(summary, indent=2, sort_keys=True))


def p1() -> None:
    build()
    commands = "; ".join(
        "python3 /workspace/bin/physics.py preflight "
        f"/workspace/{ROOT.relative_to(REPO)}/generated_wall03/{name}/input.i"
        for name in CASE_NAMES
    )
    script = (
        "set -euo pipefail; source /environment; export PYTHONPATH=/workspace; "
        "uv pip install --system --python \"$(command -v python3)\" "
        "-r /workspace/requirements-evidence-engine.txt; "
        "python3 /workspace/bin/physics.py preflight --self-test; " + commands
    )
    base._docker(script)
    print("ISSUE306_WALL03_P1: PASS")


def p2() -> None:
    if not GENERATED.exists():
        build()
    rel = ROOT.relative_to(REPO)
    checks: list[str] = []
    for name in CASE_NAMES:
        checks.append(
            f"cd /workspace/{rel}/generated_wall03/{name} && "
            f"/workspace/physics_app/physics-opt --check-input -i input.i "
            f"> /workspace/{rel}/results_wall03/{name}_parent_p2.log 2>&1"
        )
        checks.append(
            f"cd /workspace/{rel}/generated_wall03/{name} && "
            f"/workspace/physics_app/physics-opt --check-input -i fast_sub.i "
            f"> /workspace/{rel}/results_wall03/{name}_fast_p2.log 2>&1"
        )
    script = (
        "set -euo pipefail; source /environment; "
        "export MOOSE_DIR=/opt/physics_vendor/moose; export CRANE_DIR=/opt/physics_vendor/crane; "
        "export SQUIRREL_DIR=/opt/physics_vendor/squirrel; export ZAPDOS_DIR=/opt/physics_vendor/zapdos; "
        "export METHOD=opt; "
        f"mkdir -p /workspace/{rel}/results_wall03; "
        "make -C /workspace/physics_app -j2; test -x /workspace/physics_app/physics-opt; "
        + "; ".join(checks)
    )
    base._docker(script)
    print("ISSUE306_WALL03_P2: PASS")


def inner_run(case_name: str) -> int:
    if case_name not in CASE_NAMES:
        raise SystemExit(f"unknown case {case_name}")
    RESULTS.mkdir(parents=True, exist_ok=True)
    case_dir = GENERATED / case_name
    log = RESULTS / f"{case_name}_runtime.log"
    started = time.perf_counter()
    with log.open("w", encoding="utf-8") as handle:
        completed = subprocess.run(
            [str(REPO / "physics_app/physics-opt"), "-i", "input.i"],
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
    result["flow_inlet"] = p["flow_inlet"]
    result["wall_boundary"] = p["wall_boundary"]
    result["positive_ion_surface_model"] = p["positive_ion_surface_model"]

    if code == 0:
        rows = base._rows(GENERATED / case_name / "input_step_csv.csv")
        if rows:
            final = rows[-1]
            result["right_wall_rates"] = {
                species: {
                    "surface_rate_signed": float(final[f"right_{species}_surface_rate"]),
                    "migration_rate_signed": float(final[f"right_{species}_migration_rate"]),
                }
                for species in ALL_CHARGED
            }
    return result, code


def _profile_metrics(
    anchor: dict[str, object], trial: dict[str, object]
) -> dict[str, float]:
    ap = anchor["final_profile"]
    pp = trial["final_profile"]
    return {
        "electron_density_einf": base._profile_error(ap, pp, "electron_density"),
        "mean_energy_einf": base._profile_error(ap, pp, "mean_energy_eV"),
        "raw_potential_einf": base._profile_error(ap, pp, "potential"),
        "net_charge_einf": base._profile_error(ap, pp, "net_charge_C_m3"),
        **base._offset_shape(ap, pp),
    }


def aggregate(root: Path) -> dict[str, object]:
    found: dict[str, dict[str, object]] = {}
    for path in root.rglob("*_result.json"):
        item = json.loads(path.read_text(encoding="utf-8"))
        name = str(item.get("case", ""))
        if name in CASE_NAMES:
            found[name] = item
    missing = [name for name in CASE_NAMES if name not in found]
    if missing:
        raise RuntimeError(f"missing wall03 result(s): {missing}")
    if not all(bool(found[name].get("evidence_valid")) for name in CASE_NAMES):
        return {
            "issue": 306,
            "sequence": 3,
            "classification": "WALL03_INVALID_EVIDENCE",
            "evidence_valid": False,
            "cases": found,
        }

    chi_dependence: dict[str, object] = {}
    for mode in ("thermal", "comsol"):
        anchor = found[f"{mode}_chi1"]
        for chi in (10, 20):
            chi_dependence[f"{mode}_chi{chi}_vs_{mode}_chi1"] = _profile_metrics(
                anchor, found[f"{mode}_chi{chi}"]
            )

    bohm_effect: dict[str, object] = {}
    for chi in (1, 10, 20):
        thermal = found[f"thermal_chi{chi}"]
        comsol = found[f"comsol_chi{chi}"]
        bohm_effect[f"chi{chi}_comsol_vs_thermal"] = {
            **_profile_metrics(thermal, comsol),
            "net_charge_integral_change_C_m2": (
                float(comsol["final_net_charge_integral_C_m2"])
                - float(thermal["final_net_charge_integral_C_m2"])
            ),
            "heavy_charge_integral_change_C_m2": (
                float(comsol["final_heavy_charge_integral_C_m2"])
                - float(thermal["final_heavy_charge_integral_C_m2"])
            ),
        }

    return {
        "issue": 306,
        "sequence": 3,
        "classification": "COMSOL_RIGHT_WALL_BOHM_EVIDENCE_COMPLETE",
        "evidence_valid": True,
        "chi_h": CHI_H,
        "heavy_cycles": HEAVY_CYCLES,
        "total_time_tau": FINAL_TAU,
        "boundary_contract": {
            "left": "20 sccm pure-O2 inlet",
            "right": "electron wall + charged-heavy wall + pressure reference",
        },
        "cases": found,
        "chi_dependence": chi_dependence,
        "bohm_effect": bohm_effect,
        "interpretation_guard": (
            "The right pressure condition is only the incompressible-flow pressure "
            "reference. Particle-wall attribution is owned by the explicit electron "
            "and charged-heavy wall fluxes."
        ),
    }


def p3() -> None:
    if not GENERATED.exists():
        build()
    RESULTS.mkdir(parents=True, exist_ok=True)
    rel = ROOT.relative_to(REPO)
    inner = "; ".join(
        f"python3 /workspace/{rel}/wall03_control.py --inner-run {name}"
        for name in CASE_NAMES
    )
    script = (
        "set -euo pipefail; source /environment; "
        "export MOOSE_DIR=/opt/physics_vendor/moose; export CRANE_DIR=/opt/physics_vendor/crane; "
        "export SQUIRREL_DIR=/opt/physics_vendor/squirrel; export ZAPDOS_DIR=/opt/physics_vendor/zapdos; "
        "export METHOD=opt; export PYTHONPATH=/workspace; "
        + inner
    )
    base._docker(script)

    invalid: list[str] = []
    for name in CASE_NAMES:
        result, code = _analyze_case(name)
        (RESULTS / f"{name}_result.json").write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print("ISSUE306_WALL03_CASE:", name, result["classification"])
        if code:
            invalid.append(name)

    summary = aggregate(RESULTS)
    (RESULTS / "issue306_wall03_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print("ISSUE306_WALL03_P3:", summary["classification"])
    print(json.dumps(summary, indent=2, sort_keys=True))
    if invalid or not bool(summary.get("evidence_valid")):
        raise SystemExit(2)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=("p0", "p1", "p2", "p3"))
    parser.add_argument("--inner-run", choices=CASE_NAMES)
    parser.add_argument("--aggregate", action="store_true")
    args = parser.parse_args()
    RESULTS.mkdir(parents=True, exist_ok=True)

    if args.inner_run:
        return inner_run(args.inner_run)
    if args.aggregate:
        root = os.environ.get("CHATGPT_MATRIX_EVIDENCE_ROOT")
        if not root:
            raise SystemExit("CHATGPT_MATRIX_EVIDENCE_ROOT is required")
        summary = aggregate(Path(root))
        (RESULTS / "issue306_wall03_summary.json").write_text(
            json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print("ISSUE306_WALL03_CLASSIFICATION:", summary["classification"])
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 0 if bool(summary["evidence_valid"]) else 2
    if args.phase:
        {"p0": p0, "p1": p1, "p2": p2, "p3": p3}[args.phase]()
        return 0
    parser.error("one action is required")


if __name__ == "__main__":
    raise SystemExit(main())
