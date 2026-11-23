"""Fail-closed semantic absence of electron-particle source kernels (#817).

A standard FVCoupledForce on electron *energy* is legitimate for EI18/EI19.
The same object on electron particle variable n_e must be rejected.
"""
from __future__ import annotations
from physics_harness.adapters.moose.input import MooseInput
from physics_harness.adapters.moose import parameters as mp

ELECTRON_PARTICLE_SOURCE_TYPES = frozenset((
    "FVCoupledForce", "PhysicsFVElectronReactionSource",
))


def assert_no_electron_particle_source(text: str, *, channel: str) -> dict:
    checked = 0
    for span in MooseInput(text).blocks:
        if not span.path.startswith("FVKernels/") or span.path.count("/") != 1:
            continue
        typ = mp.get_parameter(text, span.path, "type")
        variable = mp.get_parameter(text, span.path, "variable")
        checked += 1
        if variable == "n_e" and (
            typ in ELECTRON_PARTICLE_SOURCE_TYPES or "source" in span.path.lower()
        ):
            raise AssertionError(
                f"{channel} must not create an electron-particle source: {span.path} ({typ})"
            )
    if checked == 0:
        raise AssertionError(f"{channel} kernel inventory was not inspected")
    return {"channel": channel, "checked_fvkernels": checked,
            "electron_particle_source_absent": True}
