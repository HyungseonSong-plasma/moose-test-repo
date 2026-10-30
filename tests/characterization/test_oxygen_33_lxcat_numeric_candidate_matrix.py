"""Source-contract regression tests; no third-party numerical data are bundled."""
import csv
from pathlib import Path

DATA = Path(__file__).resolve().parents[2] / "experiments/Issue395_powered_chemistry_ladder"


def rows(name):
    with (DATA / name).open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def test_candidate_matrix_preserves_33_scope_with_only_14_numeric_candidates():
    source = rows("OXYGEN_33_LXCAT_NUMERIC_CANDIDATE_MATRIX.csv")
    registry = rows("OXYGEN_FINAL_UNIFIED_COLLISION_REGISTRY_33.csv")
    assert len(source) == len(registry) == 33
    assert [r["id"] for r in source] == [r["id"] for r in registry]
    assert len({r["id"] for r in source}) == 33
    candidates = [r for r in source if r["candidate_status"].startswith("PUBLIC_NUMERIC_ARRAY")]
    assert len(candidates) == 14
    assert len(source) - len(candidates) == 19
    assert all(r["source_blob_sha"] == "df3b84eae6ae503fa46f9bfa14ec4469d615fe03"
               for r in candidates)
    assert all(int(r["number_of_energy_knots"]) >= 2 for r in candidates)
    assert all(r["local_original_data"] == "NOT_ACQUIRED" for r in source)
    assert all(r["approved_for_solver"] == "NO" for r in source)


def test_no_out_of_scope_chemistry_and_no_unchecked_excited_target_substitution():
    source = {r["id"]: r for r in rows("OXYGEN_33_LXCAT_NUMERIC_CANDIDATE_MATRIX.csv")}
    for excluded in ("KIN-R01", "KIN-E01", "KIN-E02", "KIN-EL-O2", "attachment_three_body"):
        assert excluded not in source
    for k in ("EI-2058", "EI-2067", "EI-2068", "EI-2069",
              "EI-2072", "EI-2073", "EI-2074", "EI-417", "EI-2259"):
        assert source[k]["candidate_status"] == "NO_VERIFIED_PROCESS_LEVEL_NUMERIC_MATCH"
    assert source["EI-2738"]["provider"] == "Morgan O-"
    assert source["KIN-EL-O"]["candidate_status"] == "NO_VERIFIED_PROCESS_LEVEL_NUMERIC_MATCH"


def test_restricted_energy_range_and_products_not_silently_accepted():
    source = {r["id"]: r for r in rows("OXYGEN_33_LXCAT_NUMERIC_CANDIDATE_MATRIX.csv")}
    assert source["EI-411"]["source_max_energy_eV"] == "15"
    assert source["KIN-V01"]["source_max_energy_eV"] == "3.5"
    assert "NOT verified 2O dissociation" in source["EI-411"]["physics_match_guard"]
    assert "NOT Cosby explicit dissociation" in source["EI-412"]["physics_match_guard"]
    assert "GROUND_O2" in source["EI-415"]["physics_match_guard"]
    assert source["EI-401"]["number_of_energy_knots"] == "19"
    assert source["KIN-M01"]["number_of_energy_knots"] == "66"
    assert sum(r["scope"] == "CHEMISTRY_HEAVY" for r in source.values()) == 3
