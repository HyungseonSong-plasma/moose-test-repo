"""Source-provenance and scratch-only cutover gate for issue #402 S6 chemistry.

Archived EI channel assignments are S6 *input evidence*, not an independent
scientific acceptance. P2 uses synthetic kinetic progress; P3 is not run.
"""
from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PILOT = ROOT / "experiments/Issue402_plasma_dsl_g1"
MOD = PILOT / "chemistry/prepare_s6_run_input.py"

spec = importlib.util.spec_from_file_location("issue402_s6_chemistry_prep", MOD)
assert spec and spec.loader
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)

EXPECTED = {
    "417": {
        "EI-02": ("R_EI02", "functor"),
        "EI-17": ("R_EI17", "functor"),
        "EI-415": ("R_EI415", -12.06),
        "EI-401": ("R_EI401", 0),
        "EI-407": ("R_EI407", -0.977),
        "EI-2069": ("R_EI2069", -5.02),
        "H25": ("R_H25", "none"),
        "EI-417": ("R_EI417", -17.0),
    },
    "941": {
        "EI-02": ("R_EI02", "functor"),
        "EI-17": ("R_EI17", "functor"),
        "EI-415": ("R_EI415", -12.06),
        "EI-401": ("R_EI401", 0),
        "EI-407": ("R_EI407", -0.977),
        "EI-2069": ("R_EI2069", -5.02),
        "H25": ("R_H25", "none"),
        "EI-941": ("R_EI941", -13.62),
    }
}


def progress_from_id(reaction_id):
    if reaction_id.startswith("EI-") and reaction_id[3:].isdigit():
        return "R_EI" + reaction_id[3:]
    if reaction_id.startswith("H") and reaction_id[1:].isdigit():
        return "R_H" + reaction_id[1:]
    raise ValueError(reaction_id)


def load(variant):
    common = json.loads((PILOT / "chemistry/oxygen_s6_common.json").read_text())
    chosen = json.loads((PILOT / f"chemistry/oxygen_s6_{variant}.json").read_text())
    return common, chosen


def parse_side(text):
    result = {}
    for term in text.split("+"):
        match = re.fullmatch(r"\s*(?:([1-9][0-9]*)\s*)?([A-Za-z][A-Za-z0-9_]*)\s*", term)
        assert match, term
        result[match.group(2)] = result.get(match.group(2), 0) + int(match.group(1) or 1)
    return result


@pytest.mark.parametrize("variant", ["417", "941"])
def test_s6_channel_id_equation_atom_charge_energy_and_ownership(variant):
    common, chosen = load(variant)
    assert chosen["species"] == {}
    catalogue = {**common["species"], **chosen["species"]}
    equations = {**common["equations"], **chosen["equations"]}
    reactions = common["reactions"] + chosen["reactions"]
    assert len(reactions) == 8
    assert {r["id"] for r in reactions} == set(EXPECTED[variant])
    assert all("progress" not in r for r in reactions)
    assert len({progress_from_id(r["id"]) for r in reactions}) == 8
    assert set(equations) == {r["id"] for r in reactions}
    assert catalogue["e"] == {"elements": {}, "charge_number": -1}
    for r in reactions:
        assert r["progress_units"] == "mol/(m^3 s)"
        assert progress_from_id(r["id"]) == EXPECTED[variant][r["id"]][0]
        assert r.get("provenance", {}).get("archive_layer", "").endswith(".i")
        reactants, products = (parse_side(s) for s in equations[r["id"]].split("->"))
        assert reactants == r["reactants"]
        assert products == r["products"]
        for left in (reactants, products):
            assert all(x in catalogue for x in left)
        for element in ("O",):
            assert sum(catalogue[s]["elements"].get(element, 0)*n
                       for s,n in reactants.items()) == sum(
                           catalogue[s]["elements"].get(element, 0)*n
                           for s,n in products.items())
        assert sum(catalogue[s]["charge_number"]*n for s,n in reactants.items()) == sum(
            catalogue[s]["charge_number"]*n for s,n in products.items())
        delta = r["electron_energy_change_eV"]
        expected = EXPECTED[variant][r["id"]][1]
        if expected == "functor":
            assert delta["model"] == "functor"
            assert delta["name"] == f"signed_delta_epsilon_{r['id'].replace('-', '')}_eV"
        elif expected == "none":
            assert delta == {"model": "none"}
        else:
            assert delta == expected
    sources = {
        r["id"]: r["products"].get("e", 0) - r["reactants"].get("e", 0)
        for r in reactions
    }
    assert sources["EI-415"] == 1 and sources["EI-401"] == -1
    assert sources[f"EI-{variant}"] == 1
    assert sum(sources.values()) == 1
    assert sum(r["electron_energy_change_eV"] for r in reactions
               if isinstance(r["electron_energy_change_eV"], (int,float))) == pytest.approx(
                   -35.057 if variant == "417" else -31.677
               )


@pytest.mark.parametrize("variant", ["417", "941"])
def test_template_uses_single_chemistry_energy_owner_and_signed_elastic_functors(variant):
    text = (PILOT / f"s6_{variant}_chemistry_run.template.i").read_text()
    assert f"oxygen_s6_{variant}.json" in text
    assert "oxygen_s6_common.json" in text
    assert text.count("[Chemistry]") == 1
    assert text.count("[Continuity]") == 1
    assert text.count("[Energy]") == 1
    assert "variable = log_energy" not in text
    assert "variable = log_e_energy" not in text
    for canonical in ("R_EI02", "R_EI17", "R_EI415"):
        assert f"property_name = {canonical}" in text
    assert "block = plasma" in text
    assert "fem_charge_numbers" not in text
    assert "fvm_charge_numbers" not in text
    for tag in ("EI02", "EI17"):
        assert f"property_name = signed_delta_epsilon_{tag}_eV" in text
    assert text.count("expression = '-loss'") == 2
    assert "rf_heating_material" not in text  # Existing Native RF owner remains
    fixture = (PILOT / f"chemistry_s6_{variant}_catalogue_p2.i").read_text()
    assert "SYNTHETIC" in fixture
    assert f"oxygen_s6_{variant}.json" in fixture
    runner = (PILOT / "run_native_binding_smoke.sh").read_text()
    assert f"chemistry_s6_" in runner


def fake_layer(removals):
    text = "[FunctorMaterials]\n"
    # Deliberately reuse a name as a FunctorMaterial, matching the EI17 archive.
    for name, (_variable, _fn) in removals.items():
        text += f"  [{name}]\n    type = ADParsedFunctorMaterial\n    property_name = dummy_{name}\n  []\n"
    text += "[]\n[Kernels]\n"
    for name, (variable, fn) in removals.items():
        text += (f"  [{name}]\n    type = FunctorKernel\n    variable = {variable}\n"
                 f"    functor = {fn}\n    functor_on_rhs = true\n    block = plasma\n  []\n")
    text += "  [retain_joule_probe]\n    type = Diffusion\n    variable = log_energy\n  []\n[]\n"
    return text


@pytest.mark.parametrize("variant", ["417", "941"])
def test_guarded_scratch_cutover_retains_native_nonchem_operators(tmp_path, variant):
    removals = {**helper.BASE_REMOVE, **helper.VARIANT_REMOVE[variant]}
    ordered = list(removals) + [f"other_{i}.i" for i in range(10-len(removals))]
    assert len(ordered) == 10
    ordered.append("migrated_continuity.i")
    for basename in ordered[:-1]:
        (tmp_path / basename).write_text(fake_layer(removals.get(basename, {})))
    overlay = tmp_path / ordered[-1]
    overlay.write_text("ORIGINAL OVERLAY - DO NOT USE")
    result = helper.prepare(tmp_path, ordered, variant)
    assert result["removed_count"] == 9
    assert result["status"] == "P2_INPUT_PREPARED"
    assert result["native_check_input"] == "NOT_RUN"
    assert result["run"] == "NOT_RUN"
    assert result["science"] == "SCIENCE_HOLD"
    assert overlay.read_text() == (PILOT / f"s6_{variant}_chemistry_run.template.i").read_text()
    for basename, items in removals.items():
        text = (tmp_path / basename).read_text()
        assert "retain_joule_probe" in text
        assert "variable = log_e_energy" in text
        assert "variable = log_energy" not in text
        for name in items:
            assert f"type = ADParsedFunctorMaterial\n    property_name = dummy_{name}" in text
            assert not any(
                m.group("name") == name and "type = FunctorKernel" in m.group("body")
                for m in helper.KERNEL.finditer(text)
            )
    assert (tmp_path / "chemistry/oxygen_s6_common.json").read_bytes() == (
        PILOT / "chemistry/oxygen_s6_common.json").read_bytes()
    assert (tmp_path / f"chemistry/oxygen_s6_{variant}.json").exists()


def test_cutover_rejects_wrong_sign_before_any_write(tmp_path):
    v = "417"
    removals = {**helper.BASE_REMOVE, **helper.VARIANT_REMOVE[v]}
    ordered = list(removals) + [f"other_{i}.i" for i in range(10-len(removals))]
    ordered.append("migrated_continuity.i")
    for basename in ordered[:-1]:
        original = fake_layer(removals.get(basename, {}))
        if basename == "issue477_S2-415_generation_overlay.i":
            original = original.replace("functor_on_rhs = true", "functor_on_rhs = false", 1)
        (tmp_path / basename).write_text(original)
    overlay = tmp_path / ordered[-1]
    overlay.write_text("ORIGINAL")
    with pytest.raises(ValueError, match="source/sign owner differs"):
        helper.prepare(tmp_path, ordered, v)
    assert overlay.read_text() == "ORIGINAL"
    assert not (tmp_path / "chemistry").exists()
