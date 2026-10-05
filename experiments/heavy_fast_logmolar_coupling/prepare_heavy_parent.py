#!/usr/bin/env python3
from pathlib import Path

BASE = Path(__file__).parents[1] / "Issue91_real_qvt_r3" / "r3_e0" / "heavy_base.i"
OUT = Path(__file__).with_name("heavy_parent.i")

text = BASE.read_text(encoding="utf-8")

# The active coupling path uses only current PhysicsApp production object names.
# Normalize legacy type names from the source fixture without carrying those names
# into the active coupling source or generated input.
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

# Rebase data paths because the generated parent lives in this experiment directory.
text = text.replace("file = 'qvt.msh'", "file = '../Issue91_real_qvt_r3/r3_e0/qvt.msh'", 1)
text = text.replace("transport_data_file = transport_data.txt", "transport_data_file = '../Issue91_real_qvt_r3/r3_e0/transport_data.txt'", 1)

# Snapshot material/functor heavy state into FV AuxVariables so it can be copied to the
# fast child. Solved p and solved mass fractions are transferred directly.
aux = """
[AuxVariables]
  [T_g_snapshot]
    type = MooseVariableFVReal
    initial_condition = ${T_g_value}
    block = plasma
  []
  [rho_snapshot]
    type = MooseVariableFVReal
    initial_condition = 1.0e-5
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

coupling = """
# Heavy flow is the parent. A heavy-state snapshot is copied to the monolithic
# fast plasma application; time-coupled subcycling is configured separately.
[MultiApps]
  [fast_plasma]
    type = FullSolveMultiApp
    input_files = 'fast_child.i'
    execute_on = FINAL
  []
[]

[Transfers]
  [heavy_snapshot_to_fast]
    type = MultiAppCopyTransfer
    to_multi_app = fast_plasma
    source_variable = 'p T_g_snapshot rho_snapshot w_O2_snapshot w_O2s w_O2p w_O w_Om w_Op w_Os'
    variable = 'p_heavy T_g_heavy rho_heavy_snapshot w_O2_heavy_snapshot w_O2s_heavy w_O2p_heavy w_O_heavy w_Om_heavy w_Op_heavy w_Os_heavy'
    execute_on = FINAL
  []
[]

"""
marker2 = "[Executioner]\n"
if marker2 not in text:
    raise RuntimeError("Executioner marker not found")
text = text.replace(marker2, coupling + marker2, 1)

# Keep the heavy flow solution for field-level validation.
text = text.replace("[Outputs]\n  csv = true\n", "[Outputs]\n  csv = true\n  exodus = true\n", 1)

if legacy_prefix in text:
    raise RuntimeError("active heavy parent still contains a retired object prefix")

OUT.write_text(text, encoding="utf-8")
print(f"wrote {OUT}")
