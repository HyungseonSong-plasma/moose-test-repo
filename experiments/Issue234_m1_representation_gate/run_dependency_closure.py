#!/usr/bin/env python3
"""Issue #234 bounded repair for child functor dependency closure.

The M1 split deliberately removes heavy transient FunctorMaterials from the fast
child. The production input also carries diagnostic postprocessors that consume
functors produced only by those removed materials. This wrapper keeps the
Issue-234 repair local: prune those known diagnostics, add a construction audit,
and add a mutation self-test. The generic MOOSE preflight remains conservative
and separate in PR #249 because ``functor`` can resolve through multiple MOOSE
provider namespaces.
"""
from __future__ import annotations

from typing import Any

from experiments.Issue234_m1_representation_gate import run as base


PRUNED_HEAVY_TRANSIENT_FUNCTORS = frozenset(
    {
        "drho_dt_model",
        "dMn_dt_model",
    }
)

_ORIGINAL_BUILD_CHILD_INPUT = base.build_child_input
_ORIGINAL_AUDIT_CHILD = base._audit_child
_ORIGINAL_SELF_TEST = base.self_test


def _heavy_transient_postprocessor_paths(text: str) -> list[str]:
    """Return diagnostics that consume functors pruned from the M1 fast child."""
    result: list[str] = []
    for path in base._children(text, "Postprocessors"):
        functor = base.mp.unquote(base.mp.get_parameter(text, path, "functor"))
        if functor in PRUNED_HEAVY_TRANSIENT_FUNCTORS:
            result.append(path)
    return result


def _remove_heavy_transient_postprocessors(text: str) -> str:
    """Remove known consumers whenever their heavy transient providers are absent."""
    for path in list(_heavy_transient_postprocessor_paths(text)):
        text = base.mb.remove_block(text, path)
    return text


def _build_child_input(production_text: str, *, dt_e: float) -> str:
    text = _ORIGINAL_BUILD_CHILD_INPUT(production_text, dt_e=dt_e)
    return _remove_heavy_transient_postprocessors(text)


def _audit_child(text: str, *, dt_e: float) -> dict[str, Any]:
    audit = _ORIGINAL_AUDIT_CHILD(text, dt_e=dt_e)
    checks = dict(audit["checks"])
    lingering = _heavy_transient_postprocessor_paths(text)
    checks["heavy_transient_functor_consumers_absent"] = not lingering
    failed = sorted(key for key, ok in checks.items() if not ok)
    audit.update(
        {
            "status": "PASS" if not failed else "FAIL",
            "checks": checks,
            "failed_checks": failed,
            "heavy_transient_functor_consumers": lingering,
        }
    )
    return audit


def _self_test() -> dict[str, Any]:
    result = _ORIGINAL_SELF_TEST()
    checks = dict(result.get("checks", {}))
    detail = dict(result.get("detail", {}))

    if result.get("status") == "PASS":
        _, child, _ = base.build_split(dt_e=base.DT_E_CONSTRUCTION_S)
        mutated_child = base._ensure_top_block(child, "Postprocessors")
        mutated_child = base.mb.insert_child_block(
            mutated_child,
            "Postprocessors",
            """  [m1_bad_heavy_transient_diagnostic]
    type = ElementAverageFunctorPostprocessor
    functor = dMn_dt_model
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []""",
        )
        mutation_audit = _audit_child(
            mutated_child, dt_e=base.DT_E_CONSTRUCTION_S
        )
        checks["reject_heavy_transient_functor_consumer_after_provider_prune"] = (
            mutation_audit["status"] == "FAIL"
            and "heavy_transient_functor_consumers_absent"
            in mutation_audit["failed_checks"]
        )
        detail["heavy_transient_mutation_failed_checks"] = mutation_audit[
            "failed_checks"
        ]
    else:
        checks["reject_heavy_transient_functor_consumer_after_provider_prune"] = False
        detail["heavy_transient_mutation_failed_checks"] = [
            "base_self_test_failed_before_dependency_mutation"
        ]

    failed = sorted(key for key, ok in checks.items() if not ok)
    result.update(
        {
            "status": "PASS" if not failed else "FAIL",
            "checks": checks,
            "failed_checks": failed,
            "detail": detail,
        }
    )
    return result


# Install the bounded Issue-234 repair into the existing construction driver.
# Functions in base.build_split/base.run resolve these module globals at runtime,
# so the normal staging/runtime path and the self-test use the same repaired logic.
base.build_child_input = _build_child_input
base._audit_child = _audit_child
base.self_test = _self_test


def main() -> int:
    return base.main()


if __name__ == "__main__":
    raise SystemExit(main())
