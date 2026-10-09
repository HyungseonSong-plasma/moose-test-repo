#!/usr/bin/env python3
"""Stage-B v2 generator wrapper.

The first Stage-B run exposed only a text-splice formatting mismatch: the
Stage-A O+ generator leaves three newlines before [FVBCs], while the Stage-B
splice expected two.  Keep every physics and constraint decision from v1 and
make only that anchor tolerant to the exact Stage-A formatting.
"""
from pathlib import Path

import prepare_op_neutral_flow_staged_15us as v1

_original_replace_once = v1.replace_once


def robust_replace_once(text: str, old: str, new: str, label: str) -> str:
    if text.count(old) == 1:
        return text.replace(old, new, 1)

    if label == "FVKernels closing block":
        alternate = "\n[]\n\n\n[FVBCs]\n"
        count = text.count(alternate)
        if count != 1:
            raise RuntimeError(
                f"expected exactly one FVKernels closing block via primary or alternate anchor, found {count}"
            )
        return text.replace(alternate, new, 1)

    return _original_replace_once(text, old, new, label)


def main() -> None:
    v1.replace_once = robust_replace_once
    text = v1.build_case()
    v1.validate_generated_contract(text)

    out = Path(v1.base.HERE) / f"{v1.CASE_NAME}.i"
    out.write_text(text, encoding="utf-8")

    v1.validate_analytic_constraints()
    print(f"wrote {out}")
    print("generator_v2_change=FVKernels/FVBCs splice-anchor tolerance only")
    print("physics_change_from_stageb_v1=none")
    print("constraint_change_from_stageb_v1=none")
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
