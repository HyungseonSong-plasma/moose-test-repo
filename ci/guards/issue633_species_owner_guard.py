#!/usr/bin/env python3
"""Issue #633 P04/P05 input-only owner preflight for assembled 11-layer decks.

Checks selected species and Native collisions. This is NOT a MOOSE warehouse
inspection, a Physics generated-object count, or a P2/P3 scientific verdict.
Input must already contain the final combined HIT blocks (no unresolved include).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from physics_harness.adapters.moose.input import MooseInput, MooseInputError
from physics_harness.adapters.moose.parameters import get_parameter, words

CONTINUITY = "Physics/Plasmas/Transport/DriftDiffusion/Continuity"
NATIVE_FV_SECTIONS = ("FVKernels", "FVBCs")


class OwnerContractError(ValueError):
    """Fail-closed selection, source or competing Native ownership."""


def validate(text: str, mechanism: dict) -> dict:
    """Validate input-only selection; return expected (not observed) FV objects."""
    if re.search(r"(?m)^\s*!include\b", text):
        raise OwnerContractError("UNRESOLVED_LAYER: stage all input layers first")
    try:
        doc = MooseInput(text)
        fem = words(get_parameter(text, CONTINUITY, "fem_species"))
        fvm = words(get_parameter(text, CONTINUITY, "fvm_species"))
    except (MooseInputError, ValueError) as exc:
        raise OwnerContractError(f"INVALID_HIT: {exc}") from exc
    if not (fem or fvm):
        raise OwnerContractError("MISSING_SELECTION: fem_species/fvm_species")
    ids = fem + fvm
    if len(ids) != len(set(ids)):
        raise OwnerContractError("DUPLICATE_DISCRETIZATION: selected species repeated")
    species_data = mechanism.get("species")
    if not isinstance(species_data, dict):
        raise OwnerContractError("MISSING_JSON_SPECIES: species object required")
    for sid in ids:
        item = species_data.get(sid)
        if not isinstance(item, dict):
            raise OwnerContractError(f"UNKNOWN_JSON_SPECIES: {sid}")
        density = item.get("initial_number_density")
        if not isinstance(density, (int, float)) or isinstance(density, bool) or not (0 < density < float("inf")):
            raise OwnerContractError(f"MISSING_INITIAL_DENSITY: {sid}")
        if item.get("transport_coef") not in {"constant", "lookup", "functor"}:
            raise OwnerContractError(f"MISSING_JSON_TRANSPORT: {sid}")
        if not isinstance(item.get("charge_number"), int):
            raise OwnerContractError(f"MISSING_CHARGE: {sid}")

    # A selected FV species needs a volume reaction source to generate its
    # species-owned fourth kernel. No empty-source fallback is inferred here.
    reactions = mechanism.get("reactions", [])
    for sid in fvm:
        if not any(
            entry.get("domain", "volume") == "volume"
            and entry.get("products", {}).get(sid, 0) != entry.get("reactants", {}).get(sid, 0)
            for entry in reactions if isinstance(entry, dict)
        ):
            raise OwnerContractError(f"MISSING_SPECIES_SOURCE: {sid}")

    # Explicit Native FVKernels/FVBCs are forbidden for selected FV variables,
    # even if the object name or legacy class type has been changed.
    selected_variables = {"log_" + sid: sid for sid in fvm}
    for block in doc.blocks:
        if not any(block.path.startswith(section + "/") and block.path.count("/") == 1
                   for section in NATIVE_FV_SECTIONS):
            continue
        try:
            variable = words(get_parameter(text, block.path, "variable"))
        except (MooseInputError, ValueError) as exc:
            raise OwnerContractError(f"AMBIGUOUS_NATIVE_OBJECT: {block.path}: {exc}") from exc
        if any(name in selected_variables for name in variable):
            raise OwnerContractError(
                f"DUPLICATE_NATIVE_OWNER: {block.path} targets "
                + ", ".join(selected_variables[name] for name in variable
                            if name in selected_variables)
            )

    suffixes = ("time", "diffusion", "drift", "source")
    expected = [f"{sid}_{suffix}" for sid in fvm for suffix in suffixes]
    return {
        "fem_species": fem,
        "fvm_species": fvm,
        "expected_fv_kernel_names": expected,
        "expected_fv_kernel_count": len(expected),
        "verdict": "INPUT_ONLY_PRECHECK_PASS",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True,
                        help="fully materialized combined HIT input")
    parser.add_argument("--json", type=Path, required=True,
                        help="resolved merged chemistry JSON for this input")
    args = parser.parse_args()
    try:
        result = validate(args.input.read_text(encoding="utf-8"),
                          json.loads(args.json.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError, OwnerContractError) as exc:
        print(f"ISSUE633_OWNER_P0=FAIL: {exc}")
        return 1
    print(f"ISSUE633_OWNER_P0=PASS_EXPECTED_ONLY: {json.dumps(result, sort_keys=True)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
