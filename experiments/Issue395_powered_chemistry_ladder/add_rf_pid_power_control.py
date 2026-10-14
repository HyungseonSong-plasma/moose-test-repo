#!/usr/bin/env python3
"""Patch the Issue #395 RF plasma overlay with standard-MOOSE lagged PID power feedback.

The controller does not repeat/reject a timestep.  It observes the accepted
TIMESTEP_END plasma absorbed RF power and changes a Receiver postprocessor that
multiplies RF deposition on the following timestep.
"""
from __future__ import annotations

import argparse
from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    n = text.count(old)
    if n != 1:
        raise RuntimeError(f"{label}: expected one match, found {n}")
    return text.replace(old, new, 1)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--overlay", type=Path, required=True)
    ap.add_argument("--target-w", type=float, default=1000.0)
    ap.add_argument("--kp", type=float, default=-1.0e-3)
    ap.add_argument("--minimum-scale", type=float, default=0.5)
    ap.add_argument("--maximum-scale", type=float, default=1.5)
    a = ap.parse_args()

    if a.target_w <= 0.0:
        raise RuntimeError("target power must be positive")
    if a.kp >= 0.0:
        raise RuntimeError("Kp must be negative because PID delta = current - target")
    if not (0.0 < a.minimum_scale < a.maximum_scale):
        raise RuntimeError("invalid PID scale bounds")

    text = a.overlay.read_text(encoding="utf-8")

    # The standard T6 overlay defines a scalar rf_scale_t6 root parameter.  The
    # PID overlay replaces that path completely with a Receiver postprocessor;
    # keeping the legacy root parameter would make strict MOOSE input checking
    # reject it as unused.
    text = replace_once(
        text,
        "rf_scale_t6 = 1.0\n",
        "",
        "obsolete scalar RF scale parameter",
    )

    old_scaled = """  [q_rf_scaled_t6]\n    type = ParsedMaterial\n    property_name = q_rf_scaled_t6\n    coupled_variables = 'E_real_rf_t6 E_imag_rf_t6'\n    material_property_names = 'sigma_real_rf_t6'\n    constant_names = 'scale'\n    constant_expressions = '${rf_scale_t6}'\n    expression = 'scale*0.5*sigma_real_rf_t6*(E_real_rf_t6^2 + E_imag_rf_t6^2)'\n    block = plasma\n  []\n"""
    new_scaled = """  [q_rf_scaled_t6]\n    type = ParsedMaterial\n    property_name = q_rf_scaled_t6\n    coupled_variables = 'E_real_rf_t6 E_imag_rf_t6'\n    material_property_names = 'sigma_real_rf_t6'\n    postprocessor_names = 'rf_pid_scale_t6'\n    expression = 'rf_pid_scale_t6*0.5*sigma_real_rf_t6*(E_real_rf_t6^2 + E_imag_rf_t6^2)'\n    block = plasma\n  []\n"""
    text = replace_once(text, old_scaled, new_scaled, "scaled RF material")

    old_source = """  [q_rf_eV_mol_t6]\n    type = ParsedMaterial\n    property_name = q_rf_eV_mol_t6\n    coupled_variables = 'E_real_rf_t6 E_imag_rf_t6'\n    material_property_names = 'sigma_real_rf_t6'\n    constant_names = 'scale enabled F'\n    constant_expressions = '${rf_scale_t6} ${source_enable_t6} ${faraday_t6}'\n    expression = 'enabled*scale*0.5*sigma_real_rf_t6*(E_real_rf_t6^2 + E_imag_rf_t6^2)/F'\n    block = plasma\n  []\n"""
    new_source = """  [q_rf_eV_mol_t6]\n    type = ParsedMaterial\n    property_name = q_rf_eV_mol_t6\n    coupled_variables = 'E_real_rf_t6 E_imag_rf_t6'\n    material_property_names = 'sigma_real_rf_t6'\n    postprocessor_names = 'rf_pid_scale_t6'\n    constant_names = 'enabled F'\n    constant_expressions = '${source_enable_t6} ${faraday_t6}'\n    expression = 'enabled*rf_pid_scale_t6*0.5*sigma_real_rf_t6*(E_real_rf_t6^2 + E_imag_rf_t6^2)/F'\n    block = plasma\n  []\n"""
    text = replace_once(text, old_source, new_source, "electron RF source material")

    pp_anchor = "[Postprocessors]\n"
    pp_insertion = """[Postprocessors]\n  [rf_pid_scale_t6]\n    type = Receiver\n    default = 1.0\n    execute_on = 'INITIAL TIMESTEP_END'\n  []\n"""
    text = replace_once(text, pp_anchor, pp_insertion, "PID Receiver postprocessor")

    control = f"""[Controls]\n  [rf_power_pid_t6]\n    type = PIDTransientControl\n    postprocessor = P_rf_scaled_W_t6\n    target = {a.target_w:.17g}\n    parameter_pp = rf_pid_scale_t6\n    K_integral = 0\n    K_proportional = {a.kp:.17g}\n    K_derivative = 0\n    minimum_output_value = {a.minimum_scale:.17g}\n    maximum_output_value = {a.maximum_scale:.17g}\n    execute_on = TIMESTEP_END\n  []\n[]\n\n"""
    text = replace_once(text, "[Outputs]\n", control + "[Outputs]\n", "PID Controls insertion")

    required = (
        "type = PIDTransientControl",
        "postprocessor = P_rf_scaled_W_t6",
        "parameter_pp = rf_pid_scale_t6",
        "postprocessor_names = 'rf_pid_scale_t6'",
    )
    for token in required:
        if token not in text:
            raise RuntimeError(f"PID patch missing token: {token}")
    if "rf_scale_t6" in text:
        raise RuntimeError("obsolete rf_scale_t6 path remains in PID overlay")

    a.overlay.write_text(text, encoding="utf-8")
    print(
        "ISSUE395_RF_PID_OVERLAY_PATCH_PASS "
        f"target_W={a.target_w:.9g} Kp={a.kp:.9g} "
        f"bounds=[{a.minimum_scale:.9g},{a.maximum_scale:.9g}] "
        "mode=accepted_timestep_lagged_feedback trial_repeat=false "
        "legacy_rf_scale_removed=true"
    )


if __name__ == "__main__":
    main()
