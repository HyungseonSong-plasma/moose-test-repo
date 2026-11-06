"""P0/P1 native C++ elastic Boltzmann regression, automatically run by pytest.

This does not exercise real PhysicsApp/physics-opt and must not be used as P2/P3.
"""

from pathlib import Path
import shutil
import subprocess


def test_standalone_elastic_boltzmann_core(tmp_path: Path) -> None:
    compiler = shutil.which("g++")
    if compiler is None:
        raise AssertionError("g++ required to validate native Boltzmann kernel")
    root = Path(__file__).resolve().parents[1]
    binary = tmp_path / "boltzmann-elastic-test"
    cmd = [
        compiler,
        "-std=c++17",
        "-O2",
        "-Wall",
        "-Wextra",
        "-Werror",
        "-pedantic",
        f"-I{root / 'physics_app/include/utils'}",
        str(root / "physics_app/src/utils/PhysicsBoltzmannElasticSolver.C"),
        str(root / "tests/boltzmann/elastic_core_test.C"),
        "-o",
        str(binary),
    ]
    compiled = subprocess.run(cmd, capture_output=True, text=True, check=False)
    assert compiled.returncode == 0, compiled.stdout + compiled.stderr
    executed = subprocess.run([str(binary)], capture_output=True, text=True, check=False)
    assert executed.returncode == 0, executed.stdout + executed.stderr
    assert "BOLTZMANN_ELASTIC_P0_P1_PASS" in executed.stdout
    assert "MAXWELL_REFINEMENT_ERRORS=" in executed.stdout
    assert "BOLTZMANN_EXCITATION_M2_P0_P1_PASS" in executed.stdout
    assert "BOLTZMANN_SPARSE_M3_P0_P1_PASS" in executed.stdout
    assert "EXCITATION_ENERGY_BALANCE_ERRORS=" in executed.stdout
    assert "MAX_NORMALIZED_FLUX_RESIDUAL=" in executed.stdout
