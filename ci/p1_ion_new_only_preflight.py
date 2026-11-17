#!/usr/bin/env python3
"""P1 ion FV input-only owner preflight (no MOOSE build, no simulation).

Read S6 staged 11 .i layers and unified JSON. The explicitly selected
Continuity fem_species/fvm_species decide FE/FV generation; no owner-mode flag.
Reject conflicting legacy explicit FV equation/BC blocks in a new-only scratch.
A clean P0 input is NOT proof that Physics generated FV kernels at runtime.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
import zipfile
from pathlib import Path

BLOCK_RE = re.compile(r"^\s*\[([^\]]*)\]\s*$")
ASSIGN_RE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$")


def scan_layer(text: str):
    stack = []
    found = []
    lines = text.splitlines()
    for n, line in enumerate(lines, 1):
        match = BLOCK_RE.fullmatch(line)
        if match:
            if match[1]:
                stack.append({"name": match[1], "line": n, "params": {}})
            elif stack:
                blk = stack.pop()
                if stack:
                    # Keep a copy of the fully qualified hierarchy from which the
                    # object was closed, rather than guessing based on its name.
                    blk["parent"] = "/".join(x["name"] for x in stack)
                else:
                    blk["parent"] = ""
                found.append(blk)
            continue
        assign = ASSIGN_RE.fullmatch(line)
        if assign and stack:
            stack[-1]["params"][assign[1]] = assign[2].strip("'\"")
    if stack:
        raise ValueError("P1_UNBALANCED_I_BLOCKS")
    return found


def inspect(layers: dict[str, str], mechanism: dict) -> dict:
    errors = []
    blocks = []
    for name, text in layers.items():
        for block in scan_layer(text):
            blocks.append({**block, "file": name})
    cs = [b for b in blocks if b["name"] == "Continuity" and
          b["parent"].endswith("/DriftDiffusion")]
    if len(cs) != 1:
        errors.append(f"P1_CONTINUITY_COUNT_{len(cs)}")
        return {"status": "FAIL", "errors": errors, "continuity_count": len(cs)}
    params = cs[0]["params"]
    if "fvm_kernel_ownership" in params:
        errors.append("P1_MANUAL_OWNER_FLAG_FORBIDDEN")
    fem, fvm = params.get("fem_species", "").split(), params.get("fvm_species", "").split()
    if not (fem or fvm) or len(set(fem + fvm)) != len(fem) + len(fvm):
        errors.append("P1_SPECIES_DUPLICATE_OR_EMPTY")
    species = mechanism.get("species", {})
    if not isinstance(species, dict):
        errors.append("P1_JSON_SPECIES_INVALID")
        species = {}
    for ident in fem + fvm:
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", ident):
            errors.append("P1_SPECIES_INVALID_IDENTIFIER:" + ident)
        record = species.get(ident)
        if not isinstance(record, dict):
            errors.append("P1_JSON_SELECTED_SPECIES_MISSING:" + ident)
        else:
            density = record.get("initial_number_density")
            if isinstance(density, bool) or not isinstance(density, (float, int)) or not math.isfinite(density) or density <= 0:
                errors.append("P1_JSON_INITIAL_NUMBER_DENSITY_INVALID:" + ident)
    selected_variables = {"log_" + ident for ident in fvm}
    native = []
    for b in blocks:
        if b["parent"] in ("FVKernels", "FVBCs") and b["params"].get("variable") in selected_variables:
            native.append({"file": b["file"], "line": b["line"], "section": b["parent"],
                           "name": b["name"], "type": b["params"].get("type"),
                           "variable": b["params"].get("variable")})
    if native:
        errors.append(f"P1_NATIVE_FV_ION_OWNER_PRESENT_{len(native)}")
    return {"status": "FAIL" if errors else "P0_STATIC_PASS_ONLY", "errors": errors,
            "fem_species": fem, "fvm_species": fvm, "native_fv_owner_count": len(native),
            "native_fv_owners": native,
            "runtime_generated_kernel_bc_count": "NOT_VERIFIED_P0_ONLY"}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--zip", type=Path, required=True)
    parser.add_argument("--case", choices=("417", "941"), required=True)
    parser.add_argument("--json", type=Path, required=True)
    args = parser.parse_args(argv)
    prefix = f"S6_{args.case}/11_layers/"
    with zipfile.ZipFile(args.zip) as z:
        layers = {n.rsplit("/", 1)[-1]: z.read(n).decode("utf-8") for n in z.namelist()
                  if n.startswith(prefix) and n.endswith(".i")}
    if len(layers) != 11:
        parser.error(f"expected exactly 11 staged layers, got {len(layers)}")
    result = inspect(layers, json.loads(args.json.read_text()))
    print(json.dumps(result, sort_keys=True, ensure_ascii=False))
    return 0 if result["status"] == "P0_STATIC_PASS_ONLY" else 1


if __name__ == "__main__":
    sys.exit(main())
