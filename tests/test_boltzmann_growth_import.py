"""M6a entire synthetic BOLSIG-format import into particle-changing core."""
from pathlib import Path
import shutil
import subprocess


def test_bolsig_growth_full_mechanism_import(tmp_path: Path) -> None:
    compiler = shutil.which("g++")
    assert compiler, "g++ required to verify M6 native cross-section import"
    root = Path(__file__).resolve().parents[1]
    out = tmp_path / "boltzmann_growth_import"
    built = subprocess.run(
        [
            compiler, "-std=c++17", "-O2", "-Wall", "-Wextra", "-Werror",
            "-pedantic", f"-I{root / 'physics_app/include/utils'}",
            str(root / "physics_app/src/utils/PhysicsBoltzmannElasticSolver.C"),
            str(root / "physics_app/src/utils/PhysicsBoltzmannGrowth.C"),
            str(root / "physics_app/src/utils/PhysicsBoltzmannCrossSections.C"),
            str(root / "tests/boltzmann/growth_import_test.C"),
            "-o", str(out),
        ],
        capture_output=True, text=True, check=False,
    )
    assert built.returncode == 0, built.stdout + built.stderr
    ran = subprocess.run([str(out)], capture_output=True, text=True, check=False)
    assert ran.returncode == 0, ran.stdout + ran.stderr
    assert "BOLTZMANN_GROWTH_M6_IMPORT_P0_P1_PASS" in ran.stdout
