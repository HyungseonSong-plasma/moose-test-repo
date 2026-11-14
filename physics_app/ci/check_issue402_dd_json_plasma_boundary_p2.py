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
PHYSICS_AUTO_INPUT = (CI / "dd_plasma_boundary_json_physics_auto_p2.i").read_text()
LEGACY_DATA = (CI / "json_surface_rate_p2.json").read_text()
KINETIC_TABLE = (CI / "plasma_closures_rate_a.txt").read_text()
# Synthetic kinetic-rate construction; actual private S6 tables are not used.
KINETIC_DATA = copy.deepcopy(DATA)
KINETIC_DATA["species"].update({
    "O2": {
        "elements": {"O": 2}, "charge_number": 0,
        "molar_mass_kg_mol": 0.032,
        "initial_vol_mass_fraction": 1.0,
        "initial_inlet_mass_fraction": 1.0,
        "mass_fraction_functor": "w_O2"
    },
    "O2p": {
        "elements": {"O": 2}, "charge_number": 1,
        "molar_mass_kg_mol": 0.032,
        "initial_vol_mass_fraction": 0.0,
        "initial_inlet_mass_fraction": 0.0,
        "mass_fraction_functor": "w_O2p"
    }
})
KINETIC_DATA["equations"] = {"EI-415": "e + O2 -> 2e + O2p"}
KINETIC_DATA["reactions"] = [{
    "id": "EI-415", "reactants": {"e": 1, "O2": 1},
    "products": {"e": 2, "O2p": 1},
    "table": "plasma_closures_rate_a.txt",
    "units": "mol/(m^3 s)", "energy_loss_eV": 12.06
}]
KINETIC_INPUT = PHYSICS_AUTO_INPUT.replace(
    "    files = dd_plasma_boundary_json_p2.json\n",
    "    files = dd_plasma_boundary_json_p2.json\n"
    "    pressure = 1.333223684\n    temperature = 300\n"
    "    state_model = ideal_gas\n", 1
).replace(
    "    [Transport]\n      [DriftDiffusion]",
    "    [Transport]\n      [Chemistry]\n      []\n      [DriftDiffusion]", 1
).replace(
    "[Executioner]\n",
    "[FunctorMaterials]\n  [synthetic_live_composition]\n"
    "    type = ADGenericFunctorMaterial\n"
    "    prop_names = 'w_O2 w_O2p'\n"
    "    prop_values = '1 0'\n  []\n[]\n[Executioner]\n", 1
)
assert KINETIC_INPUT != PHYSICS_AUTO_INPUT
assert "target_molar_concentration" not in json.dumps(KINETIC_DATA)
assert "table_sha256" not in json.dumps(KINETIC_DATA)

def synthetic_s6(variant: str) -> dict:
    """Exercise eight *real* S6 reaction definitions without private rate bytes."""
    mechanism = json.loads((
        CI.parents[1] / "experiments/Issue402_plasma_dsl_g1/chemistry" /
        f"unified_s6_{variant}.json"
    ).read_text())
    data = copy.deepcopy(mechanism)
    # Retain all eight original S6 electron sheath BC objects and their
    # canonical names/variable bindings. Only map physical S6 sideset
    # identifiers to the four public GeneratedMesh sidesets for synthetic P2.
    original_boundaries = copy.deepcopy(data["boundaries"])
    assert len(original_boundaries) == 4
    data["boundaries"] = {
        synthetic_side: entry
        for synthetic_side, entry in zip(("left", "bottom", "right", "top"),
                                         original_boundaries.values())
    }
    assert sum(len(entry["bcs"]) for entry in data["boundaries"].values()) == 8
    assert sum(bc["type"] == "FEMElectronSheathBC"
               for entry in data["boundaries"].values()
               for bc in entry["bcs"].values()) == 4
    assert sum(bc["type"] == "FEMElectronEnergySheathBC"
               for entry in data["boundaries"].values()
               for bc in entry["bcs"].values()) == 4
    data["species"]["e"] = copy.deepcopy(DATA["species"]["e"])
    for name, spec in data["species"].items():
        if name == "e":
            continue
        for key in ("transport_coef", "mobility", "diffusivity", "table_file",
                    "table_units", "bounds_policy", "pressure", "gas_temperature"):
            spec.pop(key, None)
        spec["initial_vol_mass_fraction"] = 1.0 if name == "O2" else 0.0
        spec["initial_inlet_mass_fraction"] = 1.0 if name == "O2" else 0.0
        spec["mass_fraction_functor"] = "w_" + name
    for reaction in data["reactions"]:
        if "table" in reaction:
            reaction["table"] = "plasma_closures_rate_a.txt"
        assert "table_sha256" not in reaction
        assert "target_molar_concentration" not in reaction
    assert sum("table" in r for r in data["reactions"]) == 7
    assert sum(r.get("rate", {}).get("model") == "power_law"
               for r in data["reactions"]) == 1
    assert len(data["reactions"]) == 8
    return data


S6_SYNTHETIC_INPUT = KINETIC_INPUT.replace(
    "  [potential]\n    type = MooseVariable\n  []",
    "  [potential]\n    type = MooseVariable\n  []\n"
    "  [log_Op]\n    type = MooseVariableFVReal\n  []", 1
).replace(
    "prop_names = 'w_O2 w_O2p'",
    "prop_names = 'w_O2 w_O w_O2p w_Om w_Op w_O2a'", 1
).replace(
    "prop_values = '1 0'",
    "prop_values = '1 0 0 0 0 0'", 1
)
assert S6_SYNTHETIC_INPUT != KINETIC_INPUT
assert "log_Op" in S6_SYNTHETIC_INPUT


def check(exe: Path, root: Path, name: str, source: str, data: dict, valid: bool,
          expected_error: str | None = None):
    work = root / name.lower()
    work.mkdir(parents=True, exist_ok=True)
    (work / "input.i").write_text(source, encoding="utf-8")
    (work / "dd_plasma_boundary_json_p2.json").write_text(
        json.dumps(data) + "\n", encoding="utf-8"
    )
    (work / "json_surface_rate_p2.json").write_text(LEGACY_DATA, encoding="utf-8")
    (work / "plasma_closures_rate_a.txt").write_text(KINETIC_TABLE, encoding="utf-8")
    result = subprocess.run([str(exe), "--check-input", "-i", "input.i"],
                            cwd=work, text=True, capture_output=True, check=False)
    combined = result.stdout + result.stderr
    if valid:
        assert result.returncode == 0 and "Syntax OK" in combined, (
            name + " expected Syntax OK:\n" + combined[-4500:])
    else:
        assert result.returncode != 0 and "Syntax OK" not in combined, (
            name + " expected fail closed:\n" + combined[-4500:])
        if expected_error:
            assert expected_error in combined, (
                name + " expected diagnostic '" + expected_error + "':\n" +
                combined[-4500:])
    print("DD_JSON_BC_" + name + "_P2_PASS", flush=True)


def main(exe: Path):
    assert exe.is_file()
    with TemporaryDirectory(prefix="issue402_bc_exact_") as folder:
        root = Path(folder)
        # Root JSON parses/validates declarations but does not instantiate
        # DriftDiffusion BCs without the corresponding equation Physics.
        check(exe, root, "ROOT_ONLY_JSON_BC_REJECTED", JSON_INPUT, DATA,
              False, "JSON FEMElectronSheathBC requires")
        check(exe, root, "JSON_PRESENT", PHYSICS_AUTO_INPUT, DATA, True)
        check(exe, root, "PHYSICS_AUTO_LOG_E_ENERGY_AND_BCS",
              PHYSICS_AUTO_INPUT, DATA, True)
        wrong_particle_state = copy.deepcopy(DATA)
        wrong_particle_state["boundaries"]["left"]["bcs"]["electron_wafer"][
            "variable"] = "log_e_energy"
        check(exe, root, "ELECTRON_SHEATH_WRONG_SOLVER_STATE",
              PHYSICS_AUTO_INPUT, wrong_particle_state, False,
              "JSON FEMElectronSheathBC must target canonical log_e")
        wrong_energy_state = copy.deepcopy(DATA)
        wrong_energy_state["boundaries"]["left"]["bcs"]["electron_energy_wafer"][
            "variable"] = "log_e"
        check(exe, root, "ENERGY_SHEATH_WRONG_SOLVER_STATE",
              PHYSICS_AUTO_INPUT, wrong_energy_state, False,
              "JSON FEMElectronEnergySheathBC must target canonical log_e_energy")
        # One Chemistry action creates the EI strict-table progress R_EI415,
        # both electron RHS FunctorKernels, and all eight? Here two BC
        # groups exercise canonical e_wall_number_flux and energy coupling.
        check(exe, root, "NATIVE_EI415_TABLE_BOTH_FEM_EQUATIONS",
              KINETIC_INPUT, KINETIC_DATA, True)
        for variant in ("417", "941"):
            check(exe, root, "S6_" + variant + "_EIGHT_REACTION_FEM_CONSTRUCTION",
                  S6_SYNTHETIC_INPUT, synthetic_s6(variant), True)
        wrong_table = copy.deepcopy(KINETIC_DATA)
        wrong_table["reactions"][0]["table"] = "missing_ei415.txt"
        check(exe, root, "EI_RATE_MISSING_TABLE_FAIL_CLOSED",
              KINETIC_INPUT, wrong_table, False, "table cannot be opened")
        for forbidden in ("target_molar_concentration", "table_sha256"):
            invalid = copy.deepcopy(KINETIC_DATA)
            invalid["reactions"][0][forbidden] = "not-an-input-option"
            check(exe, root, "EI_FORBIDDEN_" + forbidden.upper(),
                  KINETIC_INPUT, invalid, False, "table metadata/target")
        dual_owner = copy.deepcopy(KINETIC_DATA)
        dual_owner["reactions"][0]["rate"] = {
            "model": "constant", "A": 1.0, "basis": "molar"
        }
        check(exe, root, "EI_DUPLICATE_RATE_AND_TABLE_FAIL_CLOSED",
              KINETIC_INPUT, dual_owner, False,
              "table requires an EI volume reaction without rate")
        # A JSON electron energy BC cannot be silently ignored when its
        # DriftDiffusion Energy Physics is absent.
        energy_missing = PHYSICS_AUTO_INPUT.replace(
            "        [Energy]\n          fem_species = e\n          fem_potential = potential\n          initial_molar_energy_density_eV = 8.3e-9\n        []\n",
            "", 1
        )
        assert energy_missing != PHYSICS_AUTO_INPUT
        check(exe, root, "ENERGY_BC_WITHOUT_DD_ENERGY_REJECTED",
              energy_missing, DATA, False,
              "JSON FEMElectronEnergySheathBC requires")

        # JSON owns continuity initial number density for FEM AND FVM.
        # The .i selectors contain only species IDs (no positional values).
        assert "fem_species = e" in PHYSICS_AUTO_INPUT
        assert "fem_species = 'e 1e15'" not in PHYSICS_AUTO_INPUT
        assert DATA["species"]["e"]["initial_number_density"] == 1e15

        fvm_data = copy.deepcopy(DATA)
        fvm_data["species"]["O2p"] = {
            "elements": {"O": 2},
            "charge_number": 1,
            "initial_number_density": 1e14
        }
        fvm_data["species"]["O2p"].update(
            transport_coef="constant", mobility=0.15, diffusivity=0.075
        )
        fvm_input = PHYSICS_AUTO_INPUT.replace(
            "fem_species = e\n          fem_potential = potential",
            "fem_species = e\n          fvm_species = O2p\n          fem_potential = potential",
            1
        )
        assert fvm_input != PHYSICS_AUTO_INPUT
        check(exe, root, "JSON_FEM_FVM_INITIAL_NUMBER_DENSITY",
              fvm_input, fvm_data, True)

        # Electrons use FEM for both continuity and energy. Ion/non-electron
        # FVM paths above remain valid; these negative controls must fail.
        electron_fvm_continuity = PHYSICS_AUTO_INPUT.replace(
            "fem_species = e\n          fem_potential = potential",
            "fvm_species = e\n          fem_potential = potential", 1
        )
        assert electron_fvm_continuity != PHYSICS_AUTO_INPUT
        check(exe, root, "ELECTRON_FVM_CONTINUITY_REJECTED",
              electron_fvm_continuity, DATA, False, "Electron continuity is FEM-only")

        electron_fvm_energy = PHYSICS_AUTO_INPUT.replace(
            "        [Energy]\n          fem_species = e\n",
            "        [Energy]\n          fem_species = e\n          fvm_species = e\n", 1
        )
        assert electron_fvm_energy != PHYSICS_AUTO_INPUT
        check(exe, root, "ELECTRON_FVM_ENERGY_OPTION_REJECTED",
              electron_fvm_energy, DATA, False)

        fvm_missing = copy.deepcopy(fvm_data)
        del fvm_missing["species"]["O2p"]["initial_number_density"]
        check(exe, root, "JSON_FVM_INITIAL_MISSING_WITHOUT_EXTERNAL_VARIABLE",
              fvm_input, fvm_missing, False, "requires species.O2p.initial_number_density")

        # Fail-closed JSON schema: a log-molar solved density requires a
        # finite, strictly positive particle number density [1/m^3].
        for label, bad in (
            ("JSON_INITIAL_ZERO", 0.0),
            ("JSON_INITIAL_NEGATIVE", -1.0),
            ("JSON_INITIAL_STRING", "1e15"),
            ("JSON_INITIAL_NULL", None)
        ):
            invalid = copy.deepcopy(DATA)
            invalid["species"]["e"]["initial_number_density"] = bad
            check(exe, root, label, PHYSICS_AUTO_INPUT, invalid, False)

        no_initial = copy.deepcopy(DATA)
        del no_initial["species"]["e"]["initial_number_density"]
        check(exe, root, "JSON_INITIAL_MISSING_WITHOUT_EXTERNAL_VARIABLE",
              PHYSICS_AUTO_INPUT, no_initial, False, "requires species.e.initial_number_density")

        # The older external [Variables]/[ICs] fallback is deliberately
        # rejected even when a matching solver variable and IC are provided.
        external_input = PHYSICS_AUTO_INPUT.replace(
            "  [potential]\n    type = MooseVariable\n  []",
            "  [potential]\n    type = MooseVariable\n  []\n"
            "  [log_e]\n    type = MooseVariable\n  []",
            1
        ).replace(
            "[Physics]\n",
            "[ICs]\n  [external_log_e_initial]\n"
            "    type = ConstantIC\n    variable = log_e\n"
            "    value = -20\n  []\n[]\n[Physics]\n",
            1
        )
        assert external_input != PHYSICS_AUTO_INPUT
        check(exe, root, "JSON_INITIAL_MISSING_DESPITE_EXTERNAL_VARIABLE_AND_IC",
              external_input, no_initial, False, "requires species.e.initial_number_density")
        fvm_external_input = fvm_input.replace(
            "  [potential]\n    type = MooseVariable\n  []",
            "  [potential]\n    type = MooseVariable\n  []\n"
            "  [log_O2p]\n    type = MooseVariableFVReal\n  []",
            1
        )
        assert fvm_external_input != fvm_input
        check(exe, root, "JSON_FVM_INITIAL_MISSING_DESPITE_EXTERNAL_VARIABLE",
              fvm_external_input, fvm_missing, False, "requires species.O2p.initial_number_density")

        old_input = PHYSICS_AUTO_INPUT.replace(
            "fem_species = e", "fem_species = 'e 1e15'", 1
        )
        check(exe, root, "RETIRED_POSITIONAL_FEM_INITIAL",
              old_input, DATA, False)
        duplicate_input = PHYSICS_AUTO_INPUT.replace(
            "  [potential]\n    type = MooseVariable\n  []",
            "  [potential]\n    type = MooseVariable\n  []\n"
            "  [log_e]\n    type = MooseVariable\n  []",
            1
        )
        assert duplicate_input != PHYSICS_AUTO_INPUT
        check(exe, root, "JSON_INITIAL_DUPLICATE_EXTERNAL_VARIABLE",
              duplicate_input, DATA, False)

        # The complete Physics path must not infer missing electron transport
        # or a missing electron-fluid energy closure from parser defaults.
        no_e_transport = copy.deepcopy(DATA)
        del no_e_transport["species"]["e"]["transport_coef"]
        del no_e_transport["species"]["e"]["mobility"]
        del no_e_transport["species"]["e"]["diffusivity"]
        check(exe, root, "FULL_PHYSICS_MISSING_E_TRANSPORT",
              PHYSICS_AUTO_INPUT, no_e_transport, False)
        no_fluid_energy = copy.deepcopy(DATA)
        del no_fluid_energy["species"]["e"]["energy_transport_coef"]
        check(exe, root, "FULL_PHYSICS_MISSING_E_ENERGY_FLUID",
              PHYSICS_AUTO_INPUT, no_fluid_energy, False)
        retired = copy.deepcopy(DATA)
        legacy = {
            "e": {
                "model": retired["species"]["e"].pop("transport_coef"),
                "mobility": retired["species"]["e"].pop("mobility"),
                "diffusivity": retired["species"]["e"].pop("diffusivity")
            },
            "e_energy": {"type": retired["species"]["e"].pop("energy_transport_coef")}
        }
        retired["transport_coefficients"] = {"drift_diffusion": legacy}
        check(exe, root, "RETIRED_TOP_LEVEL_DRIFT_DIFFUSION",
              PHYSICS_AUTO_INPUT, retired, False,
              "transport_coefficients.drift_diffusion is retired")
        invalid_mode = copy.deepcopy(DATA)
        invalid_mode["species"]["e"]["transport_coef"] = "unsupported"
        check(exe, root, "INVALID_SPECIES_TRANSPORT_MODE",
              PHYSICS_AUTO_INPUT, invalid_mode, False,
              "transport model must be")
        non_e_energy = copy.deepcopy(DATA)
        non_e_energy["species"]["O2p"] = {
            "elements": {"O": 2}, "charge_number": 1,
            "energy_transport_coef": "fluid"
        }
        check(exe, root, "NON_ELECTRON_FLUID_ENERGY",
              PHYSICS_AUTO_INPUT, non_e_energy, False,
              "energy_transport_coef supports only species.e = fluid")

        # A standalone manually provided mean-energy Functor is valid only
        # when no JSON sheath BCs ask a missing DriftDiffusion owner to build them.
        no_registry = copy.deepcopy(DATA)
        no_registry.pop("boundaries")
        check(exe, root, "PARSED_MEAN_FUNCTOR_CONSTRUCTION",
              PARSED_MEAN_INPUT, no_registry, True)
        # One original BC block can own several sidesets. The JSON path
        # must not split it into multiple independent operators.
        multiside = copy.deepcopy(DATA)
        multiside["boundaries"]["left bottom"] = (
            multiside["boundaries"].pop("left")
        )
        multiside["boundaries"].pop("bottom")
        check(exe, root, "MULTI_SIDESET_GROUP_UNSPLIT", PHYSICS_AUTO_INPUT, multiside, True)
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
        check(exe, root, "RETIRED_PHYSICAL_EV_MEAN_STATE",
              LEGACY_INPUT.replace("state_form = log_molar_eV",
                                   "state_form = physical_eV"), DATA, False)
        check(exe, root, "RETIRED_MEAN_OUTPUT_PARAM",
              LEGACY_INPUT.replace("    state_form = log_molar_eV",
                                   "    state_form = log_molar_eV\n    mean_energy_output = e_energy_eV"),
              DATA, False)
        # A missing Functor may remain unresolved at --check-input because
        # the residual is lazily evaluated. P0 proves the old output is not
        # registered; no unverified P2 failure is asserted for this case.
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
