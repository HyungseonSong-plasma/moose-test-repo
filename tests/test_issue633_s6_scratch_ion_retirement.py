"""#633: exact 14+12 native ion ownership removal, scratch only (no P2 claim)."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
PILOT = ROOT / "experiments/Issue402_plasma_dsl_g1"
sys.path.insert(0, str(PILOT))
from chemistry.retire_s6_ion_fv_owners import (  # noqa: E402
    CutoverError, cutover_texts, retire_in_disposable_scratch,
)


def fixture(case):
    names = [f"native_s6_{case}_base.i"] + [f"rate_layer_{n}.i" for n in range(1, 10)] + ["migrated_continuity.i"]
    layers = {n: "# Retained historical layer\n" for n in names}
    kernels = ["[FVKernels]\n"]
    bcs = ["[FVBCs]\n"]
    for species in ("O2p", "Om", "Op"):
        variable = "log_" + species
        for suffix, typ in (("time", "PhysicsFVLogMolarElectronTimeDerivative"),
                            ("diffusion", "PhysicsFVLogMolarElectronDiffusion"),
                            ("drift", "PhysicsFVLogMolarElectrostaticDrift")):
            kernels.append(f"  [{species}_{suffix}]\n    type = {typ}\n    variable = {variable}\n    block = plasma\n  []\n")
        for n in range(4):
            typ = "FVFunctorNeumannBC" if n == 0 else "PhysicsFVLogMolarDielectricFluxBC"
            options = ("    functor = ion_wall_number_flux\n    factor = -1.6605390671738466e-24\n"
                       if n == 0 else "    signed_number_flux = ion_wall_number_flux\n")
            bcs.append(f"  [{species}_wall_{n}]\n    type = {typ}\n    variable = {variable}\n" +
                       options + "    boundary = plasma_wafer\n  []\n")
    kernels += ["  [neutral_transport]\n    type = FVDiffusion\n    variable = pressure\n    block = plasma\n  []\n", "[]\n"]
    bcs.append("[]\n")
    layers[names[0]] = "".join(kernels + bcs)
    sources = [("O2p", "EI415"), ("O2p", "H25"), ("Om", "EI401"),
               ("Op", "EI417" if case == "417" else "EI941"),
               ("Op", "H25")]
    for idx, (species, rxn) in enumerate(sources, 1):
        layers[names[idx]] = (
            f"[FVKernels]\n  [{species}_{rxn}_source]\n"
            f"    type = FVCoupledForce\n    variable = log_{species}\n"
            f"    v = S_{species}_{rxn}\n    block = plasma\n  []\n[]\n"
        )
    layers[names[-1]] = "[Physics]\n  [Plasmas]\n  []\n[]\n"
    return names, layers


@pytest.mark.parametrize("case", ("417", "941"))
def test_exact_native_26_owner_retirement_without_touching_other_operators(case):
    names, layers = fixture(case)
    original = deepcopy(layers)
    output, evidence = cutover_texts(layers)
    assert layers == original
    assert evidence["old_native_fv_kernels"] == 14
    assert evidence["old_native_fv_bcs"] == 12
    assert (evidence["expected_generated_fv_kernels"], evidence["expected_generated_fv_bcs"]) == (12, 12)
    assert len(evidence["retired_owners"]) == 26
    assert "[neutral_transport]" in output[names[0]]
    assert "[Physics]" in output[names[-1]]
    assert all("old_block_sha256" in item for item in evidence["retired_owners"])
    assert evidence["P2"] == "NOT_RUN" and evidence["P3"] == "NOT_RUN"
    assert evidence["science"] == "SCIENCE_HOLD"


@pytest.mark.parametrize("case", ("417", "941"))
def test_disposable_scratch_writes_are_exact_and_have_sha_receipts(tmp_path, case):
    names, source = fixture(case)
    for name, body in source.items():
        (tmp_path / name).write_text(body)
    result = retire_in_disposable_scratch(tmp_path, names)
    assert len(result["retired_owners"]) == 26
    assert all(result["files"][n]["before_sha256"] == result["files"][n]["after_sha256"]
               for n in names if n not in result["changed_staged_files"])
    assert len(result["changed_staged_files"]) == 6
    assert (tmp_path / names[0]).read_text().count("[neutral_transport]") == 1
    assert (tmp_path / names[-1]).read_text() == source[names[-1]]


def test_unknown_type_and_missing_source_fail_before_any_write(tmp_path):
    names, layers = fixture("417")
    changed = layers[names[1]].replace("type = FVCoupledForce", "type = NativeUnknown")
    layers[names[1]] = changed
    for name, value in layers.items():
        (tmp_path / name).write_text(value)
    with pytest.raises(CutoverError, match="ION26_UNCHARACTERIZED"):
        retire_in_disposable_scratch(tmp_path, names)
    assert all((tmp_path / name).read_text() == value for name, value in layers.items())
    layers[names[1]] = "# source owner missing\n"
    with pytest.raises(CutoverError, match="ION26_OWNER_CENSUS_CHANGED"):
        cutover_texts(layers)


def test_legacy_ion_alias_and_native_owner_duplicate_rejected():
    names, layers = fixture("941")
    layers[names[0]] = layers[names[0]].replace("variable = log_O2p", "variable = log_ni", 1)
    with pytest.raises(CutoverError, match="ION26_UNCANONICALIZED_VARIABLE"):
        cutover_texts(layers)
    _, layers = fixture("941")
    layers[names[8]] = layers[names[1]]
    with pytest.raises(CutoverError, match="ION26_DUPLICATE_FVKernels_NAME"):
        cutover_texts(layers)


def test_symlink_or_non_disposable_layer_path_rejected(tmp_path):
    names, layers = fixture("417")
    for name, value in layers.items():
        (tmp_path / name).write_text(value)
    target = tmp_path / "outside.i"
    target.write_text("# protected\n")
    link = tmp_path / names[0]
    link.unlink()
    link.symlink_to(target)
    with pytest.raises(CutoverError, match="ION26_STAGED_PATH_NOT_PLAIN_FILE"):
        retire_in_disposable_scratch(tmp_path, names)
    assert target.read_text() == "# protected\n"


def test_same_module_is_not_a_native_p2_or_science_acceptance():
    module = PILOT / "chemistry/retire_s6_ion_fv_owners.py"
    source = module.read_text()
    assert 'P2": "NOT_RUN"' in source
    assert 'P3": "NOT_RUN"' in source
    assert "SCIENCE_HOLD" in source
    assert "EXPECTED" in source and "14" in source and "12" in source
