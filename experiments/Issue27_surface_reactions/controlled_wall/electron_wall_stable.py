"""Stable A7 wrapper for the COMSOL-style electron thermal wall discriminator.

The accepted R4-QF1 predecessor uses a 1e-8 s one-step transient.  With the
COMSOL random thermal electron wall loss enabled, that step is too large for the
current reactor mesh and can drive the nonlinear iterate to negative electron
density before the transport material can evaluate.  This wrapper changes only
the bounded A7 discriminator timestep to 1e-10 s; the electron-wall flux law,
A6 heavy-wall physics, Poisson coupling, SEE=0, and wall ownership are unchanged.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from experiments.Issue27_surface_reactions.controlled_wall import electron_wall as base
from physics_harness.adapters.moose import parameters as mp

A7_DISCRIMINATOR_DT_S = 1.0e-10
_ORIGINAL_BUILD = base._build_a7_case_input


def _build_a7_case_input(
    base_text: str,
    *,
    parameters: Mapping[str, Any],
    mode: str,
) -> tuple[str, dict[str, Any]]:
    text, meta = _ORIGINAL_BUILD(
        base_text,
        parameters=parameters,
        mode=mode,
    )
    previous_dt = mp.get_parameter(text, "Executioner", "dt")
    previous_end_time = mp.get_parameter(text, "Executioner", "end_time")
    text = mp.upsert_parameter(
        text,
        "Executioner",
        "dt",
        f"{A7_DISCRIMINATOR_DT_S:.17g}",
    )
    text = mp.upsert_parameter(
        text,
        "Executioner",
        "end_time",
        f"{A7_DISCRIMINATOR_DT_S:.17g}",
    )
    return text, {
        **meta,
        "a7_discriminator_timestep_s": A7_DISCRIMINATOR_DT_S,
        "a7_predecessor_timestep": previous_dt,
        "a7_predecessor_end_time": previous_end_time,
        "a7_timestep_scope": (
            "numerical stabilization of the one-step electron-wall discriminator only; "
            "COMSOL thermal wall-flux physics unchanged"
        ),
    }


def run_comsol_electron_thermal_wall_control(
    *,
    qpx: str | Path | None,
    results_root: Path,
    timeout: float,
    parameters: Mapping[str, Any],
) -> int:
    previous = base._build_a7_case_input
    base._build_a7_case_input = _build_a7_case_input
    try:
        return int(
            base.run_comsol_electron_thermal_wall_control(
                qpx=qpx,
                results_root=results_root,
                timeout=timeout,
                parameters=parameters,
            )
        )
    finally:
        base._build_a7_case_input = previous


__all__ = [
    "A7_DISCRIMINATOR_DT_S",
    "_build_a7_case_input",
    "run_comsol_electron_thermal_wall_control",
]
