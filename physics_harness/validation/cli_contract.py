"""QPX-free regression contract for the stable CLI command surface."""
from __future__ import annotations

EXPECTED_CANONICAL_COMMANDS = frozenset({
    "compile", "plan", "lower", "run", "preflight", "temporal-csv",
})
EXPECTED_LEGACY_COMMANDS = frozenset({
    "test", "test-all", "contract", "measure", "analyze", "inventory",
})
EXPECTED_INTERNAL_TARGETS = frozenset({"architecture", "regression", "all"})


def validate_command_surface(
    commands: dict[str, str],
    internal_targets: dict[str, str],
    canonical_commands: dict[str, str] | None = None,
) -> list[str]:
    """Validate the separated canonical, compatibility, and internal surfaces.

    ``commands`` is the bounded compatibility command table. Campaign-specific
    commands are intentionally absent; historical experiments must not define
    the reusable CLI surface. Performance profiling is represented by
    ``measure`` with a PROFILE manifest rather than a second ``profile`` entry.
    """
    errors: list[str] = []

    actual_commands = set(commands)
    missing = sorted(EXPECTED_LEGACY_COMMANDS - actual_commands)
    extra = sorted(actual_commands - EXPECTED_LEGACY_COMMANDS)
    if missing:
        errors.append("missing legacy commands: " + ", ".join(missing))
    if extra:
        errors.append("uncharacterized legacy commands: " + ", ".join(extra))

    if canonical_commands is not None:
        actual_canonical = set(canonical_commands)
        missing_canonical = sorted(EXPECTED_CANONICAL_COMMANDS - actual_canonical)
        extra_canonical = sorted(actual_canonical - EXPECTED_CANONICAL_COMMANDS)
        if missing_canonical:
            errors.append("missing canonical commands: " + ", ".join(missing_canonical))
        if extra_canonical:
            errors.append("uncharacterized canonical commands: " + ", ".join(extra_canonical))

    actual_internal = set(internal_targets)
    missing_internal = sorted(EXPECTED_INTERNAL_TARGETS - actual_internal)
    extra_internal = sorted(actual_internal - EXPECTED_INTERNAL_TARGETS)
    if missing_internal:
        errors.append("missing internal targets: " + ", ".join(missing_internal))
    if extra_internal:
        errors.append("uncharacterized internal targets: " + ", ".join(extra_internal))
    return errors


__all__ = [
    "EXPECTED_CANONICAL_COMMANDS",
    "EXPECTED_INTERNAL_TARGETS",
    "EXPECTED_LEGACY_COMMANDS",
    "validate_command_surface",
]
