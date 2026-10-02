from __future__ import annotations

import json
from pathlib import Path

import pytest

from physics_harness.specification.simple_cases import (
    STABLE_STATUS,
    SimpleCaseCatalogError,
    create_simple_case,
    load_simple_case_catalog,
    materialize_input_template,
    resolve_simple_case,
    validate_simple_case_catalog,
)

ROOT = Path(__file__).resolve().parents[2]


def test_simple_case_catalog_is_code_addressable_and_valid() -> None:
    assert validate_simple_case_catalog(ROOT) == ()
    cases = load_simple_case_catalog(ROOT / "experiments" / "simple_case_inventory.json")
    assert [case.simple_case_id for case in cases] == [
        "electron-diffusion-experiment",
        "electron-diffusion-energy-experiment",
        "poisson",
    ]
    assert all(case.status == STABLE_STATUS for case in cases)
    first = cases[0]
    assert first.simple_case_id == "electron-diffusion-experiment"
    assert first.status == STABLE_STATUS
    assert first.template_source is True
    assert resolve_simple_case("electron diffusion") == first
    second = cases[1]
    assert second.simple_case_id == "electron-diffusion-energy-experiment"
    assert second.status == STABLE_STATUS
    assert second.template_source is True
    assert resolve_simple_case("electron diffusion energy") == second
    third = cases[2]
    assert third.simple_case_id == "poisson"
    assert third.status == STABLE_STATUS
    assert third.template_source is True
    assert resolve_simple_case("all-ground-poisson") == third


def test_materialize_template_is_qualified_input(tmp_path: Path) -> None:
    output = tmp_path / "input.i"
    materialize_input_template("electron-diffusion-experiment", output)
    qualified = ROOT / "experiments/2d-icp-electron-diffusion-experiment/input.i"
    assert output.read_bytes() == qualified.read_bytes()
    with pytest.raises(SimpleCaseCatalogError):
        materialize_input_template("electron-diffusion-experiment", output)


def test_second_template_materializes_solved_energy_baseline(tmp_path: Path) -> None:
    output = tmp_path / "energy-input.i"
    materialize_input_template("electron-diffusion-energy-experiment", output)
    qualified = ROOT / "experiments/2d-icp-electron-diffusion-energy-experiment/input.i"
    assert output.read_bytes() == qualified.read_bytes()
    assert "[c_epsilon]" in output.read_text()
    assert "coeff = electron_energy_diffusion" in output.read_text()


def test_create_scaffolds_existing_harness_case(tmp_path: Path) -> None:
    destination = tmp_path / "derived-case"
    create_simple_case("electron-diffusion-experiment", destination)

    source = ROOT / "experiments/2d-icp-electron-diffusion-experiment"
    assert (destination / "input.i").read_bytes() == (source / "input.template.i").read_bytes()
    assert (destination / "qvt.msh").read_bytes() == (source / "qvt.msh").read_bytes()
    assert (destination / "electron_moments.txt").read_bytes() == (source / "electron_moments.txt").read_bytes()

    manifest = json.loads((destination / "test.json").read_text())
    assert manifest == {"name": "derived-case", "type": "diagnostic", "input": "input.i"}

    origin = json.loads((destination / "template_origin.json").read_text())
    assert origin["template_id"] == "electron-diffusion-experiment"
    assert origin["source_status"] == STABLE_STATUS
    assert origin["qualification_inherited"] is False
    assert origin["overlay_input_sha256"] is None


def test_create_scaffolds_solved_energy_case(tmp_path: Path) -> None:
    destination = tmp_path / "derived-energy-case"
    create_simple_case("electron-diffusion-energy-experiment", destination)

    source = ROOT / "experiments/2d-icp-electron-diffusion-energy-experiment"
    assert (destination / "input.i").read_bytes() == (source / "input.template.i").read_bytes()
    assert (destination / "qvt.msh").read_bytes() == (source / "qvt.msh").read_bytes()
    assert (destination / "electron_moments.txt").read_bytes() == (source / "electron_moments.txt").read_bytes()

    origin = json.loads((destination / "template_origin.json").read_text())
    assert origin["template_id"] == "electron-diffusion-energy-experiment"
    assert origin["source_status"] == STABLE_STATUS
    assert origin["qualification_inherited"] is False


def test_poisson_template_materializes_all_ground_one_way_case(tmp_path: Path) -> None:
    output = tmp_path / "poisson-input.i"
    materialize_input_template("poisson", output)
    qualified = ROOT / "experiments/2d-icp-poisson-experiment/input.i"
    assert output.read_bytes() == qualified.read_bytes()
    text = output.read_text()
    assert "[phi]" in text
    assert "[phi_ground_all]" in text
    assert "boundary = plasma_all_ground" in text
    assert "v = poisson_source_V_m2" in text
    assert "PhysicsFVLogMolarElectrostaticDrift" not in text


def test_create_applies_new_input_after_scaffold(tmp_path: Path) -> None:
    overlay = tmp_path / "new_input.i"
    overlay.write_text("[Mesh]\n  type = GeneratedMesh\n[]\n")
    destination = tmp_path / "derived-overlay"

    create_simple_case("electron-diffusion-experiment", destination, input_path=overlay)

    assert (destination / "input.i").read_bytes() == overlay.read_bytes()
    origin = json.loads((destination / "template_origin.json").read_text())
    assert origin["overlay_input_name"] == "new_input.i"
    assert origin["overlay_input_sha256"] == origin["generated_input_sha256"]
    assert origin["qualification_inherited"] is False


def test_numeric_selector_is_not_supported() -> None:
    with pytest.raises(SimpleCaseCatalogError):
        resolve_simple_case("1")


def test_unregistered_future_case_is_not_supported(tmp_path: Path) -> None:
    with pytest.raises(SimpleCaseCatalogError):
        create_simple_case("electron-poisson-experiment", tmp_path / "bad")
