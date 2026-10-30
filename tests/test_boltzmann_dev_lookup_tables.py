"""M8a DEV-ONLY export tests, manufactured synthetic transport candidates."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from physics_app.ci.boltzmann_dev_lookup_tables import (
    DevelopmentTableError,
    make_dev_lookup_tables,
)


def _case(directory: Path) -> tuple[Path, list[Path]]:
    source = directory / "synthetic_source.txt"
    source.write_bytes(b"SELF-AUTHORED CROSS SECTIONS; NOT LXCAT\n")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    paths = []
    for i in range(2):
        obj = {
            "schema_version": 1,
            "conditions": {
                "collision_source_sha256": digest,
                "model": "elastic_excitation_superelastic_transport_moments",
                "mixture": {"Ar": 0.7, "O2": 0.3},
                "gas_temperature_K": 300.0,
                "reduced_field_Td": 10.0 + 10.0 * i,
            },
            "mean_energy_eV": 1.2 + i * 0.5,
            "elastic_transport": {
                "mobility_times_N_per_m_V_s": 1e24 + i * 1e23,
                "diffusion_times_N_per_m_s": 1e24 + i * 2e23,
                "energy_mobility_times_N_per_m_V_s": 0.9e24 + i * 1e23,
                "energy_diffusion_times_N_per_m_s": 0.8e24 + i * 1e23,
                "tail_ratio": 1e-5,
            },
        }
        path = directory / f"candidate_{i}.json"
        path.write_text(json.dumps(obj), encoding="utf-8")
        paths.append(path)
    return source, paths


def test_development_lookup_rows_are_hashed_and_separate(tmp_path: Path) -> None:
    source, files = _case(tmp_path)
    out = tmp_path / "dev_tables"
    hashes = make_dev_lookup_tables(source, files, out)
    manifest = json.loads((out / "DEVELOPMENT_ONLY_manifest.json").read_text())
    assert manifest["status"] == "DEV_ONLY_NOT_PHYSICS_VALIDATED"
    assert manifest["file_hashes"] == hashes
    part = out / "DEVELOPMENT_ONLY_particle_transport.txt"
    energy = out / "DEVELOPMENT_ONLY_energy_transport.txt"
    particle_rows = [list(map(float, line.split())) for line in part.read_text().splitlines()]
    energy_rows = [list(map(float, line.split())) for line in energy.read_text().splitlines()]
    assert len(particle_rows) == len(energy_rows) == 2
    assert all(len(row) == 3 for row in particle_rows + energy_rows)
    assert particle_rows[0][0] == energy_rows[0][0] == 1.2
    assert particle_rows[0][1] == 1e24
    assert energy_rows[0][1] == 0.9e24
    assert energy_rows[0][2] == 0.8e24
    assert hashlib.sha256(part.read_bytes()).hexdigest() == hashes["particle_sha256"]
    assert hashlib.sha256(energy.read_bytes()).hexdigest() == hashes["energy_sha256"]
    with pytest.raises(DevelopmentTableError, match="overwrite"):
        make_dev_lookup_tables(source, files, out)


def test_dev_table_rejects_mixture_hash_tail_and_coordinate_changes(tmp_path: Path) -> None:
    source, files = _case(tmp_path)
    with pytest.raises(DevelopmentTableError, match="at least two"):
        make_dev_lookup_tables(source, files[:1], tmp_path / "one")
    data = json.loads(files[1].read_text())
    data["elastic_transport"]["tail_ratio"] = 0.02
    files[1].write_text(json.dumps(data))
    with pytest.raises(DevelopmentTableError, match="tail"):
        make_dev_lookup_tables(source, files, tmp_path / "tail")
    data["elastic_transport"]["tail_ratio"] = 0.0
    data["mean_energy_eV"] = 1.2
    files[1].write_text(json.dumps(data))
    with pytest.raises(DevelopmentTableError, match="distinct"):
        make_dev_lookup_tables(source, files, tmp_path / "dup")
    data["mean_energy_eV"] = 1.7
    data["conditions"]["mixture"] = {"Ar": 1.0}
    files[1].write_text(json.dumps(data))
    with pytest.raises(DevelopmentTableError, match="mixture"):
        make_dev_lookup_tables(source, files, tmp_path / "mixture")
    data["conditions"]["mixture"] = {"Ar": 0.7, "O2": 0.3}
    data["conditions"]["collision_source_sha256"] = "0" * 64
    files[1].write_text(json.dumps(data))
    with pytest.raises(DevelopmentTableError, match="SHA-256"):
        make_dev_lookup_tables(source, files, tmp_path / "hash")
