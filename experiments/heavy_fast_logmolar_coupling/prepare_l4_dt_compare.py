#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
LEVEL_MATRIX = HERE / "prepare_full_monolithic_log_simplex_level_matrix.py"
TOTAL_TIME = 1.0e-8  # 10 ns

CASES = {
    "dt1ns_10steps": (1.0e-9, 10),
    "dt10ns_1step": (1.0e-8, 1),
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
    next_section = text.find("\n[Outputs]\n", start)
    if next_section < 0:
        next_section = text.find("\n[Preconditioning]\n", start)
    if next_section < 0:
        next_section = text.find("\n[Debug]\n", start)
    if next_section < 0:
        next_section = len(text)
    return start, next_section


def set_top_level_parameter(section: str, name: str, value: str) -> str:
    # Executioner parameters are two-space indented. Restrict replacement to those
    # so nested TimeStepper blocks are not accidentally edited.
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
    section = set_top_level_parameter(section, "dt", f"{dt:.17g}")
    section = set_top_level_parameter(section, "num_steps", str(num_steps))
    section = set_top_level_parameter(section, "end_time", f"{TOTAL_TIME:.17g}")
    text = text[:start] + section + text[end:]

    # Contract: solver hierarchy and full plasma physics are inherited unchanged
    # from the successful L4 baseline; only physical timestep/count changes.
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
    for expected in (
        f"  dt = {dt:.17g}",
        f"  num_steps = {num_steps}",
        f"  end_time = {TOTAL_TIME:.17g}",
    ):
        if expected not in exec_section:
            raise RuntimeError(f"time contract missing: {expected}")

    out = HERE / f"full_monolithic_l4_{case}.i"
    out.write_text(text, encoding="utf-8")
    print(f"wrote {out}")
    print(f"case={case} dt={dt:.17g} num_steps={num_steps} total_time={TOTAL_TIME:.17g}")
    print("L4 baseline solver/physics unchanged; only timestep schedule differs")
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", choices=tuple(CASES), required=True)
    args = parser.parse_args()
    build(args.case)


if __name__ == "__main__":
    main()
