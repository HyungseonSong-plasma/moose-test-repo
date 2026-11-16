#!/usr/bin/env python3
"""Fail-closed named-field parity for the tiny Issue402 native control.

This does not establish full S6 replay or scientific parity.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import numpy as np
from scipy.io import netcdf_file


def variable_names(exodus, key):
    """Decode an Exodus variable-name table, or return [] when absent."""
    if key not in exodus.variables:
        return []
    rows = np.asarray(exodus.variables[key].data)
    decoded = [np.asarray(row).tobytes().decode("ascii").split("\x00", 1)[0].strip()
               for row in rows]
    if not all(decoded) or len(decoded) != len(set(decoded)):
        raise ValueError(f"Nonunique/missing Exodus field identities in {key}")
    return decoded


def physical_fields(exodus):
    """Index physical arrays by field identity, not Exodus storage position."""
    variables = exodus.variables
    nodal = variable_names(exodus, "name_nod_var")
    elemental = variable_names(exodus, "name_elem_var")
    global_names = variable_names(exodus, "name_glo_var")
    block_ids = (np.asarray(variables["eb_prop1"].data).tolist()
                 if "eb_prop1" in variables else [])
    if len(block_ids) != len(set(block_ids)):
        raise ValueError("Duplicate Exodus element block IDs")

    fields = {}
    for name, variable in variables.items():
        key = None
        if name in {"time_whole", "coordx", "coordy", "coordz", "coord",
                    "node_num_map", "elem_num_map"}:
            key = ("mesh", name)
        elif re.fullmatch(r"connect[1-9][0-9]*", name):
            index = int(name[len("connect"):])
            block = block_ids[index - 1] if block_ids else index
            key = ("connect", block)
        else:
            node_match = re.fullmatch(r"vals_nod_var([1-9][0-9]*)", name)
            elem_match = re.fullmatch(r"vals_elem_var([1-9][0-9]*)eb([1-9][0-9]*)", name)
            if node_match:
                index = int(node_match.group(1))
                if index > len(nodal):
                    raise ValueError(f"Missing nodal field identity for {name}")
                key = ("nodal", nodal[index - 1])
            elif elem_match:
                index, block_index = map(int, elem_match.groups())
                if index > len(elemental):
                    raise ValueError(f"Missing elemental field identity for {name}")
                if block_ids and block_index > len(block_ids):
                    raise ValueError(f"Missing element block ID for {name}")
                block = block_ids[block_index - 1] if block_ids else block_index
                key = ("elemental", block, elemental[index - 1])
            elif name == "vals_glo_var":
                data = np.asarray(variable.data)
                if data.ndim != 2 or data.shape[1] != len(global_names):
                    raise ValueError("Global Exodus field labels/shape mismatch")
                for i, field_name in enumerate(global_names):
                    fields[("global", field_name)] = data[:, i]
                continue
            elif name.startswith(("vals_nod_var", "vals_elem_var", "vals_glo_var")):
                raise ValueError(f"Unsupported unlabelled Exodus physical field: {name}")
        if key is not None:
            if key in fields:
                raise ValueError(f"Duplicate Exodus physical field identity: {key}")
            fields[key] = np.asarray(variable.data)

    for kind, names in (("nodal", nodal), ("elemental", elemental),
                        ("global", global_names)):
        if names and not any(key[0] == kind for key in fields):
            raise ValueError(f"Exodus {kind} names exist without values")
    if not any(key[0] in {"nodal", "elemental", "global"} for key in fields):
        raise ValueError("No physical Exodus state variables found")
    return {"nodal": set(nodal), "elemental": set(elemental),
            "global": set(global_names), "blocks": set(block_ids)}, fields


def compare(reference, candidate):
    ref_labels, ref_fields = physical_fields(reference)
    candidate_labels, candidate_fields = physical_fields(candidate)
    if ref_labels != candidate_labels:
        raise ValueError(f"Exodus physical identity metadata differs: "
                         f"{ref_labels} != {candidate_labels}")
    ref_keys, candidate_keys = set(ref_fields), set(candidate_fields)
    if ref_keys != candidate_keys:
        raise ValueError(f"Exodus physical field inventory differs: "
                         f"missing={sorted(ref_keys - candidate_keys, key=str)}, "
                         f"extra={sorted(candidate_keys - ref_keys, key=str)}")
    compared = []
    for key in sorted(ref_keys, key=str):
        a = np.asarray(ref_fields[key])
        b = np.asarray(candidate_fields[key])
        if a.shape != b.shape or not np.isfinite(a).all() or not np.isfinite(b).all():
            raise ValueError(f"Shape/nonfinite Exodus field mismatch: {key}")
        if key[0] in {"mesh", "connect"}:
            good = np.array_equal(a, b)
        else:
            good = np.allclose(a, b, rtol=1e-12, atol=1e-12)
        if not good:
            raise ValueError(f"Numerical discrepancy from external-only action: {key}")
        compared.append({"physical_field": list(key)})
    return compared


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", required=True, type=Path)
    parser.add_argument("--candidate", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    report = {
        "schema": "issue402.g1.native.external_binding_parity.v1",
        "scope": "tiny FEM+FV diffusion fixture only; no plasma Chemistry or S6 equivalence",
        "result": "NOT_EVALUATED",
        "direct_jacobian_matrix_comparison": "NOT_EVALUATED",
    }
    try:
        with netcdf_file(args.baseline, "r", mmap=False) as ref, netcdf_file(
            args.candidate, "r", mmap=False
        ) as candidate:
            report["compared_exodus_fields"] = compare(ref, candidate)
            report["result"] = "TINY_DIFFUSION_NATIVE_NUMERICAL_PARITY_PASS"
        print(report["result"])
    except Exception as error:
        report["result"] = "NATIVE_PARITY_NOT_PROVEN"
        report["reason"] = str(error)
        raise
    finally:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
