"""User-selected EI407/413/414 -> O2(a) state-lumped 400/1000 W case."""
import importlib.util
import json
import math
import re
from pathlib import Path

import pytest

from experiments.Issue395_powered_chemistry_ladder.oxygen_25_stoichiometry_contract import (
    ACTIVE_REACTIONS, REACTIONS, active_audit, stoich
)

ROOT = Path(__file__).resolve().parents[1]
CHEM = ROOT / "experiments" / "Issue395_powered_chemistry_ladder"
SCRIPT = CHEM / "build_lumped_o2a_ei407_413_414.py"
CONFIG = CHEM / "oxygen_icp_operating_200sccm_sticking1.json"


def _load():
    spec = importlib.util.spec_from_file_location("o2a_lumped_builder", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _base():
    return "\n".join(("[w_O2s]", "[log_energy]", "property_name = w_O2_constraint",
                      "property_name = rho_neutral", "property_name = n_e_physical",
                      "mean_energy = mean_en_solved"))


def test_active_chemistry_reuses_tracked_o2a_with_original_inventory():
    assert len(REACTIONS) == 25
    orig = {r[0]: r for r in REACTIONS}
    active = {r[0]: r for r in ACTIVE_REACTIONS}
    assert len(active) == 24 and "936" not in active
    for rid in ("407", "413", "414"):
        assert stoich(active[rid]) == {"O2": -1, "O2a": 1}
    for rid in ("413", "414"):
        assert orig[rid][2] == "e O2star"  # immutable source provenance
    report = active_audit()
    assert report["lumped_O2a_production_reaction_ids"] == ["407", "413", "414"]
    assert report["missing_transport_species"] == []
    assert report["lumped_energy_losses_eV"] == {"407":0.977, "413":8.4, "414":10.0}
    config = json.loads(CONFIG.read_text())
    assert config["rf_targets_w"] == [400, 1000]
    assert config["inlet"]["Q_sccm"] == 200
    assert config["wall"]["research_uniform_sticking"] is True
    policy = config["chemistry"]["lumped_O2a_source"]
    assert policy["solver_product"] == "O2s"
    assert policy["microscopic_branching_validated"] is False
    assert policy["electron_particle_source"] == "zero"


def test_three_owners_one_mass_source_and_individual_energy():
    mod = _load()
    overlay = mod.build(_base(), {407:"private_rates/EI-407_O2_X.txt",
                                  413:"private_rates/EI-413_O2_X.txt",
                                  414:"private_rates/EI-414_O2_X.txt"})
    for rid in (407, 413, 414):
        assert overlay.count(f"reaction_progress = R_EI{rid}") == 1
    assert overlay.count("variable = w_O2s") == 1
    assert "variable = w_O2_constraint" not in overlay
    assert "variable = log_ne" not in overlay
    assert re.search(r"(?m)^\s*variable\s*=\s*w_O\s*$", overlay) is None
    assert "expression = 'a+b+c'" in overlay
    assert "expression = '-0.977*a-8.4*b-10.0*c'" in overlay
    assert "expression = '-0.032*R'" in overlay
    assert overlay.count("variable = log_energy") == 1
    assert "R_EI936" not in overlay
    assert "O2star" not in overlay
    for rates in ((0.02, 0.1, 0.3), (1.0, 0.01, 0.2)):
        total = sum(rates)
        positive = 0.032 * total
        negative = -0.032 * total
        energy = -0.977*rates[0] - 8.4*rates[1] - 10.0*rates[2]
        assert math.isclose(positive+negative, 0, abs_tol=1e-15)
        assert energy < 0


def test_fail_closed_missing_or_duplicate_owners():
    mod = _load()
    with pytest.raises(ValueError, match="duplicate"):
        mod.build(_base()+"\nR_EI407", {407:"a",413:"b",414:"c"})
    with pytest.raises(ValueError, match="exactly"):
        mod.build(_base(), {407:"a",413:"b"})


def test_stage_100point_lookup_tables_in_solver_cwd(tmp_path, monkeypatch):
    mod = _load()
    monkeypatch.chdir(tmp_path)
    incoming = tmp_path / "private_input"
    incoming.mkdir()
    for rid, name in mod.CHANNELS:
        (incoming/name).write_text(
            "# unit is m3/(mol s)\n" +
            "".join(f"{1.5+(36/99)*i:.16g} {1e5+rid+i:.16g}\n" for i in range(100)))
    base = tmp_path / "base.i"
    base.write_text(_base())
    output = tmp_path / "test_case" / "o2a_overlay.i"
    output.parent.mkdir()
    mod.prepare(base, incoming, output)
    t = output.read_text()
    assert "test_case/private_rates/EI-413_O2_X.txt" in t
    assert t.count("reaction_progress = R_EI413") == 1
    assert len(list((output.parent/"private_rates").glob("*.txt"))) == 3

    (incoming/"EI-414_O2_X.txt").write_text(
        "".join(f"{1.6+(36/99)*i:.16g} 1\n" for i in range(100)))
    with pytest.raises(ValueError, match="grids differ"):
        mod.prepare(base, incoming, output)
