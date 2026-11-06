"""M4 strict synthetic BOLSIG-format importer and fail-closed cross-section tests.

This verifies native C++ parser/solver integration, not any real LXCat Ar/O2
download, BOLSIG+ numerical oracle, or coupled Physics production runtime.
"""
from pathlib import Path
import shutil
import subprocess


def test_bolsig_collision_text_reader_and_conservative_solver(tmp_path: Path) -> None:
    compiler = shutil.which("g++")
    assert compiler, "g++ is required to validate the standalone C++ Boltzmann importer"
    root = Path(__file__).resolve().parents[1]
    executable = tmp_path / "boltzmann-cross-sections"
    cmd = [
        compiler,
        "-std=c++17", "-O2", "-Wall", "-Wextra", "-Werror", "-pedantic",
        f"-I{root / 'physics_app/include/utils'}",
        str(root / "physics_app/src/utils/PhysicsBoltzmannElasticSolver.C"),
        str(root / "physics_app/src/utils/PhysicsBoltzmannCrossSections.C"),
        str(root / "tests/boltzmann/cross_section_import_test.C"),
        "-o", str(executable),
    ]
    built = subprocess.run(cmd, check=False, text=True, capture_output=True)
    assert built.returncode == 0, built.stdout + built.stderr
    ran = subprocess.run([str(executable)], check=False, text=True, capture_output=True)
    assert ran.returncode == 0, ran.stdout + ran.stderr
    assert "BOLTZMANN_BOLSIG_IMPORT_M4_P0_P1_PASS" in ran.stdout
    assert "BOLTZMANN_IMPORT_MEAN_EV=" in ran.stdout
    assert "BOLTZMANN_IMPORT_NUMBER_BALANCE=" in ran.stdout
