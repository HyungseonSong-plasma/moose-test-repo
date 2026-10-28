"""Compile and exercise M4 developer-only source-to-result JSON path.

All collision values are synthetic; no real LXCat download or BOLSIG+ oracle.
"""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess


SYNTHETIC_CROSS_SECTIONS = """ELASTIC
Ar
1.37e-5
Reference: original author synthetic fixture
------
0.0 5e-20
1.0 5e-20
2.0 5e-20
------
EXCITATION
Ar -> Ar_test
0.27
Reference: original author synthetic fixture
------
0.0 0.0
1.0 1e-20
2.0 2e-20
------
"""


def test_bolsig_candidate_export_from_external_text_file(tmp_path: Path) -> None:
    compiler = shutil.which("g++")
    assert compiler, "g++ is required for M4 C++ developer runner"
    root = Path(__file__).resolve().parents[1]
    binary = tmp_path / "candidate"
    command = [
        compiler, "-std=c++17", "-O2", "-Wall", "-Wextra", "-Werror", "-pedantic",
        f"-I{root / 'physics_app/include/utils'}",
        str(root / "physics_app/src/utils/PhysicsBoltzmannElasticSolver.C"),
        str(root / "physics_app/src/utils/PhysicsBoltzmannCrossSections.C"),
        str(root / "physics_app/ci/boltzmann_candidate_export.C"),
        "-o", str(binary),
    ]
    compiled = subprocess.run(command, capture_output=True, text=True)
    assert compiled.returncode == 0, compiled.stdout + compiled.stderr
    source = tmp_path / "external.txt"
    source.write_text(SYNTHETIC_CROSS_SECTIONS, encoding="utf-8")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    cmd = [str(binary), str(source), digest, "0.2", "300", "2", "125", "Ar=1"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    output = json.loads(result.stdout)
    assert output["schema_version"] == 1
    assert output["conditions"]["collision_source_sha256"] == digest
    assert output["conditions"]["model"] == "elastic_excitation_steady_dc"
    assert output["conditions"]["mixture"] == {"Ar": 1.0}
    edges = output["energy_cell_edges_eV"]
    eepf = output["eepf_eV_minus_3_halves"]
    assert len(edges) == 126 and len(eepf) == 125
    norm = sum(v * 2 / 3 * (b**1.5 - a**1.5)
               for v, a, b in zip(eepf, edges, edges[1:]))
    assert abs(norm - 1) < 2e-10
    assert 0 < output["mean_energy_eV"] < 2
    assert output["rates_m3_per_s"]["Ar:excitation:1"] > 0

    malformed = SYNTHETIC_CROSS_SECTIONS.replace("ELASTIC", "EFFECTIVE", 1)
    source.write_text(malformed, encoding="utf-8")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    rejected = subprocess.run(
        [str(binary), str(source), digest, "0.2", "300", "2", "125", "Ar=1"],
        capture_output=True, text=True,
    )
    assert rejected.returncode == 2
    assert rejected.stdout == ""
    assert "BOLTZMANN_CANDIDATE_PREFLIGHT_HOLD" in rejected.stderr
    assert "unsupported" in rejected.stderr
