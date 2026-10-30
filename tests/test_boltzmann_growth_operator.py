"""M6a independent C++ electron-growth collision operator verification.

Synthetic, frozen EEPF rate and collision-matrix checks, NOT a growth-corrected
self-consistent Boltzmann eigenproblem or a real BOLSIG+ comparison.
"""
from pathlib import Path
import shutil
import subprocess


def test_particle_changing_growth_collision_operator(tmp_path: Path) -> None:
    compiler = shutil.which("g++")
    assert compiler, "g++ required for native M6a Boltzmann collision verification"
    root = Path(__file__).resolve().parents[1]
    binary = tmp_path / "boltzmann_growth"
    build = subprocess.run(
        [
            compiler, "-std=c++17", "-O2", "-Wall", "-Wextra", "-Werror",
            "-pedantic", f"-I{root / 'physics_app/include/utils'}",
            str(root / "physics_app/src/utils/PhysicsBoltzmannElasticSolver.C"),
            str(root / "physics_app/src/utils/PhysicsBoltzmannGrowth.C"),
            str(root / "tests/boltzmann/growth_operator_test.C"),
            "-o", str(binary),
        ],
        capture_output=True, text=True, check=False,
    )
    assert build.returncode == 0, build.stdout + build.stderr
    execute = subprocess.run([str(binary)], capture_output=True, text=True,
                             check=False)
    assert execute.returncode == 0, execute.stdout + execute.stderr
    assert "BOLTZMANN_GROWTH_M6A_P0_P1_PASS" in execute.stdout
    assert "M6_IONIZATION_REDUCED_GROWTH=" in execute.stdout
    assert "M6_ATTACHMENT_REDUCED_GROWTH=" in execute.stdout
