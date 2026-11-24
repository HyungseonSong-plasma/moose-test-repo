#!/usr/bin/env python3
"""CORE Issue541: four retired-workflow candidate P2 checks with ONE built Physics binary.

Source/OCI/binary bound, all controls are actual --check-input/negative mutations.
P3 remains NOT_RUN; this is not a scientific or archival acceptance.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[2]
# Direct script invocation sets sys.path[0]=physics_app/ci; add the repository
# root before importing existing physics_app.ci Stage5 source generators.
sys.path.insert(0, str(ROOT))
CI = ROOT / "physics_app/ci"
PINNED = "ghcr.io/hyungseonsong-plasma/physics-build-base@sha256:2c3352da4f5c1b2ae98475fc01463ad0cdbc6ce7d221ce55055ddea152182008"


def run(args: list[str], *, cwd: Path = ROOT):
    proc = subprocess.run(args, cwd=cwd, capture_output=True, text=True, check=False)
    output = proc.stdout + proc.stderr
    if proc.returncode != 0:
        raise AssertionError(
            f"Native P2 command failed rc={proc.returncode}: {args!r}\n"
            + output[-9000:]
        )
    print(output[-3000:], flush=True)
    return output


def check_input(exe: Path, name: str):
    output = run([str(exe), "--check-input", "-i", name], cwd=CI)
    if "Syntax OK" not in output:
        raise AssertionError(f"{name}: missing Native Syntax OK marker")
    print("CORE_FOUR_INPUT_" + name.replace(".", "_").upper() + "_PASS", flush=True)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--executable", type=Path, required=True)
    parser.add_argument("--source", required=True)
    parser.add_argument("--oci", required=True)
    parser.add_argument("--identity", type=Path, required=True)
    args = parser.parse_args()

    exe = args.executable.resolve(strict=True)
    source = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    assert source == args.source and len(source) == 40, "P1_SOURCE_MISMATCH"
    assert args.oci == PINNED, "PINNED_OCI_MISMATCH"
    identity = json.loads(args.identity.read_text())
    assert identity == {
        "source_sha": source,
        "oci_image": args.oci,
        "binary_sha256": sha256(exe),
        "P1": "PASS",
    }, "P1_BINARY_IDENTITY_MISMATCH"
    print("ISSUE541_CORE_FOUR_P1_SOURCE_BINARY_OCI_VERIFIED", flush=True)
    print("SCCM_STATIC_GAS_NATIVE_P1_PASS", flush=True)
    print("JSON_RATE_NATIVE_P1_PASS", flush=True)

    # Workflow 1: all four published boundary inputs, legacy explicit control,
    # and fail-closed JSON density, transport, BC and owner mutations.
    for name in (
        "dd_plasma_boundary_json_p2.i",
        "dd_plasma_boundary_legacy_p2.i",
        "dd_plasma_boundary_parsed_mean_p2.i",
        "dd_plasma_boundary_json_physics_auto_p2.i",
    ):
        check_input(exe, name)
    run(["python3", str(CI / "check_issue402_dd_json_plasma_boundary_p2.py"),
         str(exe)])
    for name in (
        "valid_json_dd_fem_fvm_mixed_p2.i",
        "valid_json_generated_functor.i",
        "valid_json_generated_transport.i",
    ):
        res = run([str(exe), "--check-input", "-i", name],
                  cwd=ROOT / "experiments/Issue402_plasma_dsl_g1")
        assert "Syntax OK" in res, "DD_SPECIES_LOCAL_SYNTAX_MISSING:" + name
    print("SPECIES_LOCAL_DD_CONSTANT_LOOKUP_FUNCTOR_NATIVE_P2_PASS")
    print("DD_JSON_BOUNDARY_NATIVE_P2_PASS_P3_NOT_RUN", flush=True)

    # Workflow 2: actual gas-state and SCCM positive source, live all4 state
    # (its missing feed/boundary and derived-state negative cases are below).
    check_input(exe, "json_surface_rate_p2.i")
    print("SCCM_SURFACE_POSITIVE_P2_PASS")
    print("JSON_SURFACE_RATE_NATIVE_P2_PASS")
    check_input(exe, "json_species_live_all4_p2.i")
    print("SCCM_LIVE_ALL4_P2_PASS")
    print("FOUR_LIVE_Y_MATERIALS_FV_IC_AND_INLET_NATIVE_P2_PASS")

    # Workflow 3: H01-H05 source-bound Native syntax, EI direct Materials and
    # all twenty species initial/inlet mutation cases. H05 now emits
    # canonical Material bindings at its source; no scratch conversion.
    from physics_app.ci.check_stage5_s5d_heavy_reactions import input_text
    from physics_app.ci.check_stage5_h05_runtime import runtime_input
    with TemporaryDirectory(prefix="issue541-core4-") as temp:
        root = Path(temp)
        for label, inp in (
            ("H01_H04", input_text(600.0)),
            ("H05", runtime_input()),
        ):
            (root / f"{label}.i").write_text(inp)
            output = run([str(exe), "--check-input", "-i", f"{label}.i"], cwd=root)
            assert "Syntax OK" in output, f"{label}: NO_SYNTAX_OK"
            print(label + "_JSON_NATIVE_P2_PASS")
    check_input(exe, "plasma_direct_existing_materials_smoke.i")
    print("EI_RATE_COEF_DIRECT_SMOKE_NATIVE_P2_PASS")

    run(["python3", str(CI / "check_issue402_species_initial_composition_p2.py"),
         str(exe)])
    print("SPECIES_INITIAL_VOLUME_INLET_NATIVE_P2_PASS", flush=True)
    # The original SCCM one-shot emitted this marker only after the real
    # positive/negative composition and derived-state checker finished.
    print("SCCM_MUTATIONS_AND_DERIVED_OWNER_P2_PASS", flush=True)
    print("ISSUE402_SCCM_STATIC_GAS_NATIVE_P2_PASS_P3_NOT_RUN", flush=True)
    print("ISSUE402_SPECIES_INITIAL_AND_LIVE_NATIVE_P2_PASS_P3_NOT_RUN")
    print("JSON_HEAVY_SURFACE_NATIVE_P2_PASS_P3_NOT_RUN", flush=True)
    print("ISSUE541_CORE_FOUR_NATIVE_P2_PASS; P3=NOT_RUN; SCIENCE_HOLD", flush=True)


if __name__ == "__main__":
    main()
