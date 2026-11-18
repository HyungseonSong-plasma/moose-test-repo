"""P6-D4 Public D original 100-row/Physics Chemistry source ownership regression.

Source-only: no MOOSE invocation, time integration, private EI rate or old
Public D hybrid compatibility runner.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
PILOT = ROOT / "experiments/Issue402_plasma_dsl_g1"
sys.path.insert(0, str(PILOT / "chemistry"))
import prepare_public_d_newphysics_100row as public_d  # noqa: E402


def _mechanism(case):
    target = PILOT / "chemistry" / f"unified_s6_{case}_newonly.json"
    blob = target.read_bytes()
    assert hashlib.sha256(blob).hexdigest() == public_d.JSON_SHA[case]
    return json.loads(blob)


@pytest.mark.parametrize("case", ["417", "941"])
def test_both_new_physics_8reaction_owner_graphs_preserve_original_lookup(case):
    data = _mechanism(case)
    public_d.check_mechanism(case, data)
    assert set(data["equations"]) == public_d.EXPECTED_REACTIONS | {"EI-" + case}
    assert all(data["species"][ion]["transport_coef"] == public_d.ION_TRANSPORT
               for ion in public_d.EXPECTED_IONS)
    template = (PILOT / f"issue633_newonly_s6_{case}_continuity.template.i").read_text()
    assert template.count("[Chemistry]") == 1
    assert template.count("[Continuity]") == 1
    assert template.count("[Energy]") == 1
    assert "transport_coefficient = fluid" in template
    assert "fvm_species = 'O2p Om Op'" in template
    assert "dont_create_kernels" not in template


def test_original_100row_table_is_still_the_repository_source():
    blob = public_d.check_100row_table(public_d.ORIGINAL_TABLE)
    assert len(blob.splitlines()) == 100
    assert hashlib.sha256(blob).hexdigest() == public_d.ORIGINAL_TABLE_SHA256
    assert public_d.ELECTRON_MOMENTS_SHA != public_d.ORIGINAL_TABLE_SHA256


def test_100row_table_one_byte_mutant_rejected(tmp_path):
    blob = public_d.check_100row_table(public_d.ORIGINAL_TABLE)
    target = tmp_path / "electron_moments.txt"
    target.write_bytes(blob.replace(b"1.40991", b"1.40992", 1))
    with pytest.raises(public_d.PublicDHold, match="SHA_MISMATCH"):
        public_d.check_100row_table(target)


@pytest.mark.parametrize("alter", [
    lambda d: d["species"]["e"]["transport_coef"].update({"type": "constant"}),
    lambda d: d["species"]["O2p"].update({"charge_number": -1}),
    lambda d: d["species"]["Om"]["transport_coef"].update({"mobility": 1}),
    lambda d: d["species"]["Op"].update({"molar_mass": 0.032}),
    lambda d: d["equations"].pop("EI-415"),
    lambda d: d["reactions"].pop(),
    lambda d: d["ion_surface_current"].update({"electron_wall_number_flux": "none"}),
    lambda d: d["drift_diffusion_boundaries"].pop("plasma_cover"),
])
def test_physical_owner_chemistry_and_boundary_mutants_rejected(alter):
    data = copy.deepcopy(_mechanism("417"))
    alter(data)
    with pytest.raises(public_d.PublicDHold):
        public_d.check_mechanism("417", data)


def test_refuse_unstaged_public_d_without_compatible_mode(tmp_path):
    with pytest.raises(public_d.PublicDHold, match="NOT_DISPOSABLE_CASE_DIR"):
        public_d.stage_public_d_physics(tmp_path, "417", ["a.i"])


def test_new_public_d_contract_never_installs_legacy_bypass():
    src = Path(public_d.__file__).read_text()
    assert "P3_NOT_RUN" not in src
    assert "dont_create_kernels" not in src
    assert "def run_historical_public_d_compat" not in src
    assert "HISTORICAL_100_ROW" not in src
