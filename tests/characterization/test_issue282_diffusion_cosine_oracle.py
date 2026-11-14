"""Issue #282: independent, synthetic diffusion oracle (no QPX/MOOSE imports).

Research characterization for user-approved D5-D8 design direction, NOT a
scientifically accepted plasma model or proof of the existing Gaussian E2a run.
The 1-D cosine benchmark is independent of HIT generation, Physics target.py,
SOL realization DTOs, and the external adapter.

Exact reference for the constant-D, zero-source, zero-Neumann-flux equation:

    du/dt = D * d²u/dx²
    u(x, 0) = u_bar + A*cos(pi*x/L)
    u(x, t) = u_bar + A*exp(-D*(pi/L)**2*t)*cos(pi*x/L)

1e-4 is a *candidate field relative-L2 target*, not a nonlinear solver
residual target or scientific PASS without independent MOOSE evidence.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import pytest


RELATIVE_TARGET = 1.0e-4  # 0.01%; proposed, not Physics-Validator accepted
STRICT_ZERO_D_REL_TOL = 1.0e-10  # preserve the existing E2a control regression
STRICT_ZERO_D_ABS_TOL = 1.0e-12
ELECTRON_VOLT_J = 1.602176634e-19
ENERGY_REFERENCE_EV = 5.73276  # historical Physics implementation value


@dataclass(frozen=True)
class CosineNeumannOracle:
    """Standalone 1-D test problem, NOT the historical 2-D Gaussian E2a case."""

    length_m: float = 0.01
    diffusivity_m2_s: float = 100.0
    mean: float = 1.0
    amplitude: float = 0.25

    def __post_init__(self) -> None:
        values = (self.length_m, self.diffusivity_m2_s, self.mean, self.amplitude)
        if not all(math.isfinite(v) for v in values):
            raise ValueError("oracle inputs must be finite")
        if self.length_m <= 0.0 or self.diffusivity_m2_s < 0.0:
            raise ValueError("length must be positive and diffusivity nonnegative")

    def state(self, x_m: float, t_s: float) -> float:
        if not math.isfinite(x_m) or not 0.0 <= x_m <= self.length_m:
            raise ValueError("sample outside benchmark interval")
        if not math.isfinite(t_s) or t_s < 0.0:
            raise ValueError("time must be finite and nonnegative")
        eigenvalue = (math.pi / self.length_m) ** 2
        return self.mean + self.amplitude * math.exp(
            -self.diffusivity_m2_s * eigenvalue * t_s
        ) * math.cos(math.pi * x_m / self.length_m)

    def sample_midpoints(self, t_s: float, count: int = 128) -> tuple[float, ...]:
        if count < 2:
            raise ValueError("at least two midpoint cells are required")
        return tuple(
            self.state(self.length_m * (i + 0.5) / count, t_s)
            for i in range(count)
        )

    def exact_integral(self) -> float:
        """Integrated dimensionless state across the 1-D length."""
        return self.mean * self.length_m


def relative_l2(measured: tuple[float, ...], reference: tuple[float, ...]) -> float:
    """Field metric with explicit refusal of a zero/undefined reference norm."""
    if not measured or len(measured) != len(reference):
        raise ValueError("nonempty, aligned field samples are required")
    if not all(math.isfinite(v) for v in (*measured, *reference)):
        raise ValueError("nonfinite field sample")
    reference_norm = math.sqrt(sum(v * v for v in reference))
    if reference_norm == 0.0:
        raise ValueError("zero reference requires a separately justified absolute bound")
    error_norm = math.sqrt(sum((a - b) ** 2 for a, b in zip(measured, reference)))
    return error_norm / reference_norm


def energy_density_j_m3(
    normalized_energy: float, *, reference_density_m3: float
) -> float:
    """Conditional unit conversion: only valid once Physics approves u semantics."""
    if (
        not math.isfinite(normalized_energy)
        or not math.isfinite(reference_density_m3)
        or reference_density_m3 <= 0.0
    ):
        raise ValueError("finite state and positive reference density required")
    return (
        reference_density_m3
        * ENERGY_REFERENCE_EV
        * ELECTRON_VOLT_J
        * normalized_energy
    )


def mean_energy_ev(
    normalized_energy: float, *, normalized_electron_density: float
) -> float:
    """Conditional bridge found in historical Physics lowering; not SOL authority."""
    if (
        not math.isfinite(normalized_energy)
        or not math.isfinite(normalized_electron_density)
        or normalized_electron_density <= 0.0
    ):
        raise ValueError("normalized electron density must be finite and positive")
    return ENERGY_REFERENCE_EV * normalized_energy / normalized_electron_density


def test_no_diffusion_preserves_every_sample_and_the_existing_strict_range_gate() -> None:
    control = CosineNeumannOracle(diffusivity_m2_s=0.0)
    initial = control.sample_midpoints(0.0)
    final = control.sample_midpoints(1.0e-8)
    assert final == initial
    assert math.isclose(
        max(final) - min(final),
        max(initial) - min(initial),
        rel_tol=STRICT_ZERO_D_REL_TOL,
        abs_tol=STRICT_ZERO_D_ABS_TOL,
    )


def test_positive_diffusion_has_exact_decay_with_no_flux_and_conserved_integral() -> None:
    treatment = CosineNeumannOracle(diffusivity_m2_s=100.0)
    t_s = 1.0e-8
    initial = treatment.sample_midpoints(0.0)
    final = treatment.sample_midpoints(t_s)
    decay = math.exp(-100.0 * (math.pi / treatment.length_m) ** 2 * t_s)
    assert 0.0 < decay < 1.0
    assert max(final) - min(final) < max(initial) - min(initial)
    assert math.isclose(
        (max(final) - min(final)) / (max(initial) - min(initial)),
        decay,
        rel_tol=1.0e-12,
    )
    # The cosine derivative is proportional to sin(pi*x/L), hence zero at
    # both ends; its analytic domain integral is constant at mean * L.
    for values in (initial, final):
        midpoint_integral = sum(values) * treatment.length_m / len(values)
        assert math.isclose(
            midpoint_integral, treatment.exact_integral(), rel_tol=1.0e-12
        )


def test_energy_inventory_uses_joules_and_matches_both_arms_in_synthetic_slab() -> None:
    # Explicit synthetic numbers, NOT claims about the E2a plasma geometry.
    reference_density_m3 = 1.0e15
    cross_section_m2 = 1.0e-4
    baseline = energy_density_j_m3(
        1.0, reference_density_m3=reference_density_m3
    )
    assert baseline > 0.0
    reference_inventory_j = baseline * cross_section_m2 * 0.01
    for diffusivity in (0.0, 100.0):
        oracle = CosineNeumannOracle(diffusivity_m2_s=diffusivity)
        for t_s in (0.0, 1.0e-8):
            measured_inventory_j = (
                sum(oracle.sample_midpoints(t_s))
                / 128
                * baseline
                * cross_section_m2
                * oracle.length_m
            )
            assert (
                abs(measured_inventory_j - reference_inventory_j)
                / reference_inventory_j
                <= RELATIVE_TARGET
            )


def test_profile_error_metric_accepts_below_and_rejects_above_point_zero_one_percent() -> None:
    reference = CosineNeumannOracle().sample_midpoints(1.0e-8)
    below = tuple(v * (1.0 + 0.9 * RELATIVE_TARGET) for v in reference)
    above = tuple(v * (1.0 + 1.1 * RELATIVE_TARGET) for v in reference)
    assert relative_l2(below, reference) <= RELATIVE_TARGET
    assert relative_l2(above, reference) > RELATIVE_TARGET


def test_wrong_diffusivity_is_detected_even_though_both_profiles_conserve_energy() -> None:
    expected = CosineNeumannOracle(diffusivity_m2_s=100.0).sample_midpoints(1.0e-8)
    wrong = CosineNeumannOracle(diffusivity_m2_s=80.0).sample_midpoints(1.0e-8)
    assert relative_l2(wrong, expected) > RELATIVE_TARGET
    assert math.isclose(sum(expected), sum(wrong), rel_tol=1.0e-12)


def test_normalization_bridge_is_explicit_and_density_zero_fails_closed() -> None:
    assert mean_energy_ev(1.2, normalized_electron_density=0.8) == pytest.approx(
        ENERGY_REFERENCE_EV * 1.5
    )
    with pytest.raises(ValueError, match="positive"):
        mean_energy_ev(1.0, normalized_electron_density=0.0)
    with pytest.raises(ValueError, match="positive"):
        energy_density_j_m3(1.0, reference_density_m3=0.0)


def test_relative_field_error_requires_absolute_policy_at_zero() -> None:
    with pytest.raises(ValueError, match="zero reference"):
        relative_l2((0.0, 1.0e-9), (0.0, 0.0))
    with pytest.raises(ValueError, match="aligned"):
        relative_l2((1.0,), (1.0, 2.0))


def test_one_coarse_backward_euler_step_is_not_assumed_to_meet_analytic_target() -> None:
    # Mathematical example, NOT evidence that the existing MOOSE executioner
    # chooses backward Euler: temporal scheme and backend pin remain unresolved.
    oracle = CosineNeumannOracle(diffusivity_m2_s=100.0)
    step_s = 1.0e-8
    z = oracle.diffusivity_m2_s * (math.pi / oracle.length_m) ** 2 * step_s
    exact_amplitude_ratio = math.exp(-z)
    hypothetical_backward_euler_ratio = 1.0 / (1.0 + z)
    assert (
        abs(hypothetical_backward_euler_ratio - exact_amplitude_ratio)
        / exact_amplitude_ratio
        > RELATIVE_TARGET
    )
