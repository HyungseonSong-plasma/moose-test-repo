"""G1-only S6 Poisson JSON contract: no runtime owners or cutover implied."""
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path

import pytest

from experiments.Issue402_plasma_dsl_g1.chemistry.poisson_contract import (
    BLOCK_EPS, GROUND, SURFACE, PoissonContractError,
    parse_strict_json, validate_poisson,
)

ROOT = Path(__file__).resolve().parents[1]
CHEM = ROOT / "experiments/Issue402_plasma_dsl_g1/chemistry"


def case_json(case):
    return CHEM / f"unified_s6_{case}_newonly.json"


@pytest.mark.parametrize("case", ("417", "941"))
def test_unified_json_g1_source_and_sha_are_exact(case):
    content = case_json(case).read_bytes()
    doc = parse_strict_json(content)
    validate_poisson(doc)
    assert doc["poisson"]["relative_permittivity"] == BLOCK_EPS
    assert tuple(doc["poisson"]["boundaries"]["ground"]) == GROUND
    assert doc["poisson"]["boundaries"]["surface_charge"] == SURFACE
    assert "diffusivity_material" not in json.dumps(doc["poisson"])
    assert "source_block" not in json.dumps(doc["poisson"])
    generator = (CHEM / "prepare_s6_newonly.py").read_text()
    assert hashlib.sha256(content).hexdigest() in generator
    assert "PIN_HEAD = \"9c15a4f0e2cf8042cb0d4b2f18af31511021d168\"" in generator
    # G1 is DATA/PARSER ONLY. Generating a second Poisson owner is G4/G5.
    template = (CHEM.parent / f"issue633_newonly_s6_{case}_continuity.template.i").read_text()
    assert "[Poisson]" not in template


@pytest.mark.parametrize("case", ("417", "941"))
def test_legacy_hybrid_json_has_no_poisson_cutover(case):
    old = json.loads((CHEM / f"unified_s6_{case}.json").read_text())
    assert "poisson" not in old


@pytest.mark.parametrize("change,error", [
    (lambda d: d.pop("poisson"), "POISSON_ROOT_KEYS_INVALID"),
    (lambda d: d["poisson"].__setitem__("source_block", "plasma"), "POISSON_FIELDS_INVALID"),
    (lambda d: d["poisson"]["relative_permittivity"].pop("coil3"), "POISSON_EPS_BLOCKS_INVALID"),
    (lambda d: d["poisson"]["relative_permittivity"].__setitem__("coil4", 1), "POISSON_EPS_BLOCKS_INVALID"),
    (lambda d: d["poisson"]["relative_permittivity"].__setitem__("cover", -3.6), "POISSON_EPS_VALUE_INVALID"),
    (lambda d: d["poisson"]["relative_permittivity"].__setitem__("cover", float("nan")), "POISSON_EPS_VALUE_INVALID"),
    (lambda d: d["poisson"]["relative_permittivity"].__setitem__("vacuum", True), "POISSON_EPS_VALUE_INVALID"),
    (lambda d: d["poisson"]["relative_permittivity"].__setitem__("wafer", 13), "POISSON_EPS_VALUE_INVALID"),
    (lambda d: d["poisson"]["boundaries"]["ground"].append("inlet"), "POISSON_GROUND_BOUNDARIES_INVALID"),
    (lambda d: d["poisson"]["boundaries"]["ground"].pop(), "POISSON_GROUND_BOUNDARIES_INVALID"),
    (lambda d: d["poisson"]["boundaries"]["ground"].__setitem__(0, "unknown_wall"), "POISSON_GROUND_BOUNDARIES_INVALID"),
    (lambda d: d["poisson"]["boundaries"].__setitem__("ground_boundaries", []), "POISSON_BOUNDARY_FIELDS_INVALID"),
    (lambda d: d["poisson"]["boundaries"]["surface_charge"].__setitem__("plasma_wafer", "sigma_s"), "POISSON_SURFACE_CHARGE_INVALID"),
    (lambda d: d["poisson"]["boundaries"]["surface_charge"].pop("plasma_cover"), "POISSON_SURFACE_CHARGE_INVALID"),
    (lambda d: d["species"]["Om"].__setitem__("charge_number", 1), "POISSON_CHARGED_SPECIES_SIGNS_INVALID"),
])
def test_g1_mutations_fail_closed(change, error):
    document = parse_strict_json(case_json("417").read_bytes())
    broken = deepcopy(document)
    change(broken)
    with pytest.raises(PoissonContractError, match=error):
        validate_poisson(broken)


@pytest.mark.parametrize("raw,error", [
    ('{"poisson":{}, "poisson":{}}', "POISSON_JSON_DUPLICATE_KEY"),
    ('{"poisson":{"boundaries":{"ground":[],"ground":[]}}}', "POISSON_JSON_DUPLICATE_KEY"),
    ('{"poisson":{"relative_permittivity":{"cover":NaN}}}', "POISSON_JSON_NONFINITE"),
    ('{"poisson":{"relative_permittivity":{"cover":Infinity}}}', "POISSON_JSON_NONFINITE"),
    ('{"poisson":', "POISSON_JSON_SYNTAX_INVALID"),
])
def test_json_parser_does_not_silently_normalize_bad_input(raw, error):
    with pytest.raises(PoissonContractError, match=error):
        parse_strict_json(raw)


def test_cpp_parser_contract_is_record_only_not_activated():
    header = (ROOT / "physics_app/include/physics/plasma/Chemistry.h").read_text()
    source = (ROOT / "physics_app/src/physics/plasma/Chemistry.C").read_text()
    for token in (
        "struct PoissonRecord", "relative_permittivity", "ground_boundaries",
        "surface_charge", "const PoissonRecord * poisson() const",
    ):
        assert token in header, token
    for token in ("parsePoissonRecord", "verifyUniquePoissonJsonKeys",
                  "POISSON_REQUIRES_SINGLE_UNIFIED_JSON",
                  "POISSON_EPS_BLOCKS_INVALID", "POISSON_SURFACE_CHARGE_INVALID"):
        assert token in source, token
    assert 'params.set<MooseFunctorName>("surface_charge")' not in source
