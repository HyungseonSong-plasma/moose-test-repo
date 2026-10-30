"""Synthetic-only tests of rights-aware local source acquisition, not Phelps data."""
import importlib.util
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
FILE = ROOT / "experiments/Issue395_powered_chemistry_ladder/acquire_lxcat_cantera_o2_candidates.py"
spec = importlib.util.spec_from_file_location("cantera_phelps_candidate_acquisition", FILE)
assert spec and spec.loader
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)


def fixture():
    chunks = ["description: SYNTHETIC TEST ONLY\n",
              "generator: lxcat2yaml + manual edits\n",
              "reactions:\n"]
    for i, (key, kind, subject, product, process, threshold) in enumerate(m.MAPPINGS):
        heading = f"- {kind}: {subject}\n"
        body = f"  product: {product}\n" if product else ""
        if kind == "target":
            body += f"  kind: {process}\n"
        body += "  energy-levels: [0.0, 1.0, 10.0]\n"
        body += "  cross-sections: [0.0, 1.0e-22, 2.0e-22]\n"
        if threshold is not None:
            body += f"  threshold: {threshold}\n"
        chunks.append(heading + body)
    # Forbidden third-body channel may exist in source, never imported.
    chunks.append("- equation: O2 + Electron => O2-\n"
                  "  energy-levels: [0.0, 1.0, 10.0]\n"
                  "  cross-sections: [0.0, 1.0e-41, 0.0]\n"
                  "  threshold: 0.0\n")
    return "".join(chunks)


def test_14_numeric_candidates_and_exclusion(tmp_path):
    records = m.select(fixture())
    assert len(records) == 14
    assert "KIN-R01" not in records
    assert "KIN-E01" not in records
    assert "KIN-E02" not in records
    assert not any(x["subject"] == "O2 + Electron => O2-" for x in records.values())
    source = tmp_path / "source.yaml"
    source.write_text(fixture(), encoding="utf-8")
    out = tmp_path / "not_for_publication"
    manifest = m.extract(source, out, "2026-10-30")
    assert manifest["record_count"] == 14
    assert manifest["status"].startswith("CANDEMO_NUMERIC_CANDIDATE")
    assert len(list(out.glob("*_candidate.csv"))) == 14
    assert not any("O2-" in p.name for p in out.iterdir())
    assert all(not entry["solver_accepted"] and not entry["hpem_equivalence"]
               for entry in manifest["channels"].values())
    assert manifest["source_sha256"]
    with pytest.raises(FileExistsError):
        m.extract(source, out, "2026-10-30")


def test_unmatched_reaction_fails_closed():
    src = fixture().replace("  product: O2(a1)\n", "  product: O2(WRONG)\n")
    with pytest.raises(ValueError, match="EI-407"):
        m.select(src)


def test_threshold_change_fails_closed():
    src = fixture().replace("  product: O2(4.5eV)\n", "  product: O2(4.5eV)\n")
    # Change only the EI-411 metadata in its exact source block.
    chunk = "- target: O2\n  product: O2(4.5eV)\n"
    assert chunk in src
    before, after = src.split(chunk, 1)
    after = after.replace("  threshold: 4.5\n", "  threshold: 4.4\n", 1)
    with pytest.raises(ValueError, match="EI-411"):
        m.select(before + chunk + after)


def test_nonmonotonic_numeric_energy_is_rejected():
    src = fixture().replace(
        "  energy-levels: [0.0, 1.0, 10.0]\n",
        "  energy-levels: [0.0, 1.0, 1.0]\n", 1,
    )
    with pytest.raises(ValueError, match="energy must strictly increase"):
        m.select(src)


def test_no_internet_or_numerical_data_is_bundled():
    text = FILE.read_text(encoding="utf-8")
    assert "requests.get" not in text
    assert "urllib.request" not in text
    assert "EXCLUDED_NAMES" in text
    assert m.DEMO_URL.endswith("air-plasma-Phelps.yaml")
    assert len(m.MAPPINGS) == 14
