#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys
import time

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from experiments.Issue253_g1_gummel_dt_release import prepare

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
GENERATED = ROOT / "generated_ion_advance"
RESULTS = ROOT / "results_ion_advance"
BUILD_BASE_REF = (
    "ghcr.io/hyungseonsong-plasma/physics-build-base@"
    "sha256:2c3352da4f5c1b2ae98475fc01463ad0cdbc6ce7d221ce55055ddea152182008"
)

ION_DT = 1.0e-4
ION_STEPS = 2
ION_END = ION_DT * ION_STEPS
E0 = 50.0
T_G = 600.0
D_O2P = 7.141154e-3
E_OVER_KB = 11604.518121550082
MU_O2P = E_OVER_KB * D_O2P / T_G
DX = 0.01 / 20.0
W0 = prepare.NE0 * prepare.M_O2P / (prepare.RHO * prepare.NA)
LOG_CE = math.log(prepare.NE0 / prepare.NA)


def _run(command: list[str], *, cwd: Path | None = None) -> None:
    print("+", " ".join(command), flush=True)
    subprocess.run(command, cwd=cwd, check=True)


def _docker(script: str) -> None:
    _run(["docker", "pull", BUILD_BASE_REF])
    _run(
        [
            "docker",
            "run",
            "--rm",
            "--entrypoint",
            "/bin/bash",
            "--user",
            "0:0",
            "--workdir",
            "/workspace",
            "-v",
            f"{REPO}:/workspace",
            BUILD_BASE_REF,
            "-lc",
            script,
        ]
    )


def _silence_poisson_outputs(text: str) -> str:
    old = """[Outputs]
  csv = true
  exodus = true
  execute_on = 'INITIAL FINAL'
[]
"""
    new = """[Outputs]
  console = false
[]
"""
    if text.count(old) != 1:
        raise RuntimeError("Poisson Outputs block changed unexpectedly")
    return text.replace(old, new, 1)


def build(clean: bool = True) -> dict[str, float | int]:
    if clean and GENERATED.exists():
        shutil.rmtree(GENERATED)
    GENERATED.mkdir(parents=True, exist_ok=True)

    parent_template = (ROOT / "ion_advance_template.i").read_text(encoding="utf-8")
    poisson_template = (ROOT / "poisson_template.i").read_text(encoding="utf-8")
    parent = prepare._render(
        parent_template,
        {
            "W_O2P": f"{W0:.17g}",
            "LOG_CE": f"{LOG_CE:.17g}",
            "D_O2P": f"{D_O2P:.17g}",
            "MU_O2P": f"{MU_O2P:.17g}",
            "E0": f"{E0:.17g}",
            "DT": f"{ION_DT:.17g}",
            "END_TIME": f"{ION_END:.17g}",
            "STEPS": str(ION_STEPS),
        },
    )
    poisson = prepare._render(
        poisson_template,
        {"LOG_CE": f"{LOG_CE:.17g}", "W_O2P": f"{W0:.17g}"},
    )
    poisson = _silence_poisson_outputs(poisson)

    (GENERATED / "input.i").write_text(parent, encoding="utf-8")
    (GENERATED / "poisson_sub.i").write_text(poisson, encoding="utf-8")
    metadata = {
        "issue": 253,
        "sequence": 6,
        "ion_species": "O2+",
        "ion_steps": ION_STEPS,
        "ion_dt_s": ION_DT,
        "end_time_s": ION_END,
        "D_O2p_m2_s": D_O2P,
        "mu_O2p_m2_V_s": MU_O2P,
        "prescribed_E_V_m": E0,
        "expected_free_drift_shift_m": MU_O2P * E0 * ION_END,
        "baseline_w_O2p": W0,
        "scope": (
            "two solved O2+ physical advances under prescribed electric drift/diffusion; "
            "Poisson is a one-way observer; electron density and other heavy charge are frozen"
        ),
    }
    (GENERATED / "case.json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return metadata


def static_contract() -> dict[str, object]:
    meta = build()
    text = (GENERATED / "input.i").read_text(encoding="utf-8")
    poisson = (GENERATED / "poisson_sub.i").read_text(encoding="utf-8")

    assert meta["ion_steps"] == 2
    assert math.isclose(float(meta["ion_dt_s"]), 1.0e-4, rel_tol=0.0, abs_tol=0.0)
    assert "QPXFVConservativeMassFractionTimeDerivative" in text
    assert "QPXFVMixtureAveragedDiffusion" in text
    assert "QPXFVElectrostaticDrift" in text
    assert "variable = w_O2p" in text
    assert "execute_on = 'INITIAL TIMESTEP_END'" in text
    assert "source_variable = w_O2p" in text
    assert "variable = w_O2p_frozen" in text
    assert "potential = phi_drift" in text
    assert "potential_observer" in text
    assert "PhysicsFVLogMolarElectronTimeDerivative" not in text
    assert "PhysicsFVLogMolarElectronEnergy" not in text
    assert "[Outputs]\n  console = false\n[]" in poisson
    assert "@@" not in text
    assert "@@" not in poisson
    return {"status": "PASS", **meta}


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _profiles() -> list[list[dict[str, str]]]:
    files = sorted(GENERATED.glob("input_out_ion_profile*.csv"))
    profiles = [_rows(path) for path in files]
    return [rows for rows in profiles if rows]


def _excess_centroid(rows: list[dict[str, str]]) -> float:
    weighted = []
    for row in rows:
        x = float(row["x"])
        w = float(row["w_O2p"])
        excess = max(w - W0, 0.0)
        weighted.append((x, excess))
    denom = sum(w for _, w in weighted)
    if denom <= 0.0:
        raise RuntimeError("positive O2+ excess vanished")
    return sum(x * w for x, w in weighted) / denom


def analyze_result(returncode: int, elapsed: float) -> tuple[dict[str, object], int]:
    summary: dict[str, object] = {
        "issue": 253,
        "sequence": 6,
        "returncode": returncode,
        "elapsed_seconds": elapsed,
        "ion_steps_requested": ION_STEPS,
        "scope": (
            "ion advance and one-way Poisson response only; not yet self-consistent "
            "ion-electron-Poisson multirate coupling"
        ),
    }
    if returncode != 0:
        summary["classification"] = "ION_RUNTIME_FAILURE"
        summary["evidence_valid"] = False
        return summary, 2

    scalar_rows = _rows(GENERATED / "input_out.csv")
    times = [float(row["time"]) for row in scalar_rows]
    positive_times = sorted({t for t in times if t > 0.0})
    profiles = _profiles()
    if len(positive_times) != ION_STEPS or len(profiles) < ION_STEPS + 1:
        summary["classification"] = "ION_ADVANCE_EVIDENCE_INCOMPLETE"
        summary["evidence_valid"] = False
        summary["positive_times"] = positive_times
        summary["profile_snapshots"] = len(profiles)
        return summary, 2

    initial = profiles[0]
    final = profiles[-1]
    c0 = _excess_centroid(initial)
    cf = _excess_centroid(final)
    shift = cf - c0
    expected = MU_O2P * E0 * ION_END

    w0 = [float(row["w_O2p"]) for row in initial]
    wf = [float(row["w_O2p"]) for row in final]
    p0 = [float(row["potential_observer"]) for row in initial]
    pf = [float(row["potential_observer"]) for row in final]
    profile_change_rel = max(abs(a - b) for a, b in zip(wf, w0)) / W0
    phi_change = max(abs(a - b) for a, b in zip(pf, p0))

    inv0 = float(scalar_rows[0]["ion_inventory"])
    invf = float(scalar_rows[-1]["ion_inventory"])
    inv_rel = abs(invf - inv0) / max(abs(inv0), 1.0e-300)
    nmin = float(scalar_rows[-1]["ion_n_min"])

    summary.update(
        {
            "positive_times": positive_times,
            "profile_snapshots": len(profiles),
            "centroid_initial_m": c0,
            "centroid_final_m": cf,
            "centroid_shift_m": shift,
            "expected_free_drift_shift_m": expected,
            "shift_ratio_to_free_drift": shift / expected if expected != 0.0 else None,
            "profile_change_relative_to_baseline": profile_change_rel,
            "poisson_observer_phi_change_V": phi_change,
            "inventory_relative_change": inv_rel,
            "ion_n_min_final_m3": nmin,
        }
    )

    advance = shift > 0.25 * DX and profile_change_rel > 1.0e-4
    poisson_responded = phi_change > 1.0e-8
    positive = nmin > 0.0
    conservative = inv_rel < 1.0e-6

    if advance and poisson_responded and positive and conservative:
        summary["classification"] = "ION_ADVANCE_AND_POISSON_RESPONSE_CONFIRMED"
        summary["evidence_valid"] = True
        return summary, 0

    summary["classification"] = "ION_ADVANCE_PARTIAL_OR_UNRESOLVED"
    summary["evidence_valid"] = True
    return summary, 0


def p0() -> None:
    summary = static_contract()
    print("ISSUE253_G1_ION_ADVANCE_P0: PASS")
    print(json.dumps(summary, indent=2, sort_keys=True))


def p1() -> None:
    build()
    script = (
        "set -euo pipefail; "
        "source /environment; "
        "export PYTHONPATH=/workspace; "
        "uv pip install --system --python \"$(command -v python3)\" "
        "-r /workspace/requirements-evidence-engine.txt; "
        "python3 /workspace/bin/physics.py preflight --self-test; "
        "python3 /workspace/bin/physics.py preflight "
        "/workspace/experiments/Issue253_g1_gummel_dt_release/generated_ion_advance/input.i"
    )
    _docker(script)
    print("ISSUE253_G1_ION_ADVANCE_P1: PASS")


def p2() -> None:
    if not GENERATED.exists():
        build()
    script = (
        "set -euo pipefail; "
        "source /environment; "
        "export MOOSE_DIR=/opt/physics_vendor/moose; "
        "export CRANE_DIR=/opt/physics_vendor/crane; "
        "export SQUIRREL_DIR=/opt/physics_vendor/squirrel; "
        "export ZAPDOS_DIR=/opt/physics_vendor/zapdos; "
        "export METHOD=opt; "
        "make -C /workspace/physics_app -j2; "
        "cd /workspace/experiments/Issue253_g1_gummel_dt_release/generated_ion_advance; "
        "/workspace/physics_app/physics-opt --check-input -i input.i"
    )
    _docker(script)
    print("ISSUE253_G1_ION_ADVANCE_P2: PASS")


def p3() -> None:
    if not GENERATED.exists():
        build()
    RESULTS.mkdir(parents=True, exist_ok=True)
    script = (
        "set -euo pipefail; "
        "source /environment; "
        "export MOOSE_DIR=/opt/physics_vendor/moose; "
        "export CRANE_DIR=/opt/physics_vendor/crane; "
        "export SQUIRREL_DIR=/opt/physics_vendor/squirrel; "
        "export ZAPDOS_DIR=/opt/physics_vendor/zapdos; "
        "export METHOD=opt; "
        "cd /workspace/experiments/Issue253_g1_gummel_dt_release/generated_ion_advance; "
        "start=$(python3 -c 'import time; print(time.perf_counter())'); "
        "set +e; /workspace/physics_app/physics-opt -i input.i "
        "> /workspace/experiments/Issue253_g1_gummel_dt_release/results_ion_advance/runtime.log 2>&1; "
        "rc=$?; set -e; "
        "end=$(python3 -c 'import time; print(time.perf_counter())'); "
        "python3 -c \"print(float('$end')-float('$start'))\" "
        "> /workspace/experiments/Issue253_g1_gummel_dt_release/results_ion_advance/elapsed_seconds.txt; "
        "echo $rc > /workspace/experiments/Issue253_g1_gummel_dt_release/results_ion_advance/returncode.txt"
    )
    _docker(script)

    rc = int((RESULTS / "returncode.txt").read_text(encoding="utf-8").strip())
    elapsed = float((RESULTS / "elapsed_seconds.txt").read_text(encoding="utf-8").strip())
    summary, exit_code = analyze_result(rc, elapsed)
    (RESULTS / "ion_advance_analysis.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print("ISSUE253_G1_ION_ADVANCE_CLASSIFICATION:", summary["classification"])
    print(json.dumps(summary, indent=2, sort_keys=True))
    if exit_code:
        raise SystemExit(exit_code)
    print("ISSUE253_G1_ION_ADVANCE_P3: EVIDENCE_READY")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=("p0", "p1", "p2", "p3"), required=True)
    args = parser.parse_args()
    RESULTS.mkdir(parents=True, exist_ok=True)
    {"p0": p0, "p1": p1, "p2": p2, "p3": p3}[args.phase]()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
