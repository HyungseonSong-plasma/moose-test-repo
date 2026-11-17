#!/usr/bin/env python3
"""P1 ion FV input-only owner preflight (no MOOSE build, no simulation).

Read S6 staged 11 .i layers and unified JSON. The explicitly selected
Continuity fem_species/fvm_species decide FE/FV generation; no owner-mode flag.
Use distinct NEW-ONLY and archived LEGACY-HYBRID validation contracts.
Neither contract activates a Physics ownership mode: fvm_species selects FV.
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

UNRESOLVED_INCLUDE_RE = re.compile(r"(?m)^\s*!include\b")
LEGACY_S6_VARIABLES = {"O2p": "log_ni", "Om": "log_nm", "Op": "log_nop"}
LEGACY_S6_KERNEL_COUNTS = {"O2p": 5, "Om": 4, "Op": 5}
LEGACY_S6_BC_COUNTS = {"O2p": 4, "Om": 4, "Op": 4}
CONTRACTS = ("new-only", "legacy-hybrid")

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


def inspect(layers: dict[str, str], mechanism: dict, contract: str = "new-only") -> dict:
    if contract not in CONTRACTS:
        raise ValueError("P1_INVALID_INPUT_CONTRACT")
    errors = []
    blocks = []
    for name, text in layers.items():
        if UNRESOLVED_INCLUDE_RE.search(text):
            errors.append("P1_UNRESOLVED_INCLUDE:" + name)
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
            model = record.get("transport_coef")
            if model not in ("constant", "functor", "lookup"):
                errors.append("P1_JSON_TRANSPORT_MISSING_OR_INVALID:" + ident)
            elif model == "constant":
                for key in ("mobility", "diffusivity"):
                    value = record.get(key)
                    if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or value < 0:
                        errors.append(f"P1_JSON_TRANSPORT_COEFFICIENT_INVALID:{ident}:{key}")
            elif model == "functor":
                if any(not isinstance(record.get(key), str) or not record[key].strip()
                       for key in ("mobility", "diffusivity")):
                    errors.append("P1_JSON_TRANSPORT_FUNCTOR_MISSING:" + ident)
            elif model == "lookup":
                if not isinstance(record.get("table_file"), str) or not record["table_file"].strip():
                    errors.append("P1_JSON_TRANSPORT_TABLE_MISSING:" + ident)
    canonical = {"log_" + ident: ident for ident in fvm}
    legacy = {old_name: ident for ident, old_name in LEGACY_S6_VARIABLES.items() if ident in fvm}
    tracked = {**canonical, **legacy}
    native = []
    for block in blocks:
        if block["parent"] not in ("FVKernels", "FVBCs"):
            continue
        variables = block["params"].get("variable", "").split()
        matched = [variable for variable in variables if variable in tracked]
        if matched:
            native.append({"file": block["file"], "line": block["line"],
                           "section": block["parent"], "name": block["name"],
                           "type": block["params"].get("type"),
                           "variable": " ".join(matched),
                           "species": [tracked[v] for v in matched]})
    if contract == "new-only":
        if native:
            errors.append(f"P1_NATIVE_FV_ION_OWNER_PRESENT_{len(native)}")
        status = "P0_STATIC_PASS_ONLY"
    else:
        # This is a provenance-only S6-417/941 archived Native inventory.
        # It is NOT a successful New-only input and does not enable any C++ mode.
        if set(fvm) != set(LEGACY_S6_VARIABLES):
            errors.append("P1_LEGACY_S6_SPECIES_SET_MISMATCH")
        counts = {ident: {"FVKernels": 0, "FVBCs": 0} for ident in LEGACY_S6_VARIABLES}
        for obj in native:
            if len(obj["species"]) != 1:
                errors.append("P1_LEGACY_AMBIGUOUS_FV_VARIABLE:" + obj["name"])
                continue
            counts[obj["species"][0]][obj["section"]] += 1
        for ident in LEGACY_S6_VARIABLES:
            if counts[ident]["FVKernels"] != LEGACY_S6_KERNEL_COUNTS[ident]:
                errors.append("P1_LEGACY_KERNEL_COUNT_MISMATCH:" + ident)
            if counts[ident]["FVBCs"] != LEGACY_S6_BC_COUNTS[ident]:
                errors.append("P1_LEGACY_BC_COUNT_MISMATCH:" + ident)
        status = "P0_LEGACY_PROVENANCE_ONLY"
    return {"status": "FAIL" if errors else status, "contract": contract, "errors": errors,
            "fem_species": fem, "fvm_species": fvm, "native_fv_owner_count": len(native),
            "native_fv_owners": native,
            "runtime_generated_kernel_bc_count": "NOT_VERIFIED_P0_ONLY"}

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--zip", type=Path, required=True)
    parser.add_argument("--case", choices=("417", "941"), required=True)
    parser.add_argument("--json", type=Path, required=True)
    parser.add_argument("--contract", choices=CONTRACTS, default="new-only",
                        help="new-only rejects all Native ion FV owners; legacy-hybrid is provenance only")
    args = parser.parse_args(argv)
    prefix = f"S6_{args.case}/11_layers/"
    with zipfile.ZipFile(args.zip) as z:
        layers = {n.rsplit("/", 1)[-1]: z.read(n).decode("utf-8") for n in z.namelist()
                  if n.startswith(prefix) and n.endswith(".i")}
    if len(layers) != 11:
        parser.error(f"expected exactly 11 staged layers, got {len(layers)}")
    result = inspect(layers, json.loads(args.json.read_text()), contract=args.contract)
    print(json.dumps(result, sort_keys=True, ensure_ascii=False))
    return 0 if result["status"] in ("P0_STATIC_PASS_ONLY", "P0_LEGACY_PROVENANCE_ONLY") else 1


if __name__ == "__main__":
    sys.exit(main())
