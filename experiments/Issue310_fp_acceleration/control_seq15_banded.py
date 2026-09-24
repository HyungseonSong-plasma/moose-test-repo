"""Issue #310 Generation 15: measured banded electron-Jacobian discriminator.

The Gen13 direct basis experiment measured the 20x20 map
    J_e = d n_e / d phi
at the accepted end-of-step-1 operating point.

This generation converts that matrix to a dimensionless row-normalized form
    W_ij = J_ij / (n_e/VTe)_i
and tests row-sum-preserving +/-1, +/-3 and +/-5 band projections:
    Jhat_ij(state) = (n_e/VTe)_i(state) * Wband_ij.

The Poisson residual receives
    (e/eps0) * Jhat * (phi - phi_anchor).
Thus the correction vanishes at a converged Gummel fixed point. Each projected
row is explicitly reset to zero sum, preserving the nearly-null response to a
uniform potential shift.

This file also records phi_current and the returned phi_anchor at every fixed
point iteration to test transfer/update timing directly.
"""
from __future__ import annotations

import argparse
import base64
import csv
import json
import math
import os
import shutil
import sys
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from experiments.Issue310_fp_acceleration import control_seq08 as seq08
from experiments.Issue306_heavy_charge_motion import wall08_control as wall08

base = wall08.base
GENERATED = ROOT / "generated_fp15_banded"
RESULTS = ROOT / "results_fp15_banded"

CHI_E = 100.0
CHI_H = 400.0
FINAL_TAU = 400.0
HEAVY_CYCLES = 1
RATIO = 4
FP_MAX = 3000
NCELL = 20
XMIN = 0.0
XMAX = 0.01
DX = (XMAX - XMIN) / NCELL
E_OVER_EPS0 = 1.8095128179727827e-8
MEAN_E0_EV = 5.73276
NE0 = 1.0e16
GEN13_RUN = 35978463311
GEN13_HEAD = "864fd4ed3a10bb1de3a25e5b8938a529fa85f8e0"

_REFERENCE_W_B64 = """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"""
_REFERENCE_W = json.loads(zlib.decompress(base64.b64decode(_REFERENCE_W_B64)).decode("utf-8"))
if len(_REFERENCE_W) != NCELL * NCELL:
    raise RuntimeError("embedded Gen13 reference matrix length changed")

BANDS = (1, 3, 5)
SPECS = (
    {"name": "picard2x_control", "bandwidth": 0},
    {"name": "band1_jacobian", "bandwidth": 1},
    {"name": "band3_jacobian", "bandwidth": 3},
    {"name": "band5_jacobian", "bandwidth": 5},
)
CASE_NAMES = tuple(str(x["name"]) for x in SPECS)
wall08.FINAL_TAU = FINAL_TAU


def _project_band(bandwidth: int) -> list[float]:
    if bandwidth not in BANDS:
        raise ValueError(f"unsupported bandwidth: {bandwidth}")
    matrix = [[0.0 for _ in range(NCELL)] for _ in range(NCELL)]
    for i in range(NCELL):
        for j in range(NCELL):
            if i != j and abs(i - j) <= bandwidth:
                matrix[i][j] = float(_REFERENCE_W[i * NCELL + j])
        matrix[i][i] = -sum(matrix[i][j] for j in range(NCELL) if j != i)
    return [v for row in matrix for v in row]


def _projection_metrics(bandwidth: int) -> dict[str, float]:
    m = _project_band(bandwidth)
    ref2 = sum(v * v for v in _REFERENCE_W)
    err2 = sum((m[k] - _REFERENCE_W[k]) ** 2 for k in range(len(m)))
    diag_fraction = []
    for i in range(NCELL):
        dref = float(_REFERENCE_W[i * NCELL + i])
        dtrial = float(m[i * NCELL + i])
        if dref:
            diag_fraction.append(dtrial / dref)
    diag_fraction.sort()
    n = len(diag_fraction)
    median = diag_fraction[n // 2] if n % 2 else 0.5 * (diag_fraction[n // 2 - 1] + diag_fraction[n // 2])
    return {
        "relative_frobenius_error": math.sqrt(err2 / ref2),
        "median_diagonal_fraction": median,
        "max_abs_row_sum": max(
            abs(sum(m[i * NCELL:(i + 1) * NCELL])) for i in range(NCELL)
        ),
    }


def _matrix_literal(bandwidth: int) -> str:
    return " ".join(f"{v:.17g}" for v in _project_band(bandwidth))


def _cell_centers() -> list[float]:
    return [XMIN + (i + 0.5) * DX for i in range(NCELL)]


def _spec(raw: dict[str, object]) -> dict[str, object]:
    return {
        **raw,
        "architecture": "transient_timeaware",
        "algorithm": "picard",
        "mode": "thermal",
        "chi": CHI_E,
        "chi_h": CHI_H,
        "heavy_cycles": HEAVY_CYCLES,
        "ratio": RATIO,
        "fp_max": FP_MAX,
        "relaxation_factor": 2.0 / (1.0 + CHI_E),
    }


def _params(raw: dict[str, object]) -> dict[str, object]:
    spec = _spec(raw)
    with wall08._clock(spec):
        p = wall08.wall03._params(spec)
    p.update(
        heavy_to_electron_dt_ratio=RATIO,
        architecture="transient_timeaware",
        fixed_point_algorithm="picard",
        relaxation_factor=2.0 / (1.0 + CHI_E),
        banded_jacobian_width=int(raw["bandwidth"]),
        gen13_basis_run=GEN13_RUN,
        gen13_basis_head=GEN13_HEAD,
    )
    return p


def _timeaware(raw: dict[str, object], p: dict[str, object]) -> tuple[str, str, str]:
    spec = _spec(raw)
    old_final = seq08.FINAL_TAU
    old_cycles = seq08.HEAVY_CYCLES
    try:
        seq08.FINAL_TAU = FINAL_TAU
        seq08.HEAVY_CYCLES = HEAVY_CYCLES
        with wall08._clock(spec):
            parent, fast, poisson = seq08._render_case(spec, p)
    finally:
        seq08.FINAL_TAU = old_final
        seq08.HEAVY_CYCLES = old_cycles
    return parent, fast, poisson


def _instrument_anchor(fast: str) -> str:
    aux_anchor = """  [elastic_loss_candidate_out]
    type = MooseVariableFVReal
    initial_condition = 4.622905967454569
  []
[]
"""
    if fast.count(aux_anchor) != 1:
        raise RuntimeError("anchor diagnostic AuxVariables anchor changed")
    fast = fast.replace(
        aux_anchor,
        """  [elastic_loss_candidate_out]
    type = MooseVariableFVReal
    initial_condition = 4.622905967454569
  []
  [fp_phi_anchor_diag]
    type = MooseVariableFVReal
    initial_condition = 0.0
  []
[]
""",
        1,
    )

    fp_anchor = """  [fixed_point_iterations]
    type = NumFixedPointIterations
    execute_on = 'TIMESTEP_END'
  []
"""
    if fast.count(fp_anchor) != 1:
        raise RuntimeError("fixed-point postprocessor anchor changed")

    points = []
    for i, x in enumerate(_cell_centers()):
        points.append(
            f"""  [fp_phi_current_{i:02d}]
    type = PointValue
    variable = potential_from_poisson
    point = '{x:.17g} 0 0'
    execute_on = 'MULTIAPP_FIXED_POINT_CONVERGENCE'
  []
  [fp_phi_anchor_{i:02d}]
    type = PointValue
    variable = fp_phi_anchor_diag
    point = '{x:.17g} 0 0'
    execute_on = 'MULTIAPP_FIXED_POINT_CONVERGENCE'
  []
"""
        )
    fast = fast.replace(fp_anchor, "".join(points) + fp_anchor, 1)

    outputs = """[Outputs]
  [step_csv]
    type = CSV
    execute_on = 'INITIAL TIMESTEP_END'
    new_row_tolerance = 1.0e-30
  []
"""
    if fast.count(outputs) != 1:
        raise RuntimeError("fast output anchor changed")
    fast = fast.replace(
        outputs,
        outputs + """  [fp_anchor_csv]
    type = CSV
    execute_on = 'MULTIAPP_FIXED_POINT_ITERATION_END'
    execute_postprocessors_on = 'MULTIAPP_FIXED_POINT_ITERATION_END'
    new_row_detection_columns = all
    new_row_tolerance = 1.0e-30
    precision = 17
    scientific_notation = true
  []
""",
        1,
    )
    return fast


def _apply_banded(fast: str, poisson: str, bandwidth: int) -> tuple[str, str]:
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
        transfer_anchor + """  [n_epsilon_to_poisson]
    type = MultiAppCopyTransfer
    to_multi_app = poisson
    source_variable = n_epsilon
    variable = n_epsilon_frozen
    execute_on = SAME_AS_MULTIAPP
  []
  [phi_anchor_to_poisson]
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
        """  [n_epsilon_frozen]
    type = MooseVariableFVReal
    initial_condition = 1.0
  []
  [phi_anchor_frozen]
    type = MooseVariableFVReal
    initial_condition = 0.0
  []
""" + aux_anchor,
        1,
    )

    material_anchor = """  [plasma_charge]
    type = PhysicsPlasmaChargeDensityMaterial
"""
    if poisson.count(material_anchor) != 1:
        raise RuntimeError("Poisson material anchor changed")
    poisson = poisson.replace(
        material_anchor,
        f"""  [gummel_mean_energy]
    type = ADParsedFunctorMaterial
    property_name = gummel_mean_energy_ev
    functor_names = 'electron_density_m3 n_epsilon_frozen'
    functor_symbols = 'ne n_eps'
    expression = '{MEAN_E0_EV:.17g}*n_eps/max(ne/{NE0:.17g},1.0e-30)'
  []
  [gummel_band_beta]
    type = ADParsedFunctorMaterial
    property_name = gummel_band_beta
    functor_names = 'electron_density_m3 gummel_mean_energy_ev'
    functor_symbols = 'ne mean_ev'
    expression = '{E_OVER_EPS0:.17g}*ne/((2.0/3.0)*max(mean_ev,1.0e-6))'
  []
""" + material_anchor,
        1,
    )

    kernel_anchor = """  [phi_charge_source]
    type = FVCoupledForce
    variable = potential_plasma
    v = poisson_charge_source
    coef = 1.0
  []
"""
    if poisson.count(kernel_anchor) != 1:
        raise RuntimeError("Poisson charge kernel anchor changed")
    poisson = poisson.replace(
        kernel_anchor,
        kernel_anchor + f"""  [gummel_banded_correction]
    type = PhysicsFVGummelBandedCorrection
    variable = potential_plasma
    anchor = phi_anchor_frozen
    beta = gummel_band_beta
    matrix = '{_matrix_literal(bandwidth)}'
    n_cells = {NCELL}
    bandwidth = {bandwidth}
    xmin = {XMIN:.17g}
    dx = {DX:.17g}
    ghost_layers = 6
  []
""",
        1,
    )
    return fast, poisson


def render(raw: dict[str, object], p: dict[str, object]) -> tuple[str, str, str]:
    parent, fast, poisson = _timeaware(raw, p)
    bandwidth = int(raw["bandwidth"])
    if bandwidth > 0:
        fast = _instrument_anchor(fast)
        fast, poisson = _apply_banded(fast, poisson, bandwidth)
    return parent, fast, poisson


def build(clean: bool = True) -> list[dict[str, object]]:
    if clean and GENERATED.exists():
        shutil.rmtree(GENERATED)
    GENERATED.mkdir(parents=True, exist_ok=True)
    built = []
    for raw in SPECS:
        p = _params(raw)
        d = GENERATED / str(raw["name"])
        d.mkdir(parents=True, exist_ok=True)
        parent, fast, poisson = render(raw, p)
        (d / "input.i").write_text(parent, encoding="utf-8")
        (d / "fast_sub.i").write_text(fast, encoding="utf-8")
        (d / "poisson_sub.i").write_text(poisson, encoding="utf-8")
        shutil.copy2(base.ELECTRON_MOMENTS, d / "electron_moments.txt")
        shutil.copy2(base.ELASTIC_DATA, d / "o2_elastic.txt")
        shutil.copy2(base.HEAVY_TRANSPORT_DATA, d / "transport_data.txt")
        (d / "case.json").write_text(json.dumps(p, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        built.append(p)
    return built


def p0() -> None:
    built = build()
    assert len(built) == 4
    control = GENERATED / "picard2x_control"
    control_parent = (control / "input.i").read_text(encoding="utf-8")
    assert "gummel_banded_correction" not in (control / "poisson_sub.i").read_text(encoding="utf-8")

    for b in BANDS:
        metrics = _projection_metrics(b)
        assert metrics["max_abs_row_sum"] < 1.0e-12
        d = GENERATED / f"band{b}_jacobian"
        fast = (d / "fast_sub.i").read_text(encoding="utf-8")
        poisson = (d / "poisson_sub.i").read_text(encoding="utf-8")
        assert (d / "input.i").read_text(encoding="utf-8") == control_parent
        assert "type = PhysicsFVGummelBandedCorrection" in poisson
        assert f"bandwidth = {b}" in poisson
        assert "gummel_band_beta" in poisson
        assert "phi_anchor_from_poisson_diag" in fast
        assert fast.count("type = PointValue") == 2 * NCELL
        assert "execute_on = 'MULTIAPP_FIXED_POINT_ITERATION_END'" in fast
        assert "TimeDerivative" not in poisson
        assert "no_restore = true" in fast

    print("ISSUE310_GEN15_BANDED_P0: PASS")
    print(json.dumps({str(b): _projection_metrics(b) for b in BANDS}, sort_keys=True))


def p1() -> None:
    build()
    rel = ROOT.relative_to(REPO)
    cmds = "; ".join(
        f"python3 /workspace/bin/physics.py preflight /workspace/{rel}/generated_fp15_banded/{n}/input.i"
        for n in CASE_NAMES
    )
    base._docker("set -euo pipefail; source /environment; export PYTHONPATH=/workspace; " + cmds)
    print("ISSUE310_GEN15_BANDED_P1: PASS")


def p2() -> None:
    build()
    rel = ROOT.relative_to(REPO)
    checks = []
    for n in CASE_NAMES:
        for f in ("input.i", "fast_sub.i", "poisson_sub.i"):
            checks.append(
                f"cd /workspace/{rel}/generated_fp15_banded/{n} && "
                f"/workspace/physics_app/physics-opt --check-input -i {f}"
            )
    base._docker(
        "set -euo pipefail; source /environment; "
        "export MOOSE_DIR=/opt/physics_vendor/moose CRANE_DIR=/opt/physics_vendor/crane "
        "SQUIRREL_DIR=/opt/physics_vendor/squirrel ZAPDOS_DIR=/opt/physics_vendor/zapdos METHOD=opt; "
        "make -C /workspace/physics_app -j2; " + "; ".join(checks)
    )
    print("ISSUE310_GEN15_BANDED_P2: PASS")


def _bind() -> None:
    seq08.GENERATED = GENERATED
    seq08.RESULTS = RESULTS
    seq08.FINAL_TAU = FINAL_TAU
    seq08.HEAVY_CYCLES = HEAVY_CYCLES
    seq08.CASE_NAMES = CASE_NAMES
    seq08.SPECS = tuple(_spec(x) for x in SPECS)
    wall08.FINAL_TAU = FINAL_TAU


def inner_run(name: str) -> int:
    _bind()
    RESULTS.mkdir(parents=True, exist_ok=True)
    return seq08.inner_run(name)


def _anchor_diagnostic(name: str) -> dict[str, object]:
    if name == "picard2x_control":
        return {}
    d = GENERATED / name
    files = sorted(d.glob("*fp_anchor_csv.csv"))
    if not files:
        return {"anchor_diagnostic_available": False}
    rows = []
    for path in files:
        with path.open(newline="", encoding="utf-8") as handle:
            rr = list(csv.DictReader(handle))
        if rr and "fp_phi_current_00" in rr[0]:
            rows = rr
    if not rows:
        return {"anchor_diagnostic_available": False}

    groups: dict[float, list[dict[str, str]]] = {}
    for row in rows:
        try:
            t = float(row["time"])
        except (KeyError, ValueError):
            continue
        if t <= 0.0:
            continue
        groups.setdefault(t, []).append(row)

    alignment = []
    same_iter = []
    samples = 0
    for _, grp in sorted(groups.items()):
        for k, row in enumerate(grp):
            cur = [float(row[f"fp_phi_current_{i:02d}"]) for i in range(NCELL)]
            anchor = [float(row[f"fp_phi_anchor_{i:02d}"]) for i in range(NCELL)]
            same_iter.append(max(abs(cur[i] - anchor[i]) for i in range(NCELL)))
            if k > 0:
                prev = [float(grp[k - 1][f"fp_phi_current_{i:02d}"]) for i in range(NCELL)]
                alignment.append(max(abs(anchor[i] - prev[i]) for i in range(NCELL)))
            samples += 1

    return {
        "anchor_diagnostic_available": True,
        "anchor_rows": samples,
        "anchor_equals_previous_phi_max_abs_V": max(alignment) if alignment else None,
        "anchor_equals_previous_phi_median_max_abs_V": (
            sorted(alignment)[len(alignment) // 2] if alignment else None
        ),
        "same_iteration_phi_minus_anchor_max_abs_V": max(same_iter) if same_iter else None,
    }


def run_case(name: str) -> None:
    _bind()
    if not GENERATED.exists():
        build()
    if not (REPO / "physics_app" / "physics-opt").exists():
        raise SystemExit("physics-opt missing")
    rel = ROOT.relative_to(REPO)
    base._docker(
        "set -euo pipefail; source /environment; "
        "export MOOSE_DIR=/opt/physics_vendor/moose CRANE_DIR=/opt/physics_vendor/crane "
        "SQUIRREL_DIR=/opt/physics_vendor/squirrel ZAPDOS_DIR=/opt/physics_vendor/zapdos "
        "METHOD=opt PYTHONPATH=/workspace; "
        f"python3 /workspace/{rel}/control_seq15_banded.py --inner-run {name}; "
        f"chmod -R a+rwX /workspace/{rel}/results_fp15_banded /workspace/{rel}/generated_fp15_banded"
    )
    result, code = seq08.analyze(name)
    raw = next(x for x in SPECS if x["name"] == name)
    b = int(raw["bandwidth"])
    result.update(
        sequence=15,
        banded_jacobian_width=b,
        gen13_basis_run=GEN13_RUN,
        **(_projection_metrics(b) if b else {}),
        **_anchor_diagnostic(name),
    )
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / f"{name}_result.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print("ISSUE310_GEN15_BANDED_CASE:", name, result["classification"])
    if code:
        raise SystemExit(code)


def aggregate() -> None:
    root = os.environ.get("CHATGPT_MATRIX_EVIDENCE_ROOT")
    if not root:
        raise SystemExit("CHATGPT_MATRIX_EVIDENCE_ROOT is required")
    found = {}
    for path in Path(root).rglob("*_result.json"):
        item = json.loads(path.read_text(encoding="utf-8"))
        name = str(item.get("case", ""))
        if name in CASE_NAMES:
            found[name] = item

    missing = [n for n in CASE_NAMES if n not in found]
    control = found.get("picard2x_control")
    trials = {}
    if control:
        cfp = control.get("cumulative_fixed_point_iterations")
        for raw in SPECS[1:]:
            name = str(raw["name"])
            item = found.get(name)
            if not item:
                continue
            fp = item.get("cumulative_fixed_point_iterations")
            comp = {
                "bandwidth": int(raw["bandwidth"]),
                "evidence_valid": bool(item.get("evidence_valid")),
                "classification": item.get("classification"),
                "cumulative_fixed_point_iterations": fp,
                "average_fixed_point_iterations_per_observed_step": item.get(
                    "average_fixed_point_iterations_per_observed_step"
                ),
                "relative_frobenius_error": item.get("relative_frobenius_error"),
                "median_diagonal_fraction": item.get("median_diagonal_fraction"),
                "anchor_diagnostic_available": item.get("anchor_diagnostic_available"),
                "anchor_equals_previous_phi_max_abs_V": item.get("anchor_equals_previous_phi_max_abs_V"),
                "same_iteration_phi_minus_anchor_max_abs_V": item.get(
                    "same_iteration_phi_minus_anchor_max_abs_V"
                ),
            }
            if isinstance(fp, (int, float)) and isinstance(cfp, (int, float)) and cfp:
                comp["fixed_point_reduction_fraction_vs_control"] = 1.0 - float(fp) / float(cfp)
            if bool(control.get("evidence_valid")) and bool(item.get("evidence_valid")):
                comp["final_profile_parity"] = wall08._comparison(control, item)
                comp["potential_time_series_parity"] = seq08._potential_series_parity(control, item)
            trials[name] = comp

    summary = {
        "issue": 310,
        "sequence": 15,
        "classification": (
            "GEN15_BANDED_EVIDENCE_COMPLETE"
            if not missing else "GEN15_BANDED_EVIDENCE_PARTIAL"
        ),
        "missing_cases": missing,
        "control": control,
        "trials": trials,
        "cases": found,
        "source_basis": {"run": GEN13_RUN, "head": GEN13_HEAD},
        "guard": (
            "Banded correction is an iteration-operator approximation only. Rows are explicitly "
            "zero-sum and the term vanishes for phi=phi_anchor. Promotion requires stable FP "
            "reduction plus trajectory/profile parity and later long-horizon validation."
        ),
    }
    RESULTS.mkdir(parents=True, exist_ok=True)
    out = RESULTS / "issue310_gen15_banded_summary.json"
    out.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("ISSUE310_GEN15_BANDED_AGGREGATE:", summary["classification"])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--p0", action="store_true")
    ap.add_argument("--p1", action="store_true")
    ap.add_argument("--p2", action="store_true")
    ap.add_argument("--inner-run", choices=CASE_NAMES)
    ap.add_argument("--case", choices=CASE_NAMES)
    ap.add_argument("--aggregate", action="store_true")
    args = ap.parse_args()
    if args.p0:
        p0()
    elif args.p1:
        p1()
    elif args.p2:
        p2()
    elif args.inner_run:
        raise SystemExit(inner_run(args.inner_run))
    elif args.case:
        run_case(args.case)
    elif args.aggregate:
        aggregate()
    else:
        ap.error("choose one action")


if __name__ == "__main__":
    main()
