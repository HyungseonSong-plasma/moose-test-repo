"""Static contract checks for the full S6-417/941 public native P2 gate.

The separate GitHub Actions OCI job executes the real 4-way --check-input.
These pytest checks never run the time-dependent native solver.
"""
from __future__ import annotations

import ast
import hashlib
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
PILOT = ROOT / "experiments" / "Issue402_plasma_dsl_g1"
PUBLIC = ROOT / "experiments" / "Issue493_s6_boltzmann"
EXPECTED_OVERLAY = "edf3f8e8194927e93783d136066799d60df2673af9245d6d4b990fb7d267b513"


def extract_overlay():
    text = (PILOT / "public_option_s6_p2.py").read_text()
    tree = ast.parse(text)
    matches = [
        node for node in tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "OVERLAY"
                for target in node.targets)
    ]
    assert len(matches) == 1
    return ast.literal_eval(matches[0].value)


def test_pinned_new_option_overlay_uses_canonical_species_provider_names():
    overlay = extract_overlay()
    assert hashlib.sha256(overlay.encode()).hexdigest() == EXPECTED_OVERLAY
    assert "fem_species = 'e'" in overlay
    assert "fvm_species = 'O2p Om Op'" in overlay
    assert "legacy_s6_state_names" not in overlay
    assert overlay.count("type = DDTransportMaterial") == 3
    assert overlay.count("model = functor") == 3
    assert "mobility_source = ion_mobility" in overlay
    assert "diffusivity_source = ion_diffusion" in overlay
    assert "files = plasma_species_only.json" in overlay
    assert "fem_charge_numbers" not in overlay and "fvm_charge_numbers" not in overlay
    # Provider names are derived in ContinuityEq, not user input.
    assert "fem_potential = potential" in overlay
    for forbidden in ("variables =", "fem_kernel_names", "fvm_kernel_names",
                      "fem_mobility =", "fem_diffusion =", "mobility =", "diffusivity ="):
        assert forbidden not in overlay



def test_canonical_s6_migration_changes_scratch_only(tmp_path):
    """Exercise the actual migration function without Docker or S6 solves."""
    import re

    script = (PILOT / "public_option_s6_p2.py").read_text()
    tree = ast.parse(script)
    declarations = [
        node for node in tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id in
                {"CANONICAL_STATE_NAMES", "_STATE_TOKEN"} for t in node.targets)
    ]
    functions = [
        node for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "canonicalize_staged_D_inputs"
    ]
    assert len(declarations) == 2 and len(functions) == 1
    namespace = {
        "re": re,
        "hashlib": hashlib,
        "Path": Path,
        "sha_file": lambda p: hashlib.sha256(p.read_bytes()).hexdigest(),
    }
    exec(compile(ast.Module(body=declarations + functions, type_ignores=[]),
                 str(PILOT / "public_option_s6_p2.py"), "exec"), namespace)

    archived = tmp_path / "source"
    staged = tmp_path / "scratch"
    archived.mkdir()
    staged.mkdir()
    ordered = []
    sample = ("variable = log_ne\n"
              "coupled = 'log_ni log_nm log_nop'\n"
              "similar_name = log_ne_custom\n"
              "  [ne_time]\n"
              "    type = PhysicsFEMLogMolarTimeDerivative\n"
              "    variable = log_ne\n"
              "    block = plasma\n"
              "  []\n")
    for index in range(10):
        name = f"layer_{index}.i"
        content = sample if index == 0 else f"# original {index}\\n"
        (archived / name).write_text(content)
        (staged / name).write_text(content)
        ordered.append(f"chem/{name}")
    (staged / "migrated_continuity.i").write_text("PINNED_SIDECAR")
    ordered.append("chem/migrated_continuity.i")

    report = namespace["canonicalize_staged_D_inputs"](staged, ordered)
    assert report["status"] == "SCRATCH_ONLY_CANONICAL_STATE_AND_TIME_OWNER_REWRITE"
    assert report["removed_native_time"]["source_layer"] == "layer_0.i"
    assert report["removed_native_time"]["old_name"] == "ne_time"
    assert report["removed_native_time"]["generated_name"] == "e_time"
    assert report["removed_native_time"]["kernel_type"] == "PhysicsFEMLogMolarTimeDerivative"
    assert report["changed_reference_count"] == 4
    assert report["files"]["layer_0.i"]["original_sha256"] == (
        hashlib.sha256(sample.encode()).hexdigest())
    assert (archived / "layer_0.i").read_text() == sample
    assert (staged / "migrated_continuity.i").read_text() == "PINNED_SIDECAR"
    migrated = (staged / "layer_0.i").read_text()
    assert "variable = log_e" in migrated
    assert "coupled = 'log_O2p log_Om log_Op'" in migrated
    assert "similar_name = log_ne_custom" in migrated
    assert "[ne_time]" not in migrated
    assert "PhysicsFEMLogMolarTimeDerivative" not in migrated
    assert report["files"]["layer_0.i"]["staged_sha256"] == (
        hashlib.sha256(migrated.encode()).hexdigest())
    # A malformed, absent, or duplicated Native time term must fail BEFORE
    # any scratch file is rewritten. Never turn an ambiguous input into PASS.
    from pytest import raises
    time_block = ("  [ne_time]\n"
                  "    type = PhysicsFEMLogMolarTimeDerivative\n"
                  "    variable = log_ne\n"
                  "    block = plasma\n"
                  "  []\n")
    for fault, defective, extra in (
        ("missing", sample.replace(time_block, ""), ""),
        ("changed", sample.replace("    block = plasma\n", "    block = other\n"), ""),
        ("duplicate", sample, time_block),
    ):
        damaged = tmp_path / fault
        damaged.mkdir()
        for index in range(10):
            name = f"layer_{index}.i"
            body = defective if index == 0 else f"# original {index}\n"
            if index == 1:
                body += extra
            (damaged / name).write_text(body)
        (damaged / "migrated_continuity.i").write_text("PINNED_SIDECAR")
        snapshot = {name.name: name.read_bytes() for name in damaged.iterdir()}
        with raises(ValueError):
            namespace["canonicalize_staged_D_inputs"](damaged, ordered)
        assert snapshot == {name.name: name.read_bytes() for name in damaged.iterdir()}

    # The original decks are still byte-identical and cannot be confused
    # with the scratch-only canonical migration.
    assert all((archived / f"layer_{i}.i").read_text() ==
               (sample if i == 0 else f"# original {i}\\n") for i in range(10))




def test_s6_D_json_initials_retire_exact_native_solver_owners(tmp_path):
    import importlib.util
    import json
    import math
    import pytest

    script = PILOT / "public_option_s6_p2.py"
    spec = importlib.util.spec_from_file_location("s6_native_initials", script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    original_base = PILOT / "native/s6_c0_physics_base_no_d1.i"
    saved = original_base.read_bytes()
    json_source = PILOT / "plasma_species_only.json"
    saved_json = json_source.read_bytes()
    names = [original_base.name] + [f"side_{i}.i" for i in range(9)]
    ordered = ["chem/" + name for name in names] + ["chem/migrated_continuity.i"]

    def staged(name):
        folder = tmp_path / name
        folder.mkdir()
        for i, filename in enumerate(names):
            (folder / filename).write_bytes(saved if i == 0 else f"# side {i}\n".encode())
        (folder / "migrated_continuity.i").write_text("PINNED_OVERLAY")
        (folder / "plasma_species_only.json").write_bytes(saved_json)
        module.canonicalize_staged_D_inputs(folder, ordered)
        return folder

    good = staged("good")
    report = module.reconcile_staged_D_json_initials(good, ordered)
    assert report["status"] == "SCRATCH_ONLY_JSON_INITIALS_FOUR_NATIVE_OWNERS_RETIRED"
    assert report["retired_native_variables"] == ["log_O2p", "log_Om", "log_Op", "log_e"]
    assert report["P3"] == "NOT_RUN" and report["science"] == "SCIENCE_HOLD"
    revised = (good / original_base.name).read_text()
    for variable in ("log_e", "log_O2p", "log_Om", "log_Op"):
        assert f"  [{variable}]\n" not in revised
    assert "  [log_energy]\n" in revised
    payload = json.loads((good / "plasma_species_only.json").read_bytes())
    values = {"e": -20.216123548032986, "O2p": -20.216123548032986,
              "Om": -27.123878827015126, "Op": -27.123878827015126}
    for species, lexical in values.items():
        assert payload["species"][species]["initial_number_density"] == (
            math.exp(lexical) * 6.02214076e23)
    assert original_base.read_bytes() == saved and json_source.read_bytes() == saved_json
    for fault in ("density", "duplicate", "charge", "extra"):
        folder = staged(fault)
        base = folder / original_base.name
        if fault == "density":
            data = base.read_text()
            assert "initial_condition = -20.216123548032986" in data
            base.write_text(data.replace("initial_condition = -20.216123548032986",
                                         "initial_condition = 0", 1))
        elif fault == "duplicate":
            (folder / names[1]).write_text("  [log_e]\n    initial_condition = 0\n  []\n")
        else:
            data = json.loads((folder / "plasma_species_only.json").read_bytes())
            if fault == "charge":
                data["species"]["e"]["charge_number"] = 1
            else:
                data["species"]["e"]["initial_number_density"] = 1e15
            (folder / "plasma_species_only.json").write_text(json.dumps(data))
        snapshot = {file.name: file.read_bytes() for file in folder.iterdir()}
        with pytest.raises(ValueError):
            module.reconcile_staged_D_json_initials(folder, ordered)
        assert snapshot == {file.name: file.read_bytes() for file in folder.iterdir()}



def test_B_historical_D1_observers_preserved_with_canonical_types_only(tmp_path):
    """All 14 diagnostics survive B P2 with pinned provenance and no aliases."""
    import importlib.util
    import pytest

    spec = importlib.util.spec_from_file_location(
        "s6_B_diagnostics", PILOT / "public_option_s6_p2.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    instrument_path = ROOT / "experiments/Issue395_powered_chemistry_ladder/issue397_d1_instrument.py"
    source_text = instrument_path.read_bytes()
    original = "source control byte identity"
    fields = {
        "wafer_net_current_probe": "wafer_net_surface_current_density",
        "d1_gamma_o2_positive": "ion_wall_number_flux",
        "d1_gamma_o_positive": "atomic_positive_ion_wall_number_flux",
        "d1_gamma_o_negative": "negative_ion_wall_number_flux",
        "d1_gamma_electron": "electron_wall_number_flux",
        "d1_sheath_drop_V": "electron_sheath_drop_V",
        "d1_ne_m3": "n_e_physical",
        "d1_mean_energy_eV": "mean_en_solved",
        "d1_electron_mean_speed_m_s": "electron_mean_speed",
    }
    geometry = {
        "d1_normal_r": "normal_r", "d1_normal_z": "normal_z",
        "d1_owner": "owner", "d1_d_perp_m": "d_perp", "d1_e_n_V_m": "e_n",
    }
    vars_text = "".join(
        "  [" + name + "]\n    family = MONOMIAL\n"
        "    order = CONSTANT\n    block = wafer_surface\n  []\n"
        for name in (*fields, *geometry))
    kernel_text = ""
    for name, functor in fields.items():
        kernel_text += (
            f"  [{name}_kernel]\n    type = PhysicsLowerDSurfaceCurrentProbeAux\n"
            f"    variable = {name}\n    surface_current_density = {functor}\n"
            "    block = wafer_surface\n"
            "    execute_on = 'INITIAL TIMESTEP_END'\n  []\n"
        )
    for name, comp in geometry.items():
        kernel_text += (
            f"  [{name}_kernel]\n    type = PhysicsWaferD1GeometryProbeAux\n"
            f"    variable = {name}\n"
            "    surface_current_density = wafer_net_surface_current_density\n"
            f"    potential = potential\n    component = {comp}\n"
            "    block = wafer_surface\n"
            "    execute_on = 'INITIAL TIMESTEP_END'\n  []\n"
        )
    physical = (
        "[Kernels]\n  [sigma_surface_current]\n"
        "    type = PhysicsLowerDSurfaceCurrent\n    variable = sigma_s\n  []\n[]\n"
        "[BCs]\n  [cover_surface_charge_poisson]\n"
        "    type = PhysicsADSurfaceChargePoissonBC\n    variable = potential\n  []\n[]\n"
    )
    base = ("[AuxVariables]\n" + vars_text + "[]\n[AuxKernels]\n" +
            kernel_text + "[]\n" + physical)
    names = ["original.i"] + [f"other_{i}.i" for i in range(9)]
    ordered = ["chem/" + name for name in names]

    def stage(label, contents=base, extra=""):
        folder = tmp_path / label
        folder.mkdir()
        (folder / names[0]).write_text(contents)
        for i, name in enumerate(names[1:]):
            (folder / name).write_text(extra if i == 0 else f"# layer {i}\n")
        return folder

    original_folder = stage("original")
    snapshot = {file.name: file.read_bytes() for file in original_folder.iterdir()}
    receipt = module.retire_staged_B_d1_observations(original_folder, ordered)
    assert receipt["status"] == "SCRATCH_ONLY_B_D1_OBSERVERS_VERIFIED_PRESERVED"
    assert receipt["observer_pairs"] == 14
    assert receipt["science"] == "SCIENCE_HOLD"
    assert receipt["B_historical_observation_parity"] == "NOT_CLAIMED"
    # The preflight validates 14 observers without deleting their source blocks.
    after = (original_folder / names[0]).read_text()
    assert after == base
    assert receipt["native_staged_sha256"] == hashlib.sha256(base.encode()).hexdigest()
    assert "type = PhysicsLowerDSurfaceCurrent\n" in after
    assert "type = PhysicsADSurfaceChargePoissonBC\n" in after
    assert after.count("type = PhysicsLowerDSurfaceCurrentProbeAux\n") == 9
    assert after.count("type = PhysicsWaferD1GeometryProbeAux\n") == 5
    assert all((original_folder / name).read_bytes() == snapshot[name]
               for name in names[1:])
    remap = module.remap_staged_fem_types(original_folder, ordered)
    assert remap["status"] == "STAGED_TYPES_RENAMED_WITHOUT_FACTORY_ALIASES"
    assert remap["totals"]["PhysicsLowerDSurfaceCurrentProbeAux"] == 9
    assert remap["totals"]["PhysicsWaferD1GeometryProbeAux"] == 5
    migrated = (original_folder / names[0]).read_text()
    assert migrated.count("type = LowerDSurfaceCurrentProbeAux\n") == 9
    assert migrated.count("type = WaferD1GeometryProbeAux\n") == 5
    assert "type = PhysicsLowerDSurfaceCurrentProbeAux\n" not in migrated
    assert "type = PhysicsWaferD1GeometryProbeAux\n" not in migrated
    assert "type = PhysicsLowerDSurfaceCurrent\n" in migrated
    assert "type = PhysicsADSurfaceChargePoissonBC\n" in migrated
    assert all(f"  [{name}]\n" in migrated for name in (*fields, *geometry))
    for cls, required in (
        ("LowerDSurfaceCurrentProbeAux", (
            "interior_parent()", "getHigherDSide(_current_elem)",
            "_surface_current_density.hasFaceSide(*fi, true)",
            "_surface_current_density.hasFaceSide(*fi, false)",
            "if (on_elem == on_neighbor)",
            "_surface_current_density(face_arg, Moose::currentState())",
        )),
        ("WaferD1GeometryProbeAux", (
            "getHigherDSide(_current_elem)",
            'MooseEnum("normal_r normal_z owner d_perp e_n")',
            "_potential.gradient(face_arg.makeElem()",
            "_potential.gradient(face_arg.makeNeighbor()",
        )),
    ):
        header = (ROOT / "physics_app/include/auxkernels" / f"{cls}.h").read_text()
        source = (ROOT / "physics_app/src/auxkernels" / f"{cls}.C").read_text()
        assert f"class {cls} : public AuxKernel" in header
        assert f'registerMooseObject("PhysicsApp", {cls});' in source
        assert f'registerMooseObject("PhysicsApp", Physics{cls});' not in source
        assert all(marker in source for marker in required)
    for label, contents, extra in (
        ("wrong_functor", base.replace("surface_current_density = ion_wall_number_flux",
                                       "surface_current_density = fake_flux"), ""),
        ("wrong_owner", base.replace("block = wafer_surface", "block = wrong", 1), ""),
        ("extra_consumer", base, "observe = d1_gamma_electron\n"),
        ("duplicate", base + kernel_text, ""),
    ):
        folder = stage(label, contents, extra)
        before = {file.name: file.read_bytes() for file in folder.iterdir()}
        with pytest.raises(ValueError):
            module.retire_staged_B_d1_observations(folder, ordered)
        assert before == {file.name: file.read_bytes() for file in folder.iterdir()}
    assert instrument_path.read_bytes() == source_text


def test_archived_s6_kernel_types_remap_only_in_scratch_without_aliases(tmp_path):
    """The old B input is immutable; only temporary B/D type fields change."""
    import re
    import pytest

    path = PILOT / "public_option_s6_p2.py"
    tree = ast.parse(path.read_text())
    assignments = [
        node for node in tree.body if isinstance(node, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id in
                {"RENAMED_FEM_KERNEL_TYPES", "_FEM_TYPE_LINE"} for t in node.targets)
    ]
    fun = next(node for node in tree.body
               if isinstance(node, ast.FunctionDef) and node.name == "remap_staged_fem_types")
    assert len(assignments) == 2
    namespace = {"re": re, "Path": Path, "hashlib": hashlib}
    exec(compile(ast.Module(body=assignments + [fun], type_ignores=[]),
                 str(path), "exec"), namespace)

    archived = tmp_path / "archive"
    staged = tmp_path / "scratch"
    archived.mkdir()
    staged.mkdir()
    source = (
        "[Kernels]\n"
        "  [ne_time]\n    type = PhysicsFEMLogMolarTimeDerivative\n"
        "    variable = log_ne\n  []\n"
        "  [ne_transport]\n    type = PhysicsFEMLogMolarDriftDiffusion\n"
        "    variable = log_ne\n  []\n"
        "  [energy_joule]\n    type = PhysicsFEMLogMolarElectronJouleHeating\n"
        "    variable = log_energy\n  []\n[]\n"
    )
    ordered = []
    for i in range(10):
        name = f"layer_{i}.i"
        data = source if i == 0 else f"# control {i}\n"
        (archived / name).write_text(data)
        (staged / name).write_text(data)
        ordered.append(f"chem/{name}")
    result = namespace["remap_staged_fem_types"](staged, ordered)
    assert result["status"] == "STAGED_TYPES_RENAMED_WITHOUT_FACTORY_ALIASES"
    assert all(count == 1 for old, count in result["totals"].items()
               if old.startswith("PhysicsFEM"))
    assert all(count == 0 for old, count in result["totals"].items()
               if not old.startswith("PhysicsFEM"))
    migrated = (staged / "layer_0.i").read_text()
    for old, new in ((old, new) for old, new in namespace["RENAMED_FEM_KERNEL_TYPES"].items()
                     if old.startswith("PhysicsFEM")):
        assert "type = " + old not in migrated
        assert "type = " + new in migrated
        assert "type = " + old in (archived / "layer_0.i").read_text()
    assert result["files"]["layer_0.i"]["original_sha256"] == hashlib.sha256(source.encode()).hexdigest()
    snapshot = {p.name: p.read_bytes() for p in staged.iterdir()}
    with pytest.raises(ValueError, match="layer count"):
        namespace["remap_staged_fem_types"](staged, ordered[:-1])
    assert snapshot == {p.name: p.read_bytes() for p in staged.iterdir()}




def test_s6_mean_energy_log_molar_remap_preserves_source_and_rejects_wrong_semantics(tmp_path):
    """The retired producer and consumers change only in disposable S6 P2 copies."""
    import re
    import pytest

    script = (PILOT / "public_option_s6_p2.py").read_text()
    tree = ast.parse(script)
    functions = [
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "remap_staged_mean_energy"
    ]
    assert len(functions) == 1
    ns = {"re": re, "Path": Path, "hashlib": hashlib}
    exec(compile(ast.Module(body=functions, type_ignores=[]),
                 str(PILOT / "public_option_s6_p2.py"), "exec"), ns)
    convert = ns["remap_staged_mean_energy"]

    archived = tmp_path / "original"
    staged = tmp_path / "scratch"
    archived.mkdir()
    staged.mkdir()
    original = (
        "  [mean_energy]\n"
        "    type = PhysicsElectronMeanEnergyMaterial\n"
        "    electron_energy_density = log_energy\n"
        "    electron_density = log_ne\n"
        "    state_form = log_molar_eV\n"
        "    mean_energy_output = mean_en_solved\n"
        "    block = plasma\n"
        "  []\n"
        "  [energy_consumer]\n"
        "    mean_energy = mean_en_solved\n"
        "  []\n"
    )
    ordered = [f"chem/layer_{i}.i" for i in range(10)]
    for i in range(10):
        content = original if i == 0 else f"# original layer {i}\n"
        (archived / f"layer_{i}.i").write_text(content)
        (staged / f"layer_{i}.i").write_text(content)
    result = convert(staged, ordered)
    assert result["status"] == "SCRATCH_ONLY_LOG_MOLAR_MEAN_ENERGY_CUTOVER"
    assert result["consumer_renames"] == 1
    assert result["producer_layer"] == "layer_0.i"
    after = (staged / "layer_0.i").read_text()
    assert "type = ElectronEnergyMaterial" in after
    assert "mean_energy = e_energy_eV" in after
    assert "mean_energy_output" not in after
    assert "state_form = log_molar_eV" in after
    assert "electron_energy_density = log_energy" in after
    assert (archived / "layer_0.i").read_text() == original
    assert result["files"]["layer_0.i"]["original_sha256"] == (
        hashlib.sha256(original.encode()).hexdigest()
    )
    assert result["files"]["layer_0.i"]["staged_sha256"] == (
        hashlib.sha256(after.encode()).hexdigest()
    )

    # Unsupported historical representations, competing/changed producers,
    # absent consumers or duplicate owners must HOLD before any writes.
    faulty = (
        ("normalized", original.replace("state_form = log_molar_eV",
                                         "state_form = normalized"), ""),
        ("physical", original.replace("state_form = log_molar_eV",
                                       "state_form = physical_eV"), ""),
        ("wrong_output", original.replace("mean_energy_output = mean_en_solved",
                                           "mean_energy_output = alternate"), ""),
        ("extra_option", original.replace("    block = plasma\n",
                                           "    energy_reference_eV = 1\n    block = plasma\n"), ""),
        ("already_new", original.replace("PhysicsElectronMeanEnergyMaterial",
                                          "ElectronEnergyMaterial"), ""),
        ("no_consumer", original.replace("mean_energy = mean_en_solved",
                                          "mean_energy = unrelated"), ""),
        ("duplicate", original, original),
    )
    for label, bad, extra in faulty:
        scratch = tmp_path / f"negative_{label}"
        scratch.mkdir()
        for i in range(10):
            content = bad if i == 0 else (extra if i == 1 and extra else f"# layer {i}\n")
            (scratch / f"layer_{i}.i").write_text(content)
        snapshot = {p.name: p.read_bytes() for p in scratch.iterdir()}
        with pytest.raises(ValueError):
            convert(scratch, ordered)
        assert snapshot == {p.name: p.read_bytes() for p in scratch.iterdir()}



def test_exact_s6_electron_lookup_cutover_is_wired_into_native_p2(tmp_path):
    """Use the independently tested historical S6 lookup adapter in P2 scratch."""
    import importlib.util
    import pytest

    path = PILOT / "public_option_s6_p2.py"
    spec = importlib.util.spec_from_file_location("issue541_s6_p2_lookup_runner", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    source_path = PILOT / "native/s6_c0_physics_base_no_d1.i"
    original = source_path.read_text(encoding="utf-8")
    assert original.count("type = PhysicsElectronTransportLookupMaterial") == 1
    source_snapshot = source_path.read_bytes()
    staged = tmp_path / "scratch"
    staged.mkdir()
    base = source_path.name
    ordered = [f"chem/{base}"] + [f"chem/extra_{i}.i" for i in range(9)]
    (staged / base).write_text(original, encoding="utf-8")
    for i in range(9):
        (staged / f"extra_{i}.i").write_text(f"# original {i}\n")

    report = module.remap_staged_electron_lookup(staged, ordered)
    assert report["status"] == "SCRATCH_ONLY_EXACT_ELECTRON_LOOKUP_CUTOVER"
    assert report["source_layer"] == base
    assert report["table_units"] == "reduced"
    assert report["fluid_energy"] is True
    assert report["bounds_policy"] == "clamp"
    assert report["P3"] == "NOT_RUN" and report["science"] == "SCIENCE_HOLD"
    changed = (staged / base).read_text(encoding="utf-8")
    assert "type = PhysicsElectronTransportLookupMaterial" not in changed
    block = changed.split("  [electron_transport]\n", 1)[1].split("  []", 1)[0]
    for expected in (
        "type = DDTransportMaterial", "species_id = e", "model = lookup",
        "table_units = reduced", "fluid_energy = true", "bounds_policy = clamp",
        "pressure = p", "gas_temperature = T_g_fixed",
        "table_file = '../Issue91_real_qvt_r3/r3_e0/electron_moments.txt'",
    ):
        assert expected in block
    assert "property_table_file" not in block and "mean_energy =" not in block
    assert source_path.read_bytes() == source_snapshot

    # Reject an unproved historical bounds change and preserve the entire
    # scratch directory unchanged even when validation fails.
    owner, rest = original.split("  [electron_transport]\n", 1)
    content, suffix = rest.split("  []", 1)
    assert "bounds_policy = clamp" in content
    bad = owner + "  [electron_transport]\n" + content.replace(
        "bounds_policy = clamp", "bounds_policy = error", 1
    ) + "  []" + suffix
    (staged / base).write_text(bad, encoding="utf-8")
    before = {item.name: item.read_bytes() for item in staged.iterdir()}
    with pytest.raises(ValueError, match="S6_ELECTRON_LOOKUP_IDENTITY_UNPROVED"):
        module.remap_staged_electron_lookup(staged, ordered)
    assert before == {item.name: item.read_bytes() for item in staged.iterdir()}
    assert source_path.read_bytes() == source_snapshot


def test_actual_s6_native_wall_cutover_preserves_archive_and_rejects_charge_flip(tmp_path):
    """The P2 caller must preserve owner identity and reject a flipped ion sign."""
    import importlib.util
    import runpy
    import pytest

    path = PILOT / "public_option_s6_p2.py"
    spec = importlib.util.spec_from_file_location("issue541_s6_native_wall_runner", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    examples = runpy.run_path(str(ROOT / "tests/test_issue402_s6_wall_naming_staging.py"))
    producer = examples["ION_PRODUCER"]
    consumers = examples["CONSUMERS"]
    staged = tmp_path / "scratch"
    staged.mkdir()
    ordered = [f"chem/layer_{i}.i" for i in range(10)]
    (staged / "layer_0.i").write_text(producer)
    (staged / "layer_1.i").write_text(consumers)
    for i in range(2, 10):
        (staged / f"layer_{i}.i").write_text(f"# layer {i}\n")
    untouched = {p.name: p.read_bytes() for p in staged.iterdir()}

    report = module.remap_staged_wall_owners(staged, ordered)
    assert report["status"] == "SCRATCH_ONLY_SPECIES_WALL_NAMES"
    assert report["owner_count"] == 4
    assert {v["species_id"] for v in report["wall_material_owners"]} == {
        "e", "O2p", "Om", "Op"}
    assert report["P3"] == "NOT_RUN" and report["science"] == "SCIENCE_HOLD"
    assert "type = PhysicsIonWallTotalFluxMaterial" not in (staged / "layer_0.i").read_text()
    assert "type = IonWallFluxMaterial" in (staged / "layer_0.i").read_text()
    assert "functor = Op_wall_number_flux" in (staged / "layer_1.i").read_text()
    assert (staged / "layer_0.i").read_bytes() != untouched["layer_0.i"]

    # A flipped sign must stop before rewriting any staged consumer/source.
    wrong = producer.replace("charge_number = -1", "charge_number = 1", 1)
    assert wrong != producer
    (staged / "layer_0.i").write_text(wrong)
    (staged / "layer_1.i").write_text(consumers)
    snapshot = {p.name: p.read_bytes() for p in staged.iterdir()}
    with pytest.raises(ValueError, match="S6_WALL_CHARGE_IDENTITY_UNPROVED"):
        module.remap_staged_wall_owners(staged, ordered)
    assert snapshot == {p.name: p.read_bytes() for p in staged.iterdir()}


def test_both_s6_native_sheath_variants_strict_eight_owner_cutover(tmp_path):
    """Exercise the actual current Native P2 adapter without running the solver."""
    import importlib.util
    import re
    import pytest

    src = PILOT / "public_option_s6_p2.py"
    spec = importlib.util.spec_from_file_location("issue541_native_sheath_runner", src)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    base_file = PILOT / "native/s6_c0_physics_base_no_d1.i"
    source_original = base_file.read_bytes()
    legacy = source_original.decode("utf-8")
    old_particle = "PhysicsFEMLogMolarElectronFieldLimitedFluxBC"
    old_energy = "PhysicsFEMLogMolarElectronEnergyFieldLimitedFluxBC"
    assert legacy.count("type = " + old_particle) == 4
    assert legacy.count("type = " + old_energy) == 4

    for variant in ("B", "D"):
        staging = tmp_path / variant
        staging.mkdir()
        # Reproduce the proven preceding scratch wall + mean-energy names.
        staged = legacy.replace("electron_wall_number_flux", "e_wall_number_flux")
        staged = staged.replace("mean_en_solved", "e_energy_eV")
        if variant == "D":
            # This option migrates continuity only; native energy stays log_energy.
            staged = re.sub(r"\blog_ne\b", "log_e", staged)
        names = [base_file.name] + [f"other_{i}.i" for i in range(9)]
        ordered = [f"chem/{name}" for name in names]
        for i, name in enumerate(names):
            (staging / name).write_text(staged if i == 0 else f"# other {i}\n")
        unmodified = {p.name: p.read_bytes() for p in staging.iterdir()}
        result = module.remap_staged_sheath_bcs(staging, ordered, variant)
        assert result["status"] == "SCRATCH_ONLY_EXACT_EIGHT_SHEATH_BC_TYPE_CUTOVER"
        assert result["owner_count"] == 8
        assert result["variant"] == variant
        assert len({item["owner"] for item in result["owners"]}) == 8
        assert result["P3"] == "NOT_RUN"
        assert result["science"] == "SCIENCE_HOLD"
        revised = (staging / base_file.name).read_text()
        assert revised.count("type = FEMElectronSheathBC") == 4
        assert revised.count("type = FEMElectronEnergySheathBC") == 4
        assert old_particle not in revised and old_energy not in revised
        # Only eight class names change, not the energy/boundary/flux owners.
        assert (revised.replace("type = FEMElectronSheathBC",
                                "type = " + old_particle)
                       .replace("type = FEMElectronEnergySheathBC",
                                "type = " + old_energy)) == staged
        assert result["original_sha256"] == hashlib.sha256(unmodified[base_file.name]).hexdigest()
        assert result["staged_sha256"] == hashlib.sha256(revised.encode()).hexdigest()
        assert all((staging / name).read_bytes() == unmodified[name] for name in names[1:])
        assert base_file.read_bytes() == source_original

        # Wrong boundary, source flux, mean energy or old factory must stop
        # BEFORE any scratch file is written; never silently "fix" physics.
        def corrupt_only_bc_owner(name, expected, replacement):
            prefix, body = staged.split(f"  [{name}]\n", 1)
            owner, suffix = body.split("  []", 1)
            assert expected in owner, (name, expected)
            return (prefix + f"  [{name}]\n" +
                    owner.replace(expected, replacement, 1) + "  []" + suffix)

        faulty_sources = (
            corrupt_only_bc_owner("electron_energy_sheath",
                                  "variable = log_energy",
                                  "variable = log_e_energy"),
            corrupt_only_bc_owner("electron_cover_dielectric",
                                  "boundary = 'plasma_cover'",
                                  "boundary = 'plasma_fake'"),
            corrupt_only_bc_owner("electron_sheath",
                                  "wall_number_flux = e_wall_number_flux",
                                  "wall_number_flux = fake_flux"),
            corrupt_only_bc_owner("electron_energy_sheath",
                                  "mean_energy = e_energy_eV",
                                  "mean_energy = fake_energy"),
            corrupt_only_bc_owner("electron_sheath",
                                  "type = " + old_particle,
                                  "type = FEMElectronSheathBC"),
        )
        for number, bad in enumerate(faulty_sources):
            assert bad != staged, number
            (staging / base_file.name).write_text(bad)
            before = {p.name: p.read_bytes() for p in staging.iterdir()}
            with pytest.raises(ValueError, match="S6_SHEATH_OWNER_IDENTITY_"):
                module.remap_staged_sheath_bcs(staging, ordered, variant)
            assert before == {p.name: p.read_bytes() for p in staging.iterdir()}

        (staging / base_file.name).write_text(staged)
        (staging / names[1]).write_text(
            "  [unexpected]\n    type = " + old_particle + "\n  []\n")
        before = {p.name: p.read_bytes() for p in staging.iterdir()}
        with pytest.raises(ValueError, match="S6_SHEATH_SECONDARY_LAYER_RETIRED_OWNER"):
            module.remap_staged_sheath_bcs(staging, ordered, variant)
        assert before == {p.name: p.read_bytes() for p in staging.iterdir()}
        assert base_file.read_bytes() == source_original


def test_full_s6_p2_provenance_and_no_solver_execution():
    script = (PILOT / "public_option_s6_p2.py").read_text()
    shell = PILOT / "run_public_option_s6_p2.sh"
    bash = shell.read_text()
    public = (PUBLIC / "public_p2_check.py").read_text()
    native = (PILOT / "run_native_binding_smoke.sh").read_text()
    assert "29d1acc6ef7969908b86719e4b95c73a1565136d" in bash
    assert "export OXYGEN_RESEARCH_400=1" in bash
    assert "export OXYGEN_RESEARCH_FULL24=0" in bash
    assert "export OXYGEN_RESEARCH_EI2738_FORMULA=0" in bash
    assert "export OXYGEN_RESEARCH_QUICK_5MIN=0" in bash
    assert "35534a522fa48ccb5222339c5040040630eef31e623e1c53f1e1c4540d2d653b" in bash
    assert "OVERLAY_SHA256" in script
    assert "p2.preflight(ROOT)" in script and "p2.stage(ROOT, historical, case" in script
    assert 'VARIANTS = ("B", "D")' in script
    assert " --check-input -i " in script
    assert '"--network", "none"' in script
    # The Native binary is linked from /workspace in the OCI build. Preserve
    # that mount path for runtime so libphysics_test-opt.so.0 is discoverable.
    assert '/workspace/physics_app/physics-opt --check-input -i ' in script
    assert 'trap \'rm -rf /case/.jitcache\' EXIT' in script
    assert "dst=/workspace,readonly" in script
    assert "NATIVE_RUNTIME_LINKER_ERROR" in script
    assert '"P3": "NOT_RUN"' in script and '"P4": "NOT_RUN"' in script
    assert "SCIENCE_HOLD" in script
    workflow = (ROOT / ".github/workflows/physics-native-ci.yml").read_text()
    assert "preflight_public_option_s6.sh" in workflow
    assert "run_public_option_s6_p2.sh" in workflow
    assert "P0 - Public S6 environment and scratch-permission preflight" in workflow
    assert "P1 - Build PhysicsApp and verify generated and native solver operators" in workflow
    assert "P2 - Public S6-417 and S6-941 four-way Native input checks" in workflow
    assert "run_public_option_s6_p2.sh" not in native  # Independent P2 CI step
    assert "native_p1_identity.json" in native
    assert '"schema": "issue402.native_p1.job_local.v1"' in native
    assert "persist_report(evidence, report)" in script
    assert '"cleanup"] = "HOLD"' in script
    assert 'result.get("cleanup") == "PASS"' in script
    assert "option_s6_environment.json" in script
    assert "same_exact_head_ci_job_only" in script
    gate = PILOT / "preflight_public_option_s6.sh"
    gate_text = gate.read_text()
    assert "OXYGEN_RESEARCH" not in gate_text or "400" in gate_text
    assert "public_p2_check.py --control . --mode preflight" in gate_text
    assert "root_scratch_create_and_cleanup" in gate_text
    subprocess.run(["bash", "-n", str(gate)], check=True)
    assert "public_p2_decks.tar.xz.b64" in public
    assert "PACK_SHA" in public and "PINNED_SOURCE" in public
    assert "issue493_option_only" not in bash  # no secret runner or alternate old-rate owner
    subprocess.run(["bash", "-n", str(shell)], check=True)
    subprocess.run(["bash", "-n", str(PILOT / "run_native_binding_smoke.sh")], check=True)


def test_p2_case_verdict_survives_cleanup_failure(tmp_path):
    """Execute actual P2 control flow with a fault-injected cleanup failure.

    Four simulated, isolated Native PASS results must survive unchanged while
    the overall gate remains HOLD. No Docker, rate data or solver is invoked.
    """
    import json
    import os
    import tempfile
    from types import SimpleNamespace

    script = (PILOT / "public_option_s6_p2.py").read_text()
    tree = ast.parse(script)
    names = {"execute", "persist_report"}
    functions = [node for node in tree.body
                 if isinstance(node, ast.FunctionDef) and node.name in names]
    assert {fn.name for fn in functions} == names
    module = ast.Module(body=functions, type_ignores=[])

    root = tmp_path / "control"
    root.mkdir()
    (root / "manifest.json").write_text("{}")
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    source = "a" * 40
    image = "pinned-ci-image@sha256:" + "b" * 64
    evidence.joinpath("option_s6_environment.json").write_text(json.dumps({
        "source_sha": source,
        "image": image,
        "public_p0": "PASS",
        "docker_mount": "PASS",
        "root_scratch_create_and_cleanup": "PASS",
        "host_cleanup": "PASS",
    }))

    def stage(_root, _historical, case, old_variant, staged, _manifest, *, d_base_source=None):
        if old_variant == "C":
            assert d_base_source is not None and d_base_source.name == "s6_c0_physics_base_no_d1.i"
        staged.mkdir(parents=True)
        directory = staged / "chem"
        directory.mkdir()
        if old_variant == "C":
            directory.joinpath("migrated_continuity.i").write_text("OLD")
        return [f"{case}.i"]

    class CleanupFault:
        def __enter__(self):
            path = tmp_path / "scratch"
            path.mkdir()
            return str(path)

        def __exit__(self, *_args):
            raise PermissionError("simulated root-owned .jitcache")

    options = {
        "Path": Path,
        "os": os,
        "json": json,
        "hashlib": hashlib,
        "ROOT": root,
        "OCI": image,
        "OVERLAY": "new option input",
        "OVERLAY_SHA256": EXPECTED_OVERLAY,
        "CASES": ("417", "941"),
        "VARIANTS": ("B", "D"),
        "validate_overlay": lambda: None,
        "retire_staged_B_d1_observations": lambda *_args: {"status": "SYNTHETIC_B_RETIREMENT"},
        "canonicalize_staged_D_inputs": lambda *_args: {"status": "SYNTHETIC_MIGRATION"},
        "reconcile_staged_D_json_initials": lambda *_args: {"status": "SYNTHETIC_JSON_INITIALS"},
        "remap_staged_fem_types": lambda *_args: {"status": "SYNTHETIC_TYPE_REMAP"},
        "remap_staged_electron_lookup": lambda *_args: {"status": "SYNTHETIC_LOOKUP_REMAP"},
        "remap_staged_wall_owners": lambda *_args: {"status": "SYNTHETIC_WALL_REMAP"},
        "remap_staged_mean_energy": lambda *_args: {"status": "SYNTHETIC_MEAN_ENERGY_REMAP"},
        "remap_staged_sheath_bcs": lambda *_args: {"status": "SYNTHETIC_SHEATH_REMAP"},
        "check_source": lambda *_args: {"binary_sha256": "123"},
        "sha_file": lambda path: EXPECTED_OVERLAY if str(path).endswith("migrated_continuity.i") else "manifest-hash",
        "p2": SimpleNamespace(
            preflight=lambda _root: {"P0": "PASS"},
            DECKS=Path("."),
            PINNED_CANDIDATE="legacy-pinned",
            CHEM=Path("chem"),
            stage=stage,
        ),
        "run_one": lambda *_args: {"P2": "PASS", "exit_code": 0, "syntax_ok": True},
        "tempfile": SimpleNamespace(TemporaryDirectory=lambda **_kwargs: CleanupFault()),
        "shutil": SimpleNamespace(copy2=lambda _src, dst: Path(dst).write_text("{}")),
    }
    exec(compile(module, str(PILOT / "public_option_s6_p2.py"), "exec"), options)
    report = options["execute"](tmp_path, tmp_path / "physics-opt", source, evidence)
    assert report["P2"] == "PASS"
    assert report["cleanup"] == "HOLD"
    assert report["status"] == "HOLD_INFRASTRUCTURE_CLEANUP"
    assert report["cleanup_error_class"] == "PermissionError"
    assert all(report["checks"][case][variant]["P2"] == "PASS"
               for case in ("417", "941") for variant in ("B", "D"))
    durable = json.loads((evidence / "issue402_option_s6_p2_status.json").read_text())
    assert durable["P2"] == "PASS"
    assert durable["status"] == "HOLD_INFRASTRUCTURE_CLEANUP"
    assert durable["P3"] == "NOT_RUN"
