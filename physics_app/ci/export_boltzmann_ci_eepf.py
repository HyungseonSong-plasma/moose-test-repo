"""Run the actual development Boltzmann C++ solver in CI and retain its EEPF.

These are *manufactured elastic-only controls*, NOT real-gas BOLSIG parity.
Only source-free numerical vectors and metadata are uploaded as CI artifacts.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess

MODEL = "SYNTHETIC_ELASTIC_ONLY_NOT_BOLSIG_PARITY"
COOLING_MODEL = "SYNTHETIC_ELASTIC_N2_EXCITATION_NOT_BOLSIG_PARITY"
EXPECTED = {
    "example1_R21", "example2_R1_DC", "example3_R31",
    "example3_R33", "example3_R35", "example4_R1",
    "example4_R1_Emax2x", "example4_R1_Emax4x", "example4_R1_Emax8x",
    "example4_R1_SYNTHETIC_N2_1x", "example4_R1_SYNTHETIC_N2_2x",
}


def create_ci_eepf(out: Path) -> dict:
    if out.exists() and any(out.iterdir()):
        raise RuntimeError("refusing to overwrite nonempty EEPF output directory")
    compiler = shutil.which("g++")
    if not compiler:
        raise RuntimeError("g++ required to run native Boltzmann in CI")
    root = Path(__file__).resolve().parents[2]
    build_dir = out.parent / (out.name + "_bin")
    build_dir.mkdir(parents=True, exist_ok=True)
    binary = build_dir / "boltzmann_ci_eepf"
    cmd = [
        compiler, "-std=c++17", "-O2", "-Wall", "-Wextra", "-Werror",
        "-pedantic", f"-I{root / 'physics_app/include/utils'}",
        str(root / "physics_app/src/utils/PhysicsBoltzmannElasticSolver.C"),
        str(root / "physics_app/ci/boltzmann_ci_eepf_controls.C"),
        "-o", str(binary),
    ]
    built = subprocess.run(cmd, capture_output=True, text=True)
    if built.returncode:
        raise RuntimeError("native solver CI compile failed\n" + built.stderr)
    executed = subprocess.run([str(binary)], capture_output=True, text=True)
    if executed.returncode:
        raise RuntimeError("native solver CI execution failed\n" + executed.stderr)
    try:
        runs = [json.loads(line) for line in executed.stdout.splitlines() if line.strip()]
    except json.JSONDecodeError as exc:
        raise RuntimeError("native C++ solver output is not valid JSON") from exc
    if len(runs) != len(EXPECTED) or {r["id"] for r in runs} != EXPECTED:
        raise RuntimeError("native solver EEPF case inventory incomplete")
    out.mkdir(parents=True, exist_ok=True)
    manifest = {
        "status": "CI_NATIVE_SOLVER_EXECUTED_DEVELOPMENT_ONLY",
        "scientific_acceptance": "HOLD_REAL_COLLISION_PROCESS_EQUIVALENCE",
        "model": "MIXED_MANUFACTURED_ELASTIC_AND_N2_EXCITATION_NOT_BOLSIG_PARITY",
        "source": "first-party invented elastic and N2-vibration cross sections",
        "process_limitations": [
            "EFFECTIVE momentum cross sections unsupported",
            "two N2 excitation processes only in explicitly marked synthetic cooling controls",
            "no real EXCITATION/IONIZATION/ATTACHMENT source data in any run",
            "RF reduced angular frequency (Example 2 runs 2+) unsupported",
            "four-component example4 is NOT a validated physical match",
        ],
        "runs": {},
    }
    for run in runs:
        expected_model = (COOLING_MODEL if run["id"].startswith("example4_R1_SYNTHETIC_N2_")
                          else MODEL)
        if run["model"] != expected_model:
            raise RuntimeError("native solver attempted to relabel physics model")
        n = run["cells"]
        eps = run["energy_eV"]
        f = run["eepf_eV_minus_3_halves"]
        if not (len(eps) == len(f) == n and n > 10 and
                all(math.isfinite(v) and v >= 0.0 for v in f)):
            raise RuntimeError(f"invalid EEPF vector for {run['id']}")
        h = run["max_energy_eV"] / n
        if any(abs(eps[i] - (i + 0.5) * h) > 1e-10
               for i in range(n)):
            raise RuntimeError(f"EEPF coordinate mismatch for {run['id']}")
        integral = sum(f[i] * (2 / 3) *
                       (((i + 1) * h)**1.5 - (i * h)**1.5)
                       for i in range(n))
        if abs(integral - 1.0) > 1e-10:
            raise RuntimeError(f"CI EEPF not normalized for {run['id']}: {integral}")
        if not (math.isfinite(run["mean_energy_eV"]) and
                0 < run["mean_energy_eV"] < run["max_energy_eV"]):
            raise RuntimeError("native solver reported nonphysical mean energy")
        if abs(sum(run["mixture"].values()) - 1) > 1e-12:
            raise RuntimeError("native solver returned nonunit gas mixture")
        filename = run["id"] + "_native_eepf.json"
        raw = (json.dumps(run, separators=(",", ":"), sort_keys=True) + "\n").encode()
        (out / filename).write_bytes(raw)
        manifest["runs"][run["id"]] = {
            "file": filename,
            "sha256": hashlib.sha256(raw).hexdigest(),
            "mean_energy_eV": run["mean_energy_eV"],
            "reduced_field_Td": run["reduced_field_Td"],
            "model": expected_model,
            "normalization_integral": integral,
        }
    # Domain truncation is a separate numerical gate. BOLSIG+ selected an
    # energy ceiling where its tail had decayed; our purely elastic synthetic
    # EEPF can remain large at the same ceiling. Never hide this in a plot.
    base = manifest["runs"]["example4_R1"]["mean_energy_eV"]
    twice = manifest["runs"]["example4_R1_Emax2x"]["mean_energy_eV"]
    four = manifest["runs"]["example4_R1_Emax4x"]["mean_energy_eV"]
    eight = manifest["runs"]["example4_R1_Emax8x"]["mean_energy_eV"]
    increase_1x_to_2x = abs(twice - base) / twice
    increase_4x_to_8x = abs(eight - four) / eight
    if not (twice > base and four > twice and eight > four and
            increase_1x_to_2x > 0.05 and increase_4x_to_8x < 1e-3):
        raise RuntimeError(
            "native Boltzmann Example4 cutoff ablation changed unexpectedly")
    manifest["energy_cutoff_diagnostics"] = {
        "example4_1x_mean_energy_eV": base,
        "example4_2x_mean_energy_eV": twice,
        "example4_4x_mean_energy_eV": four,
        "example4_8x_mean_energy_eV": eight,
        "relative_change_1x_to_2x": increase_1x_to_2x,
        "relative_change_4x_to_8x": increase_4x_to_8x,
        "classification": "1X_ENERGY_DOMAIN_TRUNCATION_HOLD",
        "note": "fixed h, identical synthetic collision physics; NOT BOLSIG+ parity",
    }
    # Both experiments use the same input conditions, 200/400 cells and
    # invented constant elastic scattering. Only the two invented vibrational
    # energy-loss channels differ; this is a mechanism check, not a fit to BOLSIG.
    cooling_1x = manifest["runs"]["example4_R1_SYNTHETIC_N2_1x"]["mean_energy_eV"]
    cooling_2x = manifest["runs"]["example4_R1_SYNTHETIC_N2_2x"]["mean_energy_eV"]
    if not (0 < cooling_1x < base and 0 < cooling_2x < twice):
        raise RuntimeError("native Boltzmann N2 inelastic cooling discriminator failed")
    manifest["synthetic_n2_excitation_diagnostic"] = {
        "model": COOLING_MODEL,
        "channels": ["invented vibration threshold 0.3 eV, sigma 5e-20 m2",
                     "invented vibration threshold 1.0 eV, sigma 4e-20 m2"],
        "elastic_only_1x_mean_energy_eV": base,
        "cooling_1x_mean_energy_eV": cooling_1x,
        "elastic_only_2x_mean_energy_eV": twice,
        "cooling_2x_mean_energy_eV": cooling_2x,
        "classification": "SYNTHETIC_COOLING_OPERATOR_TEST_NOT_BOLSIG_PARITY",
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    manifest = create_ci_eepf(args.out)
    print("BOLTZMANN_CI_NATIVE_SOLVER_EXPORTED=" + str(len(manifest["runs"])))
    print("BOLTZMANN_CI_SCIENCE_STATUS=" + manifest["scientific_acceptance"])
    for run, evidence in sorted(manifest["runs"].items()):
        print(f"BOLTZMANN_CI_NATIVE_MEAN_E_EV {run} {evidence['mean_energy_eV']:.8g}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
