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
JSON = {"species": {x: {"initial_number_density": 1.0, "transport_coef": "constant",
                        "mobility": 0.2, "diffusivity": 0.1} for x in ("e", "O2p", "Om", "Op")}}


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
    incomplete = {"species": {"e": JSON["species"]["e"], "O2p": JSON["species"]["O2p"]}}
    result = module.inspect({"migrated_continuity.i": DECK}, incomplete)
    assert "P1_JSON_SELECTED_SPECIES_MISSING:Om" in result["errors"]
    assert "P1_JSON_SELECTED_SPECIES_MISSING:Op" in result["errors"]


def test_mode_flag_rejected():
    bad = DECK.replace("fvm_species = 'O2p Om Op'", "fvm_species = 'O2p Om Op'\n          fvm_kernel_ownership = physics")
    result = module.inspect({"migrated_continuity.i": bad}, JSON)
    assert "P1_MANUAL_OWNER_FLAG_FORBIDDEN" in result["errors"]


def test_nonfinite_and_boolean_initial_density_rejected():
    for invalid in (float("nan"), float("inf"), True, 0.0, -1.0):
        bad = {"species": {**JSON["species"], "Om": {"initial_number_density": invalid}}}
        result = module.inspect({"migrated_continuity.i": DECK}, bad)
        assert "P1_JSON_INITIAL_NUMBER_DENSITY_INVALID:Om" in result["errors"]

def test_invalid_species_identifier_rejected():
    bad = DECK.replace("fvm_species = 'O2p Om Op'", "fvm_species = 'O2p Om Op-a'")
    result = module.inspect({"migrated_continuity.i": bad}, JSON)
    assert "P1_SPECIES_INVALID_IDENTIFIER:Op-a" in result["errors"]


def test_historical_log_ni_nm_nop_aliases_fail_new_only():
    for species, old in (("O2p", "log_ni"), ("Om", "log_nm"), ("Op", "log_nop")):
        for section in ("FVKernels", "FVBCs"):
            bad = DECK + f"\n[{section}]\n  [legacy]\n    type = FVDiffusion\n    variable = {old}\n  []\n[]\n"
            result = module.inspect({"native.i": bad}, JSON)
            assert result["status"] == "FAIL", (species, section)
            assert "P1_NATIVE_FV_ION_OWNER_PRESENT_1" in result["errors"]


def test_unresolved_include_rejected_in_both_contracts():
    for contract in ("new-only", "legacy-hybrid"):
        result = module.inspect({"bad.i": DECK + "\n!include legacy_native.i\n"}, JSON, contract)
        assert result["status"] == "FAIL"
        assert "P1_UNRESOLVED_INCLUDE:bad.i" in result["errors"]


def test_selected_json_transport_is_mandatory():
    import copy
    for species in ("e", "O2p", "Om", "Op"):
        data = copy.deepcopy(JSON)
        del data["species"][species]["transport_coef"]
        result = module.inspect({"new-only.i": DECK}, data)
        assert "P1_JSON_TRANSPORT_MISSING_OR_INVALID:" + species in result["errors"]


def test_legacy_hybrid_and_new_only_are_disjoint():
    # Old S6 counts: O2p (5 K+4 BC), Om (4 K+4 BC), Op (5 K+4 BC).
    chunks = [DECK]
    for section, counts in (("FVKernels", module.LEGACY_S6_KERNEL_COUNTS),
                            ("FVBCs", module.LEGACY_S6_BC_COUNTS)):
        chunks.append("[" + section + "]")
        for species, num in counts.items():
            for index in range(num):
                chunks.extend((f"  [{species}_{section}_{index}]",
                               "    type = SyntheticLegacyOperator",
                               f"    variable = {module.LEGACY_S6_VARIABLES[species]}", "  []"))
        chunks.append("[]")
    legacy = "\n".join(chunks)
    archived = module.inspect({"legacy.i": legacy}, JSON, "legacy-hybrid")
    assert archived["status"] == "P0_LEGACY_PROVENANCE_ONLY"
    assert archived["native_fv_owner_count"] == 26
    migrated = module.inspect({"legacy.i": legacy}, JSON, "new-only")
    assert migrated["status"] == "FAIL"
    assert "P1_NATIVE_FV_ION_OWNER_PRESENT_26" in migrated["errors"]
    # Removing one object must not turn an incomplete Hybrid into provenance PASS.
    missing = legacy.replace("  [O2p_FVKernels_0]", "  [no_longer_a_legacy_kernel]", 1).replace(
        "    variable = log_ni", "    variable = unrelated", 1)
    assert "P1_LEGACY_KERNEL_COUNT_MISMATCH:O2p" in module.inspect(
        {"legacy.i": missing}, JSON, "legacy-hybrid")["errors"]


def test_json_transport_model_parameters_must_exist():
    import copy
    data = copy.deepcopy(JSON)
    data["species"]["Om"]["mobility"] = float("nan")
    assert "P1_JSON_TRANSPORT_COEFFICIENT_INVALID:Om:mobility" in module.inspect(
        {"new-only.i": DECK}, data)["errors"]


def test_legacy_contract_requires_full_three_species_census():
    result = module.inspect({"new-only.i": DECK}, JSON, "legacy-hybrid")
    assert "P1_LEGACY_KERNEL_COUNT_MISMATCH:O2p" in result["errors"]
    assert result["status"] == "FAIL"
