#!/usr/bin/env python3
"""Architecture and behavior guard for the canonical execution-contract capability."""

from __future__ import annotations

import ast
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from physics_harness.execution import contract as canonical  # noqa: E402


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _legacy_imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    hits: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "physics_harness.execution_contract":
                    hits.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module == "physics_harness.execution_contract":
                hits.append(node.module)
            elif node.module == "physics_harness":
                for alias in node.names:
                    if alias.name == "execution_contract":
                        hits.append("physics_harness.execution_contract")
    return hits


def main() -> int:
    _require(canonical.self_test() == 0, "canonical execution-contract self-test failed")
    _require(
        canonical.SCHEMA_VERSION == 1,
        "schema version changed during behavior-preserving refactor",
    )
    _require(
        canonical.OPS == set(canonical.OPERATORS),
        "operator registry and declared operator set diverged",
    )

    facade_path = ROOT / "physics_harness/execution_contract.py"
    _require(
        not facade_path.exists(),
        "retired execution_contract compatibility facade still exists",
    )

    recipe_source = (ROOT / "experiments/historical_recipe_support/issue43_execution_contract.py").read_text()
    _require(
        "from physics_harness.execution import contract as ec" in recipe_source,
        "Issue43 execution policy is not attached to the canonical capability",
    )
    _require(
        "from physics_harness import execution_contract as ec" not in recipe_source,
        "Issue43 execution policy still depends on the retired facade",
    )

    cli_source = (ROOT / "physics_harness/cli/app.py").read_text()
    _require(
        '"contract": "physics_harness.execution.contract:main"' in cli_source,
        "CLI contract command is not lazily attached to the canonical execution capability",
    )
    _require(
        "physics_harness.execution_contract" not in cli_source,
        "CLI still imports the retired execution_contract facade",
    )

    stale: dict[str, list[str]] = {}
    for base in (ROOT / "physics_harness", ROOT / "experiments/historical_recipe_support"):
        for path in base.rglob("*.py"):
            hits = _legacy_imports(path)
            if hits:
                stale[str(path.relative_to(ROOT))] = hits
    _require(stale == {}, f"retired execution_contract imports remain: {stale}")

    canonical_source = (ROOT / "physics_harness/execution/contract.py").read_text()
    for forbidden in ("from recipes", "import recipes", "physics_harness.issue"):
        _require(
            forbidden not in canonical_source,
            f"generic execution contract acquired experiment dependency: {forbidden}",
        )

    print("EXECUTION_CONTRACT_REFACTOR_GUARD: PASS")
    print("EXECUTION_CONTRACT_FACADE_RETIRED: PASS")
    print("SCIENTIFIC_EVR_CONSUMED: 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
