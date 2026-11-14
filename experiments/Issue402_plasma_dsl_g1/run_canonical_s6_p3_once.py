#!/usr/bin/env python3
"""One-shot, public-data-only S6 D Native P3 on the exact merged PhysicsApp.

Unlike historical C-only, this runs the canonical log_<species> state names.
B is not rerun. No protected rate file, archived input mutation, or science
acceptance is permitted. One 100-us/461-frame solve per requested case.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys

import public_option_s6_p2 as option

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "experiments/Issue493_s6_boltzmann"))
from compare_native_reference import analyze  # noqa: E402
from run_issue493 import verify_native_csv  # noqa: E402


def sha(path: Path) -> str:
    return option.sha_file(path)


def verify_canonical_exodus(exodus: Path, *, require_energy: bool = False) -> dict:
    """Require the new solver to emit canonical fields, not archived aliases."""
    import numpy as np
    from scipy.io import netcdf_file

    def decoded(table):
        return [b"".join(row).decode("ascii", "strict").strip("\x00 ")
                for row in table[:]]

    with netcdf_file(str(exodus), "r", mmap=False) as handle:
        names = decoded(handle.variables["name_nod_var"])
        elements = decoded(handle.variables["name_elem_var"])
        for expected, archived in (("log_e", "log_ne"),):
            if names.count(expected) != 1 or archived in names:
                raise ValueError("P3_NONCANONICAL_ELECTRON_STATE")
        if require_energy and (names.count("log_e_energy") != 1 or "log_energy" in names):
            raise ValueError("P3_NONCANONICAL_ELECTRON_ENERGY_STATE")
        for expected, archived in (("log_O2p", "log_ni"),
                                   ("log_Om", "log_nm"),
                                   ("log_Op", "log_nop")):
            if elements.count(expected) != 1 or archived in elements:
                raise ValueError("P3_NONCANONICAL_ION_STATE")
        times = np.asarray(handle.variables["time_whole"][:], dtype=float)
        if len(times) != 461 or abs(float(times[-1]) - 1e-4) > 1e-9:
            raise ValueError("P3_EXODUS_TIMEGRID_MISMATCH")
        result = {"nodal_electron": "log_e",
                  "elemental_ions": ["log_O2p", "log_Om", "log_Op"],
                  "frames": len(times)}
        if require_energy:
            result["electron_energy"] = "log_e_energy"
        return result


def run(case: str, historical: Path, expected_head: str,
        output: Path, timeout_seconds: int, *, chemistry_mode: bool = False,
        hybrid_json: bool = False) -> dict:
    if case not in option.CASES or not (600 <= timeout_seconds <= 19800):
        raise ValueError("P3_INVALID_CASE_OR_BUDGET")
    if hybrid_json and not chemistry_mode:
        raise ValueError("P3_HYBRID_REQUIRES_CANONICAL_S6_CHEMISTRY")
    if output.exists():
        raise ValueError("P3_OUTPUT_ALREADY_EXISTS")
    output.mkdir(parents=True, mode=0o700)
    status = {
        "schema": "issue402_canonical_S6_D_P3_once_v1",
        "case": case, "arm": "D",
        "physics_mode": ("chemistry_hybrid_json_native" if hybrid_json else
                         "chemistry" if chemistry_mode else "transport_only"),
        "source_sha": expected_head, "historical_sha": option.HISTORICAL_SHA,
        "oci_image": option.OCI,
        "P0": "NOT_RUN", "P1": "NOT_RUN", "P2": "NOT_RUN",
        "P3": "NOT_RUN", "P4": "NOT_RUN", "science": "SCIENCE_HOLD"
    }
    results = output / "results"
    results.mkdir()
    staged = output / "scratch_D"
    try:
        if option.git_head(ROOT) != expected_head:
            raise ValueError("P3_EXACT_MERGED_SOURCE_MISMATCH")
        if not chemistry_mode:
            option.validate_overlay()
        option.p2.preflight(ROOT)
        binary = ROOT / "physics_app/physics-opt"
        identity = option.check_source(expected_head, historical, binary)
        status["P0"] = "PASS"
        status["P1"] = "PASS_SOURCE_BOUND_BINARY"
        status["binary_sha256"] = identity["binary_sha256"]
        manifest = json.loads((ROOT / option.p2.DECKS / "manifest.json").read_text())
        # Both transport-only and Chemistry D P3 use the same prebuilt
        # no-debug physics base. Historical B/C decks remain immutable.
        d_base = (ROOT / "experiments/Issue402_plasma_dsl_g1/native/"
                  "s6_c0_physics_base_no_d1.i")
        ordered = option.p2.stage(
            ROOT, historical, case, "C", staged, manifest,
            d_base_source=d_base)
        migration = option.canonicalize_staged_D_inputs(staged / option.p2.CHEM, ordered)
        sidecar = staged / option.p2.CHEM / "migrated_continuity.i"
        status["scratch_migration"] = migration
        status["scratch_fem_type_remap"] = option.remap_staged_fem_types(
            staged / option.p2.CHEM, ordered)
        if chemistry_mode:
            from chemistry.prepare_s6_run_input import prepare
            # Full source-owner cutover: remove nine superseded electron
            # source Kernels, preserve the original public rate providers.
            cutover = prepare(staged / option.p2.CHEM, ordered, case)
            status["scratch_chemistry_cutover"] = cutover
            status["active_reaction_ids"] = (
                ["EI-02", "EI-17", "EI-415", "EI-401", "EI-407",
                 "EI-2069", "H25", "EI-" + case])
            if sha(sidecar) != cutover["overlay_sha256"]:
                raise ValueError("P3_CHEMISTRY_OVERLAY_SHA_MISMATCH")
            if hybrid_json:
                # JSON Physics owns only its generated FEM electron states,
                # kernels, mobility and energy Material. The existing Native
                # RF, Poisson, wall/charge ledger, ions and rates are retained
                # from the staged public 400-W S6 deck. Every overlapping
                # historical owner is validated and retired in SCRATCH only.
                from chemistry.prepare_hybrid_json_s6 import prepare as prepare_hybrid
                hybrid = prepare_hybrid(staged / option.p2.CHEM, ordered, case)
                status["hybrid_json_ownership_cutover"] = hybrid
                if sha(sidecar) != hybrid["overlay_sha256"]:
                    raise ValueError("P3_HYBRID_OVERLAY_SHA_MISMATCH")
        else:
            # Earlier D transport-only experiment, not the Chemistry P3 arm.
            shutil.copy2(ROOT / "experiments/Issue402_plasma_dsl_g1/plasma_species_only.json",
                         staged / option.p2.CHEM / "plasma_species_only.json")
            sidecar.write_text(option.OVERLAY, encoding="utf-8")
            if sha(sidecar) != option.OVERLAY_SHA256:
                raise ValueError("P3_CANONICAL_OVERLAY_SHA_MISMATCH")
        status["sidecar_sha256"] = sha(sidecar)
        p2 = option.run_one(binary, identity["binary_sha256"], staged, ordered,
                            output / "native_P2.log", timeout_seconds=1200)
        status["P2"] = p2["P2"]
        status["p2_log_sha256"] = p2["log_sha256"]
        if p2["P2"] != "PASS":
            raise ValueError("P3_CANONICAL_INPUT_CHECK_FAILED")
        if sha(binary) != identity["binary_sha256"]:
            raise ValueError("P3_NATIVE_BINARY_CHANGED_AFTER_P2")
        simulated = staged / "canonical_p3/run"
        simulated.mkdir(parents=True, exist_ok=False)
        args = [
            "docker", "run", "--rm", "--network", "none",
            "--entrypoint", "/bin/bash", "--user", "0:0",
            "--workdir", "/case",
            "--env", "OXYGEN_RESEARCH_400=1",
            "--env", "OXYGEN_RESEARCH_FULL24=0",
            "--env", "OXYGEN_RESEARCH_EI2738_FORMULA=0",
            "--env", "OXYGEN_RESEARCH_QUICK_5MIN=0",
            "--mount", f"type=bind,src={ROOT.resolve()},dst=/workspace,readonly",
            "--mount", f"type=bind,src={staged.resolve()},dst=/case",
            option.OCI, "-lc",
            ("set -euo pipefail; source /environment; "
             "trap 'rm -rf /case/.jitcache' EXIT; "
             "exec /workspace/physics_app/physics-opt -i " +
             " ".join(shlex.quote(value) for value in ordered) +
             " Outputs/file_base=canonical_p3/run/plasma"),
        ]
        with (output / "native_P3.log").open("wb") as logfile:
            try:
                completed = subprocess.run(args, stdout=logfile,
                                           stderr=subprocess.STDOUT,
                                           timeout=timeout_seconds, check=False)
            except subprocess.TimeoutExpired as exc:
                raise ValueError("P3_SOLVER_TIMEOUT") from exc
        status["p3_log_sha256"] = sha(output / "native_P3.log")
        if completed.returncode != 0:
            raise ValueError("P3_SOLVER_NONZERO")
        exodus = simulated / "plasma.e"
        csv_file = simulated / "plasma.csv"
        if not exodus.is_file() or not csv_file.is_file():
            raise ValueError("P3_EXODUS_OR_CSV_MISSING")
        verify_native_csv(csv_file)
        status["canonical_fields"] = (
            verify_canonical_exodus(exodus, require_energy=True)
            if chemistry_mode else verify_canonical_exodus(exodus))
        published_exodus = results / "plasma.e"
        published_csv = results / "plasma.csv"
        shutil.copyfile(exodus, published_exodus)
        shutil.copyfile(csv_file, published_csv)
        status["P3"] = "PASS"
        status["native_exodus_sha256"] = sha(published_exodus)
        status["native_csv_sha256"] = sha(published_csv)
        p3_manifest = results / "manifest.json"
        p3_manifest.write_text(json.dumps({
            "schema": "issue493_public_p3_artifact_v1",
            "case": case, "arm": "D",
            "physics_mode": ("chemistry_hybrid_json_native" if hybrid_json else
                             "chemistry" if chemistry_mode else "transport_only"),
            "source_sha": expected_head, "oci_image": option.OCI,
            "P3": "PASS", "science": "SCIENCE_HOLD",
            "files": {
                name: {"sha256": sha(results / name)}
                for name in ("plasma.e", "plasma.csv")
            }
        }, sort_keys=True, indent=2) + "\n")
        ref = ROOT / "experiments/Issue493_s6_boltzmann/reference"
        overlay = analyze(
            exodus=published_exodus, csv_file=published_csv,
            manifest_file=p3_manifest,
            vertical_reference=ref / "reference_vertical.csv",
            horizontal_reference=ref / "reference_horizontal.csv",
            output=results / "reference_comparison",
            label=f"S6-{case}-D" + ("-Chemistry" if chemistry_mode else ""),
            time_us=100.0,
        )
        status["P4"] = "DIAGNOSTIC_ONLY"
        status["reference_status"] = overlay["comparison_status"]
        status["status"] = "PASS_P3_REFERENCE_DIAGNOSTIC"
        return status
    except Exception as exc:
        status["status"] = "HOLD_OR_FAIL"
        status["blocker"] = str(exc)[:120] if str(exc).startswith("P3_") else type(exc).__name__
        raise
    finally:
        status["science"] = "SCIENCE_HOLD"
        (results / "status.json").write_text(json.dumps(status, sort_keys=True, indent=2) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", choices=option.CASES, required=True)
    parser.add_argument("--historical", type=Path, required=True)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=int, default=19800)
    parser.add_argument("--hybrid-json", action="store_true",
                        help="Only with --chemistry? Use run_chemistry_s6_p3_once.py.")
    a = parser.parse_args()
    return 0 if run(a.case, a.historical.resolve(), a.expected_head,
                    a.output.resolve(), a.timeout_seconds,
                    chemistry_mode=a.hybrid_json,
                    hybrid_json=a.hybrid_json)["P3"] == "PASS" else 3


if __name__ == "__main__":
    sys.exit(main())
