#!/usr/bin/env python3
"""Issue #397 D1: observational native face probes on original 200 W B model.

Only adds AuxVariables/AuxKernels (no residual, mesh, physical law, BC, or
time-step change). Retains the historical time nodes through 2 us.
"""
from __future__ import annotations
import argparse
import re
from pathlib import Path

TEND_US = 2.0
FIELDS = {
    "d1_gamma_o2_positive": "ion_wall_number_flux",
    "d1_gamma_o_positive": "atomic_positive_ion_wall_number_flux",
    "d1_gamma_o_negative": "negative_ion_wall_number_flux",
    "d1_gamma_electron": "electron_wall_number_flux",
    "d1_sheath_drop_V": "electron_sheath_drop_V",
    "d1_ne_m3": "n_e_physical",
    "d1_mean_energy_eV": "mean_en_solved",
    "d1_electron_mean_speed_m_s": "electron_mean_speed",
}
GEOM = {
    "d1_normal_r": "normal_r",
    "d1_normal_z": "normal_z",
    "d1_owner": "owner",
    "d1_d_perp_m": "d_perp",
    "d1_e_n_V_m": "e_n",
}


def replace_top_level_block(text: str, name: str, addition: str) -> str:
    rx = re.compile(r"(?ms)^\[" + re.escape(name) + r"\]\n.*?^\[\]\n")
    matched = list(rx.finditer(text))
    if len(matched) != 1:
        raise ValueError(f"Expected exactly one [{name}], got {len(matched)}")
    m = matched[0]
    part = m.group(0)
    return text[: m.start()] + part[:-3] + addition + "[]\n" + text[m.end():]


def transform(text: str) -> tuple[str, int]:
    if "d1_gamma_electron" in text:
        raise ValueError("D1 probes already installed")
    if "expression = '1.602176634e-19*(gi+gop-gm-ge)'" not in text:
        raise ValueError("Expected original B physical-current owner")
    # The physical electron sheath owner references mean_en_solved, not a functor called mean_energy.
    # Checking this input contract guards against another initialSetup-only missing-functor failure.
    if "mean_energy = mean_en_solved" not in text:
        raise ValueError("Original sheath mean-energy provider no longer matches mean_en_solved")
    for key in ("type = PhysicsLowerDSurfaceCurrent", "type = PhysicsElectronAdjacentSheathWallFluxMaterial",
                "type = PhysicsLowerDSurfaceCurrentProbeAux"):
        if key not in text:
            raise ValueError(f"Missing production baseline object: {key}")

    auxvars = "".join(
        f"  [{name}]\n    family = MONOMIAL\n    order = CONSTANT\n"
        "    block = wafer_surface\n  []\n"
        for name in (*FIELDS, *GEOM)
    )
    text = replace_top_level_block(text, "AuxVariables", auxvars)

    probes = "".join(
        f"  [{name}_kernel]\n"
        "    type = PhysicsLowerDSurfaceCurrentProbeAux\n"
        f"    variable = {name}\n"
        f"    surface_current_density = {functor}\n"
        "    block = wafer_surface\n"
        "    execute_on = 'INITIAL TIMESTEP_END'\n"
        "  []\n"
        for name, functor in FIELDS.items()
    )
    probes += "".join(
        f"  [{name}_kernel]\n"
        "    type = PhysicsWaferD1GeometryProbeAux\n"
        f"    variable = {name}\n"
        "    surface_current_density = wafer_net_surface_current_density\n"
        "    potential = potential\n"
        f"    component = {component}\n"
        "    block = wafer_surface\n"
        "    execute_on = 'INITIAL TIMESTEP_END'\n"
        "  []\n"
        for name, component in GEOM.items()
    )
    text = replace_top_level_block(text, "AuxKernels", probes)

    m = re.search(r"(?m)^    time_sequence = '([^']+)'$", text)
    if not m:
        raise ValueError("Canonical time_sequence missing")
    old = [float(x) for x in m.group(1).split()]
    if old[0] != 0. or any(b <= a for a, b in zip(old, old[1:])):
        raise ValueError("Invalid canonical time sequence")
    retained = [t for t in old if t <= TEND_US * 1e-6 + 1e-15]
    if len(retained) != 291 or abs(retained[-1] - TEND_US * 1e-6) > 1e-14:
        raise ValueError(f"Unexpected D1 timegrid: {len(retained)} points, last={retained[-1]}")
    repl = "    time_sequence = '" + " ".join(f"{x:.17g}" for x in retained) + "'"
    text = text[:m.start()] + repl + text[m.end():]
    text, count = re.subn(r"(?m)^  end_time = \S+[ \t]*$", f"  end_time = {TEND_US * 1e-6:.17g}", text, count=1)
    if count != 1:
        raise ValueError("Executioner end_time missing")
    for name in (*FIELDS, *GEOM):
        if text.count(f"[{name}]") != 1 or text.count(f"[{name}_kernel]") != 1:
            raise ValueError(f"D1 diagnostic {name} missing/duplicate")
    return text, len(retained) - 1


def self_test():
    template = """[Variables]\n[]\n[AuxVariables]\n  [wafer_net_current_probe]\n  []\n[]\n[AuxKernels]\n  [wafer_net_current_probe_kernel]\n    type = PhysicsLowerDSurfaceCurrentProbeAux\n  []\n[]\n[Executioner]\n  end_time = 6e-5\n    time_sequence = '""" + " ".join(
        f"{t:.17g}" for t in
        ([k * 1e-9 for k in range(101)] + [1e-7 + k * 1e-8 for k in range(1, 191)] +
         [2e-6 + k * 1e-7 for k in range(1, 81)] +
         [1e-5 + k * 1e-6 for k in range(1, 51)])
    ) + """'\n[]\n# type = PhysicsLowerDSurfaceCurrent\n# type = PhysicsElectronAdjacentSheathWallFluxMaterial\n# mean_energy = mean_en_solved\n# expression = '1.602176634e-19*(gi+gop-gm-ge)'\n"""
    updated, steps = transform(template)
    assert steps == 290
    assert updated.count("type = PhysicsWaferD1GeometryProbeAux") == len(GEOM)
    assert updated.count("type = PhysicsLowerDSurfaceCurrentProbeAux") == len(FIELDS) + 1
    assert "end_time = 2e-06" in updated or "end_time = 1.9999999999999999e-06" in updated
    try:
        transform(updated)
    except ValueError:
        pass
    else:
        raise AssertionError("duplicate-instrumentation negative control must be rejected")
    print("ISSUE397_D1_INSTRUMENT_SELFTEST_PASS")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path, nargs="?")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    if not args.input:
        parser.error("input required")
    old = args.input.read_text(encoding="utf-8")
    new, steps = transform(old)
    args.input.write_text(new, encoding="utf-8")
    print(f"ISSUE397_D1_NATIVE_DIAGNOSTICS_INPUT_PASS steps={steps} "
          f"end_time_us={TEND_US} face_fields={len(FIELDS) + len(GEOM)}")
    print("OBSERVATION_ONLY: original B current, original mesh, unchanged physics, same dt")


if __name__ == "__main__":
    main()
