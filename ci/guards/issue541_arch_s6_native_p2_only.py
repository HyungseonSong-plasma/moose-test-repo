#!/usr/bin/env python3
"""ARCH-only source-bound S6-417/941 hybrid Native P2; NEVER runs a P3 timestep.

This distinct verification reproduces the real 11-layer P3 input preparation
up to and including the exact pinned-binary --check-input. It does not weaken
or alter the historical S6 source, chemistry runner or any P3 approval gate.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[2]
PILOT = ROOT / "experiments/Issue402_plasma_dsl_g1"
sys.path.insert(0, str(PILOT))
import public_option_s6_p2 as option  # noqa: E402
from chemistry.prepare_s6_run_input import prepare as prepare_chemistry  # noqa: E402
from chemistry.prepare_hybrid_json_s6 import prepare as prepare_hybrid  # noqa: E402


def execute(case: str, historical: Path, source_sha: str, output: Path) -> dict:
    if case not in option.CASES:
        raise ValueError("ARCH_S6_P2_BAD_CASE")
    if output.exists():
        raise ValueError("ARCH_S6_P2_REFUSE_OVERWRITE")
    output.mkdir(parents=True, mode=0o700)
    record: dict = {
        "schema": "issue541.arch.s6_hybrid_native_p2_only.v1",
        "case": case,
        "source_sha": source_sha,
        "historical_sha": option.HISTORICAL_SHA,
        "oci_image": option.OCI,
        "mode": "chemistry_hybrid_json_native",
        "P0": "NOT_RUN", "P1": "NOT_RUN", "P2": "HOLD",
        "P3": "NOT_RUN", "P4": "NOT_RUN",
        "science": "SCIENCE_HOLD",
        "status": "HOLD",
    }
    try:
        if option.git_head(ROOT) != source_sha:
            raise ValueError("ARCH_S6_P2_EXACT_SOURCE_HEAD_MISMATCH")
        option.p2.preflight(ROOT)
        binary = ROOT / "physics_app/physics-opt"
        identity = option.check_source(source_sha, historical, binary)
        record["P0"] = "PASS"
        record["P1"] = "PASS_SOURCE_BOUND_BINARY"
        record["binary_sha256"] = identity["binary_sha256"]
        record["historical_mesh_sha256"] = identity["historical_mesh_sha256"]
        manifest = json.loads((ROOT / option.p2.DECKS / "manifest.json").read_text())
        staged = output / "scratch_hybrid"
        base = PILOT / "native/s6_c0_physics_base_no_d1.i"
        layers = option.p2.stage(
            ROOT, historical, case, "C", staged, manifest, d_base_source=base
        )
        chemistry = staged / option.p2.CHEM
        record["native_layers"] = len(layers)
        if len(layers) != 11:
            raise ValueError("ARCH_S6_P2_EXPECT_11_LAYERS")
        record["scratch_migration"] = option.canonicalize_staged_D_inputs(
            chemistry, layers
        )
        record["scratch_fem_type_remap"] = option.remap_staged_fem_types(
            chemistry, layers
        )
        chem_cutover = prepare_chemistry(chemistry, layers, case)
        sidecar = chemistry / "migrated_continuity.i"
        if option.sha_file(sidecar) != chem_cutover["overlay_sha256"]:
            raise ValueError("ARCH_S6_P2_CHEMISTRY_OVERLAY_HASH")
        hybrid = prepare_hybrid(chemistry, layers, case)
        if option.sha_file(sidecar) != hybrid["overlay_sha256"]:
            raise ValueError("ARCH_S6_P2_HYBRID_OVERLAY_HASH")
        integrated = chemistry / hybrid["integrated_mechanism_json"]
        if option.sha_file(integrated) != hybrid["integrated_json_source_sha256"]:
            raise ValueError("ARCH_S6_P2_INTEGRATED_JSON_HASH")
        if hybrid["removed_generated_owner_count"] != 10 or \
                hybrid["rebound_native_sheath_bc_count"] != 8 or \
                hybrid["integrated_species_count"] != 7 or \
                hybrid["integrated_reaction_count"] != 8:
            raise ValueError("ARCH_S6_P2_HYBRID_OWNER_CONTRACT")
        record["integrated_json_sha256"] = option.sha_file(integrated)
        record["owner_cutover"] = {
            "removed_generated_owner_count": hybrid["removed_generated_owner_count"],
            "rebound_native_sheath_bc_count": hybrid["rebound_native_sheath_bc_count"],
            "integrated_species_count": hybrid["integrated_species_count"],
            "integrated_reaction_count": hybrid["integrated_reaction_count"],
        }
        native_log = output / "native_P2.log"
        check = option.run_one(
            binary, identity["binary_sha256"], staged, layers, native_log, 1200
        )
        record["native_check"] = check
        record["P2"] = check["P2"]
        if check["P2"] != "PASS":
            raise ValueError(
                "ARCH_S6_P2_NATIVE_CHECK_INPUT_" + check["classification"]
            )
        if option.sha_file(binary) != identity["binary_sha256"]:
            raise ValueError("ARCH_S6_P2_BINARY_CHANGED_AFTER_CHECK")
        record["status"] = "ARCH_S6_HYBRID_NATIVE_P2_PASS_NO_P3"
    except Exception as exc:
        record["status"] = "HOLD"
        record["blocker"] = str(exc)[:300]
        if (output / "native_P2.log").is_file():
            print(
                "ARCH_S6_P2_FAILURE_DIAGNOSTIC_TAIL\n" +
                (output / "native_P2.log").read_text(errors="replace")[-7000:],
                flush=True,
            )
    finally:
        (output / "status.json").write_text(
            json.dumps(record, indent=2, sort_keys=True) + "\n"
        )
    print(
        "ARCH_S6_CASE=" + case + " P2=" + record["P2"] +
        " P3=NOT_RUN SCIENCE_HOLD STATUS=" + record["status"],
        flush=True
    )
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", choices=option.CASES, required=True)
    parser.add_argument("--historical", type=Path, required=True)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = execute(
        args.case, args.historical.resolve(), args.expected_head,
        args.output.resolve()
    )
    return 0 if result["P2"] == "PASS" else 3


if __name__ == "__main__":
    raise SystemExit(main())
