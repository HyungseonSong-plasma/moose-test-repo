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
        str(root / "physics_app/src/utils/PhysicsBoltzmannGrowth.C"),
        str(root / "physics_app/src/utils/PhysicsBoltzmannTemporalGrowth.C"),
        str(root / "physics_app/src/utils/PhysicsBoltzmannTransport.C"),
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

    # A complete EFFECTIVE record includes excitation momentum once. This
    # deliberately constructed source is mathematically equivalent to the
    # original ELASTIC + EXCITATION source; it must not be rejected solely
    # because its momentum provider is typed EFFECTIVE.
    equivalent = SYNTHETIC_CROSS_SECTIONS.replace("ELASTIC", "EFFECTIVE", 1)
    equivalent = equivalent.replace(
        "0.0 5e-20\n1.0 5e-20\n2.0 5e-20\n",
        "0.0 5e-20\n1.0 6e-20\n2.0 7e-20\n", 1,
    )
    source.write_text(equivalent, encoding="utf-8")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    accepted = subprocess.run(
        [str(binary), str(source), digest, "0.2", "300", "2", "125", "Ar=1"],
        capture_output=True, text=True,
    )
    assert accepted.returncode == 0, accepted.stdout + accepted.stderr
    effective_output = json.loads(accepted.stdout)
    assert abs(effective_output["mean_energy_eV"] - output["mean_energy_eV"]) < 1e-10
    for a, b in zip(effective_output["eepf_eV_minus_3_halves"], eepf):
        assert abs(a - b) <= 1e-9 * max(1.0, abs(b))
    assert abs(
        effective_output["rates_m3_per_s"]["Ar:excitation:1"] -
        output["rates_m3_per_s"]["Ar:excitation:1"]
    ) < 1e-9 * output["rates_m3_per_s"]["Ar:excitation:1"]

    # Instead of blanket-rejecting EFFECTIVE, fail on impossible physics:
    # the summed inelastic cross sections exceed total effective momentum.
    malformed = equivalent.replace("2.0 7e-20", "2.0 1e-21", 1)
    source.write_text(malformed, encoding="utf-8")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    rejected = subprocess.run(
        [str(binary), str(source), digest, "0.2", "300", "2", "125", "Ar=1"],
        capture_output=True, text=True,
    )
    assert rejected.returncode == 2
    assert rejected.stdout == ""
    assert "BOLTZMANN_CANDIDATE_PREFLIGHT_HOLD" in rejected.stderr
    assert "EFFECTIVE momentum smaller" in rejected.stderr


def test_reversible_candidate_requires_opt_in_and_explicit_upper_population(tmp_path: Path) -> None:
    """Synthetic detailed-balance fixture, not actual Ar cross sections."""
    import math

    compiler = shutil.which("g++")
    assert compiler
    root = Path(__file__).resolve().parents[1]
    binary = tmp_path / "candidate-reversible"
    cmd = [
        compiler, "-std=c++17", "-O2", "-Wall", "-Wextra", "-Werror", "-pedantic",
        f"-I{root / 'physics_app/include/utils'}",
        str(root / "physics_app/src/utils/PhysicsBoltzmannElasticSolver.C"),
        str(root / "physics_app/src/utils/PhysicsBoltzmannGrowth.C"),
        str(root / "physics_app/src/utils/PhysicsBoltzmannTemporalGrowth.C"),
        str(root / "physics_app/src/utils/PhysicsBoltzmannTransport.C"),
        str(root / "physics_app/src/utils/PhysicsBoltzmannCrossSections.C"),
        str(root / "physics_app/ci/boltzmann_candidate_export.C"),
        "-o", str(binary),
    ]
    built = subprocess.run(cmd, capture_output=True, text=True)
    assert built.returncode == 0, built.stdout + built.stderr
    source = tmp_path / "external-reversible.txt"
    source.write_text(
        "SYNTHETIC ONLY, NO LXCAT DATA\n"
        "ELASTIC\nAr\n1.37e-5\nsynthetic lower\n------\n0 5e-20\n10 5e-20\n------\n"
        "ELASTIC\nAr*\n1.37e-5\nsynthetic upper\n------\n0 5e-20\n10 5e-20\n------\n"
        "EXCITATION\nAr <-> Ar*\n0.4 2.0\nsynthetic reversible\n------\n"
        "0 0\n0.4 0\n0.401 1e-20\n10 1e-20\n------\n",
        encoding="utf-8",
    )
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    theta = 1.380649e-23 * 12000.0 / 1.602176634e-19
    ratio = 2.0 * math.exp(-0.4 / theta)
    lower, upper = 1 / (1 + ratio), ratio / (1 + ratio)
    args = [str(binary), str(source), digest, "0", "12000", "10", "125",
            f"Ar={lower:.17g}", f"Ar*={upper:.17g}"]
    denied = subprocess.run(args, capture_output=True, text=True)
    assert denied.returncode == 2
    assert "explicit opt-in" in denied.stderr

    accepted = subprocess.run(args + ["--enable-superelastic"],
                              capture_output=True, text=True)
    assert accepted.returncode == 0, accepted.stdout + accepted.stderr
    result = json.loads(accepted.stdout)
    assert result["conditions"]["model"] == "elastic_excitation_superelastic_steady_dc"
    rates = result["rates_m3_per_s"]
    assert rates["Ar:excitation:1"] > 0
    assert rates["Ar*:superelastic:1"] > 0
    weighted_forward = lower * rates["Ar:excitation:1"]
    weighted_reverse = upper * rates["Ar*:superelastic:1"]
    assert abs(weighted_forward - weighted_reverse) / weighted_forward < 0.025

    no_upper = subprocess.run(args[:-1] + ["Ar=1.0", "--enable-superelastic"],
                              capture_output=True, text=True)
    assert no_upper.returncode == 2
    assert "PREFLIGHT_HOLD" in no_upper.stderr


def test_frozen_particle_growth_diagnostic_does_not_claim_selfconsistent_eepf(tmp_path: Path) -> None:
    compiler = shutil.which("g++")
    assert compiler
    root = Path(__file__).resolve().parents[1]
    binary = tmp_path / "candidate_growth"
    build = subprocess.run([
        compiler, "-std=c++17", "-O2", "-Wall", "-Wextra", "-Werror", "-pedantic",
        f"-I{root / 'physics_app/include/utils'}",
        str(root / "physics_app/src/utils/PhysicsBoltzmannElasticSolver.C"),
        str(root / "physics_app/src/utils/PhysicsBoltzmannGrowth.C"),
        str(root / "physics_app/src/utils/PhysicsBoltzmannTemporalGrowth.C"),
        str(root / "physics_app/src/utils/PhysicsBoltzmannTransport.C"),
        str(root / "physics_app/src/utils/PhysicsBoltzmannCrossSections.C"),
        str(root / "physics_app/ci/boltzmann_candidate_export.C"),
        "-o", str(binary),
    ], capture_output=True, text=True)
    assert build.returncode == 0, build.stdout + build.stderr

    source = tmp_path / "synthetic_growth.txt"
    source.write_text(
        "SYNTHETIC ONLY\n"
        "ELASTIC\nAr\n1.37e-5\ninvented, not LXCat\n------\n0 5e-20\n2 5e-20\n------\n"
        "ELASTIC\nO2\n3.4e-5\ninvented, not LXCat\n------\n0 6e-20\n2 6e-20\n------\n"
        "EXCITATION\nAr -> Ar_exc\n0.25\ninvented\n------\n"
        "0 0\n0.25 0\n2 1e-20\n------\n"
        "IONIZATION\nAr -> Ar_plus\n0.65\ninvented\n------\n"
        "0 0\n0.65 0\n2 1e-20\n------\n"
        "ATTACHMENT\nO2 -> O2_minus\ninvented\n------\n"
        "0 0.2e-20\n2 0.2e-20\n------\n",
        encoding="utf-8",
    )
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    args = [str(binary), str(source), digest, "0.1", "3000", "2", "100",
            "Ar=0.7", "O2=0.3"]
    denied = subprocess.run(args, capture_output=True, text=True)
    assert denied.returncode == 2
    assert "unsupported" in denied.stderr

    permitted = subprocess.run(args + ["--diagnose-frozen-growth"],
                               capture_output=True, text=True)
    assert permitted.returncode == 0, permitted.stdout + permitted.stderr
    obj = json.loads(permitted.stdout)
    assert obj["conditions"]["model"] == "elastic_excitation_frozen_growth_diagnostic"
    assert "frozen_eepf_reduced_temporal_growth_m3_per_s" in obj
    assert obj["rates_m3_per_s"]["Ar:ionization:1"] > 0
    assert obj["rates_m3_per_s"]["O2:attachment:1"] > 0
    expected = (0.7 * obj["rates_m3_per_s"]["Ar:ionization:1"] -
                0.3 * obj["rates_m3_per_s"]["O2:attachment:1"])
    assert abs(expected - obj["frozen_eepf_reduced_temporal_growth_m3_per_s"]) < (
        1e-12 * (abs(expected) + 1e-30)
    )

    # Bounded full-process EFFECTIVE equivalence: synthetic Ar effective
    # momentum = elastic + excitation + ionization. O2 has ELASTIC +
    # attachment. All source processes are retained, none silently dropped.
    effective_text = source.read_text().replace(
        "ELASTIC\nAr\n1.37e-5\ninvented, not LXCat\n------\n0 5e-20\n2 5e-20\n------\n",
        "EFFECTIVE\nAr\n1.37e-5\ninvented total momentum\n------\n"
        "0 5e-20\n0.25 5e-20\n0.65 5.228571428571429e-20\n"
        "2 7e-20\n------\n",
        1,
    )
    assert effective_text != source.read_text()
    eff_source = tmp_path / "synthetic_effective_full.txt"
    eff_source.write_text(effective_text, encoding="utf-8")
    eff_digest = hashlib.sha256(eff_source.read_bytes()).hexdigest()
    eff_args = [str(binary), str(eff_source), eff_digest, "0.1", "3000",
                "2", "100", "Ar=0.7", "O2=0.3"]
    matched = subprocess.run(eff_args + ["--diagnose-frozen-growth"],
                             capture_output=True, text=True)
    assert matched.returncode == 0, matched.stdout + matched.stderr
    eff_obj = json.loads(matched.stdout)
    assert abs(eff_obj["mean_energy_eV"] - obj["mean_energy_eV"]) < 1e-8

    # 07/2024 boundary opt-in: preserve a pair of inaccessible, well-
    # defined positive-threshold source records rather than deleting them.
    # The active EEPF and rate diagnostics remain unchanged by zero-rate
    # processes above the finite energy ceiling.
    high_source = tmp_path / "synthetic_high_threshold_2024.txt"
    high_source.write_text(
        source.read_text()
        + "EXCITATION\nAr -> high\n19.8\ninvented\n------\n"
          "19.8 0\n24 2e-20\n------\n"
        + "IONIZATION\nAr -> high+\n24.58\ninvented\n------\n"
          "24.58 0\n30 2e-20\n------\n",
        encoding="utf-8",
    )
    high_sha = hashlib.sha256(high_source.read_bytes()).hexdigest()
    high_args = [str(binary), str(high_source), high_sha, "0.1", "3000",
                 "2", "100", "Ar=0.7", "O2=0.3"]
    no_opt_in = subprocess.run(high_args + ["--diagnose-frozen-growth"],
                               capture_output=True, text=True)
    assert no_opt_in.returncode == 2
    high = subprocess.run(
        high_args + ["--diagnose-frozen-growth", "--bolsig-2024-boundaries"],
        capture_output=True, text=True,
    )
    assert high.returncode == 0, high.stdout + high.stderr
    audited = json.loads(high.stdout)
    assert audited["source_process_count"] == 7
    assert audited["scientific_acceptance"].startswith("HOLD_")
    assert len(audited["inactive_above_energy_ceiling"]) == 2
    assert [entry["kind"] for entry in audited["inactive_above_energy_ceiling"]] == [
        "EXCITATION", "IONIZATION",
    ]
    assert sum(":inactive_above_emax:" in key for key in
               audited["rates_m3_per_s"]) == 2
    assert abs(audited["mean_energy_eV"] - obj["mean_energy_eV"]) < 1e-8

    for key in obj["rates_m3_per_s"]:
        assert abs(eff_obj["rates_m3_per_s"][key] - obj["rates_m3_per_s"][key]) < (
            1e-7 * max(obj["rates_m3_per_s"][key], 1e-40)
        )



def test_elastic_selfconsistent_growth_cli_is_different_from_frozen_rates(tmp_path: Path) -> None:
    compiler = shutil.which("g++")
    assert compiler
    root = Path(__file__).resolve().parents[1]
    binary = tmp_path / "candidate_eigen"
    compiled = subprocess.run([
        compiler, "-std=c++17", "-O2", "-Wall", "-Wextra", "-Werror", "-pedantic",
        f"-I{root / 'physics_app/include/utils'}",
        str(root / "physics_app/src/utils/PhysicsBoltzmannElasticSolver.C"),
        str(root / "physics_app/src/utils/PhysicsBoltzmannGrowth.C"),
        str(root / "physics_app/src/utils/PhysicsBoltzmannTemporalGrowth.C"),
        str(root / "physics_app/src/utils/PhysicsBoltzmannTransport.C"),
        str(root / "physics_app/src/utils/PhysicsBoltzmannCrossSections.C"),
        str(root / "physics_app/ci/boltzmann_candidate_export.C"),
        "-o", str(binary),
    ], capture_output=True, text=True)
    assert compiled.returncode == 0, compiled.stdout + compiled.stderr

    source = tmp_path / "elastic_ion.txt"
    source.write_text(
        "ONLY SYNTHETIC NON-LXCAT CROSS SECTIONS\n"
        "ELASTIC\nAr\n1.37e-5\ninvented elastic\n------\n"
        "0 5e-20\n2 5e-20\n------\n"
        "IONIZATION\nAr -> Ar_test_plus\n0.35\ninvented ionization\n------\n"
        "0 1e-20\n2 1e-20\n------\n",
        encoding="utf-8",
    )
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    args = [str(binary), str(source), digest, "0.1", "3000", "2", "50", "Ar=1"]

    default = subprocess.run(args, capture_output=True, text=True)
    assert default.returncode == 2 and "unsupported" in default.stderr

    frozen = subprocess.run(args + ["--diagnose-frozen-growth"],
                            capture_output=True, text=True)
    assert frozen.returncode == 0, frozen.stdout + frozen.stderr
    frozen_data = json.loads(frozen.stdout)
    assert frozen_data["conditions"]["model"] == "elastic_excitation_frozen_growth_diagnostic"

    eigen = subprocess.run(args + ["--solve-elastic-temporal-growth"],
                           capture_output=True, text=True)
    assert eigen.returncode == 0, eigen.stdout + eigen.stderr
    result = json.loads(eigen.stdout)
    assert result["conditions"]["model"] == "elastic_ionization_attachment_temporal_growth_eigen_dense"
    assert result["reduced_temporal_growth_eigenvalue_m3_per_s"] > 0
    assert result["generalized_eigen_residual"] < 1e-8
    assert 0 < result["eigen_inverse_iterations"] <= 8000
    assert result["rates_m3_per_s"]["Ar:ionization:1"] > 0
    assert abs(result["reduced_temporal_growth_eigenvalue_m3_per_s"] -
               result["rates_m3_per_s"]["Ar:ionization:1"]) < (
        1e-11 * result["rates_m3_per_s"]["Ar:ionization:1"]
    )

    rejected = subprocess.run(args + ["--solve-elastic-temporal-growth",
                                     "--diagnose-frozen-growth"],
                              capture_output=True, text=True)
    assert rejected.returncode == 2
    assert "incompatible" in rejected.stderr

    high_n = subprocess.run(
        args[:6] + ["257", "Ar=1", "--solve-elastic-temporal-growth"],
        capture_output=True, text=True,
    )
    assert high_n.returncode == 2
    assert "256" in high_n.stderr


def test_elastic_mobility_diffusion_json_cli_is_separate_from_inelastic(tmp_path: Path) -> None:
    compiler = shutil.which("g++")
    assert compiler
    root = Path(__file__).resolve().parents[1]
    binary = tmp_path / "elastic_transport"
    build = subprocess.run([
        compiler, "-std=c++17", "-O2", "-Wall", "-Wextra", "-Werror", "-pedantic",
        f"-I{root / 'physics_app/include/utils'}",
        str(root / "physics_app/src/utils/PhysicsBoltzmannElasticSolver.C"),
        str(root / "physics_app/src/utils/PhysicsBoltzmannGrowth.C"),
        str(root / "physics_app/src/utils/PhysicsBoltzmannTemporalGrowth.C"),
        str(root / "physics_app/src/utils/PhysicsBoltzmannTransport.C"),
        str(root / "physics_app/src/utils/PhysicsBoltzmannCrossSections.C"),
        str(root / "physics_app/ci/boltzmann_candidate_export.C"),
        "-o", str(binary),
    ], capture_output=True, text=True)
    assert build.returncode == 0, build.stdout + build.stderr

    source = tmp_path / "synthetic_elastic.txt"
    source.write_text(
        "SYNTHETIC NOT LXCAT\n"
        "ELASTIC\nAr\n1.37e-5\noriginal artificial datum\n------\n"
        "0 5e-20\n3 5e-20\n------\n",
        encoding="utf-8",
    )
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    args = [str(binary), str(source), digest, "0", "3000", "3", "200",
            "Ar=1", "--report-elastic-transport"]
    run = subprocess.run(args, capture_output=True, text=True)
    assert run.returncode == 0, run.stdout + run.stderr
    payload = json.loads(run.stdout)
    assert payload["conditions"]["model"] == "elastic_dc_transport_moments"
    trans = payload["elastic_transport"]
    assert trans["mobility_times_N_per_m_V_s"] > 0
    assert trans["diffusion_times_N_per_m_s"] > 0
    assert trans["energy_diffusion_times_N_per_m_s"] > 0
    assert trans["tail_ratio"] < 1e-3
    theta = 1.380649e-23 * 3000 / 1.602176634e-19
    assert abs(trans["diffusion_times_N_per_m_s"] /
               trans["mobility_times_N_per_m_V_s"] - theta) < 0.01 * theta
    wrong = subprocess.run(args + ["--diagnose-frozen-growth"],
                           capture_output=True, text=True)
    assert wrong.returncode == 2 and "incompatible" in wrong.stderr


def test_coupled_excitation_superelastic_ionization_eigen_cli(tmp_path: Path) -> None:
    compiler = shutil.which("g++")
    assert compiler
    root = Path(__file__).resolve().parents[1]
    binary = tmp_path / "coupled_growth"
    built = subprocess.run([
        compiler, "-std=c++17", "-O2", "-Wall", "-Wextra", "-Werror", "-pedantic",
        f"-I{root / 'physics_app/include/utils'}",
        str(root / "physics_app/src/utils/PhysicsBoltzmannElasticSolver.C"),
        str(root / "physics_app/src/utils/PhysicsBoltzmannGrowth.C"),
        str(root / "physics_app/src/utils/PhysicsBoltzmannTemporalGrowth.C"),
        str(root / "physics_app/src/utils/PhysicsBoltzmannTransport.C"),
        str(root / "physics_app/src/utils/PhysicsBoltzmannCrossSections.C"),
        str(root / "physics_app/ci/boltzmann_candidate_export.C"),
        "-o", str(binary),
    ], capture_output=True, text=True)
    assert built.returncode == 0, built.stdout + built.stderr
    source = tmp_path / "synthetic_full.txt"
    source.write_text(
        "SYNTHETIC ONLY; NEVER LXCAT\n"
        "ELASTIC\nlower\n1.37e-5\nsynthetic\n------\n0 5e-20\n3 5e-20\n------\n"
        "ELASTIC\nupper\n1.37e-5\nsynthetic\n------\n0 5e-20\n3 5e-20\n------\n"
        "EXCITATION\nlower <-> upper\n0.4 2.0\nsynthetic\n------\n"
        "0 0\n0.4 0\n0.41 9e-21\n3 9e-21\n------\n"
        "IONIZATION\nlower -> ion\n0.7\nsynthetic\n------\n"
        "0 0\n0.7 0\n0.71 2e-20\n3 2e-20\n------\n"
        "ATTACHMENT\nlower -> negative\nsynthetic\n------\n"
        "0 1e-22\n3 1e-22\n------\n",
        encoding="utf-8",
    )
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    args = [str(binary), str(source), digest, "0.2", "3000", "3", "50",
            "lower=0.96", "upper=0.04"]
    reject = subprocess.run(args + ["--solve-coupled-temporal-growth"],
                            capture_output=True, text=True)
    assert reject.returncode == 2 and "opt-in" in reject.stderr
    run = subprocess.run(args + ["--enable-superelastic",
                                 "--solve-coupled-temporal-growth"],
                         capture_output=True, text=True)
    assert run.returncode == 0, run.stdout + run.stderr
    result = json.loads(run.stdout)
    assert result["conditions"]["model"] == "elastic_excitation_superelastic_temporal_growth_eigen_dense"
    assert result["generalized_eigen_residual"] < 1e-8
    import math
    assert math.isfinite(result["reduced_temporal_growth_eigenvalue_m3_per_s"])
    rates = result["rates_m3_per_s"]
    assert rates["lower:excitation:1"] > 0
    assert rates["upper:superelastic:1"] > 0
    assert rates["lower:ionization:1"] > 0
    assert rates["lower:attachment:1"] > 0
    expected = 0.96 * (rates["lower:ionization:1"] -
                       rates["lower:attachment:1"])
    assert abs(result["reduced_temporal_growth_eigenvalue_m3_per_s"] - expected) < (
        1e-10 * abs(expected)
    )


def test_inelastic_transport_cli_and_superelastic_opt_in(tmp_path: Path) -> None:
    compiler = shutil.which("g++")
    assert compiler
    root = Path(__file__).resolve().parents[1]
    binary = tmp_path / "inelastic_transport"
    built = subprocess.run([
        compiler, "-std=c++17", "-O2", "-Wall", "-Wextra", "-Werror", "-pedantic",
        f"-I{root / 'physics_app/include/utils'}",
        str(root / "physics_app/src/utils/PhysicsBoltzmannElasticSolver.C"),
        str(root / "physics_app/src/utils/PhysicsBoltzmannGrowth.C"),
        str(root / "physics_app/src/utils/PhysicsBoltzmannTemporalGrowth.C"),
        str(root / "physics_app/src/utils/PhysicsBoltzmannTransport.C"),
        str(root / "physics_app/src/utils/PhysicsBoltzmannCrossSections.C"),
        str(root / "physics_app/ci/boltzmann_candidate_export.C"),
        "-o", str(binary),
    ], capture_output=True, text=True)
    assert built.returncode == 0, built.stdout + built.stderr
    source = tmp_path / "excitation_only.txt"
    source.write_text(
        "SYNTHETIC INELASTIC TRANSPORT ONLY\n"
        "ELASTIC\nlower\n1.37e-5\ninvented\n------\n"
        "0 5e-20\n4 5e-20\n------\n"
        "EXCITATION\nlower -> lower_excited\n0.4\ninvented\n------\n"
        "0 0\n0.4 0\n0.41 2e-20\n4 2e-20\n------\n",
        encoding="utf-8",
    )
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    args = [str(binary), str(source), digest, "0", "3000", "4", "200", "lower=1"]
    denied = subprocess.run(args + ["--report-elastic-transport"],
                            capture_output=True, text=True)
    assert denied.returncode == 2 and "elastic-only" in denied.stderr
    accepted = subprocess.run(args + ["--report-inelastic-transport"],
                              capture_output=True, text=True)
    assert accepted.returncode == 0, accepted.stdout + accepted.stderr
    obj = json.loads(accepted.stdout)
    assert obj["conditions"]["model"] == "elastic_excitation_superelastic_transport_moments"
    assert obj["elastic_transport"]["mobility_times_N_per_m_V_s"] > 0
    assert obj["elastic_transport"]["diffusion_times_N_per_m_s"] > 0
    assert obj["rates_m3_per_s"]["lower:excitation:1"] > 0



def test_coupled_growth_transport_complete_effective_momentum_cli(tmp_path: Path) -> None:
    """Synthetic P0/P1: full momentum, no excitation/ionization double-count."""
    compiler = shutil.which("g++")
    assert compiler
    root = Path(__file__).resolve().parents[1]
    binary = tmp_path / "coupled_transport_candidate"
    build = subprocess.run([
        compiler, "-std=c++17", "-O2", "-Wall", "-Wextra", "-Werror", "-pedantic",
        f"-I{root / 'physics_app/include/utils'}",
        str(root / "physics_app/src/utils/PhysicsBoltzmannElasticSolver.C"),
        str(root / "physics_app/src/utils/PhysicsBoltzmannGrowth.C"),
        str(root / "physics_app/src/utils/PhysicsBoltzmannTemporalGrowth.C"),
        str(root / "physics_app/src/utils/PhysicsBoltzmannTransport.C"),
        str(root / "physics_app/src/utils/PhysicsBoltzmannCrossSections.C"),
        str(root / "physics_app/ci/boltzmann_candidate_export.C"),
        "-o", str(binary),
    ], capture_output=True, text=True)
    assert build.returncode == 0, build.stdout + build.stderr

    changing = (
        "EXCITATION\nAr -> Ar_test\n0.4\nsynthetic\n------\n"
        "0 0\n0.4 0\n10 1e-20\n------\n"
        "IONIZATION\nAr -> Ar+\n4.0\nsynthetic\n------\n"
        "0 0\n4 0\n10 1e-21\n------\n"
        "ATTACHMENT\nAr -> Ar-\nsynthetic\n------\n"
        "0 1e-23\n10 1e-23\n------\n"
    )
    elastic = (
        "AUTHOR-OWNED SYNTHETIC ONLY; NEVER LXCAT\n"
        "ELASTIC\nAr\n1.37e-5\nsynthetic\n------\n"
        "0 5e-20\n10 5e-20\n------\n" + changing
    )
    # Complete, inclusive first-harmonic scattering at the union of every
    # explicit elastic, excitation, ionization and attachment source knot.
    effective = (
        "AUTHOR-OWNED SYNTHETIC ONLY; NEVER LXCAT\n"
        "EFFECTIVE\nAr\n1.37e-5\nsynthetic\n------\n"
        "0 5.001e-20\n0.4 5.001e-20\n4 5.376e-20\n"
        "10 6.101e-20\n------\n" + changing
    )

    def invoke(text: str, *, extra_flags: tuple[str, ...] = ()) -> subprocess.CompletedProcess:
        source = tmp_path / "local_synthetic_collision.txt"
        source.write_text(text, encoding="utf-8")
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        args = [str(binary), str(source), digest, "0.5", "300", "10", "100",
                "Ar=1", "--solve-coupled-temporal-growth",
                "--report-coupled-growth-transport", *extra_flags]
        return subprocess.run(args, capture_output=True, text=True, timeout=30)

    first = invoke(elastic)
    second = invoke(effective)
    assert first.returncode == second.returncode == 0, (
        first.stdout + first.stderr + second.stdout + second.stderr)
    a, b = (json.loads(x.stdout) for x in (first, second))
    assert a["conditions"]["model"] == b["conditions"]["model"]
    assert a["generalized_eigen_residual"] < 1e-8
    assert b["generalized_eigen_residual"] < 1e-8
    assert "elastic_transport" not in a
    assert a["transport_scattering_source"] == (
        "FULL_EFFECTIVE_OR_ELASTIC_PLUS_ALL_INELASTIC")
    assert abs(a["mean_energy_eV"] - b["mean_energy_eV"]) < 1e-9
    for name, value in a["growth_eepf_transport_diagnostic"].items():
        assert name in b["growth_eepf_transport_diagnostic"]
        other = b["growth_eepf_transport_diagnostic"][name]
        assert abs(value - other) <= 1e-8 * max(1.0, abs(value))
    moment = a["growth_eepf_transport_diagnostic"]
    assert moment["mobility_times_N_per_m_V_s"] > 0.0
    assert moment["diffusion_times_N_per_m_s"] > 0.0
    assert moment["energy_mobility_times_N_per_m_V_s"] > 0.0
    assert moment["energy_diffusion_times_N_per_m_s"] > 0.0
    assert 0 <= moment["tail_ratio"] < 1e-3

    # No silent mixing with the steady elastic-only or frozen-growth paths.
    invalid = invoke(elastic, extra_flags=("--report-elastic-transport",))
    assert invalid.returncode == 2 and "only one transport" in invalid.stderr
    source = tmp_path / "local_synthetic_collision.txt"
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    unpaired = subprocess.run([
        str(binary), str(source), digest, "0.5", "300", "10", "100",
        "Ar=1", "--report-coupled-growth-transport"
    ], capture_output=True, text=True, timeout=30)
    assert unpaired.returncode == 2
    assert "requires --solve-coupled-temporal-growth" in unpaired.stderr
