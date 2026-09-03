"""Protocol registry for declarative experiments.

The CLI knows only experiment specification paths. Protocol identifiers resolve
here so experiment-specific imports do not leak into the CLI surface.
"""
from __future__ import annotations

from collections.abc import Callable
from importlib import import_module

from .experiment_spec import ExperimentSpec

ExperimentRunner = Callable[[ExperimentSpec], int]

_PROTOCOLS: dict[str, str] = {
    "r3-electron-master-diagnostic": "qpx_harness.application.protocols.r3_electron_master_diagnostic:run_protocol",
    "r3-electron-scaling-counterfactual": "qpx_harness.application.protocols.r3_electron_scaling_counterfactual:run_protocol",
    "r3-fv-internal-completion": "qpx_harness.application.protocols.r3_fv_internal_completion:run_protocol",
    "r4-qf2-local-charge-relaxation": "qpx_harness.application.protocols.r4_qf2_local_charge_relaxation:run_protocol",
}


def registered_protocols() -> tuple[str, ...]:
    return tuple(sorted(_PROTOCOLS))


def protocol_registered(protocol: str) -> bool:
    return protocol in _PROTOCOLS


def resolve_protocol(protocol: str) -> ExperimentRunner:
    target = _PROTOCOLS.get(protocol)
    if target is None:
        known = ", ".join(registered_protocols()) or "<none>"
        raise ValueError(f"unregistered experiment protocol {protocol!r}; registered: {known}")
    module_name, function_name = target.split(":", 1)
    module = import_module(module_name)
    runner = getattr(module, function_name)
    if not callable(runner):
        raise TypeError(f"experiment protocol target is not callable: {target}")
    return runner


__all__ = ["ExperimentRunner", "protocol_registered", "registered_protocols", "resolve_protocol"]
