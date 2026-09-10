#!/usr/bin/env python3
"""P0 acceptance guard for the historical Issue #79 CLI convergence contract."""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

HISTORICAL_SEMANTIC_IMPACT = "NONE"
HISTORICAL_WRAPPERS_BEFORE = 3
HISTORICAL_WRAPPERS_AFTER = 0
HISTORICAL_DISPOSITION = "RETIRE_AFTER_CLI_MOVE"
HISTORICAL_STABLE_COMMANDS = {
    "coupling-evr1",
    "coupling-evr2",
    "dmix-equivalence",
}
RETIRED_LEAVES = {
    "coupling_evr1_runtime",
    "coupling_evr2_runtime",
    "dmix_equivalence",
}
CURRENT_REQUIRED_COMPAT_COMMANDS = {
    "test",
    "test-all",
    "contract",
    "measure",
    "analyze",
    "inventory",
}
CURRENT_REQUIRED_CANONICAL_COMMANDS = {"compile", "plan", "lower", "run"}


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    result: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            result.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            result.add(node.module)
            result.update(f"{node.module}.{alias.name}" for alias in node.names)
    return result


def _command_names(path: Path, assignment: str) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in tree.body:
        if isinstance(node, ast.Assign):
            if any(
                isinstance(target, ast.Name) and target.id == assignment
                for target in node.targets
            ):
                value = ast.literal_eval(node.value)
                if not isinstance(value, dict):
                    raise AssertionError(f"{assignment} is not a dict")
                return set(value)
    raise AssertionError(f"missing {assignment} assignment")


def main() -> int:
    assert HISTORICAL_SEMANTIC_IMPACT == "NONE"
    assert HISTORICAL_WRAPPERS_BEFORE == 3
    assert HISTORICAL_WRAPPERS_AFTER == 0
    assert len(HISTORICAL_STABLE_COMMANDS) == HISTORICAL_WRAPPERS_BEFORE
    assert HISTORICAL_DISPOSITION == "RETIRE_AFTER_CLI_MOVE"

    production = ROOT / "physics_harness"
    for leaf in RETIRED_LEAVES:
        assert not (production / f"{leaf}.py").exists(), leaf

    violations: dict[str, list[str]] = {}
    for path in production.rglob("*.py"):
        found = sorted(
            module
            for module in _imports(path)
            if module.rsplit(".", 1)[-1] in RETIRED_LEAVES
        )
        if found:
            violations[str(path.relative_to(ROOT))] = found
    assert violations == {}, violations

    cli_path = ROOT / "physics_harness/cli/app.py"
    current_commands = _command_names(cli_path, "COMMANDS")
    canonical_commands = _command_names(cli_path, "CANONICAL_COMMANDS")
    assert CURRENT_REQUIRED_COMPAT_COMMANDS <= current_commands
    assert CURRENT_REQUIRED_CANONICAL_COMMANDS <= canonical_commands
    assert not (HISTORICAL_STABLE_COMMANDS & current_commands)
    assert not (HISTORICAL_STABLE_COMMANDS & canonical_commands)

    cli_source = cli_path.read_text(encoding="utf-8")
    for token in (
        "coupling-evr1",
        "coupling-evr2",
        "dmix-equivalence",
        "coupling_evr1_runtime",
        "coupling_evr2_runtime",
        "dmix_equivalence",
    ):
        assert token not in cli_source, token

    print("ISSUE79_HISTORICAL_CLI_ADAPTER_CONVERGENCE: PASS")
    print("ISSUE79_RETIRED_CAMPAIGN_CLI_SURFACE: ABSENT")
    print("Issue79 scientific P3: NOT_RUN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
