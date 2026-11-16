"""FLOW-only P0 mutation guard for registered S6-417/941 Native sheath P2.

The original archived C0 input must remain immutable. The stage-only 4+4
rebind is a class registration rename with *no physical BC or flux changes*.
"""
from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
PILOT = ROOT / "experiments/Issue402_plasma_dsl_g1"
sys.path.insert(0, str(PILOT))
from chemistry.prepare_hybrid_json_s6 import BLOCK, migrate_exact_s6_fem_sheath
from run_chemistry_s6_p2_only import rebind_preserved_native_sheath

BASE = (
    "rf_elastic_diss_ion_ei20_ei01_400w_adjacent_sheath_wall_closed_"
    "100us_dt1000ns__C0_chemistry_off.i"
)
ARCHIVED = PILOT / "native/s6_c0_physics_base_no_d1.i"


def _canonical_source() -> str:
    # Existing project P0 model reconstructs the exact previously approved
    # canonical D base; it does not require Native build/mesh/P3.
    path = ROOT / "tests/test_issue402_hybrid_json_s6_owner_preflight.py"
    spec = importlib.util.spec_from_file_location("flow_s6_owner_fixture", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.canonical_staged_base()


def _stage(tmp_path: Path, text: str) -> tuple[Path, list[str], Path]:
    chemistry = tmp_path / "experiments/Issue395_powered_chemistry_ladder"
    chemistry.mkdir(parents=True)
    source = chemistry / BASE
    source.write_text(text, encoding="utf-8")
    return chemistry, [BASE] + [f"historical_layer_{i}.i" for i in range(10)], source


def test_flow_sheath_scratch_4_plus_4_is_exact_and_archived_source_unchanged(
    tmp_path: Path,
) -> None:
    immutable_sha = hashlib.sha256(ARCHIVED.read_bytes()).hexdigest()
    original = _canonical_source()
    expected, exact_owners = migrate_exact_s6_fem_sheath(original)
    chemistry, ordered, scratch = _stage(tmp_path, original)

    result = rebind_preserved_native_sheath(chemistry, ordered)
    assert scratch.read_text(encoding="utf-8") == expected
    assert result["counts"] == {
        "FEMElectronSheathBC": 4,
        "FEMElectronEnergySheathBC": 4,
    }
    assert result["owners"] == exact_owners
    assert result["before_sha256"] == hashlib.sha256(
        original.encode("utf-8")
    ).hexdigest()
    assert result["after_sha256"] == hashlib.sha256(
        expected.encode("utf-8")
    ).hexdigest()
    assert "PhysicsFEMLogMolarElectronFieldLimitedFluxBC" not in expected
    assert "PhysicsFEMLogMolarElectronEnergyFieldLimitedFluxBC" not in expected
    assert "wall_number_flux = e_wall_number_flux" in expected
    assert "mean_energy = e_energy_eV" in expected
    assert result["physics_equations_changed"] is False
    assert result["P3"] == "NOT_RUN"
    assert result["science"] == "SCIENCE_HOLD"
    assert hashlib.sha256(ARCHIVED.read_bytes()).hexdigest() == immutable_sha


def test_flow_sheath_preflight_is_read_only_and_hybrid_is_wired(
    tmp_path: Path,
) -> None:
    original = _canonical_source()
    expected, owners = migrate_exact_s6_fem_sheath(original)
    chemistry, ordered, scratch = _stage(tmp_path, original)
    report = rebind_preserved_native_sheath(chemistry, ordered, apply=False)
    assert report["status"] == "P2_SCRATCH_PREFLIGHT_EXACT_4_PLUS_4_SHEATH"
    assert report["owners"] == owners
    assert report["before_sha256"] == hashlib.sha256(
        original.encode("utf-8")
    ).hexdigest()
    assert report["after_sha256"] == hashlib.sha256(
        expected.encode("utf-8")
    ).hexdigest()
    assert scratch.read_text(encoding="utf-8") == original
    driver = (PILOT / "run_chemistry_s6_p2_only.py").read_text()
    assert "cutover = prepare(chemistry, ordered, case)" in driver
    assert 'sheath_receipt = cutover["scratch_sheath_bc_cutover"]' in driver
    assert '"scratch_sheath_bc_rebind": sheath_receipt' in driver
    assert 'cutover["scratch_json_initial_cutover"]["owner_count"] != 4' in driver
    assert "prepare_hybrid(chemistry, ordered, case)" not in driver


@pytest.mark.parametrize(
    "mutation",
    ["wall_flux", "boundary", "class", "variable", "duplicate",
     "quote", "extra_space", "token_order"],
)
def test_flow_sheath_refuses_mutated_owners_without_writing(
    tmp_path: Path, mutation: str,
) -> None:
    original = _canonical_source()
    blocks = [m for m in BLOCK.finditer(original) if m.group("name") == "electron_sheath"]
    assert len(blocks) == 1
    match = blocks[0]
    block = match.group(0)
    if mutation == "wall_flux":
        altered = block.replace("wall_number_flux = e_wall_number_flux",
                                "wall_number_flux = unapproved_flux", 1)
    elif mutation == "boundary":
        altered = block.replace(
            "boundary = 'plasma_electrode plasma_metal plasma_right'",
            "boundary = 'unapproved_wall'", 1)
    elif mutation == "class":
        altered = block.replace(
            "type = PhysicsFEMLogMolarElectronFieldLimitedFluxBC",
            "type = UnapprovedSheathLaw", 1)
    elif mutation == "variable":
        altered = block.replace("variable = log_e",
                                "variable = log_O2p", 1)
    elif mutation == "quote":
        altered = block.replace(
            "boundary = 'plasma_electrode plasma_metal plasma_right'",
            'boundary = "plasma_electrode plasma_metal plasma_right"', 1)
    elif mutation == "extra_space":
        altered = block.replace(
            "plasma_electrode plasma_metal plasma_right",
            "plasma_electrode  plasma_metal plasma_right", 1)
    elif mutation == "token_order":
        altered = block.replace(
            "plasma_electrode plasma_metal plasma_right",
            "plasma_metal plasma_electrode plasma_right", 1)
    else:
        altered = block + "\n" + block
    assert altered != block
    broken = original[:match.start()] + altered + original[match.end():]
    chemistry, ordered, scratch = _stage(tmp_path, broken)
    before = scratch.read_bytes()
    with pytest.raises(ValueError, match="HYBRID_SHEATH_BC_"):
        rebind_preserved_native_sheath(chemistry, ordered)
    assert scratch.read_bytes() == before


def test_flow_sheath_refuses_wrong_layer_order(tmp_path: Path) -> None:
    source = _canonical_source()
    chemistry, ordered, scratch = _stage(tmp_path, source)
    with pytest.raises(ValueError, match="FLOW_S6_DBASE_ORDER_OR_SOURCE_CHANGED"):
        rebind_preserved_native_sheath(chemistry, list(reversed(ordered)))
    assert scratch.read_text(encoding="utf-8") == source


def test_flow_sheath_refuses_second_conversion_without_writing(
    tmp_path: Path,
) -> None:
    # The original FLOW error was caused by invoking the exact archived-type
    # rebind after the canonical Chemistry cutover had already converted it.
    original = _canonical_source()
    once, owners = migrate_exact_s6_fem_sheath(original)
    assert len(owners) == 8
    chemistry, ordered, scratch = _stage(tmp_path, once)
    before = scratch.read_bytes()
    with pytest.raises(ValueError, match="HYBRID_SHEATH_BC_IDENTITY_electron_sheath"):
        rebind_preserved_native_sheath(chemistry, ordered, apply=False)
    assert scratch.read_bytes() == before
