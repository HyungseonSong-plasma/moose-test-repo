#!/usr/bin/env python3
"""Exact-source Native P2 for JSON-owned DriftDiffusion boundary migration.

Never runs a time step; exercises the real physics-opt --check-input parser,
Functor Material/BC registrations, and fail-closed JSON boundary mutations.
"""
from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

CI = Path(__file__).resolve().parent
POSITIVE = CI / "dd_plasma_boundary_json_p2.i"
EXTERNAL = CI / "dd_plasma_boundary_external_mean_p2.i"
DATA = CI / "dd_plasma_boundary_json_p2.json"


def run(exe: Path, folder: Path, inp: str, data: dict, should_pass: bool, name: str):
    folder.mkdir(exist_ok=True)
    (folder / "dd_plasma_boundary_json_p2.json").write_text(
        json.dumps(data, indent=2) + "\n", encoding="utf-8"
    )
    (folder / "input.i").write_text(inp, encoding="utf-8")
    result = subprocess.run(
        [str(exe), "--check-input", "-i", "input.i"],
        cwd=folder, text=True, capture_output=True, check=False,
    )
    output = result.stdout + result.stderr
    if should_pass:
        assert result.returncode == 0 and "Syntax OK" in output, (
            f"{name} must parse: rc={result.returncode}\n{output[-4000:]}"
        )
    else:
        assert result.returncode != 0 and "Syntax OK" not in output, (
            f"{name} must fail: rc={result.returncode}\n{output[-4000:]}"
        )
    print(f"DD_JSON_PLASMA_BOUNDARY_{name}_P2_PASS", flush=True)


def main(exe: Path):
    assert exe.is_file(), exe
    base = json.loads(DATA.read_text(encoding="utf-8"))
    inp = POSITIVE.read_text(encoding="utf-8")
    ext = EXTERNAL.read_text(encoding="utf-8")
    assert "drift_diffusion_boundary" in base
    with TemporaryDirectory(prefix="issue402_dd_bound_") as temp:
        root = Path(temp)
        run(exe, root / "positive_generated", inp, base, True, "GENERATED")
        run(exe, root / "positive_external_mean", ext, base, True, "EXTERNAL_MEAN")

        def mutate(name: str, f, original: str = inp):
            data = copy.deepcopy(base)
            f(data)
            run(exe, root / name.lower(), original, data, False, name)

        mutate("UNKNOWN_MODEL",
               lambda d: d["drift_diffusion_boundary"]["wafer"].update(
                   electron_model="invented_wall_law"))
        mutate("DUPLICATE_MESH_SIDESET",
               lambda d: d["drift_diffusion_boundary"]["cover"].update(
                   mesh_boundary="left"))
        mutate("OPEN_INLET_AS_SOLID",
               lambda d: d["drift_diffusion_boundary"]["inlet"].update(
                   electron_model="adjacent_sheath"))
        mutate("EMPTY_BOUNDARY_CATALOGUE",
               lambda d: d.update(drift_diffusion_boundary={}))
        mutate("MISSING_JSON_CATALOGUE",
               lambda d: d.pop("drift_diffusion_boundary"))
        mutate("NO_SOLID_WALL",
               lambda d: [
                   x.update(electron_model="open")
                   for x in d["drift_diffusion_boundary"].values()])
        mutate("UNKNOWN_MESH_SIDESET",
               lambda d: d["drift_diffusion_boundary"]["wafer"].update(
                   mesh_boundary="definitely_missing_sideset"))
        mutate("UNSAFE_BOUNDARY_ALIAS",
               lambda d: d["drift_diffusion_boundary"].update(
                   **{"wafer-different": d["drift_diffusion_boundary"].pop("wafer")}))
        mutate("MISSING_MESH_BOUNDARY_FIELD",
               lambda d: d["drift_diffusion_boundary"]["wafer"].pop("mesh_boundary"))
        mutate("EXTRA_UNOWNED_FIELD",
               lambda d: d["drift_diffusion_boundary"]["wafer"].update(
                   source="two_owners"))
        mutate("WALL_NEGATIVE_STICKING", lambda d: None,
               inp.replace("plasma_boundary = json",
                           "plasma_boundary = json\n        plasma_boundary_sticking = -0.1"))
        mutate("INACTIVE_WITH_CONFIG", lambda d: None,
               inp.replace("plasma_boundary = json",
                           "plasma_boundary = none\n        plasma_boundary_sticking = 0.5"))
        # Every source bound physical wall has one valid forward mapping;
        # open boundaries are parsed but create no electron sheath BC.
    print("DD_JSON_PLASMA_BOUNDARY_NATIVE_P2_PASS_P3_NOT_RUN SCIENCE_HOLD")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: check_issue402_dd_json_plasma_boundary_p2.py physics-opt")
    main(Path(sys.argv[1]).resolve())
