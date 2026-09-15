#!/usr/bin/env python3
"""Issue-236 live-electron dielectric-relaxation discriminator with volume chemistry off.

This wrapper keeps the accepted multirate schedule and fast electron+Poisson
coupling from run_live_ci_dr.py, including frozen heavy-transport electron
density, thermal electron particle/energy wall losses, and SEE boundary
sources. It removes only volumetric electron number-source and electron-energy
source/sink kernels from the fast child and requires the canonical conservative
electron-energy electrostatic drift term.

Fast child evolution therefore contains:
* n_e: time + diffusion + electrostatic drift + boundary particle loss/SEE;
* n_epsilon: time + diffusion + electrostatic drift + boundary energy loss/SEE;
* potential_plasma: Poisson;
* volumetric chemistry / collisional energy source-sink kernels: disabled.

The energy-drift topology is copied from the accepted particle drift so the
potential, carrier sign, interpolation, excluded boundaries, and block stay in
lock-step. Only the solved variable and mobility change to n_epsilon and
``electron_energy_mobility``. The 5/3 primary-wall closure is not a pass/fail
constraint for this CI.
"""
from __future__ import annotations

from experiments.Issue236_m1a_multiapp_smoke import run_live_ci_dr as dr

base = dr.base
live = dr.live

_dr_build_child_input = base.build_child_input
_dr_audit_child = base._audit_child
_dr_self_test = base.self_test

_ELECTRON_REACTION_SOURCE_TYPE = "PhysicsFVElectronReactionSource"
_SEE_PARTICLE_BC = "issue27_a8_see_electron_source"
_SEE_ENERGY_BC = "issue26_see_energy_source"
_PARTICLE_DRIFT = "FVKernels/n_e_drift"
_ENERGY_DRIFT_NAME = "s5r_n_epsilon_drift"
_ENERGY_DRIFT = f"FVKernels/{_ENERGY_DRIFT_NAME}"
_DRIFT_TOPOLOGY_PARAMETERS = (
    "potential",
    "carrier",
    "charge_number",
    "advected_interp_method",
    "boundaries_to_avoid",
    "block",
)


def _finalize(result):
    result["failed_checks"] = sorted(
        key for key, ok in result["checks"].items() if not ok
    )
    result["status"] = "PASS" if not result["failed_checks"] else "FAIL"
    return result


def _volumetric_electron_kernel_paths(text: str) -> list[str]:
    """Return fast-child volumetric electron chemistry/energy source kernels."""
    paths: list[str] = []
    for path in base._children(text, "FVKernels"):
        kernel_type = base.mp.unquote(base.mp.get_parameter(text, path, "type"))
        variable = base.mp.unquote(base.mp.get_parameter(text, path, "variable"))

        # Electron number production/loss from volume chemistry.
        if kernel_type == _ELECTRON_REACTION_SOURCE_TYPE:
            paths.append(path)
            continue

        # In the current Stage-5 production input all FVCoupledForce owners on
        # n_epsilon are volumetric collisional/chemistry energy source-sink
        # terms. Keep transport/time terms and all boundary energy owners.
        if variable == "n_epsilon" and kernel_type == "FVCoupledForce":
            paths.append(path)

    return paths


def _remove_volumetric_electron_chemistry(text: str) -> str:
    """Remove only volumetric electron-number and electron-energy chemistry owners."""
    for path in _volumetric_electron_kernel_paths(text):
        text = base.mb.remove_block(text, path)
    return text


def _energy_drift_matches_particle_topology(text: str) -> bool:
    """Check that energy drift differs from particle drift only by state/mobility."""
    if not base.mb.has_block(text, _PARTICLE_DRIFT) or not base.mb.has_block(
        text, _ENERGY_DRIFT
    ):
        return False

    if base.mp.unquote(base.mp.get_parameter(text, _ENERGY_DRIFT, "type")) != (
        "PhysicsFVElectrostaticDrift"
    ):
        return False
    if base.mp.unquote(base.mp.get_parameter(text, _ENERGY_DRIFT, "variable")) != (
        "n_epsilon"
    ):
        return False
    if base.mp.unquote(base.mp.get_parameter(text, _ENERGY_DRIFT, "mobility")) != (
        "electron_energy_mobility"
    ):
        return False

    return all(
        base.mp.get_parameter(text, _ENERGY_DRIFT, parameter)
        == base.mp.get_parameter(text, _PARTICLE_DRIFT, parameter)
        for parameter in _DRIFT_TOPOLOGY_PARAMETERS
    )


def _build_child_input(production_text: str, *, dt_e: float) -> str:
    """Build the no-chemistry child while preserving canonical energy transport."""
    text = _dr_build_child_input(production_text, dt_e=dt_e)
    if not base.mb.has_block(text, _ENERGY_DRIFT):
        raise base.Issue236Error(
            "canonical Stage-5 child lacks electron-energy electrostatic drift"
        )
    if not _energy_drift_matches_particle_topology(text):
        raise base.Issue236Error(
            "canonical electron-energy drift does not match particle-drift topology"
        )
    return _remove_volumetric_electron_chemistry(text)


def _audit_child(text: str, *, dt_e: float):
    result = _dr_audit_child(text, dt_e=dt_e)
    checks = result["checks"]

    remaining = _volumetric_electron_kernel_paths(text)
    checks["volumetric_electron_chemistry_off"] = not remaining
    checks["electron_number_source_removed"] = not any(
        base.mp.unquote(base.mp.get_parameter(text, path, "type"))
        == _ELECTRON_REACTION_SOURCE_TYPE
        for path in base._children(text, "FVKernels")
    )
    checks["electron_energy_volume_sources_removed"] = not any(
        base.mp.unquote(base.mp.get_parameter(text, path, "variable")) == "n_epsilon"
        and base.mp.unquote(base.mp.get_parameter(text, path, "type")) == "FVCoupledForce"
        for path in base._children(text, "FVKernels")
    )
    checks["electron_energy_drift_restored"] = base.mb.has_block(text, _ENERGY_DRIFT)
    checks["electron_energy_drift_matches_particle_topology"] = (
        _energy_drift_matches_particle_topology(text)
    )
    checks["electron_energy_transport_complete"] = all(
        base.mb.has_block(text, path)
        for path in (
            "FVKernels/s5r_n_epsilon_time",
            "FVKernels/s5r_n_epsilon_diffusion",
            _ENERGY_DRIFT,
        )
    )

    # Boundary physics intentionally remains active.
    checks["see_particle_boundary_retained"] = base.mb.has_block(
        text, f"FVBCs/{_SEE_PARTICLE_BC}"
    )
    checks["see_energy_boundary_retained"] = base.mb.has_block(
        text, f"FVBCs/{_SEE_ENERGY_BC}"
    )
    checks["particle_wall_loss_retained"] = base.mb.has_block(
        text, "FVBCs/issue217_grounded_sheath_primary_particle"
    )
    checks["energy_wall_loss_retained"] = base.mb.has_block(
        text, "FVBCs/issue217_grounded_sheath_primary_energy"
    )

    result["remaining_volumetric_electron_kernels"] = remaining
    return _finalize(result)


def _self_test():
    result = _dr_self_test()
    parent, child, _meta = base.build_split(dt_e=live.ELECTRON_DT_S)
    checks = result.setdefault("checks", {})

    remaining = _volumetric_electron_kernel_paths(child)
    checks["volumetric_electron_chemistry_off"] = not remaining
    checks["electron_number_source_removed"] = not base.mb.has_block(
        child, "FVKernels/s5r_electron_source"
    )
    checks["electron_energy_volume_sources_removed"] = not any(
        base.mp.unquote(base.mp.get_parameter(child, path, "variable")) == "n_epsilon"
        and base.mp.unquote(base.mp.get_parameter(child, path, "type")) == "FVCoupledForce"
        for path in base._children(child, "FVKernels")
    )
    checks["electron_energy_drift_restored"] = base.mb.has_block(child, _ENERGY_DRIFT)
    checks["electron_energy_drift_matches_particle_topology"] = (
        _energy_drift_matches_particle_topology(child)
    )
    checks["electron_energy_transport_complete"] = all(
        base.mb.has_block(child, path)
        for path in (
            "FVKernels/s5r_n_epsilon_time",
            "FVKernels/s5r_n_epsilon_diffusion",
            _ENERGY_DRIFT,
        )
    )
    checks["see_particle_boundary_retained"] = base.mb.has_block(
        child, f"FVBCs/{_SEE_PARTICLE_BC}"
    )
    checks["see_energy_boundary_retained"] = base.mb.has_block(
        child, f"FVBCs/{_SEE_ENERGY_BC}"
    )
    checks["particle_wall_loss_retained"] = base.mb.has_block(
        child, "FVBCs/issue217_grounded_sheath_primary_particle"
    )
    checks["energy_wall_loss_retained"] = base.mb.has_block(
        child, "FVBCs/issue217_grounded_sheath_primary_energy"
    )

    # This CI observes the resulting energy/particle evolution but does not
    # require the net boundary flux ratio to remain exactly 5/3.
    checks["no_five_thirds_hard_gate"] = True
    result["remaining_volumetric_electron_kernels"] = remaining
    return _finalize(result)


base.build_child_input = _build_child_input
base._audit_child = _audit_child
base.self_test = _self_test

if __name__ == "__main__":
    raise SystemExit(base.main())
