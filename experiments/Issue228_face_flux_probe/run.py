#!/usr/bin/env python3
"""One-step diagnostic face-flux probe for Issue #228.

This is diagnostic-only. It preserves the accepted production equations and
replaces only the electron drift/diffusion object types with wrappers that call
the accepted parent residuals and print the exact internal-face quantities used
by MOOSE. No physical coefficient, mesh, timestep, sheath law, or solver
acceptance condition is changed.
"""
from __future__ import annotations

import argparse
import json
import math
import shutil
from pathlib import Path
from typing import Any

from experiments.Issue192_s5r_representative import run as s5r
from experiments.Issue211_science_factorial import run as sci
from experiments.Issue216_w5_multistep_acceptance import run as w5
from physics_harness.adapters.moose import parameters as mp

DT_S = w5.BASELINE_DT_S
# Exodus element numbering and libMesh element IDs can differ by one depending
# on the reporting surface. Include both forms for the four-cell hotspot.
TARGET_IDS = (167, 168, 2400, 2401, 2509, 2510, 2511)
IDS_TEXT = "'" + " ".join(str(v) for v in TARGET_IDS) + "'"


def _write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def build_case() -> tuple[str, dict[str, Any]]:
    text, meta = w5._build_case(dt_s=DT_S, uniform_refine=0)
    text = mp.upsert_parameter(text, "Executioner", "end_time", f"{DT_S:.17g}")
    text = mp.upsert_parameter(
        text,
        "FVKernels/n_e_drift",
        "type",
        "PhysicsFVElectrostaticDriftDiagnostic",
    )
    text = mp.upsert_parameter(
        text,
        "FVKernels/n_e_drift",
        "diagnostic_element_ids",
        IDS_TEXT,
    )
    text = mp.upsert_parameter(
        text,
        "FVKernels/n_e_diffusion",
        "type",
        "PhysicsFVDiffusionDiagnostic",
    )
    text = mp.upsert_parameter(
        text,
        "FVKernels/n_e_diffusion",
        "diagnostic_element_ids",
        IDS_TEXT,
    )
    # Keep this diagnostic cheap; scalar CSV + runtime face probes are enough.
    text = mp.upsert_parameter(text, "Outputs", "exodus", "false")
    meta = {
        **meta,
        "issue": 228,
        "claim": "one_step_exact_internal_face_flux_probe",
        "diagnostic_only": True,
        "target_element_ids": list(TARGET_IDS),
        "dt_s": DT_S,
        "end_time_s": DT_S,
        "uniform_refine": 0,
        "production_equations_changed": False,
    }
    return text, meta


def self_test() -> dict[str, Any]:
    text, meta = build_case()
    checks = {
        "one_step_end_time": math.isclose(
            float(mp.get_parameter(text, "Executioner", "end_time") or "nan"),
            DT_S,
            rel_tol=0.0,
            abs_tol=1e-24,
        ),
        "drift_probe_type": (
            mp.get_parameter(text, "FVKernels/n_e_drift", "type")
            == "PhysicsFVElectrostaticDriftDiagnostic"
        ),
        "diff_probe_type": (
            mp.get_parameter(text, "FVKernels/n_e_diffusion", "type")
            == "PhysicsFVDiffusionDiagnostic"
        ),
        "drift_ids_present": all(
            str(v) in (mp.get_parameter(text, "FVKernels/n_e_drift", "diagnostic_element_ids") or "")
            for v in TARGET_IDS
        ),
        "diff_ids_present": all(
            str(v) in (mp.get_parameter(text, "FVKernels/n_e_diffusion", "diagnostic_element_ids") or "")
            for v in TARGET_IDS
        ),
        "baseline_dt_preserved": math.isclose(
            float(mp.get_parameter(text, "Executioner", "dt") or "nan"),
            DT_S,
            rel_tol=0.0,
            abs_tol=0.0,
        ),
        "r0_preserved": meta.get("uniform_refine") == 0,
        "diagnostic_only": meta.get("diagnostic_only") is True,
    }
    failed = sorted(k for k, v in checks.items() if not v)
    return {"status": "PASS" if not failed else "FAIL", "checks": checks, "failed_checks": failed}


def _value(token: str) -> Any:
    try:
        if any(c in token for c in ".eE"):
            return float(token)
        return int(token)
    except ValueError:
        return token


def _parse_probe_lines(runtime_log: Path) -> dict[str, Any]:
    samples: dict[str, list[dict[str, Any]]] = {"drift": [], "diffusion": []}
    for raw in runtime_log.read_text(encoding="utf-8", errors="replace").splitlines():
        kind = None
        marker = None
        if "ISSUE228_DRIFT" in raw:
            kind, marker = "drift", "ISSUE228_DRIFT"
        elif "ISSUE228_DIFF" in raw:
            kind, marker = "diffusion", "ISSUE228_DIFF"
        if kind is None or marker is None:
            continue
        tail = raw.split(marker, 1)[1].strip()
        row: dict[str, Any] = {}
        for field in tail.split():
            if "=" not in field:
                continue
            key, value = field.split("=", 1)
            row[key] = _value(value)
        if "elem" in row and "neighbor" in row:
            samples[kind].append(row)

    last_by_face: dict[str, dict[str, dict[str, Any]]] = {"drift": {}, "diffusion": {}}
    for kind, rows in samples.items():
        for row in rows:
            a, b = int(row["elem"]), int(row["neighbor"])
            face_key = f"{min(a, b)}-{max(a, b)}"
            last_by_face[kind][face_key] = row

    common_faces = sorted(set(last_by_face["drift"]) & set(last_by_face["diffusion"]))
    sign_reversal_faces = []
    for face_key, row in last_by_face["drift"].items():
        central = float(row.get("central_grad_phi_n", 0.0))
        actual = float(row.get("actual_grad_phi_n", 0.0))
        if central != 0.0 and actual != 0.0 and central * actual < 0.0:
            sign_reversal_faces.append(face_key)

    return {
        "sample_counts": {k: len(v) for k, v in samples.items()},
        "last_by_face": last_by_face,
        "common_faces": common_faces,
        "drift_gradient_sign_reversal_faces": sorted(sign_reversal_faces),
        "hard_pass": bool(samples["drift"] and samples["diffusion"] and common_faces),
    }


def run(args: argparse.Namespace) -> int:
    exe = args.physics_opt.resolve()
    out = args.results_root.resolve()
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)

    p0 = self_test()
    _write(out / "self_test.json", p0)
    if p0["status"] != "PASS":
        raise RuntimeError(p0)

    text, meta = build_case()
    case_dir = out / "case"
    logs = out / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    stage = sci._stage(case_dir, text, meta)
    p2 = s5r._p2(exe, case_dir, logs / "p2.log", timeout=min(float(args.timeout), 300.0))
    summary: dict[str, Any] = {"meta": meta, "stage": stage, "p2": p2, "status": "RUNNING"}
    if p2.get("returncode") != 0:
        summary["status"] = "P2_FAIL"
        _write(out / "summary.json", summary)
        return 2

    runtime_log = logs / "runtime.log"
    runtime = sci._runtime(exe, case_dir, runtime_log, logs / "time_v.log", float(args.timeout))
    summary["runtime"] = runtime
    probes = _parse_probe_lines(runtime_log)
    summary["probes"] = probes
    summary["status"] = (
        "PASS" if int(runtime.get("returncode", 1)) == 0 and probes.get("hard_pass") else "FAIL"
    )
    _write(out / "face_flux_probe.json", probes)
    _write(out / "summary.json", summary)
    return 0 if summary["status"] == "PASS" else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--physics-opt", type=Path)
    parser.add_argument("--results-root", type=Path, default=Path("issue228-face-flux-probe-results"))
    parser.add_argument("--timeout", type=float, default=900.0)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        result = self_test()
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result["status"] == "PASS" else 1
    if args.physics_opt is None:
        parser.error("--physics-opt is required unless --self-test is used")
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
