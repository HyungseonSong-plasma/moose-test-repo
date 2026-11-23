"""Independent G7 DOF ownership and synthetic Poisson FE directional sensitivity."""
from pathlib import Path
import importlib.util
import math
import sys
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ci/guards"))
spec = importlib.util.spec_from_file_location(
    "issue652_g7_dof_directional", ROOT / "ci/guards/issue652_g7_dof_directional.py"
)
assert spec and spec.loader
d = importlib.util.module_from_spec(spec)
spec.loader.exec_module(d)


def sample_map():
    names = list(d.VARIABLES)
    obj = {
        "ndof": 80,
        "demangled": True,
        "vars": [{"name": name, "subdomains": [
            {"id": 0, "kernels": [], "dofs": list(range(i*16, (i+1)*16))}
        ]} for i, name in enumerate(names)],
    }
    return obj


def test_fixture_has_dofmap_output_and_full_g3_charge_chain():
    text = d.fixture()
    assert text.count("type = DOFMap") == 1
    assert "output_screen = true" in text
    assert "output_file = false" in text
    assert text.count("type = ADParsedFunctorMaterial") == 7
    assert text.count("type = FunctorKernel") == 1
    assert text.count("type = ADMatDiffusion") == 1


def test_exact_dof_json_names_and_ownership():
    import json
    payload = d.parse_dofmap("MOOSE initialization:\n" + json.dumps(sample_map()) + "\nDONE")
    assert payload["ndof"] == 80
    assert payload["owners"][10] == "potential"
    assert payload["owners"][26] == "log_O2p"
    assert payload["owners"][42] == "log_Op"
    assert payload["owners"][58] == "log_e"
    assert payload["owners"][74] == "log_Om"


@pytest.mark.parametrize("change", ["duplicate", "missing", "range", "cardinality"])
def test_dofmap_must_be_unique_complete_partition(change):
    import json
    data = sample_map()
    if change == "duplicate":
        data["vars"][1]["subdomains"][0]["dofs"].append(10)
    elif change == "missing":
        data["vars"][3]["subdomains"][0]["dofs"].pop()
    elif change == "range":
        data["vars"][4]["subdomains"][0]["dofs"].append(80)
    else:
        data["vars"].pop()
    with pytest.raises(d.BlockHold):
        d.parse_dofmap(json.dumps(data))


def test_matrix_dof_indices_are_validated():
    log = """Mat Object: 1 MPI process
row 10: (11, -4.) (13, 1.)
Mat Object: 1 MPI process
row 10: (11, -4.001)
Mat Object: 1 MPI process
row 10: (11, 0.001)
"""
    items = d.read_petsc_matrices(log, 80)
    assert len(items) == 1
    assert items[0]["assembled"][(10, 11)] == -4.
    bad = log.replace("(11, -4.)", "(81, -4.)")
    with pytest.raises(d.BlockHold, match="OUTSIDE|INVALID"):
        d.read_petsc_matrices(bad, 80)


def test_independent_fe_mass_integral_and_finite_difference():
    for species in d.CHARGED:
        exact = d.predicted_block_sum(species)
        for h in d.FD_DIRECTION_STEPS:
            measured = d.source_directional(
                d.INTERIOR_TEST_SUM, d.STATES, species, h)
            expected_relative = abs(measured - exact) / abs(exact)
            assert expected_relative < d.DIRECTIONAL_FD_REL_TOL if h == d.PREFERRED_STEP else expected_relative < 1e-5
        assert math.copysign(1, exact) == -d.SIGNS[species]


def test_one_matrix_block_per_species_and_must_fail_if_sign_flipped():
    mapping = d.parse_dofmap(__import__("json").dumps(sample_map()))
    assembled = {}
    for species in d.CHARGED:
        # Four independent interior potential rows; each receives exactly
        # one same-species column contribution. Block total is source integral.
        species_dof = mapping["variables"][species][0]
        for i in (5, 6, 9, 10):
            assembled[(i, species_dof)] = d.predicted_block_sum(species) / 4
    report = d.analyze_jacobian(assembled, mapping)
    assert set(report) == set(d.CHARGED)
    assert all(x["block_status"] == "PASS" for x in report.values())
    assembled[(5, mapping["variables"]["log_e"][0])] *= -1
    with pytest.raises(AssertionError):
        assert all(x["block_status"] == "PASS"
                   for x in d.analyze_jacobian(assembled, mapping).values())


def test_real_python_directional_is_unrelated_to_petsc_fd_step():
    assert d.FD_DIRECTION_STEPS == (1e-3, 1e-4, 1e-5)
    assert d.PREFERRED_STEP == 1e-4
    assert d.ANALYTIC_BLOCK_REL_TOL == 1e-4
    assert d.DIRECTIONAL_FD_REL_TOL == 5e-7
    assert "-snes_test_err 1e-09 -snes_test_jacobian_view" in d._view_command(
        Path("/tmp/source"), Path("/tmp/work"))[-1]
    assert d.SOURCE == "26e84a4a33cf93d9e278a4f0b2d78c53cae2d6ce"


def test_explicit_native_gate_and_no_overwrite(tmp_path):
    with pytest.raises(d.BlockHold, match="AUTHORIZATION"):
        d.analyze(source=tmp_path, manifest=tmp_path / "manifest.json",
                  output=tmp_path / "receipt.json", authorize=False)
