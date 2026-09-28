#!/usr/bin/env python3
"""Consumer compatibility proof for centralized scientific semantics."""
from __future__ import annotations

import argparse
from dataclasses import asdict, fields
import json
from pathlib import Path
import subprocess
import sys
from typing import Any

EXPECTED_CENTRAL_REPOSITORY = "HyungseonSong-plasma/chatgpt-operation"


def _head(root: Path) -> str:
    return subprocess.check_output(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        text=True,
    ).strip()


def _field_signature(cls: type[Any]) -> tuple[tuple[str, str], ...]:
    return tuple((item.name, str(item.type)) for item in fields(cls))


def _assert_equal(name: str, left: Any, right: Any) -> None:
    if left != right:
        raise RuntimeError(f"{name} mismatch: local={left!r} central={right!r}")


def _load_central(root: Path):
    source = root / "src"
    if not source.is_dir():
        raise RuntimeError(f"central src directory missing: {source}")
    sys.path.insert(0, str(source))
    from chatgpt_operation.science import (  # type: ignore
        DevelopmentState,
        ExperimentIntent,
        RunEnvelope,
        compile_execution_plan,
        default_capabilities,
        synthesize_policy,
    )
    from chatgpt_operation.science.contract import self_test as contract_self_test  # type: ignore
    from chatgpt_operation.science.errors import (  # type: ignore
        AttributionSignals,
        classify_attribution,
    )
    return {
        "DevelopmentState": DevelopmentState,
        "ExperimentIntent": ExperimentIntent,
        "RunEnvelope": RunEnvelope,
        "compile_execution_plan": compile_execution_plan,
        "default_capabilities": default_capabilities,
        "synthesize_policy": synthesize_policy,
        "contract_self_test": contract_self_test,
        "AttributionSignals": AttributionSignals,
        "classify_attribution": classify_attribution,
    }


def validate(central_root: Path, central_revision: str) -> dict[str, Any]:
    central_root = central_root.resolve()
    actual = _head(central_root)
    if actual != central_revision:
        raise RuntimeError(
            f"central revision mismatch: expected {central_revision}, got {actual}"
        )

    central = _load_central(central_root)

    from physics_harness.evidence.error_ledger import (
        AttributionSignals as LocalAttributionSignals,
        classify_attribution as local_classify_attribution,
    )
    from physics_harness.execution.compiler import (
        compile_execution_plan as local_compile_execution_plan,
    )
    from physics_harness.execution.contract import self_test as local_contract_self_test
    from physics_harness.ontology.records import (
        DevelopmentState as LocalDevelopmentState,
        ExperimentIntent as LocalExperimentIntent,
    )
    from physics_harness.planning.policy import (
        default_capabilities as local_default_capabilities,
    )
    from physics_harness.planning.synthesizer import (
        synthesize_policy as local_synthesize_policy,
    )
    from physics_harness.provenance.envelope import RunEnvelope as LocalRunEnvelope

    for name, local_cls, central_cls in (
        (
            "DevelopmentState fields",
            LocalDevelopmentState,
            central["DevelopmentState"],
        ),
        (
            "ExperimentIntent fields",
            LocalExperimentIntent,
            central["ExperimentIntent"],
        ),
        (
            "RunEnvelope fields",
            LocalRunEnvelope,
            central["RunEnvelope"],
        ),
    ):
        _assert_equal(
            name,
            _field_signature(local_cls),
            _field_signature(central_cls),
        )

    local_capabilities = tuple(
        asdict(item) for item in local_default_capabilities()
    )
    central_capabilities = tuple(
        asdict(item) for item in central["default_capabilities"]()
    )
    _assert_equal(
        "default capability catalog",
        local_capabilities,
        central_capabilities,
    )

    common_state = {
        "state_id": "state:compatibility",
        "case_id": "case:compatibility",
        "system": (("signed_heavy_charge_number_density_m3", 2.5e16),),
        "repository": (("repository", "moose-test-repo"),),
        "provenance_id": "prov:compatibility",
    }
    common_intent = {
        "intent_id": "intent:compatibility",
        "experiment_id": "compatibility",
        "objective": "prove central/local semantic equivalence",
        "model_ref": "model:compatibility",
        "target_ids": ("gummel-convergence",),
        "requested_capabilities": (
            "electron_energy_diffusion",
            "quasi_neutral_initialization",
            "observability_instrumentation",
        ),
        "parameters": (("diffusivity", 0.25),),
        "constraint_ids": ("freeze-heavy-state",),
        "requested_observations": ("residual", "electron_density"),
        "execution_bounds": (("max_cases", 4),),
        "provenance_id": "prov:compatibility",
    }

    local_policy = local_synthesize_policy(
        LocalDevelopmentState(**common_state),
        LocalExperimentIntent(**common_intent),
        local_default_capabilities(),
    )
    central_policy = central["synthesize_policy"](
        central["DevelopmentState"](**common_state),
        central["ExperimentIntent"](**common_intent),
        central["default_capabilities"](),
    )
    _assert_equal(
        "ScientificPolicy synthesis",
        asdict(local_policy),
        asdict(central_policy),
    )

    local_plan = local_compile_execution_plan(local_policy)
    central_plan = central["compile_execution_plan"](central_policy)
    _assert_equal(
        "ExecutionPlan compilation",
        asdict(local_plan),
        asdict(central_plan),
    )

    if local_contract_self_test() != 0:
        raise RuntimeError("local scientific execution contract self-test failed")
    if central["contract_self_test"]() != 0:
        raise RuntimeError("central scientific execution contract self-test failed")

    local_attribution = local_classify_attribution(
        LocalAttributionSignals(
            contract_conformant=True,
            reproducible_runtime_failure=True,
            isolated_code_owner="solver",
        )
    )
    central_attribution = central["classify_attribution"](
        central["AttributionSignals"](
            contract_conformant=True,
            reproducible_runtime_failure=True,
            isolated_code_owner="solver",
        )
    )
    _assert_equal(
        "runtime error attribution",
        asdict(local_attribution),
        asdict(central_attribution),
    )

    envelope_payload = {
        "run_id": "run:compatibility",
        "experiment_id": "exp:compatibility",
        "protocol": "centralization-proof",
        "source_revision": "a" * 40,
    }
    _assert_equal(
        "RunEnvelope representation",
        asdict(LocalRunEnvelope(**envelope_payload)),
        asdict(central["RunEnvelope"](**envelope_payload)),
    )

    return {
        "schema_version": 1,
        "status": "PASS",
        "consumer_repository": "HyungseonSong-plasma/moose-test-repo",
        "central_repository": EXPECTED_CENTRAL_REPOSITORY,
        "central_revision": central_revision,
        "components": {
            "scientific-semantic-ir": "compatible",
            "scientific-policy-synthesis": "compatible",
            "scientific-execution-plan": "compatible",
            "scientific-execution-contract": "compatible",
            "scientific-run-provenance": "compatible",
            "scientific-error-attribution": "compatible",
        },
        "retirement_authorized": False,
        "reason": (
            "compatibility proof does not establish consumer import cutover or "
            "zero remaining local imports"
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--central-root", required=True)
    parser.add_argument("--central-revision", required=True)
    parser.add_argument("--json-out")
    args = parser.parse_args()

    revision = str(args.central_revision).strip().lower()
    if len(revision) != 40 or any(
        char not in "0123456789abcdef" for char in revision
    ):
        raise SystemExit("central revision must be lowercase 40-hex")

    result = validate(Path(args.central_root), revision)
    if args.json_out:
        Path(args.json_out).write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    print("SCIENTIFIC_CENTRALIZATION_COMPATIBILITY=PASS")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
