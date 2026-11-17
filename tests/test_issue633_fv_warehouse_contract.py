"""P05/P10-P14 source-level owner validation and negative mutation controls.

These P0 checks do not replace a real PhysicsApp build / --check-input. FV
objects live in TheWarehouse, not the FE KernelWarehouse.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "physics_app/src/physics/plasma/DDContinuityEq.C"
TRANSPORT_C = ROOT / "physics_app/src/fvkernels/FVLogMolarTransport.C"
TRANSPORT_H = ROOT / "physics_app/include/fvkernels/FVLogMolarTransport.h"

GENERATORS = (
    'getProblem().addFVKernel(time_type, id + "_time", time_params);',
    'getProblem().addFVKernel(diffusion_type, id + "_diffusion", diffusion_params);',
    'getProblem().addFVKernel(drift_type, id + "_drift", drift_params);',
    'getProblem().addFVKernel(source_type, id + "_source", source_params);',
)
WAREHOUSE_CHECKS = (
    'condition<AttribSystem>("FVElementalKernel")',
    'condition<AttribSystem>("FVFluxKernel")',
    'condition<AttribSystem>("FVFluxBC")',
    'condition<AttribSystem>("FVDirichletBC")',
    'std::vector<FVKernel *> elemental;',
    'std::vector<FVKernel *> flux;',
    'kernels.insert(kernels.end(), flux.begin(), flux.end());',
    'bcs.insert(bcs.end(), dirichlet_bcs.begin(), dirichlet_bcs.end());',
    'kernel->type() != expected_type->second',
    'kernel->name()',
    'parameters.get<NonlinearVariableName>("variable") != variable',
    'if (matched[name] != 1)',
    'bc->type() != expected_type->second',
    'if (matched_bcs[name] != 1)',
    'P05 FV Native/Physics duplicate or unexpected owner',
    'P05 missing or duplicate FV Kernel',
    'P05 legacy, duplicate or unexpected FV BC',
    'P05 partial or duplicate FV BC owner',
    'if (chemistryData().hasIonWalls() && expected_bcs.empty())',
    'P05 missing JSON FV wall BC declarations for selected species',
)


def _missing(source: str, required: tuple[str, ...]) -> set[str]:
    return {term for term in required if term not in source}


def test_four_registered_fv_factories_and_legacy_caller_preservation():
    source = TRANSPORT_C.read_text()
    header = TRANSPORT_H.read_text()
    assert '#include "FVLogMolarTransport.h"' in source
    for class_name in ("FVLogMolarTimeDerivative",
                       "FVLogMolarDiffusion",
                       "FVLogMolarElectrostaticDrift"):
        assert f"class {class_name} :" in header
        assert f'registerMooseObject("PhysicsApp", {class_name});' in source
        assert f"{class_name}::computeQpResidual()" in source
    assert 'registerMooseObject("PhysicsApp", PhysicsFVLogMolarElectronReactionSource);' in (
        ROOT / "physics_app/src/fvkernels/PhysicsFVLogMolarElectronTransport.C"
    ).read_text()


def test_p14_four_operators_per_selected_fvm_species():
    source = SOURCE.read_text()
    assert 'registerMooseAction("PhysicsApp", DDContinuityEq, "add_fv_kernel");' in source
    assert "for (const auto & id : _fvm_species)" in source
    assert not _missing(source, GENERATORS)
    assert "S_" + '" + id + "_molar' in source
    assert 'drift_params.set<MooseFunctorName>("carrier") = "carrier_one";' in source
    assert 'source_params.set<Real>("coef") = 1.0;' in source


def test_p05_warehouse_exact_names_types_and_family_coverage():
    source = SOURCE.read_text()
    assert not _missing(source, WAREHOUSE_CHECKS)
    for label, type_name in (("time", "FVLogMolarTimeDerivative"),
                             ("diffusion", "FVLogMolarDiffusion"),
                             ("drift", "FVLogMolarElectrostaticDrift"),
                             ("source", "FVCoupledForce")):
        assert f'{{id + "_{label}", "{type_name}"}}' in source
    assert 'for (const auto & [group, boundary] : chemistryData().boundaries())' in source
    assert 'expected_bcs.emplace(name, bc.type)' in source
    assert 'for (const auto & [name, type] : expected_bcs)' in source
    assert 'id + "_focus_ring_dielectric"' not in source
    assert 'id + "_cover_dielectric"' not in source
    assert "expected exactly one" in source


def test_missing_and_duplicate_guard_negative_mutations():
    source = SOURCE.read_text()
    for token in (*GENERATORS, *WAREHOUSE_CHECKS):
        mutated = source.replace(token, "")  # remove every copy of this invariant
        assert mutated != source
        required = GENERATORS if token in GENERATORS else WAREHOUSE_CHECKS
        assert token in _missing(mutated, required), token


def test_no_native_detection_switch_or_undeclared_wall_cutover():
    source = SOURCE.read_text()
    assert "fvm_kernel_ownership" not in source
    assert "native_kernel_present" not in source
    assert "if (!mechanism.ddTransport(id))" in source
    assert "if (!mechanism.hasSpeciesSource(id))" in source
    assert "if (!chemistryEnabled())" in source
    assert "addFVBC(" not in source
    assert "addFunctorMaterial(\"IonWallFluxMaterial\"" not in source
