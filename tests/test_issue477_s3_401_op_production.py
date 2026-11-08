"""Strict Issue477 S3-415-401 parent and two O+ generator test contracts."""
from pathlib import Path

import pytest

from experiments.Issue477_electron_shape import prepare_s3_401_op_production as m


def test_exact_two_current_oxygen14_channels_on_unchanged_ei401_parent():
    assert m.PARENT == "S3-415-401"
    assert m.BASE_CHANNELS == ("EI-02", "EI-17", "EI-415", "EI-401")
    assert set(m.CASES) == {"S4-401-417", "S4-401-941"}
    assert set(c["reaction"] for c in m.CASES.values()) == {"EI-417", "EI-941"}
    assert set(c["owner"] for c in m.CASES.values()) == {"R_EI417", "R_EI941"}
    assert set(m.PARENT_INPUT_SHA) == {
        "rf_elastic_diss_ion_ei20_ei01_400w_adjacent_sheath_wall_closed_100us_dt1000ns__C0_chemistry_off.i",
        "rf_elastic_multiapp_parent_400w_100us_dt1000ns_overlay.i",
        "o2_elastic_400w_100us_dt1000ns_overlay.i",
        "o_elastic_ei17_400w_100us_dt1000ns_overlay.i",
        "issue477_S2-415_generation_overlay.i",
        "issue477_S3-415-401_extra_overlay.i",
    }
    assert m.PARENT_RUN_ID == 42398716952
    assert m.PARENT_ARTIFACT_ID == 13591493238
    assert m.PARENT_MANIFEST_SHA == "8aa76a8a2fc70801fee70f1dc51850971a41d7cf48f46d090ee6653644e7d202"
    assert m.EEDF_SHA == "35534a522fa48ccb5222339c5040040630eef31e623e1c53f1e1c4540d2d653b"
    assert m.CASES["S4-401-417"]["sha256"] == "4e87121cad771a4ebbe272efa0b9349e527b0de782afc97b3f14556c57fc550d"
    assert m.CASES["S4-401-941"]["sha256"] == "ca10a223d631e04a84464649bac96ba3c7ee4ca157a1127376e04b66781e2adc"


def test_original_lookup_grid_requires_100_strict_monotone_positive_energies(tmp_path):
    p = tmp_path / "private.txt"
    p.write_text("\n".join(f"{i/10:.2f} {i*0.1:.5e}" for i in range(1, 101)))
    assert len(m.rate_grid(p)) == 100
    p.write_text("\n".join(f"{i/10:.2f} {i*0.1:.5e}" for i in range(1, 100)))
    with pytest.raises(ValueError, match="100"):
        m.rate_grid(p)
    p.write_text("\n".join(f"{i/10:.2f} {-1 if i == 20 else i*0.1:.5e}" for i in range(1, 101)))
    with pytest.raises(ValueError, match="Invalid"):
        m.rate_grid(p)


@pytest.mark.parametrize("case", ["S4-401-417", "S4-401-941"])
def test_native_owner_inventory_rejects_missing_or_duplicate_reactions(case, tmp_path):
    base_owners = ["R_elastic_O2", "R_elastic_O", "R_ion_O2", "R_EI401"]
    extra = m.CASES[case]
    src = [
        "# pristine C0 base\n",
        "# pristine RF parent\n",
        f"reaction_progress = {base_owners[0]}\n",
        f"reaction_progress = {base_owners[1]}\n",
        f"reaction_progress = {base_owners[2]}\n",
        f"reaction_progress = {base_owners[3]}\n",
    ]
    if case.endswith("417"):
        s = "functor = S_e_molar_EI417\nv = S_Op_molar_EI417\nexpression = '-17.0*R'\n"
    else:
        s = "functor = S_electron_molar_EI941\nv = S_Op_molar_EI941\nexpression = '-13.62*R'\n"
    s += (
        "type = PhysicsElectronImpactRateMaterial\n"
        f"rate_table_file = 'private_rates/{extra['rate']}'\n"
        f"reaction_progress = {extra['owner']}\n"
        "variable = log_ne\nvariable = log_energy\nvariable = log_nop\n"
        "expression = 'R'\n"
    )
    src.append(s)
    paths=[]
    for i, item in enumerate(src):
        p = tmp_path / f"{i}.i"
        p.write_text(item)
        paths.append(p)
    m.verify_inventory(paths, case)
    paths[-1].write_text(src[-1] + "reaction_progress = R_EI2058\n")
    with pytest.raises(ValueError, match="owners"):
        m.verify_inventory(paths, case)
    paths[-1].write_text(src[-1].replace("variable = log_nop", "variable = log_ni"))
    with pytest.raises(ValueError, match="projection"):
        m.verify_inventory(paths, case)
