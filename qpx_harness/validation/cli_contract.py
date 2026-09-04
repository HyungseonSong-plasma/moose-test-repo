"""QPX-free regression contract for the stable CLI command surface."""
from __future__ import annotations

EXPECTED_LEGACY_COMMANDS = frozenset({
    "test", "test-all", "scale-audit", "inventory-nullspace",
    "inventory-first-linear", "contract", "dmix-equivalence", "measure",
    "measure-smoke", "investigate", "transport-probe", "cache-audit",
    "profile", "analyze", "inventory", "preflight", "temporal-csv",
})
EXPECTED_INTERNAL_TARGETS = frozenset({"architecture", "regression", "all"})


def validate_command_surface(
    commands: dict[str, str],
    internal_targets: dict[str, str],
) -> list[str]:
    errors: list[str] = []
    actual_commands = set(commands)
    missing = sorted(EXPECTED_LEGACY_COMMANDS - actual_commands)
    extra = sorted(actual_commands - EXPECTED_LEGACY_COMMANDS)
    if missing:
        errors.append("missing legacy commands: " + ", ".join(missing))
    if extra:
        errors.append("uncharacterized legacy commands: " + ", ".join(extra))

    actual_internal = set(internal_targets)
    missing_internal = sorted(EXPECTED_INTERNAL_TARGETS - actual_internal)
    extra_internal = sorted(actual_internal - EXPECTED_INTERNAL_TARGETS)
    if missing_internal:
        errors.append("missing internal targets: " + ", ".join(missing_internal))
    if extra_internal:
        errors.append("uncharacterized internal targets: " + ", ".join(extra_internal))
    return errors


__all__ = [
    "EXPECTED_INTERNAL_TARGETS",
    "EXPECTED_LEGACY_COMMANDS",
    "validate_command_surface",
]
