"""Synthetic-only P0 tests for private-runner comparison semantics.

All numeric lookup fixtures are generated here; tests never restore an archive,
read a private coefficient table, or use the Lookup archive secret.
"""
from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import math
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / ".github/scripts/oxygen_mcs_rate_compare_ci.py"
spec = importlib.util.spec_from_file_location("oxygen_mcs_rate_compare", SCRIPT)
compare = importlib.util.module_from_spec(spec)
spec.loader.exec_module(compare)


def write_csv(path, reactions, *, mutate=None, reverse=False):
    fields = ["case", "EoverN_Td", "mean_energy_eV"] + [f"EI-{rid}" for rid in reactions]
    rows = []
    for index in range(24):
        row = {"case": str(index + 1), "EoverN_Td": str(index + 1),
               "mean_energy_eV": str(0.5 + index)}
        row.update({f"EI-{rid}": str(rid * 1e-13 + index * 1e-15) for rid in reactions})
        rows.append(row)
    if mutate:
        mutate(rows)
    if reverse:
        rows.reverse()
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    return path


def write_table(path, rid, *, mutate=None):
    # Deliberately synthetic and reaction-distinct. The particle coefficient
    # is rid * 1e-12; storing molar units exercises the conversion end to end.
    rows = [(1 + index / 4, rid * 1e-12 * compare.NA / 1e6) for index in range(100)]
    if mutate:
        rows = mutate(rows)
    path.write_text("# synthetic test fixture, not a scientific reference\n" +
                    "\n".join(f"{energy:.17g} {rate:.17g}" for energy, rate in rows) + "\n")
    return path


@pytest.fixture
def fixture_data(tmp_path):
    private = tmp_path / "synthetic-private"
    public = tmp_path / "synthetic-public"
    private.mkdir()
    public.mkdir()
    owner = compare.source_owner("build_oxygen_24_source_overlay")
    target = {"O2": "O2_X", "O2a": "O2_a1Delta", "O": "O_3P", "Os": "O_1D"}
    for rid, parent in owner.PARENT.items():
        write_table(private / f"EI-{rid}_{target[parent]}.txt", rid)
    for rid, filename in compare.PUBLIC_PANEL_FILES.items():
        write_table(public / filename, rid)
    base = write_csv(tmp_path / "base.csv", [407])
    omitted = write_csv(tmp_path / "omitted.csv", [411, 412, 417, 935, 943])
    supplement = write_csv(tmp_path / "supplement.csv", [401, 941, 2738])
    return SimpleNamespace(private=private, public=public,
                           base=base, omitted=omitted, supplement=supplement)


def panels(data, complete=False):
    refs = [data.base, data.omitted] + ([data.supplement] if complete else [])
    return compare.prepare_linear_comparison(data.private, refs, data.public,
                                             require_complete=complete)


def test_lookup_shape_and_comments_reuse_production_validation(tmp_path):
    table = compare.read_table(write_table(tmp_path / "table.txt", 407))
    assert len(table) == 100
    assert table[0][0] == 1
    assert table[-1][0] == 25.75


@pytest.mark.parametrize("mutate", [
    lambda rows: rows[:-1],
    lambda rows: rows + [rows[-1]],
    lambda rows: [(0, 1)] + rows[1:],
    lambda rows: [(math.nan, 1)] + rows[1:],
    lambda rows: [(1, math.inf)] + rows[1:],
    lambda rows: [(1, -1)] + rows[1:],
    lambda rows: rows[:1] + rows[:1] + rows[2:],
    lambda rows: rows[:1] + [(0.5, 1)] + rows[2:],
])
def test_lookup_rejects_invalid_row_count_grid_and_rates(tmp_path, mutate):
    path = write_table(tmp_path / "table.txt", 407, mutate=mutate)
    with pytest.raises(ValueError, match="Invalid or missing 100-point"):
        compare.read_table(path)


def test_lookup_parse_error_does_not_echo_source_tokens(tmp_path):
    path = tmp_path / "table.txt"
    path.write_text("1 confidential-coefficient-token\n")
    with pytest.raises(ValueError) as failure:
        compare.read_table(path)
    assert "confidential-coefficient-token" not in str(failure.value)


def test_linear_interpolation_endpoints_midpoint_and_no_extrapolation(tmp_path):
    path = tmp_path / "ramp.txt"
    path.write_text("\n".join(f"{i + 1} {2 * (i + 1) + 3}" for i in range(100)))
    table = compare.read_table(path)
    assert compare.interp(table, 1) == 5
    assert compare.interp(table, 100) == 203
    assert compare.interp(table, 31.25) == 65.5
    assert compare.interp(table, 0.99) is None
    assert compare.interp(table, 100.01) is None


@pytest.mark.parametrize("energy", [math.nan, math.inf, -math.inf, 0, -1])
def test_interpolation_rejects_invalid_query_energy(energy):
    with pytest.raises(ValueError):
        compare.interp([(1, 0), (2, 1)], energy)


def test_molar_to_particle_and_cubic_metre_conversion_is_once():
    assert compare.molar_lookup_to_cm3_s(compare.NA) == 1e6
    assert compare.molar_lookup_to_cm3_s(compare.NA * 1e-15) == pytest.approx(1e-9)
    # Independent fixed oracle detects a wrong Avogadro constant shared by
    # the implementation and the synthetic lookup writer.
    assert compare.molar_lookup_to_cm3_s(6.02214076e8) == pytest.approx(1e-9, rel=1e-14)
    assert compare.molar_lookup_to_cm3_s(0) == 0


@pytest.mark.parametrize("te", [1, 2, 7])
def test_ei2738_matches_existing_particle_formula_without_avogadro(te):
    actual = compare.analytical(2738, 1.5 * te)
    assert actual == pytest.approx(2.0e-7 * math.exp(-5.5 / te), rel=1e-14)


@pytest.mark.parametrize("energy", [1.49, 10.51])
def test_ei2738_never_extends_validated_temperature_range(energy):
    assert compare.analytical(2738, energy) is None


def test_reaction_order_mapping_and_absolute_units(fixture_data):
    result = panels(fixture_data, complete=True)
    assert [panel["reaction"] for panel in result] == [401, 411, 412, 417, 935, 941, 943, 2738, 407]
    for panel in result:
        rid = panel["reaction"]
        if rid != 2738:
            assert panel["moose"][0] is None  # Below original Lookup domain.
            assert panel["moose"][1] == pytest.approx(rid * 1e-12)
        else:
            assert panel["moose"][0] is None
            assert panel["moose"][1] == pytest.approx(2.0e-7 * math.exp(-5.5))
        assert panel["mcs"][0] == pytest.approx(rid * 1e-13)
    assert "Public Lookup" in result[0]["source"]
    assert "Public Lookup" in result[5]["source"]
    assert "Private Lookup" in result[1]["source"]
    assert "Formula" in result[7]["source"]


def test_holds_are_preserved_and_missing_mcs_is_not_manufactured(fixture_data):
    result = panels(fixture_data)
    assert {p["reaction"] for p in result if p["hold"]} == {411, 412}
    for panel in result:
        if panel["reaction"] in (401, 941, 2738):
            assert panel["mcs"] == [None] * 24


def test_strict_mode_requires_all_verified_mcs_columns(fixture_data):
    with pytest.raises(ValueError, match="Complete MCS references"):
        compare.prepare_linear_comparison(fixture_data.private,
            [fixture_data.base, fixture_data.omitted], fixture_data.public,
            require_complete=True)


def test_mcs_zero_is_retained_and_input_order_is_not_case_identity(fixture_data):
    write_csv(fixture_data.omitted, [411, 412, 417, 935, 943], reverse=True,
              mutate=lambda rows: rows[0].update({"EI-411": "0"}))
    result = panels(fixture_data)
    assert result[1]["mcs"][0] == 0
    assert result[1]["energies"] == sorted(result[1]["energies"])


def test_bundled_mcs_references_cover_all_nine_channels_with_source_provenance():
    # Public, user-supplied MCS references only; no MOOSE/private Lookup reads.
    base = ROOT / "experiments/Issue395_powered_chemistry_ladder"
    supplement = base / "mcs_oxygen_supplemental_reactions_20261104.csv"
    metadata = json.loads(supplement.with_suffix(".provenance.json").read_text())
    assert hashlib.sha256(supplement.read_bytes()).hexdigest() == metadata["supplemental_csv_sha256"]
    assert metadata["channel_mapping"] == {
        "EI-401": "O2-ATTACHMENT TWO BODY", "EI-941": "O-ION", "EI-2738": "O- Detachment"}
    cases = compare.read_mcs_cases([
        base / "oxygen_mcs_lookup_compare_14.csv",
        base / "mcs_oxygen_five_omitted_reactions_20261104.csv", supplement,
    ], require_complete=True)
    assert len(cases) == 24
    assert all(set(case["rates"]) == set(compare.PANEL_REACTIONS) for case in cases)
    assert cases[0]["energy"] == 0.1218
    assert cases[-1]["energy"] == 18.45


@pytest.mark.parametrize("mutate, message", [
    (lambda rows: rows[0].update({"mean_energy_eV": "0.51"}), "energy/field identities"),
    (lambda rows: rows[0].update({"EoverN_Td": "0.99"}), "energy/field identities"),
    (lambda rows: rows[0].update({"case": "unknown"}), "case identities"),
    (lambda rows: rows[0].update({"case": "2"}), "duplicate MCS case"),
    (lambda rows: rows[0].update({"mean_energy_eV": "1.5"}), "Duplicate MCS mean-energy"),
    (lambda rows: rows[0].update({"EoverN_Td": "2"}), "Duplicate MCS reduced-field"),
    (lambda rows: rows[0].update({"EI-411": "-1"}), "nonnegative and finite"),
    (lambda rows: rows[0].update({"EI-411": "nan"}), "nonnegative and finite"),
    (lambda rows: rows[0].update({"EI-411": "inf"}), "nonnegative and finite"),
    (lambda rows: rows[0].update({"EI-411": ""}), "invalid numeric"),
])
def test_mcs_join_rejects_ambiguous_or_invalid_sources(fixture_data, mutate, message):
    write_csv(fixture_data.omitted, [411, 412, 417, 935, 943], mutate=mutate)
    with pytest.raises(ValueError, match=message):
        panels(fixture_data)


def test_missing_lookup_does_not_select_another_reaction(fixture_data):
    (fixture_data.private / "EI-411_O2_X.txt").unlink()
    with pytest.raises(ValueError):
        panels(fixture_data)


def test_mapping_contract_and_no_unrelated_private_table_processing(fixture_data):
    expected = {
        "EI-407_O2_X.txt", "EI-411_O2_X.txt", "EI-412_O2_X.txt", "EI-417_O2_X.txt",
        "EI-935_O_3P.txt", "EI-943_O_1D.txt",
    }
    assert compare.PUBLIC_PANEL_FILES == {401: "o2_attachment.txt", 941: "o_ionization.txt"}
    for path in fixture_data.private.iterdir():
        if path.name not in expected:
            path.unlink()
    assert {p.name for p in fixture_data.private.iterdir()} == expected
    assert len(panels(fixture_data, complete=True)) == 9


def test_private_grid_mismatch_is_rejected(fixture_data):
    path = fixture_data.private / "EI-943_O_1D.txt"
    write_table(path, 943, mutate=lambda rows: [(e + 0.01, k) for e, k in rows])
    with pytest.raises(ValueError, match="grids do not match"):
        panels(fixture_data)


def test_plot_has_nine_linear_absolute_panels_and_explicit_holds(fixture_data):
    import matplotlib.pyplot as plt
    fig = compare.build_linear_figure(panels(fixture_data))
    try:
        assert len(fig.axes) == 9
        assert [ax.get_title() for ax in fig.axes] == [f"EI-{rid}" for rid in compare.PANEL_REACTIONS]
        for ax in fig.axes:
            assert ax.get_xscale() == ax.get_yscale() == "linear"
            assert ax.get_ylim()[0] == 0
            assert ax.get_ylim()[1] < 1e-5  # Detect accidentally frozen default ylim=[0,1].
        assert [len(ax.lines) for ax in fig.axes] == [1, 2, 2, 2, 2, 1, 2, 1, 2]
        assert any("reaction identity" in text.get_text() for text in fig.axes[1].texts)
        assert any("reaction identity" in text.get_text() for text in fig.axes[2].texts)
        assert any("reference missing" in text.get_text() for text in fig.axes[0].texts)
        assert "unit confirmation HOLD" in fig._suptitle.get_text()
        assert fig._supxlabel.get_text() == "Mean Electron Energy (eV)"
        assert fig._supylabel.get_text() == "Rate Coefficient k (cm³/s), Linear Scale"
    finally:
        plt.close(fig)


def test_linear_output_is_exactly_one_png_without_coefficient_files(fixture_data, tmp_path):
    out = tmp_path / "output"
    target = compare.write_linear_png(panels(fixture_data, complete=True), out)
    assert target.name == "MCS_MOOSE_3x3_LINEAR.png"
    assert target.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    assert list(out.iterdir()) == [target]
    with pytest.raises(ValueError, match="new or empty"):
        compare.write_linear_png(panels(fixture_data), out)


def test_cli_does_not_log_malformed_private_numeric_tokens(fixture_data, tmp_path):
    (fixture_data.private / "EI-411_O2_X.txt").write_text("1 SECRET_RAW_RATE_SENTINEL\n")
    out = tmp_path / "output"
    run = subprocess.run([sys.executable, str(SCRIPT), "--mode", "linear-3x3",
        "--rate-dir", str(fixture_data.private), "--mcs-csv", str(fixture_data.base),
        "--additional-mcs-csv", str(fixture_data.omitted), "--public-rate-dir", str(fixture_data.public),
        "--output-dir", str(out)], text=True, capture_output=True, check=False)
    assert run.returncode != 0
    assert "SECRET_RAW_RATE_SENTINEL" not in run.stdout + run.stderr
    assert "Traceback" not in run.stderr
    assert not out.exists()


def test_legacy_ratio_mode_preserves_ratios_only_contract(fixture_data, tmp_path):
    reference = write_csv(tmp_path / "legacy.csv", compare.ALL)
    output = tmp_path / "ratios"
    compare.run_ratios(SimpleNamespace(rate_dir=fixture_data.private, mcs_csv=reference, output_dir=output))
    assert {path.name for path in output.iterdir()} == {"rate_ratios.csv", "summary.csv", "DATA_POLICY.txt"}
    with (output / "rate_ratios.csv").open(newline="") as stream:
        reader = csv.DictReader(stream)
        assert "moose_over_mcs" in reader.fieldnames
        assert not {"moose", "mcs", "rate"} & set(reader.fieldnames)
        assert list(reader)
