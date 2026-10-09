#!/usr/bin/env python3
"""Stage-B v3 generator wrapper with section-aware FVKernels insertion.

No physics or constraint changes relative to Stage-B v1.  The v1 insertion
intended to extend [FVKernels], but Stage-A has [BCs] between [FVKernels] and
[FVBCs].  This wrapper places the neutral FV kernels at the exact
[FVKernels] -> [BCs] boundary and verifies section ownership after generation.
"""
from pathlib import Path

import prepare_op_neutral_flow_staged_15us as v1

_original_replace_once = v1.replace_once


def section_aware_replace_once(text: str, old: str, new: str, label: str) -> str:
    if label != "FVKernels closing block":
        return _original_replace_once(text, old, new, label)

    # v1 passes:
    #   new = neutral_fv + "\n[]\n\n[FVBCs]\n"
    # Recover neutral_fv and attach it to the real FVKernels closing boundary,
    # which in the Stage-A input is followed by [BCs], not [FVBCs].
    suffix = "\n[]\n\n[FVBCs]\n"
    if not new.endswith(suffix):
        raise RuntimeError("unexpected v1 FVKernels replacement payload")
    neutral_fv = new[: -len(suffix)]

    anchor = "\n[]\n\n[BCs]\n"
    count = text.count(anchor)
    if count != 1:
        raise RuntimeError(f"expected exactly one FVKernels -> BCs boundary, found {count}")

    return text.replace(anchor, neutral_fv + "\n[]\n\n[BCs]\n", 1)


def validate_section_ownership(text: str) -> None:
    fv_start = text.index("[FVKernels]")
    bc_start = text.index("[BCs]")
    fvbc_start = text.index("[FVBCs]")
    pp_start = text.index("[Postprocessors]")

    if not (fv_start < bc_start < fvbc_start < pp_start):
        raise RuntimeError("top-level section ordering changed")

    fv = text[fv_start:bc_start]
    bc = text[bc_start:fvbc_start]
    fvbc = text[fvbc_start:pp_start]

    required_fv = (
        "[neutral_mass_time]",
        "[neutral_mass_advection]",
        "[u_advection]",
        "[v_advection]",
        "[O2s_time]",
        "[O2s_advection]",
        "[O2s_diffusion]",
        "[O_time]",
        "[O_advection]",
        "[O_diffusion]",
        "[Os_time]",
        "[Os_advection]",
        "[Os_diffusion]",
    )
    for token in required_fv:
        if token not in fv:
            raise RuntimeError(f"neutral FV kernel not owned by [FVKernels]: {token}")
        if token in bc or token in fvbc:
            raise RuntimeError(f"neutral FV kernel leaked outside [FVKernels]: {token}")

    for token in ("[neutral_inlet_mass]", "[neutral_wall_u]", "[neutral_outlet_p]"):
        if token not in fvbc:
            raise RuntimeError(f"neutral FV BC not owned by [FVBCs]: {token}")

    if "[electron_sheath]" not in bc or "[grounded_potential]" not in bc:
        raise RuntimeError("existing FEM [BCs] ownership changed")


def main() -> None:
    v1.replace_once = section_aware_replace_once
    text = v1.build_case()
    v1.validate_generated_contract(text)
    validate_section_ownership(text)

    out = Path(v1.base.HERE) / f"{v1.CASE_NAME}.i"
    out.write_text(text, encoding="utf-8")

    v1.validate_analytic_constraints()
    print(f"wrote {out}")
    print("generator_v3_change=section-aware FVKernels insertion only")
    print("physics_change_from_stageb_v1=none")
    print("constraint_change_from_stageb_v1=none")
    print("section_order=FVKernels->BCs->FVBCs->Postprocessors")
    print("neutral_fv_kernel_ownership=FVKernels")
    print("neutral_bc_ownership=FVBCs")
    print(f"neutral_sum={v1.Y_O2 + v1.Y_O2S + v1.Y_O + v1.Y_OS:.17g}")
    print(f"neutral_Mn_kg_mol={v1.M_INLET:.17g}")
    print(f"inlet_total_mdot_kg_s={v1.INLET_MDOT:.17g}")
    print(
        "inlet_species_mdot_sum_kg_s="
        f"{v1.INLET_MDOT_O2 + v1.INLET_MDOT_O2S + v1.INLET_MDOT_O + v1.INLET_MDOT_OS:.17g}"
    )
    print("time_schedule=1nsx100+10nsx90+100nsx90+1000nsx5")


if __name__ == "__main__":
    main()
