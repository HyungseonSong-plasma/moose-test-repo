#!/usr/bin/env python3
"""P0/static gate for #26 E8 EI02/EI17 elastic and EI19 energy-only restoration."""

import ast
import hashlib
import json
import math
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "docs/development/2026-09-10_issue26_e8_elastic_ei19_contract.json"
OWNER_H = ROOT / "physics_app/include/materials/PhysicsElectronImpactRateMaterial.h"
OWNER_C = ROOT / "physics_app/src/materials/PhysicsElectronImpactRateMaterial.C"
RUNTIME_CHECKER = ROOT / "physics_app/ci/check_e8_elastic_ei19_runtime.py"
DATA_DIR = ROOT / "physics_app/data/electron_impact"

EXPECTED_TABLES = {
    "o2_elastic.txt": {
        "blob": "3f4b19e8f04184e38fa92b08b502a37ff3755ccb",
        "anchors": {1.40991: 2.62e10, 5.73276: 5.53e10, 22.1378: 1.19e11},
    },
    "o_elastic.txt": {
        "blob": "de9d718cf197d129db5d02fc3141c92969eca860",
        "anchors": {1.40991: 2.08e10, 5.73276: 5.89e10, 22.1378: 2.19e11},
    },
    "o_excitation_1s.txt": {
        "blob": "5ab8f6ba4c26c981c13d006364217fbadd07f603",
        "anchors": {1.40991: 3.25e5, 5.73276: 1.09e8, 22.1378: 1.90e8},
    },
}


def _git_blob_sha(data):
    header = f"blob {len(data)}\0".encode()
    return hashlib.sha1(header + data).hexdigest()


def _parse_table(data, label):
    rows = []
    for line_no, raw in enumerate(data.decode().splitlines(), 1):
        if not raw.strip():
            continue
        fields = raw.split()
        if len(fields) != 2:
            raise AssertionError(f"{label}:{line_no}: expected two columns")
        x, y = map(float, fields)
        if not (math.isfinite(x) and math.isfinite(y)):
            raise AssertionError(f"{label}:{line_no}: non-finite value")
        if y < 0:
            raise AssertionError(f"{label}:{line_no}: negative rate")
        rows.append((x, y))
    if len(rows) != 100:
        raise AssertionError(f"{label}: expected 100 rows, got {len(rows)}")
    if any(b[0] <= a[0] for a, b in zip(rows, rows[1:])):
        raise AssertionError(f"{label}: mean-energy grid is not strictly increasing")
    return rows


def _validate_table_bytes(data, spec, label):
    actual_blob = _git_blob_sha(data)
    if actual_blob != spec["blob"]:
        raise AssertionError(f"{label}: source blob {actual_blob} != frozen {spec['blob']}")
    rows = _parse_table(data, label)
    values = {x: y for x, y in rows}
    for x, expected in spec["anchors"].items():
        if x not in values or not math.isclose(values[x], expected, rel_tol=0, abs_tol=0):
            raise AssertionError(f"{label}: frozen anchor mismatch at {x} eV")
    if rows[0][0] != 1.40991 or rows[-1][0] != 22.1378:
        raise AssertionError(f"{label}: strict lookup domain changed")
    return rows


def _validate_owner_text(header, source):
    required_header = (
        "class PhysicsElectronImpactRateMaterial : public FunctorMaterial",
        "PhysicsLookupTable1D _table;",
        "const std::string _reaction_progress_name;",
    )
    required_source = (
        'registerMooseObject("PhysicsApp", PhysicsElectronImpactRateMaterial);',
        'addRequiredParam<FileName>("rate_table_file"',
        'addRequiredParam<MooseFunctorName>("mean_energy"',
        'addRequiredParam<MooseFunctorName>("electron_number_density"',
        'addRequiredParam<MooseFunctorName>("target_molar_concentration"',
        'addRequiredParam<std::string>("reaction_progress"',
        '_table(_rate_table_file, 1, {2})',
        'raw < x.front() || raw > x.back()',
        'const ADReal k_raw = interpolateStrict(_mean_energy(r, state));',
        'return k_raw * (n_e / N_A) * c_target;',
        'strict Stage-4 policy forbids clamp/floor',
    )
    for token in required_header:
        if token not in header:
            raise AssertionError(f"missing header ownership token: {token}")
    for token in required_source:
        if token not in source:
            raise AssertionError(f"missing source ownership token: {token}")
    if source.count("addFunctorProperty<ADReal>(") != 1:
        raise AssertionError("rate owner must publish exactly one canonical progress functor")
    for forbidden in ("std::clamp(", "std::max(", "std::min(", "PhysicsFVElectronReactionEnergySource"):
        if forbidden in source:
            raise AssertionError(f"forbidden rate-owner behavior: {forbidden}")


def _validate_contract(contract):
    if contract.get("status") != "CONTRACT_FROZEN":
        raise AssertionError("E8 elastic/EI19 contract is not frozen")
    if contract.get("stage") != "STAGE_4_E8":
        raise AssertionError("wrong stage")
    reactions = {entry["id"]: entry for entry in contract["reactions"]}
    expected_ids = {"EI02_O2_ELASTIC", "EI17_O_ELASTIC", "EI19_O_EXCITATION_4P192"}
    if set(reactions) != expected_ids:
        raise AssertionError("bounded reaction set changed")
    if reactions["EI19_O_EXCITATION_4P192"]["energy_loss_eV_per_event"] != 4.192:
        raise AssertionError("EI19 energy loss changed")
    if reactions["EI19_O_EXCITATION_4P192"]["particle_or_heavy_projection"] != (
        "NONE; audited reaction identity has zero net species change"
    ):
        raise AssertionError("EI19 must remain energy-only")
    regimes = contract["controlled_elastic_discriminator"]["regimes"]
    expected_t = [600.0, 44350.611537665, 60000.0]
    if [entry["Tgas_K"] for entry in regimes] != expected_t:
        raise AssertionError("elastic sign-discriminator temperatures changed")
    constraints = "\n".join(contract["implementation_constraints"])
    for required in (
        "Do not recreate PhysicsFVElectronReactionEnergySource.",
        "EI18 and EI20 remain Stage-5 deferred",
    ):
        if required not in constraints:
            raise AssertionError(f"missing staging constraint: {required}")


def _runtime_checker_production_surface(text):
    """Return runtime-checker source excluding only the negative-control self-test body."""
    tree = ast.parse(text)
    lines = text.splitlines()
    excluded = set()
    found_self_test = False
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "runtime_checker_self_test":
            found_self_test = True
            if node.end_lineno is None:
                raise AssertionError("runtime checker self-test has no AST end line")
            excluded.update(range(node.lineno - 1, node.end_lineno))
    if not found_self_test:
        raise AssertionError("runtime checker self-test function missing")
    return "\n".join(line for index, line in enumerate(lines) if index not in excluded)


def _validate_runtime_checker_text(text):
    for required in (
        "PhysicsElectronImpactRateMaterial",
        "ADParsedFunctorMaterial",
        "FVCoupledForce",
        "R_elastic_O2",
        "R_elastic_O",
        "R_excitation_O_4p192",
        "o2_elastic.txt",
        "o_elastic.txt",
        "o_excitation_1s.txt",
        "4.192",
        "bin/physics.py",
    ):
        if required not in text:
            raise AssertionError(f"runtime checker missing required surface: {required}")

    production_text = _runtime_checker_production_surface(text)
    for deferred in ("o_excitation_1d.txt", "R_ion_O", "o_ionization.txt"):
        if deferred in production_text:
            raise AssertionError(f"Stage-5 deferred channel activated: {deferred}")


def _expect_failure(fn, *args):
    try:
        fn(*args)
    except AssertionError:
        return
    raise AssertionError("mutation control unexpectedly passed")


def mutation_self_test():
    header = OWNER_H.read_text()
    source = OWNER_C.read_text()
    _validate_owner_text(header, source)

    _expect_failure(
        _validate_owner_text,
        header,
        source.replace(
            "raw < x.front() || raw > x.back()",
            "raw <= x.front() || raw >= x.back()",
            1,
        ),
    )
    _expect_failure(
        _validate_owner_text,
        header,
        source.replace(
            "return k_raw * (n_e / N_A) * c_target;",
            "return k_raw * n_e * c_target;",
            1,
        ),
    )
    _expect_failure(
        _validate_owner_text,
        header,
        source.replace(
            "addFunctorProperty<ADReal>(",
            "addFunctorProperty<ADReal>(\n      \"duplicate_progress\", [](const auto &, const auto &) -> ADReal { return 0.0; });\n  addFunctorProperty<ADReal>(",
            1,
        ),
    )

    source_path = DATA_DIR / "o2_elastic.txt"
    original = source_path.read_bytes()
    mutated = original.replace(b"5.53E+10", b"5.54E+10", 1)
    if mutated == original:
        raise AssertionError("table mutation setup failed")
    _expect_failure(_validate_table_bytes, mutated, EXPECTED_TABLES["o2_elastic.txt"], "mutated_o2")

    with tempfile.TemporaryDirectory(prefix="e8-static-selftest-") as tmp:
        p = Path(tmp) / "bad_table.txt"
        p.write_bytes(original.replace(b"1.40991", b"1.40990", 1))
        _expect_failure(_validate_table_bytes, p.read_bytes(), EXPECTED_TABLES["o2_elastic.txt"], "bad_domain")

    runtime_text = RUNTIME_CHECKER.read_text()
    _validate_runtime_checker_text(runtime_text)
    insertion = '\nDEFERRED_STAGE5_ACTIVATION = "o_excitation_1d.txt"\n\n'
    marker = "\ndef run_controlled_executable("
    if marker not in runtime_text:
        raise AssertionError("runtime checker mutation marker missing")
    activated_runtime = runtime_text.replace(marker, insertion + "def run_controlled_executable(", 1)
    _expect_failure(_validate_runtime_checker_text, activated_runtime)


def main():
    _validate_contract(json.loads(CONTRACT.read_text()))
    _validate_owner_text(OWNER_H.read_text(), OWNER_C.read_text())
    for filename, spec in EXPECTED_TABLES.items():
        _validate_table_bytes((DATA_DIR / filename).read_bytes(), spec, filename)
    _validate_runtime_checker_text(RUNTIME_CHECKER.read_text())
    mutation_self_test()
    print("E8_ELASTIC_EI19_IMPLEMENTATION_P0_PASS")


if __name__ == "__main__":
    main()
