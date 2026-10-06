#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
LEVEL_MATRIX = HERE / "prepare_full_monolithic_log_simplex_level_matrix.py"
TOTAL_TIME = 1.0e-10  # 0.1 ns

CASES = {
    "dt0p1ns_1step": (1.0e-10, 1),
    "dt0p01ns_10steps": (1.0e-11, 10),
}


def load_level_matrix_module():
    spec = importlib.util.spec_from_file_location("level_matrix", LEVEL_MATRIX)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load Level-4 matrix generator")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def executioner_bounds(text: str) -> tuple[int, int]:
    start = text.find("[Executioner]\n")
    if start < 0:
        raise RuntimeError("missing [Executioner] section")

    # Use the nearest following top-level section. The previous implementation
    # preferred [Outputs] even when [Preconditioning] was inserted first, which
    # caused num_steps to be written outside [Executioner].
    candidates = []
    for name in ("Preconditioning", "Outputs", "Debug"):
        pos = text.find(f"\n[{name}]\n", start + 1)
        if pos > start:
            candidates.append(pos)
    end = min(candidates) if candidates else len(text)
    return start, end


def set_top_level_parameter(section: str, name: str, value: str) -> str:
    pattern = re.compile(rf"(?m)^  {re.escape(name)}\s*=.*$")
    matches = list(pattern.finditer(section))
    if len(matches) > 1:
        raise RuntimeError(f"multiple top-level Executioner parameters named {name}")
    line = f"  {name} = {value}"
    if matches:
        return pattern.sub(line, section, count=1)

    close = section.rfind("[]")
    if close < 0:
        raise RuntimeError("unterminated [Executioner] section")
    return section[:close] + line + "\n" + section[close:]


def build(case: str) -> Path:
    if case not in CASES:
        raise ValueError(case)
    dt, num_steps = CASES[case]

    module = load_level_matrix_module()
    base = module.build(4)
    text = base.read_text(encoding="utf-8")

    start, end = executioner_bounds(text)
    section = text[start:end]
    for name, value in (
        ("dt", f"{dt:.17g}"),
        ("dtmin", f"{dt:.17g}"),
        ("dtmax", f"{dt:.17g}"),
        ("end_time", f"{TOTAL_TIME:.17g}"),
        ("num_steps", str(num_steps)),
    ):
        section = set_top_level_parameter(section, name, value)
    text = text[:start] + section + text[end:]

    # Solver hierarchy and plasma physics remain identical to the successful
    # L4 baseline. Only the fixed timestep schedule changes.
    required = (
        "splitting = 'heavy fast'",
        "splitting = 'electron poisson'",
        "splitting_type = multiplicative",
        "type = PhysicsFVLogMolarElectrostaticDrift",
        "type = PhysicsFVElectronEnergyJouleHeating",
        "type = PhysicsFVElectronGroundedSheathCollectionBC",
        "property_name = charge_number_density",
        "pc_hypre_type",
        "boomeramg",
    )
    for token in required:
        if token not in text:
            raise RuntimeError(f"L4 baseline contract missing: {token}")

    start, end = executioner_bounds(text)
    exec_section = text[start:end]
    expected_lines = (
        f"  dt = {dt:.17g}",
        f"  dtmin = {dt:.17g}",
        f"  dtmax = {dt:.17g}",
        f"  end_time = {TOTAL_TIME:.17g}",
        f"  num_steps = {num_steps}",
    )
    for expected in expected_lines:
        if expected not in exec_section:
            raise RuntimeError(f"time contract missing from [Executioner]: {expected}")

    # Ensure the time-control parameters did not leak into preconditioning.
    if "[Preconditioning]" in text:
        pre = text[text.find("[Preconditioning]"):]
        if re.search(r"(?m)^  (dt|dtmin|dtmax|end_time|num_steps)\s*=", pre):
            raise RuntimeError("time-control parameter leaked outside [Executioner]")

    out = HERE / f"full_monolithic_l4_{case}.i"
    out.write_text(text, encoding="utf-8")
    print(f"wrote {out}")
    print(
        f"case={case} dt={dt:.17g} dtmin={dt:.17g} dtmax={dt:.17g} "
        f"num_steps={num_steps} total_time={TOTAL_TIME:.17g}"
    )
    print("L4 baseline solver/physics unchanged; fixed timestep schedule verified")
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", choices=tuple(CASES), required=True)
    args = parser.parse_args()
    build(args.case)


if __name__ == "__main__":
    main()
