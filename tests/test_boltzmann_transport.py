"""M7a EEPF-derived particle and energy transport, native C++ synthetic tests."""
from pathlib import Path
import shutil
import subprocess


def test_eepf_transport_mobility_and_diffusion_without_closure(tmp_path: Path) -> None:
    compiler = shutil.which("g++")
    assert compiler, "native M7 C++ compiler required"
    root = Path(__file__).resolve().parents[1]
    binary = tmp_path / "boltzmann_transport"
    build = subprocess.run(
        [
            compiler, "-std=c++17", "-O2", "-Wall", "-Wextra", "-Werror",
            "-pedantic", f"-I{root / 'physics_app/include/utils'}",
            str(root / "physics_app/src/utils/PhysicsBoltzmannElasticSolver.C"),
            str(root / "physics_app/src/utils/PhysicsBoltzmannTransport.C"),
            str(root / "tests/boltzmann/transport_moments_test.C"),
            "-o", str(binary),
        ],
        capture_output=True, text=True, check=False,
    )
    assert build.returncode == 0, build.stdout + build.stderr
    run = subprocess.run([str(binary)], capture_output=True, text=True, check=False)
    assert run.returncode == 0, run.stdout + run.stderr
    assert "BOLTZMANN_TRANSPORT_M7A_P0_P1_PASS" in run.stdout
    assert "M7_REDUCED_MOBILITY=" in run.stdout
    assert "M7_ENERGY_DIFFUSION_TO_DIFFUSION=" in run.stdout
