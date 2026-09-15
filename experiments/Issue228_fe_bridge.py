#!/usr/bin/env python3
"""Issue #228 coupled FE-Poisson / FV-transport bridge discriminator.

The production FV transport objects require a face-gradient-capable FV
potential functor.  A P1 FE variable cannot supply that interface directly.
This controlled mixed formulation therefore:

  * solves Poisson on `potential_fe` with P1 FE,
  * retains `potential_plasma` as an FV algebraic bridge only,
  * enforces potential_plasma = cell evaluation of potential_fe through
    FVReaction + FVCoupledForce,
  * leaves every production transport/wall object pointed at the unchanged
    FV name `potential_plasma`.

Thus the scientific axis is the Poisson discretization while the bridge is an
explicit framework-interface adapter, not an additional electrostatic solve.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from experiments.Issue228_p2_e1_w2_pg import run as base
from experiments.Issue228_axis_bc_10step import run as axis
from physics_harness.adapters.moose import blocks as mb
from physics_harness.adapters.moose import parameters as mp

MODES = base.FE_MODES


def build_case(mode: str):
    if mode not in MODES:
        raise ValueError(mode)
    text, meta = axis.build_case()

    # Remove the FV Poisson equation, but retain the production FV variable
    # name so all drift/wall/sheath consumers remain unchanged.
    text = mb.remove_block(text, "FVKernels/r31_phi_diffusion")
    text = mb.remove_block(text, "FVKernels/r31_phi_charge_source")

    # Add the FE electrostatic unknown.
    text = mb.insert_child_block(
        text,
        "Variables",
        """  [potential_fe]
    family = LAGRANGE
    order = FIRST
    initial_condition = 0
    block = plasma
  []""",
    )

    # Algebraic FV bridge: potential_plasma - potential_fe = 0 cell-wise.
    text = mb.insert_child_block(
        text,
        "FVKernels",
        """  [r228_phi_bridge_reaction]
    type = FVReaction
    variable = potential_plasma
    rate = 1
    block = plasma
  []
  [r228_phi_bridge_force]
    type = FVCoupledForce
    variable = potential_plasma
    v = potential_fe
    block = plasma
  []""",
    )

    # FE Poisson.  Keep the production axis-free ground on the FV bridge as
    # the transport face-state contract, and add the same physical ground to
    # the FE electrostatic variable.
    text = mb.append_top_level_block(
        text,
        """[Kernels]
  [r228_fe_phi_diffusion]
    type = Diffusion
    variable = potential_fe
    block = plasma
  []
  [r228_fe_phi_charge_source]
    type = FunctorKernel
    variable = potential_fe
    functor = poisson_charge_source
    functor_on_rhs = true
    block = plasma
  []
[]""",
    )
    text = mb.append_top_level_block(
        text,
        f"""[BCs]
  [r228_fe_phi_ground]
    type = DirichletBC
    variable = potential_fe
    boundary = {axis.GROUND_NONAXIS}
    value = 0
  []
[]""",
    )

    # Governed Gauss diagnostic must use the actual FE electrostatic unknown.
    text = mb.insert_child_block(
        text,
        "Materials",
        """  [r228_fe_eps_for_gauss]
    type = GenericConstantMaterial
    prop_names = r228_fe_relative_permittivity
    prop_values = 1
    block = plasma
  []""",
    )
    text = mb.replace_block(
        text,
        "Postprocessors/r31_gauss_flux_reduced",
        """  [r31_gauss_flux_reduced]
    type = SideDiffusiveFluxIntegral
    variable = potential_fe
    boundary = r31_plasma_all_boundary
    diffusivity = r228_fe_relative_permittivity
    execute_on = 'INITIAL TIMESTEP_END'
  []""",
    )

    # Add direct FE extrema; legacy potential extrema remain on the bridge and
    # are retained so the governed acceptance parser can still run unchanged.
    text = mb.insert_child_block(
        text,
        "Postprocessors",
        """  [r228_fe_phi_min]
    type = ElementExtremeValue
    variable = potential_fe
    value_type = min
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [r228_fe_phi_max]
    type = ElementExtremeValue
    variable = potential_fe
    value_type = max
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []""",
    )

    geometry = "baseline"
    if mode == "fe_wafer_matched": geometry = "wafer_matched"
    elif mode == "fe_right_matched": geometry = "right_matched"

    return text, {
        **meta,
        "issue": 228,
        "claim": "coupled_FE_Poisson_with_FV_transport_projection_bridge",
        "diagnostic_only": True,
        "mode": mode,
        "geometry_mode": geometry,
        "poisson_unknown": "potential_fe",
        "transport_potential_bridge": "potential_plasma",
        "bridge_equation": "FVReaction(potential_plasma) + FVCoupledForce(v=potential_fe)",
        "poisson_discretization": "P1_FE",
        "transport_discretization": "production_FV",
        "transport_objects_retargeted": False,
        "chemistry_changed": False,
        "sheath_law_changed": False,
    }


def self_test():
    checks = {}
    for mode in MODES:
        text, _ = build_case(mode)
        checks[f"{mode}:fe_var"] = mp.get_parameter(text, "Variables/potential_fe", "family") == "LAGRANGE"
        checks[f"{mode}:fv_var_retained"] = mp.get_parameter(text, "Variables/potential_plasma", "type") == "MooseVariableFVReal"
        checks[f"{mode}:fv_poisson_removed"] = (not mb.has_block(text, "FVKernels/r31_phi_diffusion") and not mb.has_block(text, "FVKernels/r31_phi_charge_source"))
        checks[f"{mode}:bridge_reaction"] = mp.get_parameter(text, "FVKernels/r228_phi_bridge_reaction", "type") == "FVReaction"
        checks[f"{mode}:bridge_force"] = mp.get_parameter(text, "FVKernels/r228_phi_bridge_force", "v") == "potential_fe"
        checks[f"{mode}:fe_poisson"] = mp.get_parameter(text, "Kernels/r228_fe_phi_charge_source", "functor") == "poisson_charge_source"
        checks[f"{mode}:fv_transport_same"] = mp.get_parameter(text, "FVKernels/n_e_drift", "potential") == "potential_plasma"
        checks[f"{mode}:ion_wall_same"] = mp.get_parameter(text, "FunctorMaterials/issue27_a6_O2p_wall_flux", "potential") == "potential_plasma"
    failed = sorted(k for k,v in checks.items() if not v)
    return {"status":"PASS" if not failed else "FAIL", "checks":checks, "failed_checks":failed}


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--mode", choices=MODES, required=True)
    p.add_argument("--physics-opt", type=Path, required=True)
    p.add_argument("--results-root", type=Path, required=True)
    p.add_argument("--timeout", type=float, default=1800)
    p.add_argument("--self-test", action="store_true")
    a=p.parse_args()
    if a.self_test:
        x=self_test(); print(json.dumps(x,indent=2,sort_keys=True)); return 0 if x["status"]=="PASS" else 1
    base.build_fe_case = build_case
    # Reuse geometry staging and analysis.  The analysis routine detects the
    # FE nodal potential by name below, so alias potential_fe to the expected
    # analysis name only in post-processing.
    old_analyse = base._analyse_fe_exodus
    def analyse(epath):
        from scipy.io import netcdf_file
        import numpy as np
        f=netcdf_file(str(epath),'r',mmap=False)
        conn=f.variables['connect1'].data.copy().astype(int)
        emap=f.variables['elem_num_map'].data.copy().astype(int)[:len(conn)]
        ss=base._sidesets_from_exodus(f)
        names=base._decode_names(f.variables['name_nod_var'].data.copy())
        if 'potential_fe' not in names:
            raise RuntimeError(f'potential_fe missing from nodal output: {names}')
        iv=names.index('potential_fe')+1
        pn=f.variables[f'vals_nod_var{iv}'].data.copy()[-1].astype(float)
        cell=np.mean(pn[conn-1],axis=1)
        f.close()
        return {'phi_node_min_V':float(pn.min()),'phi_node_max_V':float(pn.max()),
                'phi_cell_centroid_min_V':float(cell.min()),'phi_cell_centroid_max_V':float(cell.max()),
                'hotspots':base._wall_hills(emap,conn,ss,cell)}
    base._analyse_fe_exodus = analyse
    return base.run_fe(a)


if __name__=='__main__':
    raise SystemExit(main())
