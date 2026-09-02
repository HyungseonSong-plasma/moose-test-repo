from __future__ import annotations

from experiments.Issue92_r3_nonlinear.diagnose import (
    analyze_residual_log,
    build_overlay,
    classify_d1,
    classify_jacobian,
    detect_two_cycle,
    scaling_discriminator,
)


def _table(iteration: int, global_norm: float, values: dict[str, float]) -> str:
    body = "\n".join(f"  {name}: {value:.6e}" for name, value in values.items())
    return f"{iteration} Nonlinear |R| = {global_norm:.6e}\nVariable Residual Norms:\n{body}\n"


def test_issue92_detects_observed_newton_two_cycle() -> None:
    assert detect_two_cycle([0.9839955, 1.0336703, 0.9476568, 1.0336703, 0.9476568])
    assert not detect_two_cycle([1.0, 0.7, 0.4, 0.2])


def test_issue92_classifies_electron_residual_dominance() -> None:
    log = "\n".join(
        [
            _table(0, 1.0, {"u": 1e-3, "v": 1e-3, "p": 1e-3, "n_e": 1.0}),
            _table(1, 1.1, {"u": 1e-3, "v": 1e-3, "p": 1e-3, "n_e": 1.1}),
            _table(2, 1.0, {"u": 1e-3, "v": 1e-3, "p": 1e-3, "n_e": 1.0}),
            _table(3, 1.1, {"u": 1e-3, "v": 1e-3, "p": 1e-3, "n_e": 1.1}),
        ]
    )
    analysis = analyze_residual_log(log)
    assert analysis.parse_complete
    assert analysis.two_cycle
    assert classify_d1(analysis)[0] == "B2"


def test_issue92_classifies_comparable_residuals_as_h3_route() -> None:
    vals = {"u": 1.0, "v": 0.9, "p": 0.8, "w_O2p": 0.7, "n_e": 0.8}
    log = "\n".join(_table(i, value, vals) for i, value in enumerate([1.0, 1.1, 1.0, 1.1]))
    analysis = analyze_residual_log(log)
    assert classify_d1(analysis)[0] == "B6"


def test_issue92_residual_scaling_requires_both_scale_collapse_and_descent() -> None:
    ref_log = "\n".join(
        _table(i, value, {"u": 1e-3, "p": 1e-3, "n_e": 1.0})
        for i, value in enumerate([1.0, 1.1, 1.0, 1.1])
    )
    cand_log = "\n".join(
        _table(i, value, {"u": 0.5, "p": 0.4, "n_e": 0.6})
        for i, value in enumerate([1.0, 0.7, 0.4, 0.2])
    )
    assert scaling_discriminator(analyze_residual_log(ref_log), analyze_residual_log(cand_log))


def test_issue92_jacobian_ratio_classification_is_fail_closed() -> None:
    ok = "Norm of matrix ratio 2.8e-08, difference 1.0e-05"
    bad = "Norm of matrix ratio 2.0e-02, difference 1.0e+01"
    assert classify_jacobian(ok)[0] == "ACCEPTABLE"
    assert classify_jacobian(bad)[0] == "MATERIAL_MISMATCH"
    assert classify_jacobian("no PETSc jacobian output")[0] == "UNAVAILABLE"


def test_issue92_overlay_changes_only_declared_diagnostic_numerics() -> None:
    base = """[Executioner]\n  type = Transient\n  dt = 1e-8\n  end_time = 1e-8\n  automatic_scaling = true\n[]\n"""
    text = build_overlay(base, residual_scaling=True, dt=1e-9)
    assert "line_search = none" in text
    assert "nl_max_its = 3" in text
    assert "abort_on_solve_fail = true" in text
    assert "resid_vs_jac_scaling_param = 1" in text
    assert "dt = 1.0000000000000001e-09" in text or "dt = 1e-09" in text
    assert "show_var_residual_norms = true" in text
    assert "show_top_residuals = 20" in text
    assert "automatic_scaling = true" in text
