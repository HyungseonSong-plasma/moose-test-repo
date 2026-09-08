"""Issue-agnostic PETSc assembled-vs-finite-difference Jacobian parsing."""
from __future__ import annotations

import re

FLOAT_PATTERN = r"[+\-]?(?:(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+\-]?\d+)?|nan|inf(?:inity)?)"


def parse_comparisons(text: str) -> list[dict[str, float]]:
    """Parse PETSc ``-snes_test_jacobian`` Frobenius-error summaries."""
    pattern = re.compile(
        rf"\|\|J\s*-\s*Jfd\|\|_F/\|\|J\|\|_F\s*=\s*({FLOAT_PATTERN})"
        rf"\s*,\s*\|\|J\s*-\s*Jfd\|\|_F\s*=\s*({FLOAT_PATTERN})",
        re.IGNORECASE,
    )
    results: list[dict[str, float]] = []
    for match in pattern.finditer(text):
        try:
            relative = float(match.group(1))
            absolute = float(match.group(2))
        except ValueError:
            continue
        results.append(
            {
                "relative_frobenius_error": relative,
                "absolute_frobenius_error": absolute,
            }
        )
    return results
