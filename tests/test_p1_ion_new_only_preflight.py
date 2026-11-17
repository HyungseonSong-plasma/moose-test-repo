"""Unit/negative tests for input-only species selection and legacy duplicate guard."""
import importlib.util
from pathlib import Path

MODULE = Path(__file__).resolve().parents[1] / "ci/p1_ion_new_only_preflight.py"
spec = importlib.util.spec_from_file_location("p1_ion_new_only_preflight", MODULE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

DECK = """[Physics]
  [Plasmas]
    [Transport]
      [DriftDiffusion]
        [Continuity]
          fem_species = 'e'
          fvm_species = 'O2p Om Op'
        []
      []
    []
  []
[]
"""
JSON = {"species": {x: {"initial_number_density": 1.0} for x in ("e", "O2p", "Om", "Op")}}


def test_clean_selected_species_only():
    result = module.inspect({"migrated_continuity.i": DECK}, JSON)
    assert result["status"] == "P0_STATIC_PASS_ONLY"
    assert result["fem_species"] == ["e"]
    assert result["fvm_species"] == ["O2p", "Om", "Op"]
    assert result["native_fv_owner_count"] == 0


def test_legacy_native_fv_ion_kernel_rejected():
    bad = DECK + "\n[FVKernels]\n  [ni_time]\n    type = FVTimeKernel\n    variable = log_O2p\n  []\n[]\n"
    result = module.inspect({"native.i": bad}, JSON)
    assert result["status"] == "FAIL"
    assert "P1_NATIVE_FV_ION_OWNER_PRESENT_1" in result["errors"]


def test_legacy_native_fv_ion_bc_rejected():
    bad = DECK + "\n[FVBCs]\n  [ni_wall]\n    type = FVFunctorNeumannBC\n    variable = log_O2p\n  []\n[]\n"
    result = module.inspect({"native.i": bad}, JSON)
    assert "P1_NATIVE_FV_ION_OWNER_PRESENT_1" in result["errors"]


def test_dual_fe_fv_species_rejected():
    bad = DECK.replace("fem_species = 'e'", "fem_species = 'e O2p'")
    result = module.inspect({"migrated_continuity.i": bad}, JSON)
    assert "P1_SPECIES_DUPLICATE_OR_EMPTY" in result["errors"]


def test_missing_selected_json_species_rejected():
    incomplete = {"species": {"e": {"initial_number_density": 1}, "O2p": {"initial_number_density": 1}}}
    result = module.inspect({"migrated_continuity.i": DECK}, incomplete)
    assert "P1_JSON_SELECTED_SPECIES_MISSING:Om" in result["errors"]
    assert "P1_JSON_SELECTED_SPECIES_MISSING:Op" in result["errors"]


def test_mode_flag_rejected():
    bad = DECK.replace("fvm_species = 'O2p Om Op'", "fvm_species = 'O2p Om Op'\n          fvm_kernel_ownership = physics")
    result = module.inspect({"migrated_continuity.i": bad}, JSON)
    assert "P1_MANUAL_OWNER_FLAG_FORBIDDEN" in result["errors"]
