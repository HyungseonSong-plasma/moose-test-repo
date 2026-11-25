#!/usr/bin/env python3
"""Exact-head syntax-only Native P2 owner of retired JSON-rate one-shot inputs.

Reuse the PhysicsApp binary built by run_native_binding_smoke.sh; never
compile here, execute timesteps, or claim original-rate scientific parity.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
CI = ROOT / "physics_app/ci"


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def run_check(executable: Path, source: Path, working_dir: Path) -> None:
    result = subprocess.run(
        [str(executable), "--check-input", "-i", source.name],
        cwd=working_dir, capture_output=True, text=True, check=False,
    )
    output = result.stdout + result.stderr
    if result.returncode != 0 or "Syntax OK" not in output:
        raise AssertionError(
            f"ISSUE402_RATE_NATIVE_P2_REJECTED:{source.name}:"
            f" exit={result.returncode} output={output[-3000:]}"
        )


def require_h05_canonical_energy(source: str) -> str:
    """Validate the canonical H05 Material inputs without rewriting the deck."""
    expected = """  [h05_log_molar_density]
    type = ADParsedFunctorMaterial
    property_name = h05_log_molar_density
    functor_names = 'n_e'
    functor_symbols = 'ne'
    expression = 'log(ne/6.02214076e23)'
  []
  [h05_log_molar_energy]
    type = ADParsedFunctorMaterial
    property_name = h05_log_molar_energy
    functor_names = 'mean_en'
    functor_symbols = 'energy'
    expression = 'log(energy/6.02214076e23)'
  []
  [mean_energy]
    type = ElectronEnergyMaterial
    electron_energy_density = h05_log_molar_energy
    electron_density = h05_log_molar_density
    state_form = log_molar_eV
  []"""
    if (source.count(expected) != 1
            or source.count("state_form = log_molar_eV") != 1
            or "physical_eV" in source):
        raise AssertionError("H05_CANONICAL_ENERGY_CONTRACT_CHANGED")
    return source



def lookup_fixture() -> tuple[dict, str]:
    """Exercise the real Action-owned lookup using synthetic state inputs.

    These constants are a construction probe, not the S6 live concentration
    owner or a scientific parity result. No external R_EI producer exists.
    """
    mechanism = {
        "species": {
            "e": {"elements": {}, "charge_number": -1},
            "O2": {"elements": {"O": 2}, "charge_number": 0},
            "O2p": {"elements": {"O": 2}, "charge_number": 1},
            "O2s": {"elements": {"O": 2}, "charge_number": 0},
        },
        "equations": {"EI-415": "e + O2 -> 2e + O2p",
                      "EI-407": "e + O2 -> e + O2s"},
        "reactions": [],
    }
    for rid, products, loss in (
        ("EI-415", {"e": 2, "O2p": 1}, 12.06),
        ("EI-407", {"e": 1, "O2s": 1}, 0.977),
    ):
        mechanism["reactions"].append({
            "id": rid, "reactants": {"e": 1, "O2": 1}, "products": products,
            "units": "mol/(m^3 s)", "energy_loss_eV": loss,
            "rate": {"model": "lookup", "file": "../database/" + rid + "_O2_X.txt",
                     "basis": "molar", "bounds_policy": "strict"},
        })
    deck = """# #898 Action-owned lookup P2; synthetic state only
[Mesh]
  type = GeneratedMesh
  dim = 1
  nx = 2
[]
[Problem]
  solve = false
  kernel_coverage_check = false
[]
[Variables]
  [probe]
    family = LAGRANGE
    order = FIRST
  []
[]
[Physics]
  [Plasmas]
    files = chemistry/mechanism.json
    [Transport]
      [Chemistry]
      []
    []
  []
[]
[FunctorMaterials]
  [synthetic_state]
    type = ADGenericFunctorMaterial
    prop_names = 'e_energy_eV n_e_physical c_O2_molar'
    prop_values = '4 1e15 0.001'
  []
[]
[Postprocessors]
  [ionization_progress]
    type = ElementAverageFunctorPostprocessor
    functor = R_EI415
  []
  [excitation_progress]
    type = ElementAverageFunctorPostprocessor
    functor = R_EI407
  []
  [particle_source]
    type = ElementAverageFunctorPostprocessor
    functor = S_O2_molar
  []
  [energy_source]
    type = ElementAverageFunctorPostprocessor
    functor = Q_e_molar_eV
  []
[]
[Executioner]
  type = Transient
  dt = 1e-6
  num_steps = 1
[]
"""
    return mechanism, deck


def check_lookup_native(executable: Path, root: Path) -> None:
    mechanism, deck = lookup_fixture()
    database = root / "database"
    chemistry = root / "chemistry"
    database.mkdir()
    chemistry.mkdir()
    for reaction in mechanism["reactions"]:
        name = Path(reaction["rate"]["file"]).name
        raw = (ROOT / "physics_app/database" / name).read_bytes()
        (database / name).write_bytes(raw)
    source = root / "lookup.i"
    source.write_text(deck)
    document = chemistry / "mechanism.json"
    document.write_text(json.dumps(mechanism))
    run_check(executable, source, root)
    print("ISSUE898_ACTION_OWNED_EI_LOOKUP_NATIVE_P2_PASS_SYNTHETIC_STATE")

    def rate_mutation(key, value):
        bad = copy.deepcopy(mechanism)
        bad["reactions"][0]["rate"][key] = value
        return bad

    for bad, marker in (
        (rate_mutation("basis", "particle"), "EI lookup requires molar coefficient basis"),
        (rate_mutation("bounds_policy", "clamp"), "EI lookup requires strict bounds_policy"),
        (rate_mutation("file", "../database/missing.txt"), "transport table cannot be opened"),
        (rate_mutation("target", "O2s"), "unsupported rate key target"),
    ):
        document.write_text(json.dumps(bad))
        result = subprocess.run(
            [str(executable), "--check-input", "-i", source.name], cwd=root,
            capture_output=True, text=True, check=False)
        output = result.stdout + result.stderr
        if result.returncode == 0 or marker not in output:
            raise AssertionError("ISSUE898_LOOKUP_MUTATION_NOT_REJECTED:" + marker
                                 + ":" + output[-3000:])
    print("ISSUE898_ACTION_OWNED_EI_LOOKUP_NATIVE_NEGATIVE_PASS")



def named_neutral_mass_fixture() -> tuple[dict, str]:
    """Synthetic P2 for .i-owned neutral masses and live AD concentration.

    The existing EOS/variables here are test state providers, not the final
    NavierStokes ownership cut. No native EI progress or concentration alias.
    """
    mechanism = {
        "species": {
            "e": {"elements": {}, "charge_number": -1},
            "O2": {"elements": {"O": 2}, "charge_number": 0},
            "O": {"elements": {"O": 1}, "charge_number": 0},
        },
        "equations": {"EI-02": "e + O2 -> e + O2", "EI-17": "e + O -> e + O"},
        "reactions": [],
        "transport_coefficients": {"navier_stokes": {
            "transport_data_file": "../database/alias_only.txt",
            "temperature": "temperature", "pressure": "pressure",
            "species": ["O2", "O"], "mass_fractions": ["w_O2", "w_O"],
        }},
    }
    for rid, target, file in (
        ("EI-02", "O2", "o2_elastic.txt"), ("EI-17", "O", "o_elastic.txt"),
    ):
        mechanism["reactions"].append({
            "id": rid, "reactants": {"e": 1, target: 1},
            "products": {"e": 1, target: 1},
            "units": "mol/(m^3 s)", "energy_loss_eV": {"model": "none"},
            "rate": {"model": "lookup", "file": "../database/" + file,
                     "basis": "molar", "bounds_policy": "strict"},
        })
    deck = """# #896 .i mass ownership and live concentration P2 only
[Mesh]
  type = GeneratedMesh
  dim = 1
  nx = 2
[]
[Problem]
  solve = false
  kernel_coverage_check = false
[]
[Variables]
  [pressure]
    type = MooseVariableFVReal
  []
  [w_O2]
    type = MooseVariableFVReal
  []
  [w_O]
    type = MooseVariableFVReal
  []
[]
[Physics]
  [Plasmas]
    files = chemistry/mechanism.json
    pressure = 100
    temperature = 300
    [Transport]
      [Chemistry]
      []
      [NavierStokes]
        species_molar_mass = 'O:0.016 O2:0.032'
      []
    []
  []
[]
[FunctorMaterials]
  [electron_state_probe]
    type = ADGenericFunctorMaterial
    prop_names = 'e_energy_eV n_e_physical'
    prop_values = '4 1e15'
  []
  [existing_eos_probe]
    type = ADParsedFunctorMaterial
    property_name = rho_neutral
    functor_names = 'pressure temperature w_O2 w_O'
    functor_symbols = 'p T y2 y1'
    expression = 'p/(8.31446261815324*T*(y2/0.032+y1/0.016))'
  []
[]
[Postprocessors]
  [c_molecule]
    type = ElementAverageFunctorPostprocessor
    functor = c_O2_molar
  []
  [c_atom]
    type = ElementAverageFunctorPostprocessor
    functor = c_O_molar
  []
  [r_molecule]
    type = ElementAverageFunctorPostprocessor
    functor = R_EI02
  []
  [r_atom]
    type = ElementAverageFunctorPostprocessor
    functor = R_EI17
  []
[]
[Executioner]
  type = Transient
  dt = 1e-6
  num_steps = 1
[]
"""
    return mechanism, deck


def alias_only_transport(source: str) -> str:
    result = []
    count = 0
    for line in source.splitlines(keepends=True):
        fields = line.split("#", 1)[0].split()
        if fields and fields[0] == "species":
            if len(fields) != 4:
                raise AssertionError("unexpected legacy species row")
            result.append(f"species {fields[1]} {fields[3]}\n")
            count += 1
        else:
            result.append(line)
    if not count:
        raise AssertionError("no legacy species rows")
    return "".join(result)


def check_named_neutral_mass_native(executable: Path, root: Path) -> None:
    mechanism, deck = named_neutral_mass_fixture()
    database = root / "database"
    chemistry = root / "chemistry"
    database.mkdir()
    chemistry.mkdir()
    for reaction in mechanism["reactions"]:
        file = Path(reaction["rate"]["file"]).name
        (database / file).write_bytes((ROOT / "physics_app/database" / file).read_bytes())
    legacy = (ROOT / "physics_app/database/neutral_transport.txt").read_text()
    table = database / "alias_only.txt"
    table.write_text(alias_only_transport(legacy))
    doc = chemistry / "mechanism.json"
    doc.write_text(json.dumps(mechanism))
    source = root / "named_masses.i"
    source.write_text(deck)
    run_check(executable, source, root)
    print("ISSUE896_NAMED_NEUTRAL_MASS_LIVE_CONCENTRATION_P2_PASS")
    for value, marker in (
        ("O:0.016", "Named neutral masses must cover every active species"),
        ("O:0.016 O2:0.032 O2:0.032", "Unknown or repeated neutral mass"),
        ("O:0.016 O2:0", "Neutral molar mass must be finite and positive"),
        ("O:0.016 O2:0.032junk", "Neutral molar mass must be finite and positive"),
        ("O:0.016 O2:0.032 X:0.01", "Unknown or repeated neutral mass"),
    ):
        source.write_text(deck.replace("O:0.016 O2:0.032", value))
        result = subprocess.run([str(executable), "--check-input", "-i", source.name],
                                cwd=root, capture_output=True, text=True, check=False)
        output = result.stdout + result.stderr
        if result.returncode == 0 or marker not in output:
            raise AssertionError("ISSUE896_NAMED_MASS_MUTANT_ACCEPTED:" + marker + ":" + output[-3000:])
    source.write_text(deck)
    table.write_text(legacy)
    result = subprocess.run([str(executable), "--check-input", "-i", source.name],
                            cwd=root, capture_output=True, text=True, check=False)
    if result.returncode == 0 or "External molar masses require alias-only species rows" not in (
            result.stdout + result.stderr):
        raise AssertionError("ISSUE896_DUPLICATE_DATABASE_MASS_NOT_REJECTED")
    print("ISSUE896_NAMED_NEUTRAL_MASS_NEGATIVE_PASS")



def named_charged_species_fixture() -> tuple[dict, str]:
    pilot = ROOT / "experiments/Issue402_plasma_dsl_g1"
    mechanism = json.loads((pilot / "plasma_species_initial_p2.json").read_text())
    # Include a real charge-balance catalogue, but no Chemistry source
    # producers or solver timesteps in this binding-only P2 fixture.
    reactions = json.loads((pilot / "issue633_ion_continuity_newonly_p2.json").read_text())
    mechanism["equations"] = reactions["equations"]
    mechanism["reactions"] = reactions["reactions"]
    for record in mechanism["species"].values():
        record.pop("charge_number")
        record.pop("initial_number_density", None)
    deck = (pilot / "species_density_pairs_p2.i").read_text()
    marker = "          fvm_species = 'O2p Om Op'\n"
    named = """          species_molar_mass = 'e:5.485799096195737e-7 O2p:0.032 Om:0.016 Op:0.016'
          species_charge = 'e:-1 O2p:1 Om:-1 Op:1'
          species_temperature_eV = 'e:2.6666666666666665'
          species_initial_density = 'e:1e16 O2p:1e16 Om:1e14 Op:1e15'
          species_sticking_coef = 'e:1 O2p:1 Om:1 Op:1'
"""
    if deck.count(marker) != 1:
        raise AssertionError("charged fixture anchor changed")
    deck = deck.replace(marker, marker + named)
    # Energy uses the very same Continuity metadata for its auto-created
    # initial state. No independent energy-density IC in the input.
    marker = "          fem_potential = potential\n        []\n"
    if deck.count(marker) != 1:
        raise AssertionError("charged fixture energy insertion anchor changed")
    deck = deck.replace(marker, marker + """        [Energy]
          fem_species = e
          dont_create_kernels = true
        []
""")
    return mechanism, deck


def check_named_charged_species_native(executable: Path, root: Path) -> None:
    mechanism, deck = named_charged_species_fixture()
    source = root / "named_charged.i"
    doc = root / "plasma_species_initial_p2.json"
    source.write_text(deck)
    doc.write_text(json.dumps(mechanism))
    run_check(executable, source, root)
    print("ISSUE896_NAMED_CHARGED_SPECIES_P2_PASS")
    for old, new, expected in (
        ("e:-1 O2p:1 Om:-1 Op:1", "e:-1 O2p:1 Om:1 Op:1", "charge conservation failed"),
        ("e:1e16 O2p:1e16 Om:1e14 Op:1e15", "e:1e16 O2p:1e16 Om:1e14", "Incomplete named Continuity coverage"),
        ("e:1 O2p:1 Om:1 Op:1", "e:1 O2p:1 Om:1 Op:2", "Nonphysical named Continuity"),
        ("e:2.6666666666666665", "e:0", "Invalid named Continuity temperature"),
    ):
        source.write_text(deck.replace(old, new))
        result = subprocess.run([str(executable), "--check-input", "-i", source.name],
                                cwd=root, capture_output=True, text=True, check=False)
        output = result.stdout + result.stderr
        if result.returncode == 0 or expected not in output:
            raise AssertionError("ISSUE896_CHARGED_MUTATION_NOT_REJECTED:" + expected + ":" + output[-3000:])
    source.write_text(deck.replace("        [Energy]\n",
                                   "        [Energy]\n          initial_molar_energy_density_eV = 1e-8\n"))
    result = subprocess.run([str(executable), "--check-input", "-i", source.name],
                            cwd=root, capture_output=True, text=True, check=False)
    if result.returncode == 0 or "Named Continuity metadata exclusively owns initial electron energy" not in (
            result.stdout + result.stderr):
        raise AssertionError("ISSUE896_DUPLICATE_ENERGY_IC_NOT_REJECTED")
    source.write_text(deck)
    mechanism["species"]["e"]["charge_number"] = -1
    doc.write_text(json.dumps(mechanism))
    result = subprocess.run([str(executable), "--check-input", "-i", source.name],
                            cwd=root, capture_output=True, text=True, check=False)
    if result.returncode == 0 or "Duplicate JSON physical owner" not in result.stdout + result.stderr:
        raise AssertionError("ISSUE896_DUPLICATE_CHARGED_OWNER_NOT_REJECTED")
    print("ISSUE896_NAMED_CHARGED_SPECIES_NEGATIVE_PASS")


def self_test() -> None:
    import math
    from physics_app.ci.check_stage5_h05_runtime import runtime_input
    original = runtime_input()
    canonical = require_h05_canonical_energy(original)
    assert canonical == original
    assert "state_form = log_molar_eV" in canonical
    assert "type = FVCoupledForce" in canonical
    assert "v = S_e_h05" in canonical
    assert "coef = 1" in canonical
    for number_density, energy_density in ((1e15, 3e15), (2e19, 8e19)):
        actual = math.exp(
            math.log(energy_density / 6.02214076e23)
            - math.log(number_density / 6.02214076e23)
        )
        assert math.isclose(actual, energy_density / number_density, rel_tol=1e-13)
    try:
        require_h05_canonical_energy(
            original.replace("state_form = log_molar_eV", "state_form = physical_eV")
        )
    except AssertionError:
        pass
    else:
        raise AssertionError("H05_BRIDGE_MUTATION_NOT_REJECTED")
    # Mutation control for a fake executable: syntax acceptance must be
    # explicit, not inferred from process exit 0 or output-file existence.
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        source = root / "control.i"
        source.write_text("[Mesh]\n  type = GeneratedMesh\n[]\n")
        for expected, text in ((True, "Syntax OK"), (False, "Silently skipped syntax")):
            exe = root / "mock"
            exe.write_text("#!/usr/bin/env python3\nprint(" + repr(text) + ")\n")
            exe.chmod(0o755)
            try:
                run_check(exe, source, root)
            except AssertionError:
                if expected:
                    raise
            else:
                if not expected:
                    raise AssertionError("MUTATION_ACCEPTED_WITHOUT_SYNTAX_OK")
    mechanism, deck = lookup_fixture()
    assert set(mechanism["equations"]) == {"EI-415", "EI-407"}
    assert "reaction_progress =" not in deck and "type = EIRateCoefMaterial" not in deck
    assert all(r["rate"]["basis"] == "molar" for r in mechanism["reactions"])
    named, named_deck = named_neutral_mass_fixture()
    assert "species_molar_mass = 'O:0.016 O2:0.032'" in named_deck
    assert "property_name = c_O2_molar" not in named_deck
    assert all("molar_mass" not in row and "molar_mass_kg_mol" not in row
               for row in named["species"].values())
    assert alias_only_transport("species O 0.016 O\npair O O 1 2\n") == (
        "species O O\npair O O 1 2\n")
    charged, charged_deck = named_charged_species_fixture()
    assert all("charge_number" not in row and "initial_number_density" not in row
               for row in charged["species"].values())
    assert "species_charge = 'e:-1 O2p:1 Om:-1 Op:1'" in charged_deck
    assert "[Energy]" in charged_deck and "initial_molar_energy_density_eV" not in charged_deck
    assert len(charged["reactions"]) == 3
    print("ISSUE402_JSON_RATE_P2_MUTATION_SELF_TEST=PASS")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--executable", type=Path)
    parser.add_argument("--p1-identity", type=Path)
    args = parser.parse_args()

    if args.self_test:
        self_test()
        if args.executable is None and args.p1_identity is None:
            return
    if not args.executable or not args.p1_identity:
        parser.error("both --executable and --p1-identity are required")

    expected_head = os.environ.get("EXPECTED_HEAD")
    expected_oci = os.environ.get("PINNED_BASE")
    if not expected_head or not expected_oci:
        raise AssertionError("REQUIRE_EXACT_HEAD_AND_PINNED_OCI")
    identity = json.loads(args.p1_identity.read_text())
    if (
        identity.get("source_sha") != expected_head
        or identity.get("oci_image") != expected_oci
        or identity.get("binary_sha256") != digest(args.executable)
        or identity.get("P1") != "PASS"
    ):
        raise AssertionError("ISSUE402_RATE_P1_BINARY_IDENTITY_CHANGED")

    # Exact obligations of old issue402-json-rate-native-once.yml, reused
    # rather than running a second MOOSE build in an independent workflow.
    from physics_app.ci.check_stage5_s5d_heavy_reactions import input_text
    from physics_app.ci.check_stage5_h05_runtime import runtime_input

    with tempfile.TemporaryDirectory(prefix="issue402-rate-p2-") as tmp:
        root = Path(tmp)
        for label, source in (
            ("H01_H04", input_text(600.0)),
            ("H05", require_h05_canonical_energy(runtime_input())),
        ):
            candidate = root / (label + ".i")
            candidate.write_text(source)
            run_check(args.executable, candidate, root)
            print(label + "_JSON_NATIVE_P2_PASS")
            if label == "H05":
                print("H05_CANONICAL_ENERGY_P2_PASS")
    with tempfile.TemporaryDirectory(prefix="issue898-lookup-p2-") as tmp:
        check_lookup_native(args.executable, Path(tmp))
    with tempfile.TemporaryDirectory(prefix="issue896-named-neutral-p2-") as tmp:
        check_named_neutral_mass_native(args.executable, Path(tmp))
    with tempfile.TemporaryDirectory(prefix="issue896-named-charged-p2-") as tmp:
        check_named_charged_species_native(args.executable, Path(tmp))
    run_check(args.executable, CI / "json_surface_rate_p2.i", CI)
    print("JSON_SURFACE_RATE_NATIVE_P2_PASS")
    print("ISSUE402_JSON_RATE_SHARED_NATIVE_P2_PASS_P3_NOT_RUN")


if __name__ == "__main__":
    main()
