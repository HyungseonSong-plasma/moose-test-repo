#!/usr/bin/env python3
"""Read-only Issue402 G1 S6 FEM/FV species placement audit.

Reads *actual* successful S6-417 and S6-941 native ZIP artifacts and
confirms archived variable type family, chemistry and provenance.
This is an offline input/run-evidence audit, NOT a new MOOSE native solve.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import zipfile
from pathlib import Path

PIN = "29d1acc6ef7969908b86719e4b95c73a1565136d"
VARIABLES = {
    "e": ("log_ne", "FEM", "LAGRANGE"),
    "O2p": ("log_ni", "FV", "MooseVariableFVReal"),
    "Om": ("log_nm", "FV", "MooseVariableFVReal"),
    "Op": ("log_nop", "FV", "MooseVariableFVReal"),
    "e_energy": ("log_energy", "FEM", "LAGRANGE"),
    "mixture_p": ("p", "FV", "INSFVPressureVariable"),
    "mixture_u": ("u", "FV", "INSFVVelocityVariable"),
    "mixture_v": ("v", "FV", "INSFVVelocityVariable"),
    "O2s": ("w_O2s", "FV", "INSFVScalarFieldVariable"),
    "O": ("w_O", "FV", "INSFVScalarFieldVariable"),
    "Os": ("w_Os", "FV", "INSFVScalarFieldVariable"),
}


def audit(archive: Path) -> dict:
    with zipfile.ZipFile(archive) as z:
        names = z.namelist()
        manifests = [n for n in names if n.endswith("/case_manifest.json")]
        if len(manifests) != 1:
            raise ValueError(f"{archive}: expected one case_manifest, found {len(manifests)}")
        manifest = json.loads(z.read(manifests[0]))
        case = manifest["case"]
        if case not in {"S6-417-407-2069-H25", "S6-941-407-2069-H25"}:
            raise ValueError("Unexpected case: " + case)
        chosen = "EI-417" if "S6-417" in case else "EI-941"
        expected = [
            "EI-02", "EI-17", "EI-415", "EI-401",
            chosen, "EI-407", "EI-2069", "H25",
        ]
        if manifest["chemistry_channels"] != expected:
            raise ValueError(f"{case}: chemistry channels changed")
        if manifest["science_acceptance"] != "HOLD" or manifest["source_sha"] != PIN:
            raise ValueError(f"{case}: provenance/science acceptance changed")
        if manifest["power_W"] != 400 or manifest["expected_native_steps"] != 460:
            raise ValueError(f"{case}: power or timestep contract changed")
        if len(manifest["input_paths"]) != 10:
            raise ValueError(f"{case}: expected 10 input source layers")
        input_files = [n for n in names if n.endswith(".i")]
        if len(input_files) != 10:
            raise ValueError(f"{case}: expected 10 archived .i files")
        base = [n for n in input_files if n.endswith("__C0_chemistry_off.i")]
        if len(base) != 1:
            raise ValueError(f"{case}: missing unique original base input")
        text = z.read(base[0]).decode("utf-8")
        resolved = {}
        for species, (var, family, identifier) in VARIABLES.items():
            # Recognize the actual leaf definition, not a coincidental variable
            # mention elsewhere in a function, kernel or comment.
            matched = re.search(
                r"(?m)^[ \t]*\[" + re.escape(var) +
                r"\][ \t]*\n(.*?)(?=^[ \t]*\[\][ \t]*$)",
                text, re.S | re.M,
            )
            if not matched:
                raise ValueError(f"{case}: no variable block for {species}/{var}")
            definition = matched.group(1)
            if family == "FEM":
                okay = re.search(r"(?m)^\s*family\s*=\s*LAGRANGE\s*$", definition)
            else:
                okay = re.search(
                    r"(?m)^\s*type\s*=\s*" + re.escape(identifier) + r"\s*$",
                    definition,
                )
            if not okay:
                raise ValueError(
                    f"{case}: unexpected {family} variable class: {var}/{identifier}"
                )
            resolved[species] = {"variable": var, "discretization": family}
        for required in ("check_input.log", "run/plasma.csv", "run/plasma.e", "runtime.log"):
            if not any(n.endswith(required) for n in names):
                raise ValueError(f"{case}: missing native evidence {required}")
        return {
            "case": case,
            "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
            "source_sha": PIN,
            "science_acceptance": "HOLD",
            "channels": expected,
            "explicit_input_layers": 10,
            "run_completed_evidence_present": True,
            "species_variable_binding": resolved,
            "new_implementation_compiled": "NOT_EVALUATED",
            "new_implementation_native_run": "NOT_EVALUATED",
        }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--archive", action="append", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    if len(args.archive) != 2:
        p.error("exactly two S6 native archives (417 and 941) required")
    rows = [audit(path) for path in args.archive]
    if {row["case"] for row in rows} != {
        "S6-417-407-2069-H25", "S6-941-407-2069-H25"
    }:
        raise ValueError("Missing one of the 417/941 cases")
    report = {
        "status": "S6_ARCHIVED_SPECIES_FEM_FV_BINDING_AUDIT_PASS",
        "scope": "archived input and completed native evidence; NOT G1 new C++ native test",
        "cases": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(report["status"])
    for row in rows:
        print(row["case"], "variables", len(row["species_variable_binding"]))


if __name__ == "__main__":
    main()
