#!/usr/bin/env python3
from __future__ import annotations
import re
import sys
from pathlib import Path

SOLVED = ["O2s","O2p","O","Om","Op","Os"]

def validate_text(text: str):
    errors = []

    # Exact Q-1 production structure.
    if "property_name = w_O2_constraint" not in text:
        errors.append("missing constrained O2 functor")
    if "expression = '1.0-s1-s2-s3-s4-s5-s6'" not in text:
        errors.append("constrained O2 expression mismatch")
    if "property_name = Mn_mix" not in text:
        errors.append("missing composition-dependent Mn")
    if "property_name = rho_mat" not in text:
        errors.append("missing composition-dependent rho")
    if "prs*mol/(8.31446*tmp)" not in text:
        errors.append("EOS expression mismatch")

    if "property_name = invMn_mix" not in text:
        errors.append("missing inverse mean molar mass state")
    if "property_name = invMn_dot_model" not in text:
        errors.append("missing inverse mean molar mass derivative")
    if "expression = '31.25*(d3+d4+d5+d6)'" not in text:
        errors.append("inverse-Mn derivative expression mismatch")

    if "property_name = dMn_dt_model" not in text:
        errors.append("missing chain-rule dMn/dt model")
    if "property_name = drho_dt_model" not in text:
        errors.append("missing chain-rule drho/dt model")
    if "-mol*mol*31.25*(d3+d4+d5+d6)" not in text:
        errors.append("dMn/dt chain-rule expression mismatch")
    if "prs*dmol/(8.31446*tmp)" not in text:
        errors.append("drho/dt chain-rule expression mismatch")

    for s in SOLVED:
        if f"functor = w_{s}" not in text:
            errors.append(f"missing direct nonlinear-variable derivative probe for {s}")

    if "functor = Mn_out" in text or "functor = rho_out" in text:
        errors.append("invalid TimeDerivativeAux-on-output-state path present")

    # v4 execution-order contract: derived derivative functors must NOT be
    # copied by timestep-end FunctorAux kernels in the same stage as dw_k/dt.
    for forbidden in [
        "variable = invMn_dot_out",
        "variable = dMn_dt_out",
        "variable = drho_dt_out",
    ]:
        if forbidden in text:
            errors.append("same-stage derived derivative Aux path present: " + forbidden)

    for required in [
        "type = ElementAverageFunctorPostprocessor\n    functor = invMn_dot_model",
        "type = ElementAverageFunctorPostprocessor\n    functor = dMn_dt_model",
        "type = ElementAverageFunctorPostprocessor\n    functor = drho_dt_model",
    ]:
        if required not in text:
            errors.append("missing post-Aux derived functor evaluation: " + required)

    for s in SOLVED:
        if f"[w_{s}]" not in text:
            errors.append(f"missing solved variable w_{s}")
        if f"type = QPXFVMassFractionTimeDerivative\n    variable = w_{s}" not in text:
            errors.append(f"missing QPX time kernel for {s}")
        if f"variable = w_{s}\n    rho = rho_mat\n    diffusivity = D_mix_{s}" not in text:
            errors.append(f"missing canonical mixture diffusion for {s}")

    # Transport must consume all seven active mass fractions.
    required_mass_list = (
        "mass_fractions = 'w_O2_constraint w_O2s w_O2p w_O w_Om w_Op w_Os'"
    )
    if required_mass_list not in text:
        errors.append("seven-species transport mass-fraction wiring mismatch")

    if "type = QPXThermalDiffusionMaterial" not in text:
        errors.append("missing canonical transport material")

    # Explicitly prohibited in this isolated tranche.
    for token in ["D_ref", "Poisson", "ElectricMigration", "ReactionSecondOrder",
                  "FVEEDFReaction", "QPXFVMassFractionAdvection"]:
        if token in text:
            # "Poisson" appears in top comment; ignore comments by stripping them below.
            stripped = "\n".join(line.split("#",1)[0] for line in text.splitlines())
            if token in stripped:
                errors.append(f"prohibited path active: {token}")

    # Avoid known FunctionParser reserved symbol collisions.
    for m in re.finditer(r"functor_symbols\s*=\s*'([^']+)'", text):
        symbols = set(m.group(1).split())
        bad = symbols.intersection({"x","y","z","t","e","pi"})
        if bad:
            errors.append("reserved functor symbol(s): " + ",".join(sorted(bad)))

    return errors

def self_test():
    original = Path(__file__).with_name("input.i").read_text()
    if validate_text(original):
        print("P0_BASELINE: FAIL")
        return False

    mutations = {
        "M1_remove_constraint": original.replace(
            "property_name = w_O2_constraint", "property_name = w_O2_missing", 1),
        "M2_break_constraint_expr": original.replace(
            "expression = '1.0-s1-s2-s3-s4-s5-s6'",
            "expression = '1.0+s1-s2-s3-s4-s5-s6'", 1),
        "M3_remove_one_time_kernel": original.replace(
            "type = QPXFVMassFractionTimeDerivative\n    variable = w_Om",
            "type = FVReaction\n    variable = w_Om", 1),
        "M4_break_eos": original.replace(
            "prs*mol/(8.31446*tmp)", "prs*0.032/(8.31446*tmp)", 1),
        "M5_break_transport_wiring": original.replace(
            "mass_fractions = 'w_O2_constraint w_O2s w_O2p w_O w_Om w_Op w_Os'",
            "mass_fractions = 'w_O2_constraint w_O2s w_O2p w_O w_Om w_Op'", 1),
        "M6_break_drho_chain": original.replace(
            "prs*dmol/(8.31446*tmp)", "prs*0.0/(8.31446*tmp)", 1),
        "M7_break_invMn_dot": original.replace(
            "expression = '31.25*(d3+d4+d5+d6)'",
            "expression = '62.5*(d3+d4+d5+d6)'", 1),
        "M8_reintroduce_same_stage_derived_aux": original.replace(
            "[AuxKernels]",
            "[AuxKernels]\n  [bad_order_probe]\n"
            "    type = FunctorAux\n"
            "    variable = dMn_dt_out\n"
            "    functor = dMn_dt_model\n"
            "    execute_on = 'TIMESTEP_END'\n"
            "  []\n",
            1),
    }

    ok = True
    for name, mutated in mutations.items():
        detected = bool(validate_text(mutated))
        print(f"{name}: {'DETECTED' if detected else 'MISSED'}")
        ok &= detected

    print("R14_EVR1D_P0_MUTATION_SELFTEST: " + ("PASS" if ok else "FAIL"))
    return ok

def main():
    if len(sys.argv) == 2 and sys.argv[1] == "--self-test":
        return 0 if self_test() else 1
    if len(sys.argv) != 2:
        print("usage: validate_case.py INPUT.i | --self-test", file=sys.stderr)
        return 2
    errors = validate_text(Path(sys.argv[1]).read_text())
    if errors:
        print("R14_EVR1D_STATIC_CONTRACT: FAIL")
        for e in errors:
            print("  -", e)
        return 1
    print("R14_EVR1D_STATIC_CONTRACT: PASS")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
