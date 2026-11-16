"""Reproduce the real S6 source-owner cutover before an expensive native build.

This P0 test uses the frozen, prebuilt C0 native base and the exact archived
electron-lookup conversion. No private rate files and no solver are required.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import re
import sys

import pytest

PILOT = Path(__file__).resolve().parents[1] / "experiments/Issue402_plasma_dsl_g1"
sys.path.insert(0, str(PILOT))
from chemistry.prepare_hybrid_json_s6 import (
    N_A, PINNED_INITIAL_LOG, NATIVE_COEFFICIENT_RENAME,
    migrate_exact_s6_fem_sheath, prepare, retire
)
from chemistry.prepare_s6_run_input import (
    canonicalize_staged_electron_lookup, canonicalize_staged_wall_inputs
)


def canonical_staged_base() -> str:
    """Reproduce exactly the relevant old C/D type and state name migrations."""
    original = (PILOT / "native/s6_c0_physics_base_no_d1.i").read_text()
    replacements = {
        "log_ne": "log_e",
        "log_ni": "log_O2p",
        "log_nm": "log_Om",
        "log_nop": "log_Op",
        "log_energy": "log_e_energy",
        "mean_en_solved": "e_energy_eV",
        "PhysicsElectronMeanEnergyMaterial": "ElectronEnergyMaterial",
        "PhysicsFEMLogMolarTimeDerivative": "FEMLogMolarTimeDerivative",
        "PhysicsFEMLogMolarDriftDiffusion": "FEMLogMolarDriftDiffusion",
        "PhysicsFEMLogMolarElectronJouleHeating": "FEMLogMolarElectronJouleHeating",
    }
    converted, owner = canonicalize_staged_electron_lookup(
        {Path("synthetic_canonical_s6_base.i"): original}
    )
    assert owner["to_type"] == "DDTransportMaterial"
    converted, wall = canonicalize_staged_wall_inputs(converted)
    assert wall["owner_count"] == 4
    source = converted[Path("synthetic_canonical_s6_base.i")]
    for old, new in replacements.items():
        source = re.sub(r"(?<![A-Za-z0-9_])" + re.escape(old) +
                        r"(?![A-Za-z0-9_])", new, source)
    return source


def prepare_scratch(tmp_path: Path, case: str, *,
                    damage_energy_ic: bool = False) -> tuple[Path, list[str], str]:
    stage = tmp_path / "experiments" / "Issue395_powered_chemistry_ladder"
    stage.mkdir(parents=True)
    source = canonical_staged_base()
    if damage_energy_ic:
        source = source.replace(
            "initial_condition = -18.829829186913098",
            "initial_condition = -18.829829186913097",
            1,
        )
    names = ["synthetic_canonical_s6_base.i"] + [
        f"unused_native_layer_{i}.i" for i in range(1, 10)
    ] + ["migrated_continuity.i"]
    (stage / names[0]).write_text(source)
    for name in names[1:-1]:
        (stage / name).write_text("# Historical untouched Native layer\n")
    (stage / names[-1]).write_text(
        (PILOT / f"s6_{case}_chemistry_run.template.i").read_text()
    )
    (stage / "chemistry").mkdir()
    for file in ("oxygen_s6_common.json", f"oxygen_s6_{case}.json"):
        (stage / "chemistry" / file).write_bytes(
            (PILOT / "chemistry" / file).read_bytes()
        )
    table = stage.parent / "Issue91_real_qvt_r3/r3_e0/electron_moments.txt"
    table.parent.mkdir(parents=True)
    table.write_text("# public transport fixture path presence (not a solver table)\n")
    return stage, names, source


@pytest.mark.parametrize("case", ["417", "941"])
def test_approved_hybrid_owner_cutover_is_exact_and_native_fallback_untouched(
    tmp_path: Path, case: str
) -> None:
    stage, names, original = prepare_scratch(tmp_path, case)
    assert PINNED_INITIAL_LOG["log_e_energy"] == "-18.829829186913098"
    assert isinstance(PINNED_INITIAL_LOG["log_e_energy"], str)
    report = prepare(stage, names, case)
    assert report["removed_generated_owner_count"] == 10
    gas = report["root_gas_state_pressure_initial_condition"]
    assert gas["status"] == "NATIVE_PRESSURE_SOLVED_ROOT_PRESSURE_INITIAL_CONDITION"
    assert gas["pressure_initial_pa"] == 1.333223684
    assert gas["temperature_constant_k"] == 300
    assert gas["pressure_solver_variable"] == "pressure"
    assert gas["pressure_runtime_functor"] == "pressure"
    assert gas["temperature_runtime_functor"] == "temperature"
    assert gas["external_pressure_functor_created"] is False
    assert gas["native_pressure_initial_retired"] is True
    assert gas["native_p_fixed_temperature_fixed_retired"] is True
    assert gas["root_outlet_parameter_coupled"] is True
    assert report["integrated_mechanism_json"] == f"unified_s6_{case}.json"
    assert report["integrated_species_count"] == 7
    assert report["integrated_reaction_count"] == 8
    rename = report["native_species_coefficient_binding_migration"]
    assert rename["old_to_species_names"] == NATIVE_COEFFICIENT_RENAME
    assert rename["physics_equations_unchanged"] is True
    assert rename["constant_values_unchanged"] is True
    assert all(v >= 2 for v in rename["substitution_counts"].values())
    assert report["rebound_native_sheath_bc_count"] == 8
    assert sum(x["new_type"] == "FEMElectronSheathBC"
               for x in report["rebound_native_sheath_bcs"]) == 4
    assert sum(x["new_type"] == "FEMElectronEnergySheathBC"
               for x in report["rebound_native_sheath_bcs"]) == 4
    assert set(report["changed_staged_layers"]) == {
        names[0], names[-1]
    }
    assert report["native_owner_preservation"] == (
        "NATIVE_EQUATIONS_UNCHANGED_WITH_ROOT_PRESSURE_IC_AND_SPECIES_FUNCTORS"
    )
    data = json.loads((stage / f"unified_s6_{case}.json").read_text())
    assert set(data) == {"species", "equations", "reactions"}
    assert set(data["species"]) == {"e", "O2", "O", "O2p", "Om", "Op", "O2a"}
    assert set(data["equations"]) == {
        "EI-02", "EI-17", "EI-415", "EI-401", "EI-407", "EI-2069",
        "H25", f"EI-{case}",
    }
    assert len(data["reactions"]) == len(data["equations"]) == 8
    assert [reaction["id"] for reaction in data["reactions"]][-1] == f"EI-{case}"
    assert data["species"]["e"]["transport_coef"] == "lookup"
    assert data["species"]["e"]["energy_transport_coef"] == "fluid"
    assert data["species"]["e"]["table_units"] == "reduced"
    assert data["species"]["e"]["pressure"] == "pressure"
    assert data["species"]["e"]["gas_temperature"] == "temperature"
    assert "T_g_fixed" not in json.dumps(data)
    assert '"pressure": "p"' not in json.dumps(data)
    assert data["species"]["e"]["bounds_policy"] == "clamp"
    for species in ("O2p", "Om", "Op"):
        assert data["species"][species]["transport_coef"] == "functor"
        assert data["species"][species]["mobility"] == f"{species}_mobility"
        assert data["species"][species]["diffusivity"] == f"{species}_diffusivity"
    assert all(data["species"][name]["initial_number_density"] > 0
               for name in ("e", "O2p", "Om", "Op"))
    assert report["hybrid_json_sha256"] == report["integrated_json_source_sha256"]
    base = (stage / names[0]).read_text()
    assert "[log_e_energy]" not in base
    assert "[electron_transport]" not in base
    assert "[energy_time]" not in base
    assert base.count("type = FEMElectronSheathBC") == 4
    assert base.count("type = FEMElectronEnergySheathBC") == 4
    assert "PhysicsFEMLogMolarElectronFieldLimitedFluxBC" not in base
    assert "PhysicsFEMLogMolarElectronEnergyFieldLimitedFluxBC" not in base
    assert "wall_number_flux = e_wall_number_flux" in base
    assert "prop_names = 'O2p_mobility O2p_diffusivity Om_mobility Om_diffusivity Op_mobility Op_diffusivity carrier_one'" in base
    assert "prop_values = '10 0.25851999786435537 10 0.25851999786435537 10 0.25851999786435537 1.0'" in base
    assert "[pressure]\n    type = INSFVPressureVariable" in base
    assert "initial_condition = 1.333223684" not in base
    assert "function = ${Physics/Plasmas/pressure}" in base
    assert "pressure = pressure" in base
    assert "temperature = temperature" in base
    assert "T_g_fixed" not in base and "p_fixed" not in base
    for original_name, canonical_name in NATIVE_COEFFICIENT_RENAME.items():
        assert original_name in original
        assert original_name not in base
        assert canonical_name in base
    assert "mobility = Op_mobility" in base
    assert "coeff = Op_diffusivity" in base
    for native in ("[potential]", "[phi_diffusion]", "[phi_source]",
                   "[sigma_surface_current]", "[electron_wall_flux]",
                   "[ion_molar_density]", "[ni_time]"):
        assert native in base and native in original
    for name in names[1:-1]:
        assert (stage / name).read_text() == "# Historical untouched Native layer\n"
    overlay = (stage / names[-1]).read_text()
    assert f"files = 'unified_s6_{case}.json'" in overlay
    assert "pressure = 1.333223684" in overlay
    assert "temperature = 300" in overlay
    assert "state_model = ideal_gas" in overlay
    assert "oxygen_s6_common.json" not in overlay
    assert "initial_molar_energy_density_eV" in overlay


def test_hybrid_rejects_changed_archived_ic_before_any_file_write(
    tmp_path: Path,
) -> None:
    stage, names, modified = prepare_scratch(
        tmp_path, "417", damage_energy_ic=True
    )
    overlay = (stage / names[-1]).read_bytes()
    with pytest.raises(ValueError, match="HYBRID_OWNER_IDENTITY_Variables_log_e_energy"):
        prepare(stage, names, "417")
    assert (stage / names[0]).read_text() == modified
    assert (stage / names[-1]).read_bytes() == overlay
    assert not (stage / "unified_s6_417.json").exists()


def test_hybrid_rejects_changed_archived_sheath_flux_before_write(tmp_path: Path):
    stage, names, original = prepare_scratch(tmp_path, "941")
    mutated = original.replace(
        "wall_number_flux = e_wall_number_flux",
        "wall_number_flux = unverified_wall_flux",
        1,
    )
    assert mutated != original
    (stage / names[0]).write_text(mutated)
    preserved_overlay = (stage / names[-1]).read_bytes()
    with pytest.raises(ValueError, match="HYBRID_SHEATH_BC_IDENTITY_"):
        prepare(stage, names, "941")
    assert (stage / names[0]).read_text() == mutated
    assert (stage / names[-1]).read_bytes() == preserved_overlay
    assert not (stage / "unified_s6_417.json").exists()


def test_hybrid_rejects_changed_native_ion_constant_before_write(tmp_path: Path):
    stage, names, original = prepare_scratch(tmp_path, "941")
    mutated = original.replace(
        "10 0.25851999786435537 10 0.25851999786435537",
        "10 0.25851999786435537 11 0.25851999786435537",
        1,
    )
    assert mutated != original
    (stage / names[0]).write_text(mutated)
    overlay = (stage / names[-1]).read_bytes()
    with pytest.raises(ValueError, match="HYBRID_NATIVE_ION_CONSTANTS_SIGNATURE_CHANGED"):
        prepare(stage, names, "941")
    assert (stage / names[0]).read_text() == mutated
    assert (stage / names[-1]).read_bytes() == overlay
    assert not (stage / "unified_s6_941.json").exists()


def test_case_reactions_are_not_cross_mixed(tmp_path: Path):
    stage, names, source = prepare_scratch(tmp_path, "417")
    swapped = (PILOT / "chemistry/oxygen_s6_941.json").read_bytes()
    (stage / "chemistry/oxygen_s6_417.json").write_bytes(swapped)
    with pytest.raises(ValueError, match="HYBRID_INTEGRATED_VARIANT_REACTION_IDENTITY_CHANGED"):
        prepare(stage, names, "417")
    assert (stage / names[0]).read_text() == source
    assert not (stage / "unified_s6_417.json").exists()


def test_hybrid_rejects_changed_archived_pressure_ic_before_writing(tmp_path: Path):
    stage, names, original = prepare_scratch(tmp_path, "417")
    mutated = original.replace("initial_condition = 1.333223684",
                               "initial_condition = 1.333223685", 1)
    assert mutated != original
    (stage / names[0]).write_text(mutated)
    overlay = (stage / names[-1]).read_bytes()
    with pytest.raises(ValueError, match="HYBRID_ROOT_PRESSURE_VARIABLE_IC_IDENTITY_CHANGED"):
        prepare(stage, names, "417")
    assert (stage / names[0]).read_text() == mutated
    assert (stage / names[-1]).read_bytes() == overlay
    assert not (stage / "unified_s6_417.json").exists()


def test_hybrid_rejects_changed_archived_pressure_outlet(tmp_path: Path):
    stage, names, original = prepare_scratch(tmp_path, "941")
    mutated = original.replace("    function = 1.333223684",
                               "    function = 1.333223685", 1)
    assert mutated != original
    (stage / names[0]).write_text(mutated)
    with pytest.raises(ValueError, match="HYBRID_ROOT_PRESSURE_OUTLET_BC_IDENTITY_CHANGED"):
        prepare(stage, names, "941")
    assert (stage / names[0]).read_text() == mutated
    assert not (stage / "unified_s6_941.json").exists()


def staged_chemistry_handoff(tmp_path: Path, case: str):
    """Simulate exactly Chemistry's four IC removals and 8 BC type rebinds."""
    stage, names, original = prepare_scratch(tmp_path, case)
    source, sheath_receipts = migrate_exact_s6_fem_sheath(original)
    retired = []
    densities = {}
    for species, var in (("e", "log_e"), ("O2p", "log_O2p"),
                         ("Om", "log_Om"), ("Op", "log_Op")):
        expected = {"initial_condition": PINNED_INITIAL_LOG[var], "block": "plasma"}
        if species == "e":
            expected.update(family="LAGRANGE", order="FIRST")
        else:
            expected["type"] = "MooseVariableFVReal"
        source, receipt = retire(source, "Variables", var, expected)
        retired.append(receipt)
        densities[species] = math.exp(float(PINNED_INITIAL_LOG[var])) * N_A
    (stage / names[0]).write_text(source)
    common_path = stage / "chemistry/oxygen_s6_common.json"
    common = json.loads(common_path.read_text())
    for species, density in densities.items():
        common["species"][species]["initial_number_density"] = density
    common_path.write_text(json.dumps(common, indent=2, sort_keys=True) + "\n")
    handoff = {
        "scratch_json_initial_cutover": {
            "status": "SCRATCH_ONLY_FOUR_NATIVE_INITIAL_OWNERS_TO_JSON",
            "owner_count": 4,
            "owners": retired,
            "densities_per_m3": densities,
            "native_initial_after_sha256": hashlib.sha256(source.encode()).hexdigest(),
        },
        "scratch_sheath_bc_cutover": {
            "status": "SCRATCH_ONLY_EIGHT_REGISTERED_SHEATH_TYPES",
            "owner_count": 8,
            "owners": sheath_receipts,
        },
    }
    return stage, names, handoff


@pytest.mark.parametrize("case", ["417", "941"])
def test_hybrid_consumes_chemistry_handoff_without_retirment_twice(
    tmp_path: Path, case: str
) -> None:
    stage, names, handoff = staged_chemistry_handoff(tmp_path, case)
    report = prepare(stage, names, case, chemistry_cutover=handoff)
    assert report["removed_generated_owner_count"] == 10
    assert report["rebound_native_sheath_bc_count"] == 8
    assert report["integrated_mechanism_json"] == f"unified_s6_{case}.json"
    text = (stage / names[0]).read_text()
    assert "[log_e]" not in text
    assert "[log_e_energy]" not in text
    assert text.count("type = FEMElectronSheathBC") == 4
    assert text.count("type = FEMElectronEnergySheathBC") == 4
    assert "P3" not in report or report.get("science_acceptance") == "HOLD"


@pytest.mark.parametrize("mutant", [
    "missing_ic_receipt", "wrong_receipt_sha", "wrong_bc_type",
    "wrong_bc_variable", "wrong_bc_boundary", "wrong_wall_functor",
    "wrong_json_initial", "wrong_reaction_variant",
])
def test_hybrid_chemistry_handoff_mutants_fail_closed_before_any_write(
    tmp_path: Path, mutant: str
) -> None:
    stage, names, handoff = staged_chemistry_handoff(tmp_path, "417")
    first = stage / names[0]
    common = stage / "chemistry/oxygen_s6_common.json"
    variant = stage / "chemistry/oxygen_s6_417.json"
    if mutant == "missing_ic_receipt":
        handoff["scratch_json_initial_cutover"]["owners"].pop()
    elif mutant == "wrong_receipt_sha":
        handoff["scratch_json_initial_cutover"]["native_initial_after_sha256"] = "0" * 64
    elif mutant in {"wrong_bc_type", "wrong_bc_variable",
                    "wrong_bc_boundary", "wrong_wall_functor"}:
        raw = first.read_text()
        old, new = {
            "wrong_bc_type": ("type = FEMElectronSheathBC", "type = INVALIDSheathBC"),
            "wrong_bc_variable": ("variable = log_e", "variable = wrong_e"),
            "wrong_bc_boundary": ("boundary = 'plasma_cover'", "boundary = 'plasma_wrong'"),
            "wrong_wall_functor": ("wall_number_flux = e_wall_number_flux",
                                   "wall_number_flux = invalid_wall_flux"),
        }[mutant]
        assert old in raw
        first.write_text(raw.replace(old, new, 1))
    elif mutant == "wrong_json_initial":
        data = json.loads(common.read_text())
        data["species"]["e"]["initial_number_density"] *= 2
        common.write_text(json.dumps(data))
    elif mutant == "wrong_reaction_variant":
        variant.write_bytes((PILOT / "chemistry/oxygen_s6_941.json").read_bytes())
    frozen = {name: (stage / name).read_bytes() for name in names}
    with pytest.raises(ValueError, match="HYBRID_"):
        prepare(stage, names, "417", chemistry_cutover=handoff)
    assert all((stage / name).read_bytes() == original for name, original in frozen.items())
    assert not (stage / "unified_s6_417.json").exists()


# Wave1-P3-B: regressions observed in the source-bound 2026-11-16 replay
# #43892446918. These P0 tests never start a Native solver or GitHub Actions.
# The entrypoint-wiring test intentionally FAILS against #578@5d15c405
# until the independently owned chemistry_cutover handoff change lands.


def _p3_runner_run_ast():
    """Parse the real expensive entrypoint without importing its runtime deps."""
    import ast

    source = (PILOT / "run_canonical_s6_p3_once.py").read_text()
    tree = ast.parse(source)
    functions = [n for n in tree.body
                 if isinstance(n, ast.FunctionDef) and n.name == "run"]
    assert len(functions) == 1
    return functions[0]


def test_p3_chemistry_handoff_is_forwarded_to_hybrid_entrypoint():
    """Catch the exact omission that broke BOTH 400 W/100 us P3 cases."""
    import ast

    runner = _p3_runner_run_ast()
    assignments = [n for n in ast.walk(runner)
                   if isinstance(n, ast.Assign)]
    chemistry = [n for n in assignments
                 if any(isinstance(t, ast.Name) and t.id == "cutover"
                        for t in n.targets)
                 and isinstance(n.value, ast.Call)
                 and isinstance(n.value.func, ast.Name)
                 and n.value.func.id == "prepare"]
    assert len(chemistry) == 1, "P3_CHEMISTRY_HANDOFF_RECEIPT_MISSING"

    hybrid = [n for n in assignments
              if any(isinstance(t, ast.Name) and t.id == "hybrid"
                     for t in n.targets)
              and isinstance(n.value, ast.Call)
              and isinstance(n.value.func, ast.Name)
              and n.value.func.id == "prepare_hybrid"]
    assert len(hybrid) == 1, "P3_HYBRID_CALL_MISSING_OR_AMBIGUOUS"
    kwargs = {k.arg: k.value for k in hybrid[0].value.keywords}
    assert chemistry[0].lineno < hybrid[0].lineno
    assert "chemistry_cutover" in kwargs, (
        "P3_HYBRID_CHEMISTRY_HANDOFF_MISSING: "
        "would retire Variables/log_e twice; see run 43892446918"
    )
    assert isinstance(kwargs["chemistry_cutover"], ast.Name)
    assert kwargs["chemistry_cutover"].id == "cutover", (
        "P3_HYBRID_HANDOFF_MUST_USE_EXACT_CHEMISTRY_RECEIPT"
    )


@pytest.mark.parametrize("case", ("417", "941"))
def test_p3_missing_handoff_rejects_double_owner_retirement_without_write(
    tmp_path: Path, case: str,
) -> None:
    """Chemistry already retired log_e; calling Hybrid without a receipt fails."""
    stage, names, handoff = staged_chemistry_handoff(tmp_path, case)
    initial = {name: (stage / name).read_bytes() for name in names}
    with pytest.raises(ValueError, match=r"HYBRID_OWNER_COUNT_Variables_log_e: 0"):
        prepare(stage, names, case)
    assert all((stage / name).read_bytes() == raw
               for name, raw in initial.items())
    assert not (stage / f"unified_s6_{case}.json").exists()

    # The already-established safe handoff must succeed on untouched scratch.
    result = prepare(stage, names, case, chemistry_cutover=handoff)
    assert result["removed_generated_owner_count"] == 10
    assert result["rebound_native_sheath_bc_count"] == 8
    assert result["integrated_mechanism_json"] == f"unified_s6_{case}.json"


@pytest.mark.parametrize("case", ("417", "941"))
def test_p3_corrupted_chemistry_receipt_sha_rejected_before_file_write(
    tmp_path: Path, case: str,
) -> None:
    """A forged source-handoff SHA must not bypass ownership verification."""
    stage, names, handoff = staged_chemistry_handoff(tmp_path, case)
    handoff["scratch_json_initial_cutover"]["native_initial_after_sha256"] = "0" * 64
    initial = {name: (stage / name).read_bytes() for name in names}
    with pytest.raises(ValueError, match="HYBRID_CHEMISTRY_INITIAL_HANDOFF_MISMATCH"):
        prepare(stage, names, case, chemistry_cutover=handoff)
    assert all((stage / name).read_bytes() == raw
               for name, raw in initial.items())
    assert not (stage / f"unified_s6_{case}.json").exists()


def test_p3_wrong_source_sha_stops_before_any_native_operation():
    """Execute only the real AST's first HEAD guard against a wrong SHA.

    Neither the P3 function nor a Native binary is imported or run.
    """
    import ast
    from types import SimpleNamespace

    runner = _p3_runner_run_ast()
    outer = [n for n in runner.body if isinstance(n, ast.Try)]
    assert len(outer) == 1
    check = outer[0].body[0]
    assert isinstance(check, ast.If), "P3_EXACT_HEAD_CHECK_NOT_FIRST"
    assert "option.git_head(ROOT) != expected_head" in ast.unparse(check.test)
    assert "P3_EXACT_MERGED_SOURCE_MISMATCH" in ast.unparse(check)
    downstream = [n.lineno for n in ast.walk(runner)
                  if isinstance(n, ast.Call) and
                  ((isinstance(n.func, ast.Attribute) and
                    n.func.attr in {"check_source", "run_one", "run"})
                   or (isinstance(n.func, ast.Name) and
                       n.func.id in {"prepare", "prepare_hybrid"}))]
    assert downstream and check.lineno < min(downstream)

    one_guard = ast.fix_missing_locations(
        ast.Module(body=[check], type_ignores=[]))
    calls = []
    actual = "a" * 40
    requested = "b" * 40
    option = SimpleNamespace(git_head=lambda root: calls.append(root) or actual)
    with pytest.raises(ValueError, match="P3_EXACT_MERGED_SOURCE_MISMATCH"):
        exec(compile(one_guard, "<p3-exact-source-guard>", "exec"),
             {"option": option, "ROOT": Path("."), "expected_head": requested})
    assert len(calls) == 1


def test_p3_manual_workflow_source_sha_gate_precedes_checkout():
    """Wrong workflow_dispatch source_sha cannot reach OCI or Native P3."""
    source = (PILOT.parents[1] / ".github/workflows/"
              "issue541-arch-s6-p3-p4-replay.yml").read_text()
    event_gate = 'test "$GITHUB_EVENT_NAME" = "workflow_dispatch"'
    approval_gate = (
        'test "$APPROVAL" = "ISSUE541_S6_400W_100US_BOTH_CASES_APPROVED"'
    )
    sha_gate = 'test "$REQUESTED_SHA" = "$GITHUB_SHA"'
    checkout = "uses: actions/checkout@"
    for literal in (event_gate, approval_gate, sha_gate, checkout):
        assert source.count(literal) >= 1, "P3_WORKFLOW_MISSING_" + literal
    assert source.index(event_gate) < source.index(approval_gate)
    assert source.index(approval_gate) < source.index(sha_gate)
    assert source.index(sha_gate) < source.index(checkout)
    assert "      source_sha:" in source
    assert "        required: true" in source
