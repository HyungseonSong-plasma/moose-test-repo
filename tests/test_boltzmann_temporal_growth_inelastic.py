"""M6b2 coupled excitation/superelastic temporal growth with independent native tests."""
from pathlib import Path
import shutil
import subprocess

def test_coupled_temporal_growth_inelastic_eigenproblem(tmp_path: Path) -> None:
    compiler = shutil.which("g++")
    assert compiler, "g++ required for bounded M6b2 native eigen solver"
    root = Path(__file__).resolve().parents[1]
    exe = tmp_path / "growth_m6b2"
    build = subprocess.run([
        compiler, "-std=c++17", "-O2", "-Wall", "-Wextra", "-Werror", "-pedantic",
        f"-I{root / 'physics_app/include/utils'}",
        str(root / "physics_app/src/utils/PhysicsBoltzmannElasticSolver.C"),
        str(root / "physics_app/src/utils/PhysicsBoltzmannGrowth.C"),
        str(root / "physics_app/src/utils/PhysicsBoltzmannTemporalGrowth.C"),
        str(root / "tests/boltzmann/temporal_growth_inelastic_test.C"),
        "-o", str(exe),
    ], capture_output=True, text=True)
    assert build.returncode == 0, build.stdout + build.stderr
    result = subprocess.run([str(exe)], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "BOLTZMANN_TEMPORAL_GROWTH_M6B2_P0_P1_PASS" in result.stdout
