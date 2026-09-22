#!/usr/bin/env python3
"""Issue #309 exact-head validation for standard-MOOSE sheath refactor."""
from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
LOCK = ROOT / "physics_app" / "dependencies.lock"
RESULTS = ROOT / "issue309-refactor-results"

LEGACY_PATHS = (
    "physics_app/include/fvbcs/PhysicsFVElectronGroundedSheathCollectionBC.h",
    "physics_app/src/fvbcs/PhysicsFVElectronGroundedSheathCollectionBC.C",
    "physics_app/include/fvbcs/PhysicsFVElectronGroundedSheathEnergyBC.h",
    "physics_app/src/fvbcs/PhysicsFVElectronGroundedSheathEnergyBC.C",
    "physics_app/include/fvbcs/PhysicsGroundedElectronSheathFlux.h",
)
LIVE_CONSUMERS = (
    "experiments/Issue27_surface_reactions/controlled_wall/issue215_sheath_particle_core.py",
    ".github/scripts/issue215_sheath_particle.py",
    "experiments/Issue217_sheath_energy_closure/run.py",
    "physics_app/ci/electron_sheath_collection_smoke.i",
    "physics_app/ci/electron_grounded_sheath_energy_smoke.i",
    "physics_app/ci/check_electron_molar_representation_contract.py",
)
LEGACY_TOKENS = (
    "PhysicsFVElectronGroundedSheathCollectionBC",
    "PhysicsFVElectronGroundedSheathEnergyBC",
    "PhysicsGroundedElectronSheathFlux.h",
    "PhysicsGroundedElectronSheath::",
)
GENERIC_HEADER = ROOT / "physics_app/include/fvbcs/PhysicsFVCellFunctorNeumannBC.h"
GENERIC_SOURCE = ROOT / "physics_app/src/fvbcs/PhysicsFVCellFunctorNeumannBC.C"


def _run(command: list[str], *, cwd: Path | None = None) -> None:
    print("+", " ".join(command), flush=True)
    subprocess.run(command, cwd=cwd or ROOT, check=True)


def _build_base_ref() -> str:
    values: dict[str, str] = {}
    for raw in LOCK.read_text(encoding="utf-8").splitlines():
        if "=" in raw and not raw.lstrip().startswith("#"):
            key, value = raw.split("=", 1)
            values[key.strip()] = value.strip()
    ref = values.get("PHYSICS_BUILD_BASE", "")
    if "@sha256:" not in ref:
        raise RuntimeError("immutable PHYSICS_BUILD_BASE ref missing")
    return ref


def _docker(script: str) -> None:
    ref = _build_base_ref()
    _run(["docker", "pull", ref])
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
            f"{ROOT}:/workspace",
            ref,
            "-lc",
            script,
        ]
    )


def static() -> None:
    checks: dict[str, bool] = {}
    for rel in LEGACY_PATHS:
        checks[f"retired::{rel}"] = not (ROOT / rel).exists()

    for rel in LIVE_CONSUMERS:
        text = (ROOT / rel).read_text(encoding="utf-8")
        checks[f"no_legacy_token::{rel}"] = not any(token in text for token in LEGACY_TOKENS)

    header = GENERIC_HEADER.read_text(encoding="utf-8")
    source = GENERIC_SOURCE.read_text(encoding="utf-8")
    checks.update(
        {
            "generic_adapter_registered": 'registerMooseObject("PhysicsApp", PhysicsFVCellFunctorNeumannBC)' in source,
            "generic_adapter_cell_side": "elemArg()" in source and "neighborArg()" in source,
            "generic_adapter_not_face_side": "singleSidedFaceArg" not in source,
            "generic_adapter_functor": 'getFunctor<ADReal>("functor")' in source,
            "generic_adapter_factor": 'getFunctor<ADReal>("factor")' in source,
            "generic_adapter_no_sheath_semantics": not any(
                token in (header + source).lower()
                for token in ("groundedsheath", "boltzmann", "electron_temperature", "primaryparticleflux", "primaryenergyflux")
            ),
        }
    )

    for rel in (
        "experiments/Issue27_surface_reactions/controlled_wall/issue215_sheath_particle_core.py",
        ".github/scripts/issue215_sheath_particle.py",
        "experiments/Issue217_sheath_energy_closure/run.py",
        "physics_app/ci/check_electron_molar_representation_contract.py",
    ):
        ast.parse((ROOT / rel).read_text(encoding="utf-8"), filename=rel)
        checks[f"python_syntax::{rel}"] = True

    _run(["python3", "physics_app/ci/check_electron_molar_representation_contract.py", "--self-test"])
    _run(["python3", "physics_app/ci/check_electron_molar_representation_contract.py"])

    failed = sorted(name for name, ok in checks.items() if not ok)
    RESULTS.mkdir(exist_ok=True)
    report = {
        "issue": 309,
        "phase": "STATIC",
        "classification": "PASS" if not failed else "FAIL",
        "checks": checks,
        "failed_checks": failed,
        "capability_classification": "REPRESENTATION_MISMATCH_REQUIRES_THIN_ADAPTER",
        "target_owner": "ADParsedFunctorMaterial + PhysicsFVCellFunctorNeumannBC",
    }
    (RESULTS / "static.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    if failed:
        raise SystemExit(f"static validation failed: {failed}")
    print("ISSUE309_STATIC=PASS")


def build_check() -> None:
    RESULTS.mkdir(exist_ok=True)
    script = r"""
set -euo pipefail
source /environment
git config --global --add safe.directory /workspace
export MOOSE_DIR=/opt/physics_vendor/moose
export CRANE_DIR=/opt/physics_vendor/crane
export SQUIRREL_DIR=/opt/physics_vendor/squirrel
export ZAPDOS_DIR=/opt/physics_vendor/zapdos
export METHOD=opt
export PYTHONPATH=/workspace
make -C /workspace/physics_app -j2
test -x /workspace/physics_app/physics-opt
python3 /workspace/.github/scripts/issue215_sheath_particle.py --self-test
python3 /workspace/experiments/Issue217_sheath_energy_closure/run.py --self-test
/workspace/physics_app/physics-opt --check-input -i /workspace/physics_app/ci/electron_sheath_collection_smoke.i
/workspace/physics_app/physics-opt --check-input -i /workspace/physics_app/ci/electron_grounded_sheath_energy_smoke.i
"""
    _docker(script)
    report = {
        "issue": 309,
        "phase": "BUILD_CHECK",
        "classification": "PASS",
        "unity_build": "PASS",
        "issue215_self_test": "PASS",
        "issue217_self_test": "PASS",
        "particle_smoke_check_input": "PASS",
        "energy_smoke_check_input": "PASS",
    }
    (RESULTS / "build_check.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print("ISSUE309_BUILD_CHECK=PASS")


def runtime() -> None:
    RESULTS.mkdir(exist_ok=True)
    script = r"""
set -euo pipefail
source /environment
git config --global --add safe.directory /workspace
export MOOSE_DIR=/opt/physics_vendor/moose
export CRANE_DIR=/opt/physics_vendor/crane
export SQUIRREL_DIR=/opt/physics_vendor/squirrel
export ZAPDOS_DIR=/opt/physics_vendor/zapdos
export METHOD=opt
export PYTHONPATH=/workspace
test -x /workspace/physics_app/physics-opt
rm -rf /workspace/issue215-sheath-particle-results
rm -rf /workspace/issue217-sheath-energy-results
python3 /workspace/.github/scripts/issue215_sheath_particle.py
python3 /workspace/experiments/Issue217_sheath_energy_closure/run.py   --physics-opt /workspace/physics_app/physics-opt   --results-root /workspace/issue217-sheath-energy-results   --timeout 1200
"""
    _docker(script)

    issue215 = json.loads(
        (ROOT / "issue215-sheath-particle-results/summary.json").read_text(encoding="utf-8")
    )
    issue217 = json.loads(
        (ROOT / "issue217-sheath-energy-results/summary.json").read_text(encoding="utf-8")
    )
    checks = {
        "issue215_accepted": issue215.get("scientific_hard_pass") is True,
        "issue217_accepted": issue217.get("decision", {}).get("scientific_hard_pass") is True,
    }
    failed = sorted(name for name, ok in checks.items() if not ok)
    report = {
        "issue": 309,
        "phase": "RUNTIME",
        "classification": "MIGRATION_PARITY_PASS" if not failed else "MIGRATION_PARITY_FAIL",
        "checks": checks,
        "issue215_status": issue215.get("status"),
        "issue217_status": issue217.get("status"),
        "failed_checks": failed,
        "scientific_claim": "preserve accepted Issue215/217 contracts only; no new physics claim",
    }
    (RESULTS / "runtime.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    if failed:
        raise SystemExit(f"runtime parity failed: {failed}")
    print("ISSUE309_RUNTIME_PARITY=PASS")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", required=True, choices=("static", "build-check", "runtime"))
    args = parser.parse_args()
    {"static": static, "build-check": build_check, "runtime": runtime}[args.phase]()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
