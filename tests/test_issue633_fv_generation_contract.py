"""P14 source-shape assertions; P1/P2 still require exact-head physics-opt evidence."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "physics_app/src/physics/plasma/DDContinuityEq.C"
HEADER = ROOT / "physics_app/include/physics/plasma/DDContinuityEq.h"


def test_four_fv_operator_families_per_selected_species():
    source = SRC.read_text(encoding="utf-8")
    header = HEADER.read_text(encoding="utf-8")
    assert "void addFVKernels() override;" in header
    section = source.split("DDContinuityEq::addFVKernels()", 1)[1].split(
        "DDContinuityEq::addFunctorMaterials()", 1
    )[0]
    assert "for (const auto & id : _fvm_species)" in section
    assert section.count("getProblem().addFVKernel(") == 4
    for name, obj_type in (
        ("time", "FVLogMolarTimeDerivative"),
        ("diffusion", "FVLogMolarDiffusion"),
        ("drift", "FVLogMolarElectrostaticDrift"),
        ("source", "FVCoupledForce"),
    ):
        assert f'"{obj_type}"' in section
        assert f'id + "_{name}"' in section
    assert 'source_params.set<MooseFunctorName>("v") = "S_" + id + "_molar"' in section
    assert 'diffusion_params.set<MooseFunctorName>("coeff") = id + "_diffusivity"' in section
    assert 'drift_params.set<MooseFunctorName>("mobility") = id + "_mobility"' in section
    assert 'drift_params.set<Real>("charge_number") = mechanism.species(id).charge_number' in section


def test_fvm_is_explicit_and_source_bound():
    source = SRC.read_text(encoding="utf-8")
    assert 'getParam<std::vector<std::string>>("fvm_species")' in source
    assert "if (!mechanism.hasSpeciesSource(id))" in source
    assert "if (!chemistryEnabled())" in source
    assert "if (!isParamValid(\"fem_potential\"))" in source
    assert "fvm_kernel_ownership" not in source
    assert "native_kernel_present" not in source
    assert "native_fvm_detected" not in source


def test_generation_is_not_a_scientific_or_archival_claim():
    source = SRC.read_text(encoding="utf-8")
    assert 'drift_params.set<MooseFunctorName>("carrier") = "carrier_one"' in source
    assert "FV kernel and BC cutover are separate P05/P14 gates" in source
    # The 12-kernel source contract does not claim P3 parity or P05 runtime
    # warehouse uniqueness. Those must be separately proven before merge.
