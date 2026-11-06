"""M7b numerical proof that excitation/superelastic momentum affects transport."""
from pathlib import Path
import shutil
import subprocess

def test_inelastic_transport_moments(tmp_path: Path) -> None:
    compiler = shutil.which("g++")
    assert compiler, "g++ required"
    root = Path(__file__).resolve().parents[1]
    exe = tmp_path / "m7b"
    build = subprocess.run([
        compiler, "-std=c++17", "-O2", "-Wall", "-Wextra", "-Werror", "-pedantic",
        f"-I{root / 'physics_app/include/utils'}",
        str(root / "physics_app/src/utils/PhysicsBoltzmannElasticSolver.C"),
        str(root / "physics_app/src/utils/PhysicsBoltzmannTransport.C"),
        str(root / "tests/boltzmann/transport_inelastic_test.C"),
        "-o", str(exe),
    ], text=True, capture_output=True)
    assert build.returncode == 0, build.stdout + build.stderr
    ran = subprocess.run([str(exe)], text=True, capture_output=True)
    assert ran.returncode == 0, ran.stdout + ran.stderr
    assert "BOLTZMANN_TRANSPORT_M7B_P0_P1_PASS" in ran.stdout
