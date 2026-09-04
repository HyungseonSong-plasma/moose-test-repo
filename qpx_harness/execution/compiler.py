"""ScientificPolicy -> solver-independent ExecutionPlan compiler."""
from __future__ import annotations

import hashlib
import json

from qpx_harness.ontology.model import ScientificPolicy

from .plan import ExecutionCase, ExecutionPlan


class UnresolvedPolicyError(ValueError):
    pass


def compile_execution_plan(policy: ScientificPolicy) -> ExecutionPlan:
    if policy.unresolved_requirements:
        raise UnresolvedPolicyError(
            "policy is not runnable while unresolved requirements remain: "
            + ", ".join(policy.unresolved_requirements)
        )
    cases = tuple(
        ExecutionCase(
            case_id=f"case:{index}:{action.action_id}",
            action_id=action.action_id,
            parameters=action.parameters,
            required_observations=policy.required_observations,
            held_fixed=tuple(dict.fromkeys((*policy.held_fixed, *action.preserves))),
        )
        for index, action in enumerate(policy.selected_actions)
    )
    payload = {
        "policy": policy.policy_id,
        "cases": [
            {
                "id": item.case_id,
                "action": item.action_id,
                "parameters": item.parameters,
                "observations": item.required_observations,
                "held_fixed": item.held_fixed,
            }
            for item in cases
        ],
        "bounds": policy.execution_bounds,
    }
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:16]
    return ExecutionPlan(
        plan_id=f"plan:{digest}",
        source_policy_id=policy.policy_id,
        cases=cases,
        execution_bounds=policy.execution_bounds,
        required_observations=policy.required_observations,
        artifact_contracts=("run_log", "observation_artifacts"),
        target_capabilities=policy.required_capabilities,
        provenance_id=policy.provenance_id,
    )


__all__ = ["UnresolvedPolicyError", "compile_execution_plan"]
