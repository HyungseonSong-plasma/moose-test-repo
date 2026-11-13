"""Exact public S6-417/941 electron lookup input and bounded formula parity.

B/C archive immutable; all transformations are in-memory disposable D drafts.
No Native face/time-step equivalence or P3 acceptance is claimed here.
"""
from __future__ import annotations

import base64
import hashlib
import importlib.util
import io
import math
import os
from pathlib import Path
import tarfile

import pytest

ROOT = Path(__file__).resolve().parents[1]
PREPARER = (ROOT / "experiments/Issue402_plasma_dsl_g1/chemistry/"
            "prepare_s6_run_input.py")
ARCHIVE = (ROOT / "experiments/Issue493_s6_boltzmann/"
           "public_p2_decks.tar.xz.b64")
TABLE = (ROOT / "experiments/Issue91_real_qvt_r3/r3_e0/"
         "electron_moments.txt")
ARCHIVE_HASH = "9e801cc6dca3860750b7b97fb6ceca8e6060a3c894dd616cbaf688f529fea240"
TABLE_GIT_BLOB = "bedcaf17fb3ef93ba8973cc6b32aa6e783e2292a"
PREPARED_TABLE_GIT_BLOB = "aa05aadde111e4ba435185954a64a4b7dbbf2d45"
BASE = "rf_elastic_diss_ion_ei20_ei01_400w_adjacent_sheath_wall_closed_100us_dt1000ns__C0_chemistry_off.i"
BASE_PATH = Path(BASE)

spec = importlib.util.spec_from_file_location("s6_transport_compat", PREPARER)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def _load() -> dict[str, bytes]:
    raw = base64.b64decode(ARCHIVE.read_text(), validate=False)
    assert hashlib.sha256(raw).hexdigest() == ARCHIVE_HASH
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:xz") as handle:
        members = handle.getmembers()
        assert len(members) == 45
        assert all(m.isfile() and not m.issym() and not m.islnk()
                   and ".." not in Path(m.name).parts for m in members)
        return {m.name: handle.extractfile(m).read() for m in members}


def _case(archive: dict[str, bytes], case: str, variant: str):
    prefix = f"S6-{case}-407-2069-H25/{variant}/"
    return {Path(Path(name).name): content.decode("utf-8")
            for name, content in archive.items() if name.startswith(prefix)
            and name.endswith(".i")}


@pytest.mark.parametrize("case", ("417", "941"))
@pytest.mark.parametrize("variant", ("B", "C"))
def test_original_archived_lookup_ownership_and_scratch_conversion(case, variant):
    archive = _load()
    source = _case(archive, case, variant)
    assert len(source) == (10 if variant == "B" else 11)
    original = {name: value.encode() for name, value in source.items()}
    updated, report = module.canonicalize_staged_electron_lookup(source)
    assert report["status"] == "SCRATCH_ONLY_EXACT_ELECTRON_LOOKUP_CUTOVER"
    assert report["source_layer"] == BASE
    assert report["bounds_policy"] == "clamp"
    assert report["coordinate"] == "mean_en_solved"
    assert report["gas_temperature"] == "T_g_fixed"
    assert report["pressure"] == "p"
    assert report["table_units"] == "reduced"
    assert report["fluid_energy"] is True
    assert report["P3"] == "NOT_RUN" and report["science"] == "SCIENCE_HOLD"
    assert all(source[name].encode() == old for name, old in original.items())
    assert all(updated[name] == source[name] for name in source if name != BASE_PATH)
    old, new = source[BASE_PATH], updated[BASE_PATH]
    assert old.count("type = PhysicsElectronTransportLookupMaterial") == 1
    assert "type = PhysicsElectronTransportLookupMaterial" not in new
    assert new.count("type = DDMaterial") == 1
    electron_block = new.split("  [electron_transport]\n", 1)[1].split("  []", 1)[0]
    for line in ("table_file = '../Issue91_real_qvt_r3/r3_e0/electron_moments.txt'",
                 "pressure = p", "gas_temperature = T_g_fixed",
                 "bounds_policy = clamp", "model = lookup",
                 "table_units = reduced", "fluid_energy = true",
                 "species_id = e", "block = plasma"):
        assert electron_block.count(line) == 1
    assert "property_table_file =" not in new
    assert "mean_energy = mean_en_solved" not in new.split("[electron_transport]")[1].split("  []")[0]
    # Preserve original physical table, pressure, temperature and all consumers.
    assert "electron_mobility" in new and "electron_diffusion" in new
    assert new.replace("    species_id = e\n", "") != old  # truly migrated


@pytest.mark.parametrize("before,after", (
    ("bounds_policy = clamp", "bounds_policy = error"),
    ("mean_energy = mean_en_solved", "mean_energy = other_mean"),
    ("pressure = p", "pressure = p_fake"),
    ("gas_temperature = T_g_fixed", "gas_temperature = T_g"),
    ("property_table_file = '../Issue91_real_qvt_r3/r3_e0/electron_moments.txt'",
     "property_table_file = 'e_transport.txt'"),
    ("type = PhysicsElectronTransportLookupMaterial", "type = DDMaterial"),
    ("block = plasma", "block = elsewhere"),
))
def test_unverified_transport_identity_rejected_without_source_change(before, after):
    archive = _load()
    text = _case(archive, "417", "C")[BASE_PATH]
    assert before in text
    # Replacement is restricted to the first matching instance in the base.
    anchor = "[electron_transport]"
    assert anchor in text
    prefix, block = text.split(anchor, 1)
    target, suffix = block.split("  []", 1)
    assert before in target
    corrupted = prefix + anchor + target.replace(before, after, 1) + "  []" + suffix
    source = {Path(BASE): corrupted, Path("other.i"): "unchanged\n"}
    with pytest.raises(ValueError, match="S6_ELECTRON_LOOKUP_IDENTITY_UNPROVED"):
        module.canonicalize_staged_electron_lookup(source)
    assert source[Path(BASE)] == corrupted
    assert source[Path("other.i")] == "unchanged\n"


@pytest.mark.parametrize("hidden", [
    "      unexpected = value",
    "    unexpected = value",
    "      mean_energy = dummy",
    "    mean_energy = mean_en_solved",
    "    garbage that is not an assignment",
])
def test_hidden_or_duplicate_electron_transport_assignment_rejected(hidden):
    original = _case(_load(), "417", "C")[BASE_PATH]
    anchor = "    bounds_policy = clamp\n"
    assert original.count(anchor) == 1
    corrupted = original.replace(anchor, anchor + hidden + "\n", 1)
    source = {BASE_PATH: corrupted, Path("other.i"): "unchanged\n"}
    with pytest.raises(ValueError, match="S6_OWNER_|S6_ELECTRON_LOOKUP_IDENTITY_UNPROVED"):
        module.canonicalize_staged_electron_lookup(source)
    assert source[BASE_PATH] == corrupted


def test_duplicate_electron_lookup_owner_rejected():
    archive = _load()
    base = _case(archive, "417", "C")[BASE_PATH]
    source = {Path(BASE): base, Path("repeated.i"): base}
    with pytest.raises(ValueError, match="S6_ELECTRON_LOOKUP_OWNER_COUNT_UNPROVED"):
        module.canonicalize_staged_electron_lookup(source)


def test_missing_electron_lookup_owner_rejected():
    with pytest.raises(ValueError, match="S6_ELECTRON_LOOKUP_OWNER_COUNT_UNPROVED"):
        module.canonicalize_staged_electron_lookup({Path("empty.i"): "[Mesh]\n[]\n"})


@pytest.mark.parametrize("table,git_blob_expected,expected_rows", [
    (TABLE, TABLE_GIT_BLOB, 100),
    (None, PREPARED_TABLE_GIT_BLOB, 42),
])
def test_archived_public_transport_table_shape_and_content_identity(table, git_blob_expected, expected_rows):
    if table is None:
        name = os.environ.get("ISSUE402_HISTORICAL_PUBLIC_TABLE")
        if not name:
            pytest.skip("Requires pinned historical 42-row public P2 staging source")
        table = Path(name)
    content = table.read_bytes()
    git_blob = hashlib.sha1(b"blob " + str(len(content)).encode() + b"\x00" + content).hexdigest()
    assert git_blob == git_blob_expected
    lines = [line for line in content.decode().splitlines() if line.strip()]
    rows = [tuple(map(float, line.split())) for line in lines]
    assert len(rows) == expected_rows
    assert all(len(x) == 3 for x in rows)
    assert all(all(math.isfinite(v) for v in row) and row[1] >= 0 and row[2] >= 0
               for row in rows)
    assert all(rows[i][0] < rows[i + 1][0] for i in range(len(rows) - 1))


@pytest.mark.parametrize("pressure,temperature", [(101325., 300.), (50., 450.)])
@pytest.mark.parametrize("coordinate", [-10., 1.40991, 3.1, 5.73276, 22.1378, 25.])
@pytest.mark.parametrize("prepared", [False, True])
def test_historical_and_dd_lookup_equations_agree_at_archived_table_points(
        coordinate, pressure, temperature, prepared):
    # Independent arithmetic oracle restricted to the proved archived S6
    # table and physically meaningful p,T; no C++ execution is claimed.
    table = TABLE
    if prepared:
        name = os.environ.get("ISSUE402_HISTORICAL_PUBLIC_TABLE")
        if not name:
            pytest.skip("Requires pinned historical 42-row P2 source")
        table = Path(name)
    rows = [tuple(map(float, line.split())) for line in table.read_text().splitlines()]
    n_n = pressure / (1.380649e-23 * temperature)
    def evaluate(column):
        if coordinate <= rows[0][0]:
            return rows[0][column]
        if coordinate >= rows[-1][0]:
            return rows[-1][column]
        for i in range(len(rows)-1):
            x0, x1 = rows[i][0], rows[i+1][0]
            if x0 <= coordinate <= x1:
                y0, y1 = rows[i][column], rows[i+1][column]
                return y0 + (coordinate - x0) * (y1 - y0) / (x1 - x0)
        raise AssertionError("unreachable")

    # Old ElectronTransportLookupMaterial.C and new DDMaterial.C both
    # interpolate reduced coefficients and divide by the same neutral N.
    old_mu = evaluate(1) / n_n
    old_diff = evaluate(2) / n_n
    new_mu = evaluate(1) * (1. / n_n)
    new_diff = evaluate(2) * (1. / n_n)
    assert math.isclose(old_mu, new_mu, rel_tol=1e-14)
    assert math.isclose(old_diff, new_diff, rel_tol=1e-14)
    assert math.isclose(5. / 3. * old_mu, (5. * new_mu) / 3., rel_tol=1e-14)
    assert math.isclose(5. / 3. * old_diff, (5. * new_diff) / 3., rel_tol=1e-14)


def test_current_cpp_lookup_ownership_has_same_energy_projection():
    cpp = (ROOT / "physics_app/src/materials/DDMaterial.C").read_text()
    header = (ROOT / "physics_app/include/materials/DDMaterial.h").read_text()
    for symbol in ('getFunctorByName<ADReal>("mean_en_solved")',
                   '"electron_mobility"', '"electron_diffusion"',
                   '"electron_energy_mobility"', '"electron_energy_diffusion"',
                   '"electron_reduced_mobility"', '"electron_reduced_diffusion"',
                   '"neutral_number_density"'):
        assert symbol in cpp
    assert '"fluid_energy"' in cpp and "5.0 / 3.0" in cpp
    assert "raw / neutralNumberDensity(r, state)" in header
    assert "_bounds_policy == BoundsPolicy::Error" in cpp
    assert not (ROOT / "physics_app/src/materials/"
                "ElectronTransportLookupMaterial.C").exists()
