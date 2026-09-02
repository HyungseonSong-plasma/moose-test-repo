#!/usr/bin/env python3
"""Architecture and behavior guard for the canonical execution-contract capability."""

from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from qpx_harness import execution_contract as facade  # noqa: E402
from qpx_harness.execution import contract as canonical  # noqa: E402


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    _require(canonical.self_test() == 0, "canonical execution-contract self-test failed")

    _require(
        facade.validate_contract is canonical.validate_contract,
        "compatibility facade owns a second validate_contract implementation",
    )
    _require(
        facade.evaluate_contract is canonical.evaluate_contract,
        "compatibility facade owns a second evaluate_contract implementation",
    )
    _require(
        facade.self_test is canonical.self_test,
        "compatibility facade does not delegate self-test to canonical owner",
    )
    _require(
        facade.SCHEMA_VERSION == canonical.SCHEMA_VERSION == 1,
        "schema version changed during behavior-preserving refactor",
    )
    _require(
        facade.OPS == canonical.OPS == set(canonical.OPERATORS),
        "operator registry and declared operator set diverged",
    )

    recipe_source = (ROOT / "recipes/issue43_execution_contract.py").read_text()
    _require(
        "from qpx_harness.execution import contract as ec" in recipe_source,
        "Issue43 execution policy is not attached to the canonical capability",
    )
    _require(
        "from qpx_harness import execution_contract as ec" not in recipe_source,
        "Issue43 execution policy still depends on the compatibility facade",
    )

    canonical_source = (ROOT / "qpx_harness/execution/contract.py").read_text()
    for forbidden in ("from recipes", "import recipes", "qpx_harness.issue"):
        _require(
            forbidden not in canonical_source,
            f"generic execution contract acquired experiment dependency: {forbidden}",
        )

    facade_source = (ROOT / "qpx_harness/execution_contract.py").read_text()
    _require(
        "qpx_harness.execution.contract" in facade_source,
        "historical execution_contract path is not a canonical compatibility facade",
    )
    _require(
        "def validate_contract" not in facade_source
        and "def evaluate_contract" not in facade_source,
        "compatibility facade contains duplicate evaluator ownership",
    )

    print("EXECUTION_CONTRACT_REFACTOR_GUARD: PASS")
    print("SCIENTIFIC_EVR_CONSUMED: 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
