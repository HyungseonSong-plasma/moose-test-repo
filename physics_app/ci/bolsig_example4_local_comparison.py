"""Private end-to-end BOLSIG+ Example4 native C++ candidate comparison.

Only hashes, explicit provenance and derived numerical errors are exported;
the original LXCat source/derived 47-channel table and native raw EEPF remain
user-local. Do not treat a numerical fit as physics equivalence.
"""
from __future__ import annotations

import argparse
from bisect import bisect_right
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
from tempfile import TemporaryDirectory

try:
    from .bolsig_local_matched_source import prepare_matched_source
    from .bolsig_native_full_process_audit import (
        NativeProcessAuditHold, parse_native,
    )
except ImportError:
    from bolsig_local_matched_source import prepare_matched_source
    from bolsig_native_full_process_audit import (
        NativeProcessAuditHold, parse_native,
    )

SOURCE_SHA = "b8b1ff807d0586795dcabf4511a2a44b8b04828626b45e0fd95a319817c01063"
NATIVE_SHA = "aa6c7c0ce00c61095934defa70f40e415474562b5e3e53374766c1ab7d6912d3"
REFERENCE_MEAN_EV = 1.35694
REFERENCE_MAX_EV = 15.8367


def compare_printed_eepf(native: list[tuple[float, float]],
                         edges: list[float], candidate: list[float]) -> dict:
    if (len(candidate) != len(edges) - 1 or len(candidate) < 2 or
            any(not math.isfinite(x) for x in edges + candidate) or
            any(v < 0 for v in candidate) or
            any(b <= a for a, b in zip(edges, edges[1:]))):
        raise NativeProcessAuditHold("invalid candidate EEPF or energy mesh")
    def get(e: float) -> float:
        k = min(max(0, bisect_right(edges, e) - 1), len(candidate) - 1)
        return candidate[k]
    errors = [(e, abs(get(e) - f)) for e, f in native
              if edges[0] <= e < edges[-1]]
    if len(errors) != len(native):
        raise NativeProcessAuditHold("candidate grid does not cover reference EEPF")
    l1 = 0.0
    for (ea, da), (eb, db) in zip(errors, errors[1:]):
        l1 += .5 * (eb - ea) * (math.sqrt(ea) * da + math.sqrt(eb) * db)
    # This is the number-mass-weighted absolute error over the *printed*
    # native energy interval, not a common-grid finite-volume error oracle.
    return {"printed_eepf_weighted_l1": l1,
            "reference_sample_count": len(errors),
            "reference_energy_coverage_eV": [native[0][0], native[-1][0]]}


def run_local_case(source: Path, native: Path, binary: Path) -> dict:
    rates, eepf, reference_norm = parse_native(native)
    if len(rates) != 47:
        raise NativeProcessAuditHold("reference must have exactly 47 native channels")
    with TemporaryDirectory(prefix="bolsig-example4-local-") as directory:
        selected = Path(directory) / "selected_PRIVATE_LXCAT_processes.txt"
        selection = prepare_matched_source(
            source, native, selected, source_sha256=SOURCE_SHA,
            native_sha256=NATIVE_SHA, excluded_source_line=5279,
            three_body_convention="as-tabulated-unscaled",
        )
        selected_sha = hashlib.sha256(selected.read_bytes()).hexdigest()
        cmd = [
            str(binary.resolve()), str(selected), selected_sha,
            "10", "300", str(REFERENCE_MAX_EV), "200",
            "Ar=0.7", "He=0.2", "N2=0.08", "O2=0.02",
            "--bolsig-2024-boundaries", "--solve-coupled-temporal-growth",
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              timeout=240, check=False)
        report = {
            "reference_source_sha256": SOURCE_SHA,
            "reference_output_sha256": NATIVE_SHA,
            "selected_source_sha256": selected_sha,
            "selected_process_count": selection["selected_process_count"],
            "source_exclusion_line": 5279,
            "reference_mean_energy_eV": REFERENCE_MEAN_EV,
            "scientific_acceptance": "HOLD_REAL_COLLISION_PROCESS_EQUIVALENCE",
            "three_body_attachment_convention": "as-tabulated-unscaled",
            "limitations": [
                "BOLSIG+ automatic grid and native C++ uniform grid are distinct",
                "Actual third-body attachment density convention is not validated",
                "Native first-angular-moment, transport and growth are not all benchmarked",
                "Reference/candidate EEPF are compared only over printed native interval",
            ],
        }
        if proc.returncode != 0:
            return {**report, "status": "HOLD_CANDIDATE_SOLVER",
                    "candidate_exit_code": proc.returncode,
                    "candidate_error": proc.stderr.strip()[-1200:]}
        try:
            data = json.loads(proc.stdout)
            comparison = compare_printed_eepf(
                eepf, data["energy_cell_edges_eV"],
                data["eepf_eV_minus_3_halves"])
            mean = data["mean_energy_eV"]
            if not (math.isfinite(mean) and mean > 0):
                raise NativeProcessAuditHold("nonphysical candidate mean energy")
            if data["source_process_count"] != 47:
                raise NativeProcessAuditHold("candidate did not retain 47 source processes")
            inactive = data.get("inactive_above_energy_ceiling", [])
            if len(inactive) != 2 or any(r["target"] != "He" for r in inactive):
                raise NativeProcessAuditHold("missing native He zero-rate inventory")
        except (ValueError, KeyError, TypeError, NativeProcessAuditHold) as exc:
            return {**report, "status": "HOLD_CANDIDATE_OUTPUT_CONTRACT",
                    "candidate_error": str(exc)}
        return {**report,
                "status": "NUMERICAL_DIAGNOSTIC_ONLY_SCIENCE_HOLD",
                "candidate_mean_energy_eV": mean,
                "mean_energy_relative_error": abs(mean / REFERENCE_MEAN_EV - 1),
                "native_printed_eepf_number_normalization": reference_norm,
                "candidate_eigen_residual": data["generalized_eigen_residual"],
                "inactive_above_energy_ceiling": inactive,
                **comparison}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cross-sections", required=True, type=Path)
    p.add_argument("--native-output", required=True, type=Path)
    p.add_argument("--candidate-binary", required=True, type=Path)
    p.add_argument("--report-json", required=True, type=Path)
    args = p.parse_args()
    try:
        output = run_local_case(
            args.cross_sections, args.native_output, args.candidate_binary)
    except (OSError, UnicodeError, NativeProcessAuditHold,
            subprocess.TimeoutExpired) as exc:
        output = {"status": "HOLD_NATIVE_SOURCE_OR_TIMEOUT",
                  "error": str(exc),
                  "scientific_acceptance": "HOLD_REAL_COLLISION_PROCESS_EQUIVALENCE"}
    args.report_json.parent.mkdir(parents=True, exist_ok=True)
    args.report_json.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0 if output["status"] == "NUMERICAL_DIAGNOSTIC_ONLY_SCIENCE_HOLD" else 2


if __name__ == "__main__":
    raise SystemExit(main())
