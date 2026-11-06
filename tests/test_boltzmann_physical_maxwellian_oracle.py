"""Scientific S1: independent analytic Maxwellian ion/attachment rate oracle.

The collision cross sections and 3000 K four-species fixture are fully synthetic.
This is *not* BOLSIG+ or experimental Ar/He/N2/O2 validation.
"""
from pathlib import Path
import shutil
import subprocess


def test_manufactured_maxwellian_analytical_growth_and_energy(tmp_path: Path) -> None:
    compiler = shutil.which("g++")
    assert compiler, "g++ needed for independent Maxwellian analytic science gate"
    root = Path(__file__).resolve().parents[1]
    binary = tmp_path / "boltzmann_analytic_oracle"
    cmd = [
        compiler, "-std=c++17", "-O2", "-Wall", "-Wextra", "-Werror", "-pedantic",
        f"-I{root / 'physics_app/include/utils'}",
        str(root / "physics_app/src/utils/PhysicsBoltzmannElasticSolver.C"),
        str(root / "physics_app/src/utils/PhysicsBoltzmannGrowth.C"),
        str(root / "tests/boltzmann/physical_maxwellian_rate_oracle_test.C"),
        "-o", str(binary),
    ]
    build = subprocess.run(cmd, text=True, capture_output=True, check=False)
    assert build.returncode == 0, build.stdout + build.stderr
    run = subprocess.run([str(binary)], text=True, capture_output=True, check=False)
    assert run.returncode == 0, run.stdout + run.stderr
    assert "BOLTZMANN_SCIENCE_ANALYTIC_RATE_PASS" in run.stdout
    assert "MODE=MANUFACTURED_MAXWELLIAN_NOT_BOLSIG_ORACLE" in run.stdout
    results = dict(line.split("=", 1) for line in run.stdout.splitlines() if "=" in line)
    assert float(results["ION_RELATIVE_ERROR_400"]) < 1e-4
    assert float(results["ATT_RELATIVE_ERROR_400"]) < 1e-4
    assert float(results["FOUR_GAS_REDUCED_GROWTH_M3_PER_S"]) > 0
