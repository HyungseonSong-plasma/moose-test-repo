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


def test_legacy_canonical_names_after_scratch_remap_are_supported():
    parts = [DECK]
    for section, counts in (("FVKernels", module.LEGACY_S6_KERNEL_COUNTS),
                            ("FVBCs", module.LEGACY_S6_BC_COUNTS)):
        parts.append(f"[{section}]")
        for sid, num in counts.items():
            for i in range(num):
                parts.extend((f"  [{sid}_{section}_{i}]", "    type = ArchivedObject",
                              f"    variable = log_{sid}", "  []"))
        parts.append("[]")
    result = module.inspect({"old_post_transform.i": "\n".join(parts)}, JSON, "legacy-hybrid")
    assert result["status"] == "P0_LEGACY_PROVENANCE_ONLY"
    assert result["native_fv_owner_count"] == 26


def test_new_only_allows_disjoint_native_surface_charge_producers_without_c2():
    # Native charge-current bookkeeping is not an ion FV Kernel/BC owner.
    # If C2 new wall/current is not configured, do not reject by type alone.
    pieces = [DECK, "[FunctorMaterials]"]
    for name in ("ion_wall_flux", "negative_ion_wall_flux",
                 "atomic_positive_ion_wall_flux"):
        pieces.extend((f"  [{name}]", "    type = PhysicsIonWallTotalFluxMaterial", "  []"))
    for side in ("cover", "wafer", "focus_ring"):
        pieces.extend((f"  [{side}_surface_current]", "    type = ADParsedFunctorMaterial",
                       f"    property_name = {side}_net_surface_current_density", "  []"))
    pieces.append("[]")
    data = module.inspect({"old_c0.i": "\n".join(pieces)}, JSON)
    assert data["status"] == "P0_STATIC_PASS_ONLY", data["errors"]
    assert data["native_fv_owner_count"] == 0
    assert data["explicit_ion_wall_current_owner_count"] == 6
    assert data["c2_native_producer_collision_count"] == 0


def test_new_only_rejects_renamed_wall_type_and_current_output_when_c2_owns_them():
    renamed = DECK + """
[FunctorMaterials]
  [renamed_ion]
    type = IonWallFluxMaterial
    species_id = O2p
  []
  [renamed_current]
    type = ADParsedFunctorMaterial
    property_name = cover_net_surface_current_density
  []
[]
"""
    from copy import deepcopy
    c2 = deepcopy(JSON)
    for id in ("O2p", "Om", "Op"):
        c2["species"][id]["wall_molar_mass"] = 0.032 if id == "O2p" else 0.016
    c2["ion_surface_current"] = {"electron_wall_number_flux": "electron_wall_number_flux"}
    result = module.inspect({"renamed.i": renamed}, c2)
    assert "P1_GENERATED_C2_FUNCTOR_OWNER_COLLISION_2" in result["errors"]
    families = {owner["family"] for owner in result["c2_native_producer_collisions"]}
    assert families == {"ion_wall", "surface_current"}


def test_c2_guard_preserves_archived_hybrid_provenance_boundary():
    old = DECK + """
[FunctorMaterials]
  [ion_wall_flux]
    type = PhysicsIonWallTotalFluxMaterial
  []
[]
"""
    archived = module.inspect({"old.i": old}, JSON, "legacy-hybrid")
    assert archived["explicit_ion_wall_current_owner_count"] == 1
    assert not any("P1_EXPLICIT_ION_WALL_OR_CURRENT_OWNER_PRESENT" in e
                   for e in archived["errors"])
    assert archived["status"] == "FAIL"  # 26 mandatory legacy FV objects absent


def test_binding_only_dont_create_kernels_cannot_certify_new_only_cutover():
    for setting in ("true", "false"):
        binding_only = DECK.replace(
            "fvm_species = 'O2p Om Op'",
            "fvm_species = 'O2p Om Op'\n          dont_create_kernels = " + setting)
        result = module.inspect({"binding_only.i": binding_only}, JSON, "new-only")
        assert result["status"] == "FAIL"
        assert "P1_BINDING_ONLY_BYPASS_FORBIDDEN" in result["errors"]
        # The old provenance contract is independently governed by the
        # exact historical 14 Kernel + 12 BC inventory, not this option.
        legacy = module.inspect({"binding_only.i": binding_only}, JSON, "legacy-hybrid")
        assert "P1_BINDING_ONLY_BYPASS_FORBIDDEN" not in legacy["errors"]


def test_native_surface_charge_fallback_is_allowed_but_same_current_output_is_not():
    from copy import deepcopy
    native_current = DECK + """
[FunctorMaterials]
  [external_surface_charge]
    type = ADParsedFunctorMaterial
    property_name = surface_current_native
  []
[]
"""
    assert module.inspect({"native.i": native_current}, JSON)["status"] == "P0_STATIC_PASS_ONLY"
    c2 = deepcopy(JSON)
    for id in ("O2p", "Om", "Op"):
        c2["species"][id]["wall_sticking"] = 1.0
    c2["ion_surface_current"] = {"electron_wall_number_flux": "electron_wall_number_flux"}
    assert module.inspect({"native.i": native_current}, c2)["status"] == "P0_STATIC_PASS_ONLY"
    duplicate = native_current.replace("surface_current_native", "cover_net_surface_current_density")
    result = module.inspect({"duplicate.i": duplicate}, c2)
    assert "P1_GENERATED_C2_FUNCTOR_OWNER_COLLISION_1" in result["errors"]


def test_new_run_electron_wall_rejects_native_eswallflux_duplicate():
    from copy import deepcopy
    new = deepcopy(JSON)
    for sid, z in (("O2p", 1), ("Om", -1), ("Op", 1)):
        record = new["species"][sid]
        record["charge_number"] = z
        record["molar_mass"] = 0.032 if sid == "O2p" else 0.016
        record["transport_coef"] = {
            "type": "functor", "file": "none", "unit": "physical"
        }
        record.pop("mobility")
        record.pop("diffusivity")
    new["drift_diffusion_boundaries"] = {
        "inlet outlet plasma_electrode plasma_metal plasma_right": {
            "e_wall": {"type": "FEMElectronSheathBC"}
        }
    }
    new["ion_surface_current"] = {
        "electron_wall_number_flux": "e_wall_number_flux"
    }
    duplicate = DECK + """
[FunctorMaterials]
  [old_electron_sheath_wall_flux]
    type = ESWallFluxMaterial
    species_id = e
  []
[]
"""
    # Default S6 Energy path is partial: the Native electron provider
    # remains valid and is required if no new electron material is emitted.
    baseline = module.inspect({"native.i": duplicate}, new)
    assert baseline["status"] == "P0_STATIC_PASS_ONLY", baseline["errors"]
    assert baseline["c2_native_producer_collision_count"] == 0

    # Turning on full Electron Energy physics creates an *additional* electron
    # wall producer; reject the same Native provider in that configuration.
    complete_energy = DECK.replace(
        "        []\n      []",
        "        []\n        [Energy]\n          fem_potential = potential\n        []\n      []",
        1,
    )
    result = module.inspect({"native.i": complete_energy + duplicate[len(DECK):]}, new)
    assert "P1_GENERATED_C2_FUNCTOR_OWNER_COLLISION_1" in result["errors"]
    assert result["c2_native_producer_collision_count"] == 1
    assert result["c2_native_producer_collisions"][0]["family"] == "electron_wall"


def test_grouped_json_electron_bc_requires_native_fem_bc_retirement_not_flux_retirement():
    from copy import deepcopy
    new = deepcopy(JSON)
    new["drift_diffusion_boundaries"] = {
        "inlet outlet plasma_electrode plasma_metal plasma_right": {
            "e_wall": {"type": "FEMElectronSheathBC"}
        }
    }
    # An electron FEM boundary is a residual operator and must not coexist
    # with the JSON-generated FEM boundary. The wall *flux* Material is a
    # separately allowed source in partial Energy mode.
    native_bc = DECK + """
[BCs]
  [electron_sheath]
    type = PhysicsFEMLogMolarElectronFieldLimitedFluxBC
    variable = log_ne
    boundary = plasma_electrode
  []
[]
"""
    result = module.inspect({"native.i": native_bc}, new)
    assert "P1_NATIVE_ELECTRON_FEM_BC_OWNER_PRESENT_1" in result["errors"]
    assert result["native_electron_bc_owner_count"] == 1
    assert result["native_fv_owner_count"] == 0
    assert result["c2_native_producer_collision_count"] == 0
