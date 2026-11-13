#!/usr/bin/env python3
"""Native P2: existing FEM electron BC list moved unchanged from .i to JSON.

No time integration, physics or numerical parity. Exercises real physics-opt
--check-input, with a legacy .i control and fail-closed JSON mutations.
"""
import copy
import json
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

CI = Path(__file__).resolve().parent
DATA = json.loads((CI / "dd_plasma_boundary_json_p2.json").read_text())
JSON_INPUT = (CI / "dd_plasma_boundary_json_p2.i").read_text()
LEGACY_INPUT = (CI / "dd_plasma_boundary_legacy_p2.i").read_text()
PARSED_MEAN_INPUT = (CI / "dd_plasma_boundary_parsed_mean_p2.i").read_text()
LEGACY_DATA = (CI / "json_surface_rate_p2.json").read_text()


def check(exe: Path, root: Path, name: str, source: str, data: dict, valid: bool):
    work = root / name.lower()
    work.mkdir(parents=True, exist_ok=True)
    (work / "input.i").write_text(source, encoding="utf-8")
    (work / "dd_plasma_boundary_json_p2.json").write_text(
        json.dumps(data) + "\n", encoding="utf-8"
    )
    (work / "json_surface_rate_p2.json").write_text(LEGACY_DATA, encoding="utf-8")
    result = subprocess.run([str(exe), "--check-input", "-i", "input.i"],
                            cwd=work, text=True, capture_output=True, check=False)
    combined = result.stdout + result.stderr
    if valid:
        assert result.returncode == 0 and "Syntax OK" in combined, (
            name + " expected Syntax OK:\n" + combined[-4500:])
    else:
        assert result.returncode != 0 and "Syntax OK" not in combined, (
            name + " expected fail closed:\n" + combined[-4500:])
    print("DD_JSON_BC_" + name + "_P2_PASS", flush=True)


def main(exe: Path):
    assert exe.is_file()
    with TemporaryDirectory(prefix="issue402_bc_exact_") as folder:
        root = Path(folder)
        check(exe, root, "JSON_PRESENT", JSON_INPUT, DATA, True)
        check(exe, root, "PARSED_MEAN_FUNCTOR_CONSTRUCTION",
              PARSED_MEAN_INPUT, DATA, True)
        # One original BC block can own several sidesets. The JSON path
        # must not split it into multiple independent operators.
        multiside = copy.deepcopy(DATA)
        multiside["boundaries"]["left bottom"] = (
            multiside["boundaries"].pop("left")
        )
        multiside["boundaries"].pop("bottom")
        check(exe, root, "MULTI_SIDESET_GROUP_UNSPLIT", JSON_INPUT, multiside, True)
        check(exe, root, "LEGACY_EXPLICIT_BCS", LEGACY_INPUT, DATA, True)
        # Old Material registrations, normalized state and old Functor
        # output names are deliberately retired, not compatibility aliases.
        for label, old_class in (
            ("RETIRED_INTERMEDIATE_ES_CLASS", "ElectronWallFluxMaterial"),
            ("RETIRED_ADJACENT_ES_CLASS", "PhysicsElectronAdjacentSheathWallFluxMaterial"),
            ("RETIRED_THERMAL_CLASS", "PhysicsElectronWallFluxMaterial"),
        ):
            check(exe, root, label,
                  LEGACY_INPUT.replace("type = ESWallFluxMaterial",
                                       "type = " + old_class), DATA, False)
        check(exe, root, "RETIRED_NORMALIZED_MEAN_STATE",
              LEGACY_INPUT.replace("state_form = log_molar_eV",
                                   "state_form = normalized"), DATA, False)
        check(exe, root, "RETIRED_MEAN_OUTPUT_PARAM",
              LEGACY_INPUT.replace("    state_form = log_molar_eV",
                                   "    state_form = log_molar_eV\n    mean_energy_output = e_energy_eV"),
              DATA, False)
        check(exe, root, "RETIRED_MEAN_EN_FUNCTOR",
              LEGACY_INPUT.replace("mean_energy = e_energy_eV",
                                   "mean_energy = mean_en_solved"), DATA, False)
        no_registry = copy.deepcopy(DATA)
        no_registry.pop("boundaries")
        check(exe, root, "JSON_ABSENT_NO_GENERATED_BC", JSON_INPUT, no_registry, True)

        def mutate(label, fn):
            data = copy.deepcopy(DATA)
            fn(data)
            check(exe, root, label, JSON_INPUT, data, False)

        mutate("UNSUPPORTED_BC_TYPE",
               lambda d: d["boundaries"]["left"]["bcs"]["electron_wafer"].update(
                   type="InventedWallBC"))
        mutate("DUPLICATE_OPERATOR",
               lambda d: d["boundaries"]["left"]["bcs"].update(
                   extra_wall=copy.deepcopy(d["boundaries"]["left"]["bcs"]["electron_wafer"])))
        mutate("DUPLICATE_MESH_BOUNDARY",
               lambda d: d["boundaries"].update(
                   {"left bottom": {"bcs": {}}}))
        mutate("MISSING_FLUX",
               lambda d: d["boundaries"]["left"]["bcs"]["electron_wafer"].pop(
                   "wall_number_flux"))
        mutate("MISSING_ENERGY",
               lambda d: d["boundaries"]["left"]["bcs"]["electron_energy_wafer"].pop(
                   "mean_energy"))
        mutate("INVALID_BCS_LIST",
               lambda d: d["boundaries"]["left"].update(bcs=["one"]))
        mutate("UNKNOWN_EXTRA_BC_PARAM",
               lambda d: d["boundaries"]["left"]["bcs"]["electron_wafer"].update(
                   imaginary_parameter=1))
        mutate("EMPTY_CATALOGUE",
               lambda d: d.update(boundaries={}))
        mutate("UNSAFE_BC_NAME",
               lambda d: d["boundaries"]["left"]["bcs"].update(
                   **{"electron-wafer": d["boundaries"]["left"]["bcs"].pop("electron_wafer")}))
        mutate("RETIRED_DD_BOUNDARY_KEY",
               lambda d: d.update(drift_diffusion_boundary=d.pop("boundaries")))
        mutate("OLD_MESH_BOUNDARY_FIELD",
               lambda d: d["boundaries"]["left"].update(
                   mesh_boundary="left"))
        mutate("INVALID_PHYSICAL_SIDESET_NAME",
               lambda d: d["boundaries"].update(
                   {"invalid-side": d["boundaries"].pop("left")}))
    print("DD_JSON_BC_EXACT_LEGACY_NATIVE_P2_PASS_P3_NOT_RUN SCIENCE_HOLD", flush=True)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: check_issue402_dd_json_plasma_boundary_p2.py /path/to/physics-opt")
    main(Path(sys.argv[1]).resolve())
