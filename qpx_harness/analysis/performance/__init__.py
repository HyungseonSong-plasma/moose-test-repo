"""Performance-analysis package preserving the legacy analyzer surface."""

from .legacy import analyze, event_time, load_petsc_events, perfgraph_jacobian_self

__all__ = [
    "analyze",
    "event_time",
    "load_petsc_events",
    "perfgraph_jacobian_self",
]
