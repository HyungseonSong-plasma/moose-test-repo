"""Synthetic-only tests; no Phelps restricted original arrays embedded."""
import csv
import importlib.util
from pathlib import Path
import sys

import pytest

MODULE = (Path(__file__).resolve().parents[2] /
          "experiments/Issue395_powered_chemistry_ladder/derive_o2_2067_from_407.py")
spec = importlib.util.spec_from_file_location("derive_o2_2067_from_407", MODULE)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def synthetic_input(tmp_path):
    path = tmp_path / "407.csv"
    energies = [0.0, 0.977] + [0.977 + j*.5 for j in range(1, 25)]
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(module.HEADERS)
        w.writerows((en, max(0., en - 0.977)*1e-21) for en in energies)
    return path


def test_detailed_balance_and_provenance(tmp_path):
    source = synthetic_input(tmp_path)
    rows = module.read_407(source)
    rev = module.detailed_balance_inverse(rows)
    assert len(rows) == 26
    assert len(rev) == 25
    assert rev[0][0] == 0
    assert rev[0][1] == pytest.approx(1.5 * 0.977e-21)
    assert rev[1][1] == pytest.approx(1.5 * (0.977+0.5) / .5 * .5e-21)
    assert all(en >= 0 and sigma >= 0 for en, sigma in rev)
    output = tmp_path / "2067.csv"
    manifest = tmp_path / "2067_manifest.json"
    meta = module.emit_local(source, output, manifest)
    assert meta["reaction_id"] == 2067
    assert meta["derived_npoints"] == 25
    assert "NO_BOLTZMANN_RATE" in meta["status"]
    assert output.exists() and manifest.exists()
    with pytest.raises(FileExistsError):
        module.emit_local(source, output, manifest)


def test_bad_threshold_fails(tmp_path):
    path = synthetic_input(tmp_path)
    text = path.read_text().replace("0.977,0.0", "0.98,0.0", 1)
    path.write_text(text)
    with pytest.raises(ValueError, match="threshold anchors"):
        module.read_407(path)


def test_bad_point_count_fails(tmp_path):
    path = synthetic_input(tmp_path)
    lines = path.read_text().splitlines()
    path.write_text("\n".join(lines[:-1]) + "\n")
    with pytest.raises(ValueError, match="26 points"):
        module.read_407(path)


def test_bad_sigma_fails(tmp_path):
    path = synthetic_input(tmp_path)
    lines = path.read_text().splitlines()
    lines[5] = lines[5].split(",")[0] + ",-1e-21"
    path.write_text("\n".join(lines) + "\n")
    with pytest.raises(ValueError, match="Invalid/nonfinite"):
        module.read_407(path)
