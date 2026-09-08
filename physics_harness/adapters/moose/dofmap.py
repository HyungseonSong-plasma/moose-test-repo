"""Reusable MOOSE DOFMap JSON parsing and ownership reconstruction."""
from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any


class DofMapError(ValueError):
    """Raised when a DOFMap artifact cannot establish unique ownership."""


def parse_dof_map_text(
    text: str,
    *,
    expected_variables: Iterable[str],
    scalar_variables: Iterable[str] = (),
) -> dict[str, Any]:
    """Parse a MOOSE DOFMap JSON artifact into variable/DOF ownership facts.

    ``expected_variables`` and ``scalar_variables`` are caller-supplied semantics.
    A single empty scalar may claim the single otherwise-unmapped nonlinear DOF,
    matching the common MOOSE scalar-variable artifact representation.
    """
    expected = tuple(expected_variables)
    scalars = tuple(scalar_variables)
    if not expected:
        raise DofMapError("expected_variables must not be empty")
    if len(set(expected)) != len(expected):
        raise DofMapError("expected_variables contains duplicates")
    unknown_scalars = [name for name in scalars if name not in expected]
    if unknown_scalars:
        raise DofMapError(f"scalar_variables not present in expected_variables: {unknown_scalars}")

    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise DofMapError(f"invalid DOFMap JSON: {exc}") from exc

    ndof = payload.get("ndof")
    vars_payload = payload.get("vars")
    if not isinstance(ndof, int) or ndof <= 0 or not isinstance(vars_payload, list):
        raise DofMapError("DOFMap JSON lacks positive ndof or vars list")

    by_name: dict[str, set[int]] = {name: set() for name in expected}
    seen_names: set[str] = set()
    for item in vars_payload:
        if not isinstance(item, dict) or not isinstance(item.get("name"), str):
            continue
        name = item["name"]
        if name not in by_name:
            continue
        seen_names.add(name)
        subdomains = item.get("subdomains", [])
        if not isinstance(subdomains, list):
            continue
        for subdomain in subdomains:
            if not isinstance(subdomain, dict):
                continue
            dofs = subdomain.get("dofs", [])
            if not isinstance(dofs, list):
                continue
            for dof in dofs:
                if isinstance(dof, int) and not isinstance(dof, bool):
                    by_name[name].add(dof)

    missing_names = [name for name in expected if name not in seen_names]
    if missing_names:
        raise DofMapError(f"DOFMap missing variables: {missing_names}")

    for name, dofs in by_name.items():
        invalid = sorted(dof for dof in dofs if dof < 0 or dof >= ndof)
        if invalid:
            raise DofMapError(f"DOFMap variable {name} has invalid DOFs: {invalid[:8]}")

    owner: dict[int, str] = {}
    overlaps: list[tuple[int, str, str]] = []
    for name, dofs in by_name.items():
        for dof in dofs:
            prior = owner.get(dof)
            if prior is not None and prior != name:
                overlaps.append((dof, prior, name))
            owner[dof] = name
    if overlaps:
        raise DofMapError(f"DOFMap variable overlap: {overlaps[:8]}")

    unmapped = sorted(set(range(ndof)) - set(owner))
    empty_scalars = [name for name in scalars if not by_name.get(name)]
    if empty_scalars:
        if len(empty_scalars) == 1 and len(unmapped) == 1:
            scalar = empty_scalars[0]
            dof = unmapped[0]
            by_name[scalar].add(dof)
            owner[dof] = scalar
            unmapped = []
        else:
            raise DofMapError(
                f"cannot resolve scalar DOFs: scalars={empty_scalars}, unmapped={unmapped[:8]}"
            )
    if unmapped:
        raise DofMapError(f"DOFMap has unmapped nonlinear DOFs: {unmapped[:8]}")

    return {
        "ndof": ndof,
        "variables": {name: sorted(dofs) for name, dofs in by_name.items()},
        "owner_by_dof": owner,
    }
