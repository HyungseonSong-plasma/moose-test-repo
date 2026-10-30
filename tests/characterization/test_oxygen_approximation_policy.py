"""Synthetic-only science-gate tests for oxygen approximate cross sections."""
import csv
import importlib.util
from pathlib import Path
import sys
import pytest

FILE = (Path(__file__).resolve().parents[2] /
        "experiments/Issue395_powered_chemistry_ladder/oxygen_approximation_policy.py")
spec = importlib.util.spec_from_file_location("oxygen_approximation_policy", FILE)
assert spec and spec.loader
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)


def test_declared_model_scope_and_hold_reactions_are_disjoint():
    assert len(m.SIGMA_METHODS) == 6
    assert set(m.SIGMA_METHODS) == {
        "EI-2067", "EI-943", "EI-2058", "EI-2069", "EI-2072", "EI-944"
    }
    assert len(m.HOLD) == 4
    for excluded in ("EI-2068", "EI-2073", "EI-2074", "EI-2738", "EI-2259", "EI-417"):
        with pytest.raises(ValueError, match="HOLD or rate-only"):
            m.derive(excluded, [(0., 0.), (1., 0.), (2., 1e-21)])


def test_microreversibility_and_forward_threshold_limit():
    points = [(0.977, 0.), (1.977, 1e-21), (2.977, 2e-21)]
    rev, meta = m.derive("EI-2067", points)
    assert meta["method"] == "DB"
    assert not meta["solver_accepted"]
    assert rev[0][0] == 0.
    assert rev[0][1] == pytest.approx(1.5 * .977e-21)
    assert rev[1][1] == pytest.approx(1.5 * 1.977e-21)


def test_atomic_oxygen_detailed_balance_9_over_5():
    rev, meta = m.derive("EI-943", [
        (1.967, 0.), (2.967, 2e-21), (3.967, 1e-21)
    ])
    assert meta["parent_id"] == "EI-935"
    assert rev[1][1] == pytest.approx(1.8 * 2.967 * 2e-21)


def test_empirical_attachment_peak_scaled_not_original_098_eV_shift():
    forward = [(4.4, 0.), (4.9, 0.), (5.38, 1e-22), (7., 1.56e-22)]
    rows, meta = m.derive("EI-2058", forward)
    assert rows[0] == (3.5, 0)
    assert rows[1][0] == pytest.approx(3.98)
    assert meta["scale"] == pytest.approx(4.6/1.56)
    assert max(x for _, x in rows) == pytest.approx(4.6e-22)
    assert meta["status"] == "PROVISIONAL_REVIEW"


@pytest.mark.parametrize("reaction,parent", [
    ("EI-2069", [(6., 0.), (7., 1e-21), (8., 2e-21)]),
    ("EI-2072", [(12.06, 0.), (13., 1e-21), (18., 2e-21)]),
    ("EI-944", [(13.6, 0.), (14., 1e-21), (20., 2e-21)]),
])
def test_threshold_shift_models_are_not_physically_validated(reaction, parent):
    rows, meta = m.derive(reaction, parent)
    assert rows[0][1] == 0
    assert meta["status"].startswith("PROVISIONAL")
    assert not meta["solver_accepted"]
    assert meta["max_eV"] == rows[-1][0]


def test_10kev_phelps_artificial_zero_is_removed():
    parent = [(0.977, 0.), (1.5, 1e-22), (45., 2e-22), (10000., 0.)]
    rev, meta = m.derive("EI-2067", parent)
    assert rev[-1][0] == pytest.approx(44.023)
    assert meta["max_eV"] < 50.


def test_maxwellian_reference_not_sigma_or_boltzmann_rate():
    assert m.maxwellian_rate_m3_s("EI-2259", 300*m.K_B_EV_K) == pytest.approx(2.4e-13)
    assert m.maxwellian_rate_m3_s("EI-417", 2.) > 0
    with pytest.raises(ValueError, match="200K"):
        m.maxwellian_rate_m3_s("EI-2259", 100*m.K_B_EV_K)


def test_local_csv_preserves_provenance_and_does_not_overwrite(tmp_path):
    inp, out, manifest = (tmp_path / n for n in ("src.csv", "rev.csv", "manifest.json"))
    with inp.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(("energy_eV", "cross_section_m2"))
        w.writerows([(1.967, 0.), (2.967, 1e-21), (3.967, 2e-21)])
    meta = m.derive_local_csv("EI-943", inp, out, manifest)
    assert out.is_file() and manifest.is_file()
    assert meta["source_sha256"] and meta["data_sha256"]
    assert not meta["solver_accepted"]
    with pytest.raises(ValueError, match="must not exist"):
        m.derive_local_csv("EI-943", inp, out, manifest)


def test_sigma_validation_raises_on_duplicate_and_negative():
    with pytest.raises(ValueError, match="strictly increasing"):
        m.derive("EI-943", [(1.967, 0.), (2.967, 1e-21), (2.967, 2e-21)])
    with pytest.raises(ValueError, match="nonfinite/negative"):
        m.derive("EI-943", [(1.967, 0.), (2.967, -1e-21), (3.967, 1e-21)])
