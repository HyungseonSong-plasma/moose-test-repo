"""Issue477 S5: exact 4+4 one-channel chemistry and immutable S4 provenance."""
from pathlib import Path

import pytest

from experiments.Issue477_electron_shape import prepare_s4_o2_consumers as s5


def test_eight_exact_isolated_cases_and_two_frozen_parents():
    assert set(s5.CASES) == {
        "S5-417-412", "S5-417-407", "S5-417-2069", "S5-417-H25",
        "S5-941-412", "S5-941-407", "S5-941-2069", "S5-941-H25",
    }
    assert {k: v["extra"] for k, v in s5.PARENTS.items()} == {
        "417": "EI-417", "941": "EI-941"}
    assert s5.PARENTS["417"]["manifest_sha256"] == (
        "39c6a12e845e2752b968d2e9de7dcbdd743744fd3bc09732c9ea202e912edf09")
    assert s5.PARENTS["941"]["manifest_sha256"] == (
        "d8f996405e831f94a0664f1912bff77f30b8a3318192c7848bb2b69a32a30248")
    assert len(s5.BASE_OWNERS) == 4
    assert s5.EXTRAS["412"]["rate_sha256"] == (
        "53bfaf78997b1992a5e9d34c014976b3a451ea2198b2acb2ed15505caadb1137")
    assert s5.EXTRAS["407"]["rate_sha256"] == (
        "2565be45b9a13204583b6714a7d1b581cf29c157c78ac502d665649e4065b359")
    assert s5.EXTRAS["2069"]["rate_sha256"] == (
        "5eba74c1870e0635a3e316e143961e9f04e259675ddad00fd8653de28980644a")
    assert s5.EXTRAS["H25"]["rate_sha256"] is None
    assert s5.EXTRAS["2069"]["o2_ground_delta"] == 0


def test_pinned_original_100node_lookup_guards(tmp_path):
    p = tmp_path / "rate.txt"
    p.write_text("".join(f"{i:.1f} {i*.01:.3e}\n" for i in range(1, 101)))
    assert len(s5.rate_grid(p)) == 100
    p.write_text("".join(f"{i:.1f} {i*.01:.3e}\n" for i in range(1, 100)))
    with pytest.raises(ValueError, match="100"):
        s5.rate_grid(p)
    p.write_text("".join(f"{i:.1f} {-.01 if i==10 else i*.01:.3e}\n" for i in range(1, 101)))
    with pytest.raises(ValueError, match="invalid"):
        s5.rate_grid(p)


@pytest.mark.parametrize("case", sorted(s5.CASES))
def test_six_owner_guard_and_no_unlisted_chemistry(case, tmp_path):
    p, e = s5.CASES[case]
    owner = s5.EXTRAS[e]["owner"]
    sources = [
        "# chemistry-off C0\n", "# RF parent\n",
        "reaction_progress = R_elastic_O2\n",
        "reaction_progress = R_elastic_O\n",
        "reaction_progress = R_ion_O2\n",
        "reaction_progress = R_EI401\n",
        f"reaction_progress = R_EI{p}\n",
    ]
    if e == "H25":
        extra = (
            "property_name = R_H25\nvariable = log_nop\nvariable = log_ni\n"
            "variable = w_O\nvariable = p\nexpression = '-R'\n"
            "expression = 'R'\n"
            "expression = '1.204428152e7*(300.0/tg)^0.4*cp*c2'\n"
        )
    else:
        extra = (
            "type = PhysicsElectronImpactRateMaterial\n"
            f"rate_table_file = 'private_rates/{s5.EXTRAS[e]['rate']}'\n"
            f"reaction_progress = {owner}\nvariable = log_energy\n"
        )
        if e == "412":
            extra += (
                "property_name = S_O2_mass_diss_implicit\nvariable = w_O\n"
                "expression = '-6*R'\n")
        if e == "407":
            extra += (
                "variable = w_O2s\nproperty_name = S_O2_implicit_EI407\n"
                "expression = '-0.977*R'\n")
        if e == "2069":
            extra += (
                "variable = w_O2s\nvariable = w_O\n"
                "expression = '-0.032*R'\nexpression = '0.032*R'\n"
                "expression = '-5.02*R'\n")
    sources.append(extra)
    paths = []
    for i, source in enumerate(sources):
        path = tmp_path / f"{i}.i"
        path.write_text(source)
        paths.append(path)
    s5.validate_inventory(paths, case)
    paths[-1].write_text(extra + "\nreaction_progress = R_EI2259\n")
    with pytest.raises(ValueError, match="ownership"):
        s5.validate_inventory(paths, case)


def test_existing_workflows_have_staged_four_plus_four_gate():
    text = Path(".github/workflows/issue477-s5-o2-consumers-4plus4-delay-once.yml").read_text()
    assert text.count("max-parallel: 4") == 2
    assert "case: [S5-417-412, S5-417-407, S5-417-2069, S5-417-H25]" in text
    assert "case: [S5-941-412, S5-941-407, S5-941-2069, S5-941-H25]" in text
    assert "sleep 600" in text
    assert "needs: delay-gate" in text
    assert "S5-417-" in text and "S5-941-" in text
