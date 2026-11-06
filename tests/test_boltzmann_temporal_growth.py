"""M6b1 generalized temporal-growth eigenproblem (native C++ reference only).

No production Physics coupling or full excitation/superelastic-growth physics.
"""
from pathlib import Path
import shutil
import subprocess


def test_temporal_growth_generalized_eigenvalue_reference(tmp_path: Path) -> None:
    compiler = shutil.which("g++")
    assert compiler, "g++ is required for native M6b eigenproblem verification"
    root = Path(__file__).resolve().parents[1]
    binary = tmp_path / "temporal_growth"
    build = subprocess.run(
        [
            compiler, "-std=c++17", "-O2", "-Wall", "-Wextra", "-Werror",
            "-pedantic", f"-I{root / 'physics_app/include/utils'}",
            str(root / "physics_app/src/utils/PhysicsBoltzmannElasticSolver.C"),
            str(root / "physics_app/src/utils/PhysicsBoltzmannGrowth.C"),
            str(root / "physics_app/src/utils/PhysicsBoltzmannTemporalGrowth.C"),
            str(root / "tests/boltzmann/temporal_growth_test.C"),
            "-o", str(binary),
        ],
        capture_output=True, text=True, check=False,
    )
    assert build.returncode == 0, build.stdout + build.stderr
    run = subprocess.run([str(binary)], capture_output=True, text=True, check=False)
    assert run.returncode == 0, run.stdout + run.stderr
    assert "BOLTZMANN_TEMPORAL_GROWTH_M6B1_P0_P1_PASS" in run.stdout
    assert "M6B_EIGEN_RESIDUAL=" in run.stdout
