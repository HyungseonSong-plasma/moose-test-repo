"""Issue #310 Gen34: accuracy-matched relax_2x reference input preparation.

This generation prepares, but does not launch, the final apples-to-apples reference
comparison inputs.

Reference:
  - current canonical transient/time-aware plasma physics
  - ordinary Poisson (no banded electron-response correction)
  - Picard outer fixed-point iteration
  - relaxation_factor = 2/(1+chi_e) = 2/101
  - custom delta-phi convergence = 1e-6 V
  - fp_anchor_csv disabled
  - compute_scaling_once = true in parent and electron apps

Optimized endpoint:
  - same physics/clock/output/scaling/convergence
  - band5 correction
  - alpha = 0.45
  - Steffensen on potential_from_poisson

The historical Sequence01 relax_2x used the superseded wall09/Bohm-positive-ion
lane and residual-only stopping. It remains a historical engineering reference,
but is not used as the scientific input for the final controlled benchmark.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from experiments.Issue310_fp_acceleration import control_seq18_deltaphi as g

GENERATED = ROOT / "generated_fp34_relax2x_reference"
RESULTS = ROOT / "results_fp34_relax2x_reference"

CHI_E = 100.0
HEAVY_CYCLES = 88
FINAL_TAU = 400.0 * HEAVY_CYCLES
RELAX_2X = 2.0 / (1.0 + CHI_E)
DELTA_PHI_TOL = 1.0e-6

SPECS = (
    {
        "name": "relax2x_reference_20ns",
        "role": "reference",
        "bandwidth": 0,
        "relaxation_factor": RELAX_2X,
        "custom_convergence": True,
        "delta_phi_abs_tol": DELTA_PHI_TOL,
        "fp_algorithm": "picard",
        "compute_scaling_once": True,
        "suppress_fp_anchor_output": True,
    },
    {
        "name": "optimized_endpoint_20ns",
        "role": "optimized",
        "bandwidth": 5,
        "relaxation_factor": 0.45,
        "custom_convergence": True,
        "delta_phi_abs_tol": DELTA_PHI_TOL,
        "fp_algorithm": "steffensen",
        "compute_scaling_once": True,
        "suppress_fp_anchor_output": True,
    },
)
CASE_NAMES = tuple(str(x["name"]) for x in SPECS)


def _bind_clock() -> None:
    g.FINAL_TAU = FINAL_TAU
    g.HEAVY_CYCLES = HEAVY_CYCLES
    g.wall08.FINAL_TAU = FINAL_TAU
    g.seq08.FINAL_TAU = FINAL_TAU
    g.seq08.HEAVY_CYCLES = HEAVY_CYCLES


def _accelerate_steffensen(fast: str) -> str:
    anchor = "  fixed_point_algorithm = 'picard'\n"
    if fast.count(anchor) != 1:
        raise RuntimeError("fast fixed-point algorithm anchor changed")
    return fast.replace(
        anchor,
        "  fixed_point_algorithm = 'steffensen'\n"
        "  transformed_variables = 'potential_from_poisson'\n",
        1,
    )


def _enable_scaling_once(text: str) -> str:
    anchor = "  compute_scaling_once = false\n"
    if text.count(anchor) != 1:
        raise RuntimeError("compute_scaling_once=false anchor changed")
    return text.replace(anchor, "  compute_scaling_once = true\n", 1)


def _disable_fp_anchor_csv(fast: str) -> str:
    anchor = "  [fp_anchor_csv]\n"
    if fast.count(anchor) != 1:
        raise RuntimeError("fp_anchor_csv output anchor changed")
    return fast.replace(anchor, anchor + "    enable = false\n", 1)


def _apply_anchor_only(fast: str, poisson: str) -> tuple[str, str]:
    """Install only the previous-potential anchor path needed by delta-phi convergence.

    This deliberately excludes the n_epsilon transfer, beta material, and
    PhysicsFVGummelBandedCorrection used by the optimized endpoint.
    """
    transfer_anchor = """  [log_e_to_poisson]
    type = MultiAppCopyTransfer
    to_multi_app = poisson
    source_variable = log_e
    variable = log_e_frozen
    execute_on = SAME_AS_MULTIAPP
  []
"""
    if fast.count(transfer_anchor) != 1:
        raise RuntimeError("log_e transfer anchor changed")
    fast = fast.replace(
        transfer_anchor,
        transfer_anchor + """  [phi_anchor_to_poisson]
    type = MultiAppCopyTransfer
    to_multi_app = poisson
    source_variable = potential_from_poisson
    variable = phi_anchor_frozen
    execute_on = SAME_AS_MULTIAPP
  []
""",
        1,
    )

    phi_from = """  [phi_from_poisson]
    type = MultiAppCopyTransfer
    from_multi_app = poisson
    source_variable = potential_plasma
    variable = potential_from_poisson
    execute_on = SAME_AS_MULTIAPP
  []
"""
    if fast.count(phi_from) != 1:
        raise RuntimeError("phi-from-Poisson transfer anchor changed")
    fast = fast.replace(
        phi_from,
        phi_from + """  [phi_anchor_from_poisson_diag]
    type = MultiAppCopyTransfer
    from_multi_app = poisson
    source_variable = phi_anchor_frozen
    variable = fp_phi_anchor_diag
    execute_on = SAME_AS_MULTIAPP
  []
""",
        1,
    )

    aux_anchor = """  [log_e_frozen]
    type = MooseVariableFVReal
"""
    if poisson.count(aux_anchor) != 1:
        raise RuntimeError("Poisson AuxVariables anchor changed")
    poisson = poisson.replace(
        aux_anchor,
        """  [phi_anchor_frozen]
    type = MooseVariableFVReal
    initial_condition = 0.0
  []
""" + aux_anchor,
        1,
    )
    return fast, poisson


def _reference_inputs(raw: dict[str, object]) -> tuple[str, str, str, dict[str, object]]:
    p = g._params(raw)
    parent, fast, poisson = g._timeaware(raw, p)

    # Add only instrumentation/anchor state required for the same delta-phi
    # accuracy criterion as the optimized endpoint.
    fast = g._instrument_anchor(fast)
    fast, poisson = _apply_anchor_only(fast, poisson)
    fast = g._apply_delta_phi_convergence(fast, DELTA_PHI_TOL)

    parent = _enable_scaling_once(parent)
    fast = _enable_scaling_once(fast)
    fast = _disable_fp_anchor_csv(fast)
    return parent, fast, poisson, p


def _optimized_inputs(raw: dict[str, object]) -> tuple[str, str, str, dict[str, object]]:
    p = g._params(raw)
    parent, fast, poisson = g.render(raw, p)
    fast = _accelerate_steffensen(fast)
    parent = _enable_scaling_once(parent)
    fast = _enable_scaling_once(fast)
    fast = _disable_fp_anchor_csv(fast)
    return parent, fast, poisson, p


def build(clean: bool = True) -> list[dict[str, object]]:
    _bind_clock()
    if clean and GENERATED.exists():
        shutil.rmtree(GENERATED)
    GENERATED.mkdir(parents=True, exist_ok=True)

    built = []
    for raw in SPECS:
        if raw["role"] == "reference":
            parent, fast, poisson, p = _reference_inputs(raw)
        else:
            parent, fast, poisson, p = _optimized_inputs(raw)

        d = GENERATED / str(raw["name"])
        d.mkdir(parents=True, exist_ok=True)
        (d / "input.i").write_text(parent)
        (d / "fast_sub.i").write_text(fast)
        (d / "poisson_sub.i").write_text(poisson)
        shutil.copy2(g.base.ELECTRON_MOMENTS, d / "electron_moments.txt")
        shutil.copy2(g.base.ELASTIC_DATA, d / "o2_elastic.txt")
        shutil.copy2(g.base.HEAVY_TRANSPORT_DATA, d / "transport_data.txt")

        meta = {
            **p,
            "role": raw["role"],
            "reference_definition": (
                "current canonical physics + Picard relax_2x + accuracy/output/scaling matched"
                if raw["role"] == "reference"
                else "qualified Gen33 endpoint"
            ),
            "fp_algorithm": raw["fp_algorithm"],
            "bandwidth": raw["bandwidth"],
            "relaxation_factor": raw["relaxation_factor"],
            "custom_convergence": True,
            "delta_phi_abs_tol": DELTA_PHI_TOL,
            "compute_scaling_once": True,
            "suppress_fp_anchor_output": True,
            "heavy_cycles": HEAVY_CYCLES,
            "electron_steps": HEAVY_CYCLES * 4,
            "nominal_target_time_ns": 20.0,
            "final_tau": FINAL_TAU,
        }
        (d / "case.json").write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n")
        built.append(meta)

    (GENERATED / "comparison_contract.json").write_text(
        json.dumps(
            {
                "issue": 310,
                "sequence": 34,
                "status": "INPUT_PREPARATION_ONLY",
                "historical_reference": {
                    "name": "Sequence01 relax_2x",
                    "run": 35837437816,
                    "note": "Historical engineering reference only; superseded wall09/Bohm lane and old stopping rule.",
                },
                "controlled_reference": {
                    "name": "relax2x_reference_20ns",
                    "physics": "current canonical transient/time-aware thermal lane",
                    "fixed_point_algorithm": "picard",
                    "relaxation_factor": RELAX_2X,
                    "banded_correction": False,
                    "delta_phi_abs_tol_V": DELTA_PHI_TOL,
                    "compute_scaling_once": True,
                    "fp_anchor_csv": False,
                },
                "optimized_endpoint": {
                    "name": "optimized_endpoint_20ns",
                    "fixed_point_algorithm": "steffensen",
                    "relaxation_factor": 0.45,
                    "banded_correction": "band5",
                    "delta_phi_abs_tol_V": DELTA_PHI_TOL,
                    "compute_scaling_once": True,
                    "fp_anchor_csv": False,
                },
            },
            indent=2,
            sort_keys=True,
        ) + "\n"
    )
    return built


def p0() -> None:
    built = build()
    assert len(built) == 2

    ref = GENERATED / "relax2x_reference_20ns"
    opt = GENERATED / "optimized_endpoint_20ns"

    ref_parent = (ref / "input.i").read_text()
    opt_parent = (opt / "input.i").read_text()
    ref_fast = (ref / "fast_sub.i").read_text()
    opt_fast = (opt / "fast_sub.i").read_text()
    ref_poisson = (ref / "poisson_sub.i").read_text()
    opt_poisson = (opt / "poisson_sub.i").read_text()

    # Physics/clock parent input must be exactly identical.
    assert ref_parent == opt_parent
    assert "num_steps = 88" in ref_parent
    assert "compute_scaling_once = true" in ref_parent

    # Common measurement/accuracy contract.
    for fast in (ref_fast, opt_fast):
        assert "no_restore = true" in fast
        assert "type = PhysicsDeltaPhiMultiAppConvergence" in fast
        assert "delta_phi_abs_tol = 9.9999999999999995e-07" in fast
        assert "compute_scaling_once = true" in fast
        assert "  [fp_anchor_csv]\n    enable = false\n" in fast
        assert "num_steps = 352" in fast

    # Controlled reference = ordinary Poisson + Picard relax_2x.
    assert f"relaxation_factor = {RELAX_2X:.17g}" in ref_fast
    assert "fixed_point_algorithm = 'picard'" in ref_fast
    assert "transformed_variables = 'potential_from_poisson'" not in ref_fast
    assert "PhysicsFVGummelBandedCorrection" not in ref_poisson
    assert "gummel_band_beta" not in ref_poisson
    assert "n_epsilon_frozen" not in ref_poisson
    assert "phi_anchor_frozen" in ref_poisson

    # Qualified endpoint = band5 + alpha .45 + Steffensen.
    assert "relaxation_factor = 0.45000000000000001" in opt_fast
    assert "fixed_point_algorithm = 'steffensen'" in opt_fast
    assert "transformed_variables = 'potential_from_poisson'" in opt_fast
    assert "type = PhysicsFVGummelBandedCorrection" in opt_poisson
    assert "bandwidth = 5" in opt_poisson

    print("ISSUE310_GEN34_INPUT_P0: PASS")
    print(json.dumps({
        "reference_relaxation_factor": RELAX_2X,
        "parent_inputs_byte_identical": True,
        "common_delta_phi_abs_tol_V": DELTA_PHI_TOL,
        "common_compute_scaling_once": True,
        "common_fp_anchor_csv_enabled": False,
        "reference": "Picard + ordinary Poisson",
        "optimized": "Steffensen + band5",
        "launch_status": "NOT_LAUNCHED",
    }, sort_keys=True))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--p0", action="store_true")
    a = ap.parse_args()
    if a.build:
        build()
        print(GENERATED)
    elif a.p0:
        p0()
    else:
        ap.error("choose --build or --p0")


if __name__ == "__main__":
    main()
