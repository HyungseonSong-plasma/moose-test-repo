from __future__ import annotations

from experiments.Issue92_r3_nonlinear.diagnose import (
    analyze_residual_log,
    build_overlay,
    classify_d1,
    classify_jacobian,
    detect_two_cycle,
    scaling_discriminator,
)


def _table(i: int, norm: float, values: dict[str, float]) -> str:
    rows = "\n".join(f"  {name}: {value:.6e}" for name, value in values.items())
    return f"{i} Nonlinear |R| = {norm:.6e}\n |residual|_2 of individual variables:\n{rows}\n"


def test_issue92_detects_observed_newton_two_cycle() -> None:
    assert detect_two_cycle([0.9839955, 1.0336703, 0.9476568, 1.0336703, 0.9476568])
    assert not detect_two_cycle([1.0, 0.7, 0.4, 0.2])


def test_issue92_parses_current_moose_variable_residual_header() -> None:
    log = _table(0, 1.0, {"u": 1e-3, "n_e": 1.0})
    a = analyze_residual_log(log)
    assert a.variable_norms == [{"u": 1e-3, "n_e": 1.0}]


def test_issue92_classifies_electron_residual_dominance() -> None:
    log = "\n".join(
        _table(i, n, {"u": 1e-3, "v": 1e-3, "p": 1e-3, "n_e": e})
        for i, (n, e) in enumerate([(1.0, 1.0), (1.1, 1.1), (1.0, 1.0), (1.1, 1.1)])
    )
    a = analyze_residual_log(log)
    assert a.parse_complete and a.two_cycle
    assert classify_d1(a)[0] == "B2"


def test_issue92_classifies_comparable_residuals_as_h3_route() -> None:
    vals = {"u": 1.0, "v": 0.9, "p": 0.8, "w_O2p": 0.7, "n_e": 0.8}
    a = analyze_residual_log("\n".join(_table(i, n, vals) for i, n in enumerate([1.0, 1.1, 1.0, 1.1])))
    assert classify_d1(a)[0] == "B6"


def test_issue92_scaling_requires_scale_collapse_and_descent() -> None:
    ref = analyze_residual_log("\n".join(_table(i, n, {"u": 1e-3, "p": 1e-3, "n_e": 1.0}) for i, n in enumerate([1.0, 1.1, 1.0, 1.1])))
    cand = analyze_residual_log("\n".join(_table(i, n, {"u": 0.5, "p": 0.4, "n_e": 0.6}) for i, n in enumerate([1.0, 0.7, 0.4, 0.2])))
    assert scaling_discriminator(ref, cand)


def test_issue92_jacobian_classification_is_fail_closed() -> None:
    assert classify_jacobian("Norm of matrix ratio 2.8e-08, difference 1.0e-05")[0] == "ACCEPTABLE"
    assert classify_jacobian("Norm of matrix ratio 2.0e-02, difference 1.0e+01")[0] == "MATERIAL_MISMATCH"
    assert classify_jacobian("no PETSc jacobian output")[0] == "UNAVAILABLE"


def test_issue92_overlay_preserves_physics_and_changes_diagnostic_numerics() -> None:
    base = """[Executioner]\n  type = Transient\n  dt = 1e-8\n  end_time = 1e-8\n  automatic_scaling = true\n[]\n"""
    text = build_overlay(base, residual_scaling=True, dt=1e-9)
    for expected in (
        "line_search = none", "nl_max_its = 3", "abort_on_solve_fail = true",
        "resid_vs_jac_scaling_param = 1", "show_var_residual_norms = true",
        "show_top_residuals = 20", "automatic_scaling = true",
    ):
        assert expected in text
