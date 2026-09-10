#!/usr/bin/env python3
"""Stage-5 S5-D bounded validation for H01-H04 oxygen heavy-particle reactions."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "docs/development/2026-09-10_issue176_stage5_s5d_heavy_reactions_contract.json"
DATABASE = ROOT / "physics_app/data/heavy_reactions/stage5_s5d_oxygen_heavy.txt"
NA = 6.02214076e23
RHO = 3.1998e-5
M_O2 = 0.032
M_O = 0.016
DT = 1.0e-7
INITIAL = {"O2p": 0.01, "O": 0.10, "Om": 0.01, "Op": 0.01}
INITIAL_O2 = 1.0 - sum(INITIAL.values())
RATE_META = {
    "h1": ("H01_Op_O2_charge_transfer", 2.0e-17, 0.5),
    "h2": ("H02_Om_Op_neutralization", 4.0e-14, 0.43),
    "h3": ("H03_Om_O2p_to_3O", 2.6e-14, 0.44),
    "h4": ("H04_Om_O2p_to_O_O2", 2.6e-14, 0.44),
}
PROGRESS = {key: f"reaction_rate_{value[0]}" for key, value in RATE_META.items()}
RESERVED = {"x", "y", "z", "t", "pi", "e"}


def close(a: float, b: float, rel: float = 2.0e-5, abs_: float = 1.0e-12) -> None:
    if not math.isclose(a, b, rel_tol=rel, abs_tol=abs_):
        raise AssertionError(f"{a!r} != {b!r}")


def concentrations(state: dict[str, float]) -> dict[str, float]:
    o2 = 1.0 - sum(state.values())
    if min(o2, *state.values()) < 0.0:
        raise AssertionError("negative mass fraction")
    return {
        "O2": RHO * o2 / M_O2,
        "O2p": RHO * state["O2p"] / M_O2,
        "O": RHO * state["O"] / M_O,
        "Om": RHO * state["Om"] / M_O,
        "Op": RHO * state["Op"] / M_O,
    }


def analytic_rates(state: dict[str, float], temperature: float) -> dict[str, float]:
    if not math.isfinite(temperature) or temperature <= 0.0:
        raise AssertionError("T_g must be finite and > 0 K")
    c = concentrations(state)
    return {
        "h1": 2.0e-17 * NA * (300.0 / temperature) ** 0.5 * c["Op"] * c["O2"],
        "h2": 4.0e-14 * NA * (300.0 / temperature) ** 0.43 * c["Om"] * c["Op"],
        "h3": 2.6e-14 * NA * (300.0 / temperature) ** 0.44 * c["Om"] * c["O2p"],
        "h4": 2.6e-14 * NA * (300.0 / temperature) ** 0.44 * c["Om"] * c["O2p"],
    }


def analytic_sources(r: dict[str, float]) -> dict[str, float]:
    return {
        "O2p": M_O2 * (r["h1"] - r["h3"] - r["h4"]),
        "O": M_O * (r["h1"] + 2.0 * r["h2"] + 3.0 * r["h3"] + r["h4"]),
        "Om": -M_O * (r["h2"] + r["h3"] + r["h4"]),
        "Op": -M_O * (r["h1"] + r["h2"]),
        "O2": M_O2 * (-r["h1"] + r["h4"]),
    }


def oxygen_atoms(state: dict[str, float]) -> float:
    c = concentrations(state)
    return 2.0 * c["O2"] + 2.0 * c["O2p"] + c["O"] + c["Om"] + c["Op"]


def heavy_charge(state: dict[str, float]) -> float:
    c = concentrations(state)
    return c["O2p"] + c["Op"] - c["Om"]


def synthetic_case(temperature: float) -> list[dict[str, float]]:
    state = dict(INITIAL)
    for _ in range(1000):
        rates = analytic_rates(state, temperature)
        src = analytic_sources(rates)
        nxt = {k: INITIAL[k] + DT * src[k] / RHO for k in INITIAL}
        if max(abs(nxt[k] - state[k]) for k in state) < 1.0e-15:
            state = nxt
            break
        state = nxt
    rates0 = analytic_rates(INITIAL, temperature)
    rates1 = analytic_rates(state, temperature)
    src1 = analytic_sources(rates1)

    def row(s: dict[str, float], r: dict[str, float], src: dict[str, float]) -> dict[str, float]:
        return {
            "w2p": s["O2p"], "wo": s["O"], "wom": s["Om"], "wop": s["Op"],
            "wo2": 1.0 - sum(s.values()),
            "h1": r["h1"], "h2": r["h2"], "h3": r["h3"], "h4": r["h4"],
            "s2p": src["O2p"], "so": src["O"], "som": src["Om"], "sop": src["Op"],
            "so2": src["O2"], "tg": temperature, "rho": RHO,
        }

    return [row(INITIAL, rates0, analytic_sources(rates0)), row(state, rates1, src1)]


def _f(row: dict[str, str] | dict[str, float], name: str) -> float:
    return float(row[name])


def validate_case(rows: list[dict[str, str]] | list[dict[str, float]], temperature: float) -> dict:
    if len(rows) < 2:
        raise AssertionError("runtime CSV must contain initial and final rows")
    a, b = rows[0], rows[-1]
    initial = {"O2p": _f(a, "w2p"), "O": _f(a, "wo"), "Om": _f(a, "wom"), "Op": _f(a, "wop")}
    final = {"O2p": _f(b, "w2p"), "O": _f(b, "wo"), "Om": _f(b, "wom"), "Op": _f(b, "wop")}
    for key in INITIAL:
        close(initial[key], INITIAL[key], rel=0.0, abs_=2.0e-12)
    close(_f(a, "wo2"), INITIAL_O2, rel=0.0, abs_=2.0e-12)
    close(_f(b, "wo2"), 1.0 - sum(final.values()), rel=0.0, abs_=3.0e-12)
    close(_f(b, "tg"), temperature, rel=0.0, abs_=1.0e-10)
    close(_f(b, "rho"), RHO, rel=0.0, abs_=1.0e-14)
    if min(_f(b, "wo2"), *final.values()) < 0.0:
        raise AssertionError("negative final mass fraction")

    expected0 = analytic_rates(initial, temperature)
    expected1 = analytic_rates(final, temperature)
    actual0 = {k: _f(a, k) for k in RATE_META}
    actual1 = {k: _f(b, k) for k in RATE_META}
    for key in RATE_META:
        close(actual0[key], expected0[key])
        close(actual1[key], expected1[key])
        if actual1[key] <= 0.0:
            raise AssertionError(f"{key} progress must be positive")
    close(actual1["h3"], actual1["h4"], rel=2.0e-12, abs_=1.0e-14)

    expected_sources = analytic_sources(actual1)
    actual_sources = {
        "O2p": _f(b, "s2p"), "O": _f(b, "so"), "Om": _f(b, "som"),
        "Op": _f(b, "sop"), "O2": _f(b, "so2"),
    }
    for key in actual_sources:
        close(actual_sources[key], expected_sources[key])

    for key in INITIAL:
        close(RHO * (final[key] - initial[key]) / DT, actual_sources[key], rel=3.0e-5, abs_=5.0e-10)
    o2_delta_rate = RHO * (_f(b, "wo2") - _f(a, "wo2")) / DT
    close(o2_delta_rate, actual_sources["O2"], rel=3.0e-5, abs_=5.0e-10)
    close(o2_delta_rate, -sum(actual_sources[k] for k in INITIAL), rel=3.0e-5, abs_=5.0e-10)

    close(oxygen_atoms(initial), oxygen_atoms(final), rel=0.0, abs_=5.0e-10)
    close(heavy_charge(initial), heavy_charge(final), rel=0.0, abs_=5.0e-10)

    return {
        "temperature_K": temperature,
        "initial_rates_mol_m3_s": actual0,
        "final_rates_mol_m3_s": actual1,
        "final_mass_fractions": {**final, "O2": _f(b, "wo2")},
        "final_mass_sources_kg_m3_s": actual_sources,
        "oxygen_atom_inventory_initial_mol_m3": oxygen_atoms(initial),
        "oxygen_atom_inventory_final_mol_m3": oxygen_atoms(final),
        "heavy_charge_inventory_initial_mol_m3": heavy_charge(initial),
        "heavy_charge_inventory_final_mol_m3": heavy_charge(final),
    }


def validate_scaling(low: dict, high: dict) -> None:
    t0, t1 = low["temperature_K"], high["temperature_K"]
    for key, (_, _, exponent) in RATE_META.items():
        ratio = high["initial_rates_mol_m3_s"][key] / low["initial_rates_mol_m3_s"][key]
        close(ratio, (t0 / t1) ** exponent, rel=2.0e-5, abs_=1.0e-12)


def input_text(temperature: float) -> str:
    active = " ".join(meta[0] for meta in RATE_META.values())
    return f"""[Mesh]
  [m]
    type = GeneratedMeshGenerator
    dim = 1
    nx = 1
  []
[]
[Variables]
  [w_O2p]
    type = MooseVariableFVReal
    initial_condition = {INITIAL['O2p']}
  []
  [w_O]
    type = MooseVariableFVReal
    initial_condition = {INITIAL['O']}
  []
  [w_Om]
    type = MooseVariableFVReal
    initial_condition = {INITIAL['Om']}
  []
  [w_Op]
    type = MooseVariableFVReal
    initial_condition = {INITIAL['Op']}
  []
[]
[FunctorMaterials]
  [state]
    type = ADGenericFunctorMaterial
    prop_names = 'rho_const T_g'
    prop_values = '{RHO} {temperature}'
  []
  [O2_constraint]
    type = ADParsedFunctorMaterial
    property_name = w_O2_constraint
    functor_names = 'w_O2p w_O w_Om w_Op'
    functor_symbols = 'm2p mo mom mop'
    expression = '1.0-m2p-mo-mom-mop'
  []
  [heavy_rates]
    type = PhysicsReactionRateMaterial
    chemistry_file = '{DATABASE.resolve()}'
    density = rho_const
    temperature = T_g
    species = 'O2 O2p O Om Op'
    mass_fractions = 'w_O2_constraint w_O2p w_O w_Om w_Op'
    active_reactions = '{active}'
  []
  [source_O2p]
    type = ADParsedFunctorMaterial
    property_name = S_O2p_s5d
    functor_names = '{PROGRESS['h1']} {PROGRESS['h3']} {PROGRESS['h4']}'
    functor_symbols = 'h1 h3 h4'
    expression = '{M_O2}*(h1-h3-h4)'
  []
  [source_O]
    type = ADParsedFunctorMaterial
    property_name = S_O_s5d
    functor_names = '{PROGRESS['h1']} {PROGRESS['h2']} {PROGRESS['h3']} {PROGRESS['h4']}'
    functor_symbols = 'h1 h2 h3 h4'
    expression = '{M_O}*(h1+2.0*h2+3.0*h3+h4)'
  []
  [source_Om]
    type = ADParsedFunctorMaterial
    property_name = S_Om_s5d
    functor_names = '{PROGRESS['h2']} {PROGRESS['h3']} {PROGRESS['h4']}'
    functor_symbols = 'h2 h3 h4'
    expression = '-{M_O}*(h2+h3+h4)'
  []
  [source_Op]
    type = ADParsedFunctorMaterial
    property_name = S_Op_s5d
    functor_names = '{PROGRESS['h1']} {PROGRESS['h2']}'
    functor_symbols = 'h1 h2'
    expression = '-{M_O}*(h1+h2)'
  []
  [source_O2_expected]
    type = ADParsedFunctorMaterial
    property_name = S_O2_constraint_expected
    functor_names = '{PROGRESS['h1']} {PROGRESS['h4']}'
    functor_symbols = 'h1 h4'
    expression = '{M_O2}*(-h1+h4)'
  []
[]
[FVKernels]
  [t_O2p]
    type = PhysicsFVMassFractionTimeDerivative
    variable = w_O2p
    rho = rho_const
  []
  [s_O2p]
    type = PhysicsFVSpeciesReactionSource
    variable = w_O2p
    source = S_O2p_s5d
  []
  [t_O]
    type = PhysicsFVMassFractionTimeDerivative
    variable = w_O
    rho = rho_const
  []
  [s_O]
    type = PhysicsFVSpeciesReactionSource
    variable = w_O
    source = S_O_s5d
  []
  [t_Om]
    type = PhysicsFVMassFractionTimeDerivative
    variable = w_Om
    rho = rho_const
  []
  [s_Om]
    type = PhysicsFVSpeciesReactionSource
    variable = w_Om
    source = S_Om_s5d
  []
  [t_Op]
    type = PhysicsFVMassFractionTimeDerivative
    variable = w_Op
    rho = rho_const
  []
  [s_Op]
    type = PhysicsFVSpeciesReactionSource
    variable = w_Op
    source = S_Op_s5d
  []
[]
[Postprocessors]
  [w2p]
    type = ElementAverageFunctorPostprocessor
    functor = w_O2p
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [wo]
    type = ElementAverageFunctorPostprocessor
    functor = w_O
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [wom]
    type = ElementAverageFunctorPostprocessor
    functor = w_Om
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [wop]
    type = ElementAverageFunctorPostprocessor
    functor = w_Op
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [wo2]
    type = ElementAverageFunctorPostprocessor
    functor = w_O2_constraint
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [h1]
    type = ElementAverageFunctorPostprocessor
    functor = {PROGRESS['h1']}
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [h2]
    type = ElementAverageFunctorPostprocessor
    functor = {PROGRESS['h2']}
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [h3]
    type = ElementAverageFunctorPostprocessor
    functor = {PROGRESS['h3']}
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [h4]
    type = ElementAverageFunctorPostprocessor
    functor = {PROGRESS['h4']}
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [s2p]
    type = ElementAverageFunctorPostprocessor
    functor = S_O2p_s5d
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [so]
    type = ElementAverageFunctorPostprocessor
    functor = S_O_s5d
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [som]
    type = ElementAverageFunctorPostprocessor
    functor = S_Om_s5d
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [sop]
    type = ElementAverageFunctorPostprocessor
    functor = S_Op_s5d
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [so2]
    type = ElementAverageFunctorPostprocessor
    functor = S_O2_constraint_expected
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [tg]
    type = ElementAverageFunctorPostprocessor
    functor = T_g
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [rho]
    type = ElementAverageFunctorPostprocessor
    functor = rho_const
    execute_on = 'INITIAL TIMESTEP_END'
  []
[]
[Executioner]
  type = Transient
  dt = {DT}
  end_time = {DT}
  solve_type = NEWTON
[]
[Outputs]
  csv = true
  exodus = false
[]
"""


def validate_surface(text: str) -> None:
    required = [
        "type = PhysicsReactionRateMaterial",
        "temperature = T_g",
        "type = PhysicsFVSpeciesReactionSource",
        "property_name = S_O2p_s5d",
        "property_name = S_O_s5d",
        "property_name = S_Om_s5d",
        "property_name = S_Op_s5d",
    ] + list(PROGRESS.values())
    for token in required:
        if token not in text:
            raise AssertionError(f"missing production token: {token}")
    forbidden = [
        "reaction_source_", "PhysicsFVElectronReactionSource",
        "PhysicsFVElectronReactionEnergySource", "FVCoupledForce", "H05_",
    ]
    for token in forbidden:
        if token in text:
            raise AssertionError(f"forbidden S5-D production token: {token}")
    if text.count("type = PhysicsReactionRateMaterial") != 1:
        raise AssertionError("S5-D requires exactly one heavy reaction-rate owner")
    for progress in PROGRESS.values():
        if text.count(progress) < 2:
            raise AssertionError(f"published progress is not reused by source/probe surfaces: {progress}")
    symbols = []
    for match in __import__("re").finditer(r"functor_symbols\s*=\s*'([^']+)'", text):
        symbols.extend(match.group(1).split())
    if RESERVED.intersection(symbols):
        raise AssertionError("reserved parser symbol used")


def parse_database(text: str) -> dict[str, dict]:
    species = {}
    reactions = {}
    current = None
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        parts = line.split()
        if current is None:
            if parts[0] == "species":
                if len(parts) != 6:
                    raise AssertionError("bad species row")
                species[parts[1]] = {
                    "solver": parts[2], "mass": float(parts[3]),
                    "charge": int(parts[4]), "kind": parts[5],
                }
            elif parts[0] == "reaction":
                if len(parts) != 4 or parts[2:] != ["volume", "power_law"]:
                    raise AssertionError("bad reaction header")
                current = {"name": parts[1], "reactants": {}, "products": {}}
            else:
                raise AssertionError(f"unexpected database token: {parts[0]}")
        else:
            key = parts[0]
            if key in ("reactant", "product"):
                current[key + "s"][parts[1]] = float(parts[2])
            elif key == "A":
                current["A"] = float(parts[1])
            elif key == "basis":
                current["basis"] = parts[1]
            elif key == "T_ref":
                current["T_ref"] = float(parts[1])
            elif key == "exponent":
                current["exponent"] = float(parts[1])
            elif key == "end":
                reactions[current["name"]] = current
                current = None
            else:
                raise AssertionError(f"unexpected reaction token: {key}")
    if current is not None:
        raise AssertionError("unterminated database reaction")
    return {"species": species, "reactions": reactions}


def static_check() -> None:
    contract = json.loads(CONTRACT.read_text())
    if contract["status"] != "CONTRACT_FROZEN" or contract["slice"] != "S5-D_H01_H04_HEAVY_REACTIONS":
        raise AssertionError("wrong S5-D contract")
    if contract["production_owner"]["rate_owner"] != "PhysicsReactionRateMaterial":
        raise AssertionError("wrong rate owner")
    if contract["production_owner"]["electron_particle_projector"] != "NONE" or contract["production_owner"]["electron_energy_projector"] != "NONE":
        raise AssertionError("electron projection must be absent")
    for src in contract["source_provenance"]["reactions"]:
        got = hashlib.sha256(src["exact_line"].encode()).hexdigest()
        if got != src["line_sha256"]:
            raise AssertionError(f"source-line provenance hash mismatch: {src['id']}")

    db = parse_database(DATABASE.read_text())
    expected_species = {
        "O2": ("O2", M_O2, 0), "O2p": ("O2p", M_O2, 1),
        "O": ("O", M_O, 0), "Om": ("Om", M_O, -1), "Op": ("Op", M_O, 1),
    }
    if set(db["species"]) != set(expected_species):
        raise AssertionError("database species surface mismatch")
    for name, (solver, mass, charge) in expected_species.items():
        item = db["species"][name]
        if (item["solver"], item["charge"], item["kind"]) != (solver, charge, "heavy"):
            raise AssertionError(f"species metadata mismatch: {name}")
        close(item["mass"], mass, rel=0.0, abs_=0.0)
    if set(db["reactions"]) != {x[0] for x in RATE_META.values()}:
        raise AssertionError("database must contain exactly H01-H04")
    contract_by_name = {r["database_name"]: r for r in contract["reactions"]}
    for key, (name, A, exponent) in RATE_META.items():
        r = db["reactions"][name]
        c = contract_by_name[name]
        close(r["A"], A, rel=0.0, abs_=0.0)
        close(r["T_ref"], 300.0, rel=0.0, abs_=0.0)
        close(r["exponent"], exponent, rel=0.0, abs_=0.0)
        if r["basis"] != "particle":
            raise AssertionError("S5-D database must use particle basis")
        expected_reactants = {k: float(-v) for k, v in c["stoichiometry"].items() if v < 0}
        expected_products = {k: float(v) for k, v in c["stoichiometry"].items() if v > 0}
        if r["reactants"] != expected_reactants or r["products"] != expected_products:
            raise AssertionError(f"stoichiometry mismatch: {name}")
        mass_balance = sum(expected_species[k][1] * v for k, v in c["stoichiometry"].items())
        charge_balance = sum(expected_species[k][2] * v for k, v in c["stoichiometry"].items())
        close(mass_balance, 0.0, rel=0.0, abs_=1.0e-15)
        close(charge_balance, 0.0, rel=0.0, abs_=1.0e-15)
    db_text = DATABASE.read_text()
    if "H05" in db_text or "electron" in db_text.lower():
        raise AssertionError("H05/electron surface must remain deferred")

    validate_surface(input_text(600.0))
    print("STAGE5_S5D_HEAVY_IMPLEMENTATION_P0_PASS")


def self_test() -> None:
    low_rows = synthetic_case(600.0)
    high_rows = synthetic_case(1200.0)
    low = validate_case(low_rows, 600.0)
    high = validate_case(high_rows, 1200.0)
    validate_scaling(low, high)

    mutations = [
        ("prefactor", "h1", lambda x: 1.01 * x),
        ("channel_identity", "h4", lambda x: 1.02 * x),
        ("source_sign", "so", lambda x: -x),
        ("constraint_sign", "wo2", lambda x: 2.0 * INITIAL_O2 - x),
    ]
    for name, field, fn in mutations:
        rows = [dict(r) for r in low_rows]
        rows[-1][field] = fn(rows[-1][field])
        try:
            validate_case(rows, 600.0)
        except AssertionError:
            pass
        else:
            raise AssertionError(f"negative mutation not detected: {name}")

    altered = json.loads(json.dumps(high))
    altered["initial_rates_mol_m3_s"]["h2"] *= 1.01
    try:
        validate_scaling(low, altered)
    except AssertionError:
        pass
    else:
        raise AssertionError("temperature-exponent mutation not detected")

    bad_surface = input_text(600.0).replace(
        "functor_names = 'reaction_rate_H01_Op_O2_charge_transfer reaction_rate_H03_Om_O2p_to_3O reaction_rate_H04_Om_O2p_to_O_O2'",
        "functor_names = 'reaction_source_Op reaction_rate_H03_Om_O2p_to_3O reaction_rate_H04_Om_O2p_to_O_O2'",
        1,
    )
    try:
        validate_surface(bad_surface)
    except AssertionError:
        pass
    else:
        raise AssertionError("downstream kinetic/source-owner mutation not detected")

    print("STAGE5_S5D_HEAVY_RUNTIME_CHECKER_SELFTEST_PASS")


def run_input(executable: Path, temperature: float, directory: Path, stem: str) -> list[dict[str, str]]:
    inp = directory / f"{stem}.i"
    inp.write_text(input_text(temperature))
    subprocess.run(
        [__import__("sys").executable, str(ROOT / "bin/physics.py"), "preflight", str(inp)],
        cwd=ROOT, check=True,
    )
    for cmd in ([str(executable), "--check-input", "-i", inp.name], [str(executable), "-i", inp.name]):
        result = subprocess.run(cmd, cwd=directory, text=True, capture_output=True)
        if result.returncode:
            raise AssertionError(result.stdout + result.stderr)
    with (directory / f"{stem}_out.csv").open() as handle:
        return list(csv.DictReader(handle))


def reject_nonpositive_temperature(executable: Path, directory: Path) -> str:
    inp = directory / "negative_tg.i"
    inp.write_text(input_text(-600.0))
    preflight = subprocess.run(
        [__import__("sys").executable, str(ROOT / "bin/physics.py"), "preflight", str(inp)],
        cwd=ROOT, text=True, capture_output=True,
    )
    if preflight.returncode:
        return "P2_PREFLIGHT"
    check = subprocess.run([str(executable), "--check-input", "-i", inp.name], cwd=directory, text=True, capture_output=True)
    if check.returncode:
        return "P2_CHECK_INPUT"
    run = subprocess.run([str(executable), "-i", inp.name], cwd=directory, text=True, capture_output=True)
    if run.returncode:
        return "P3_RUNTIME"
    raise AssertionError("non-positive T_g was silently accepted; clamp/floor/fallback is forbidden")


def runtime(executable: str, evidence_out: str | None, repository_sha: str | None, build_base_ref: str | None) -> None:
    static_check()
    self_test()
    exe = Path(executable).resolve()
    with tempfile.TemporaryDirectory() as td:
        directory = Path(td)
        low = validate_case(run_input(exe, 600.0, directory, "s5d_600K"), 600.0)
        high = validate_case(run_input(exe, 1200.0, directory, "s5d_1200K"), 1200.0)
        validate_scaling(low, high)
        rejection_layer = reject_nonpositive_temperature(exe, directory)

    evidence = {
        "schema_version": 1,
        "stage": "STAGE_5",
        "slice": "S5-D_H01_H04_HEAVY_REACTIONS",
        "decision": "LOCAL_RUNTIME_ACCURACY",
        "result": "PASS",
        "integrated_physics_accuracy": "NOT_ESTABLISHED",
        "representative_real_qvt": "NOT_TESTED",
        "repository_sha": repository_sha,
        "build_base_ref": build_base_ref,
        "executable_sha256": hashlib.sha256(exe.read_bytes()).hexdigest(),
        "production_owner": "PhysicsReactionRateMaterial.reaction_rate_*",
        "source_projection": "ADParsedFunctorMaterial_from_published_progress_then_PhysicsFVSpeciesReactionSource",
        "cases": [low, high],
        "temperature_scaling": {
            key: (high["initial_rates_mol_m3_s"][key] / low["initial_rates_mol_m3_s"][key])
            for key in RATE_META
        },
        "nonpositive_temperature_rejection_layer": rejection_layer,
    }
    if evidence_out:
        Path(evidence_out).write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(
        "STAGE5_S5D_HEAVY_LOCAL_RUNTIME_PASS "
        f"H01_600K={low['initial_rates_mol_m3_s']['h1']:.12g} "
        f"H02_600K={low['initial_rates_mol_m3_s']['h2']:.12g} "
        f"H03_H04_600K={low['initial_rates_mol_m3_s']['h3']:.12g} "
        f"negative_T_rejected_at={rejection_layer}"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--static", action="store_true")
    parser.add_argument("--executable")
    parser.add_argument("--evidence-out")
    parser.add_argument("--repository-sha")
    parser.add_argument("--build-base-ref")
    args = parser.parse_args()
    if args.self_test:
        self_test()
    elif args.static:
        static_check()
    elif args.executable:
        runtime(args.executable, args.evidence_out, args.repository_sha, args.build_base_ref)
    else:
        parser.error("select --self-test, --static, or --executable")


if __name__ == "__main__":
    main()
