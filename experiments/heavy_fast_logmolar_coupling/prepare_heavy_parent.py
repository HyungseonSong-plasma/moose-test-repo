#!/usr/bin/env python3
from pathlib import Path

BASE = Path(__file__).parents[1] / "Issue91_real_qvt_r3" / "r3_e0" / "heavy_base.i"
OUT = Path(__file__).with_name("heavy_parent.i")

text = BASE.read_text(encoding="utf-8")

# The active coupling path uses only current PhysicsApp production object names.
legacy_prefix = "QP" + "X"
production_type_names = {
    legacy_prefix + "FVConservativeMassFractionTimeDerivative": "PhysicsFVConservativeMassFractionTimeDerivative",
    legacy_prefix + "FVMassFractionAdvection": "PhysicsFVMassFractionAdvection",
    legacy_prefix + "FVMixtureAveragedDiffusion": "PhysicsFVMixtureAveragedDiffusion",
    legacy_prefix + "FVElectrostaticDrift": "PhysicsFVElectrostaticDrift",
    legacy_prefix + "FVHeavyMassElectromigrationCorrection": "PhysicsFVHeavyMassElectromigrationCorrection",
}
for old_name, current_name in production_type_names.items():
    text = text.replace(old_name, current_name)

# Clean quasi-neutral charged-heavy startup for the feedback diagnostic.
# At p=1.33322 Pa and Tg=600 K this O2+ mass fraction corresponds to
# approximately n_O2+ = 1e16 1/m3. O+ and O- start from zero.
replacements = {
    "Yin_O2 = 0.7": "Yin_O2 = 0.7299241959504238",
    "Yin_O2p = 0.01": "Yin_O2p = 7.580404957618788e-5",
    "Yin_Om = 0.01": "Yin_Om = 0.0",
    "Yin_Op = 0.01": "Yin_Op = 0.0",
}
for old, new in replacements.items():
    if old not in text:
        raise RuntimeError(f"missing composition token: {old}")
    text = text.replace(old, new, 1)

# Preserve only relative permittivity from the retired material provider.
materials_start = text.find("[Materials]\n")
r15_marker = "# ==============================================================================\n# R15 EVR3"
materials_end = text.find(r15_marker, materials_start)
if materials_start < 0 or materials_end < 0:
    raise RuntimeError("legacy Materials block not found")
text = text[:materials_start] + text[materials_end:]

current_materials = """[FunctorMaterials]\n  [permittivity_vacuum]\n    type = ADGenericFunctorMaterial\n    prop_names = 'relative_permittivity'\n    prop_values = '1.0'\n    block = vacuum\n  []\n  [permittivity_outer]\n    type = ADGenericFunctorMaterial\n    prop_names = 'relative_permittivity'\n    prop_values = '1.0'\n    block = 'top right bottom'\n  []\n  [permittivity_cover]\n    type = ADGenericFunctorMaterial\n    prop_names = 'relative_permittivity'\n    prop_values = '3.6'\n    block = cover\n  []\n  [permittivity_electrode]\n    type = ADGenericFunctorMaterial\n    prop_names = 'relative_permittivity'\n    prop_values = '1.0'\n    block = electrode\n  []\n  [permittivity_wafer]\n    type = ADGenericFunctorMaterial\n    prop_names = 'relative_permittivity'\n    prop_values = '12.5'\n    block = wafer\n  []\n  [permittivity_focus_ring]\n    type = ADGenericFunctorMaterial\n    prop_names = 'relative_permittivity'\n    prop_values = '8.0'\n    block = focus_ring\n  []\n  [permittivity_plasma]\n    type = ADGenericFunctorMaterial\n    prop_names = 'relative_permittivity'\n    prop_values = '1.0'\n    block = plasma\n  []\n  [material_coverage_only]\n    type = ADGenericFunctorMaterial\n    prop_names = 'heavy_coupling_material_coverage_only'\n    prop_values = '0.0'\n    block = 'coil1 coil2 coil3 metal port'\n  []\n"""
if "[FunctorMaterials]\n" not in text:
    raise RuntimeError("FunctorMaterials marker not found")
text = text.replace("[FunctorMaterials]\n", current_materials, 1)

# Rebase data paths because the generated parent lives in this experiment directory.
text = text.replace("file = 'qvt.msh'", "file = '../Issue91_real_qvt_r3/r3_e0/qvt.msh'", 1)
text = text.replace("transport_data_file = transport_data.txt", "transport_data_file = '../Issue91_real_qvt_r3/r3_e0/transport_data.txt'", 1)

# The potential returned by the fast plasma solver is a parent AuxVariable. It is
# frozen during each 5 ns heavy solve, giving a clean staggered 5:1 coupling.
aux = """
[AuxVariables]
  [potential_fast]
    type = MooseVariableFVReal
    initial_condition = 0.0
    block = plasma
  []
  [T_g_snapshot]
    type = MooseVariableFVReal
    initial_condition = ${T_g_value}
    block = plasma
  []
  [rho_snapshot]
    type = MooseVariableFVReal
    initial_condition = 7.01e-6
    block = plasma
  []
  [w_O2_snapshot]
    type = MooseVariableFVReal
    initial_condition = ${Yin_O2}
    block = plasma
  []
[]

[AuxKernels]
  [sample_T_g]
    type = FunctorAux
    variable = T_g_snapshot
    functor = T_g
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END FINAL'
  []
  [sample_rho]
    type = FunctorAux
    variable = rho_snapshot
    functor = rho_mat
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END FINAL'
  []
  [sample_w_O2]
    type = FunctorAux
    variable = w_O2_snapshot
    functor = w_O2_constraint
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END FINAL'
  []
[]

"""
marker = "[Functions]\n"
if marker not in text:
    raise RuntimeError("Functions marker not found")
text = text.replace(marker, aux + marker, 1)

# All charged-heavy bulk migration and zero-net-mass electromigration correction
# use the field supplied by the fast plasma child, not the old prescribed field.
if text.count("potential = phi_prescribed") < 3:
    raise RuntimeError("expected charged-heavy prescribed-potential consumers not found")
text = text.replace("potential = phi_prescribed", "potential = potential_fast")

# Add an O2+ number-density closure and a pure migration wall-loss law. Setting
# sticking=0 isolates the E-driven wall loss requested by this diagnostic.
ion_materials = """
  [O2p_number_density_feedback]
    type = ADParsedFunctorMaterial
    property_name = n_O2p_feedback
    functor_names = 'rho_mat w_O2p'
    functor_symbols = 'rhv wf'
    expression = '6.02214076e23*rhv*wf/0.032'
    block = plasma
  []
  [O2p_wall_flux_feedback]
    type = PhysicsIonWallFluxMaterial
    ion_number_density = n_O2p_feedback
    potential = potential_fast
    mobility = mu_O2p
    gas_temperature = T_g
    charge_number = 1
    molar_mass = 0.032
    sticking = 0.0
    migration_gate_smoothing_width = 1.0e-3
    block = plasma
  []
"""
fm_end = "\n[]\n\n[FVKernels]\n"
if fm_end not in text:
    raise RuntimeError("FunctorMaterials/FVKernels boundary not found")
text = text.replace(fm_end, ion_materials + fm_end, 1)

wall_bc = """  [O2p_migration_wall_loss]\n    type = FVFunctorNeumannBC\n    variable = w_O2p\n    boundary = 'plasma_electrode plasma_metal plasma_right plasma_cover plasma_wafer plasma_focus_ring'\n    functor = ion_migration_mass_flux\n    factor = -1.0\n  []\n\n"""
if "[FVBCs]\n" not in text:
    raise RuntimeError("FVBCs marker not found")
text = text.replace("[FVBCs]\n", "[FVBCs]\n" + wall_bc, 1)

feedback_pp = """  [O2p_number_inventory_feedback]\n    type = ADElementIntegralFunctorPostprocessor\n    functor = n_O2p_feedback\n    block = plasma\n    execute_on = 'INITIAL TIMESTEP_END'\n  []\n  [O2p_migration_mass_loss_rate]\n    type = SideFVFluxBCIntegral\n    boundary = 'plasma_electrode plasma_metal plasma_right plasma_cover plasma_wafer plasma_focus_ring'\n    fvbcs = 'O2p_migration_wall_loss'\n    execute_on = 'INITIAL TIMESTEP_END'\n  []\n  [O2p_migration_current]\n    type = ScalePostprocessor\n    value = O2p_migration_mass_loss_rate\n    scaling_factor = -3015166.6288534375\n    execute_on = 'INITIAL TIMESTEP_END'\n  []\n  [potential_fast_min]\n    type = ADElementExtremeFunctorValue\n    functor = potential_fast\n    value_type = min\n    block = plasma\n    execute_on = 'INITIAL TIMESTEP_END'\n  []\n  [potential_fast_max]\n    type = ADElementExtremeFunctorValue\n    functor = potential_fast\n    value_type = max\n    block = plasma\n    execute_on = 'INITIAL TIMESTEP_END'\n  []\n\n"""
if "[Postprocessors]\n" not in text:
    raise RuntimeError("Postprocessors marker not found")
text = text.replace("[Postprocessors]\n", "[Postprocessors]\n" + feedback_pp, 1)

# At each parent TIMESTEP_BEGIN: transfer the latest heavy state to the child,
# subcycle the child to the parent's new time, then transfer potential back.
coupling = """
[MultiApps]
  [fast_plasma]
    type = TransientMultiApp
    input_files = 'fast_child.i'
    sub_cycling = true
    interpolate_transfers = false
    output_sub_cycles = true
    execute_on = TIMESTEP_BEGIN
  []
[]

[Transfers]
  [heavy_state_to_fast]
    type = MultiAppCopyTransfer
    to_multi_app = fast_plasma
    source_variable = 'p T_g_snapshot rho_snapshot w_O2_snapshot w_O2s w_O2p w_O w_Om w_Op w_Os'
    variable = 'p_heavy T_g_heavy rho_heavy_snapshot w_O2_heavy_snapshot w_O2s_heavy w_O2p_heavy w_O_heavy w_Om_heavy w_Op_heavy w_Os_heavy'
    execute_on = TIMESTEP_BEGIN
  []
  [fast_potential_to_heavy]
    type = MultiAppCopyTransfer
    from_multi_app = fast_plasma
    source_variable = potential
    variable = potential_fast
    execute_on = TIMESTEP_BEGIN
  []
[]

"""
marker2 = "[Executioner]\n"
if marker2 not in text:
    raise RuntimeError("Executioner marker not found")
text = text.replace(marker2, coupling + marker2, 1)

# Requested time-scale ratio: heavy/ion 5 ns, electron child 1 ns (5 subcycles).
text = text.replace("  dt = 1.0e-4\n  end_time = 5.0e-4\n", "  dt = 5.0e-9\n  dtmin = 5.0e-9\n  dtmax = 5.0e-9\n  end_time = 2.0e-8\n", 1)

# Keep the heavy flow solution for field-level validation.
text = text.replace("[Outputs]\n  csv = true\n", "[Outputs]\n  csv = true\n  exodus = true\n", 1)

if legacy_prefix in text:
    raise RuntimeError("active heavy parent still contains a retired object prefix")
if "BaseMaterial" in text:
    raise RuntimeError("active heavy parent still contains retired BaseMaterial")
if "potential = phi_prescribed" in text:
    raise RuntimeError("active heavy parent still uses prescribed potential for migration")

OUT.write_text(text, encoding="utf-8")
print(f"wrote {OUT}")
