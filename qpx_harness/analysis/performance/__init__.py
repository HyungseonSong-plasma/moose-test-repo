"""Performance-analysis package preserving the legacy analyzer surface."""

from . import legacy as _legacy
from .legacy import analyze, event_time, load_petsc_events, perfgraph_jacobian_self

__all__ = [
    "analyze",
    "event_time",
    "load_petsc_events",
    "perfgraph_jacobian_self",
]


def __getattr__(name: str):
    """Forward the former module's incidental/private attribute surface."""

    return getattr(_legacy, name)


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(dir(_legacy)))
