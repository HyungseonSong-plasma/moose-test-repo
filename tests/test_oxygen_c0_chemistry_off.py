"""C0-P0 fail-closed chemistry source inventory, no Physics runtime claims."""
from __future__ import annotations

from pathlib import Path
import json
import pytest

from experiments.Issue395_powered_chemistry_ladder.chemistry_off_c0 import (
    ChemistryOffContractError, SURFACE_BLOCKS, expected_grid_ns, stage,
)


def setup_case(tmp_path: Path) -> tuple[Path, Path, Path]:
    base = tmp_path / "base.i"
    times = " ".join(f"{ns*1e-9:.17g}" for ns in expected_grid_ns())
    base.write_text("[Variables]\n  [log_ne]\n  []\n  [log_energy]\n  []\n[]\n"
                    "[Executioner]\n  end_time = 1e-4\n  time_sequence = '" + times + "'\n[]\n"
                    "[Physics]\n  !include physics.i\n[]\n", encoding="utf-8")
    (tmp_path / "physics.i").write_text("# neutral transport, not chemistry\n", encoding="utf-8")
    parent = tmp_path / "parent.i"
    parent.write_text("[Controls]\n  [rf]\n    target = 400\n  []\n[]\n", encoding="utf-8")
    return base, parent, tmp_path / "evidence" / "c0.json"


def test_clean_c0_contract_stages_only_base_and_rf(tmp_path):
    base, parent, out = setup_case(tmp_path)
    result = stage(tmp_path, base, parent, out, verify_git_sha=False)
    assert result["phase"] == "P0_STATIC_CANDIDATE_ONLY"
    assert result["native_runtime_proved"] is False
    assert result["chemistry_source_ownership_proved"] is False
    assert result["active_cli_input_files"] == ["base__C0_chemistry_off.i", "parent.i"]
    assert result["check_argv"][3:] == ["base__C0_chemistry_off.i", "parent.i"]
    assert (tmp_path / "base__C0_chemistry_off.i").read_text() == base.read_text()
    assert json.loads(out.read_text()) == result
    with pytest.raises(ChemistryOffContractError, match="overwrite"):
        stage(tmp_path, base, parent, out, verify_git_sha=False)


@pytest.mark.parametrize("mutation", [
    "  reaction_progress = R_EI415\n",
    "  type = PhysicsElectronImpactRateMaterial\n",
    "  source = S_electron_energy_EI415\n",
    "  stageb4_O_surface_loss = 1\n",
    "  functor_names = 'R_EI412'\n",
])
def test_rejects_embedded_or_included_reaction(tmp_path, mutation):
    base, parent, out = setup_case(tmp_path)
    (tmp_path / "physics.i").write_text(mutation)
    with pytest.raises(ChemistryOffContractError, match="residual chemistry"):
        stage(tmp_path, base, parent, out, verify_git_sha=False)
    assert not out.exists()


def test_rejects_wrong_time_power_and_restart(tmp_path):
    base, parent, out = setup_case(tmp_path)
    parent.write_text(parent.read_text().replace("target = 400", "target = 1000"))
    with pytest.raises(ChemistryOffContractError, match="400 W"):
        stage(tmp_path, base, parent, out, verify_git_sha=False)
    parent.write_text(parent.read_text().replace("target = 1000", "target = 400"))
    base.write_text(base.read_text().replace("end_time = 1e-4", "end_time = 1e-5"))
    with pytest.raises(ChemistryOffContractError, match="end_time"):
        stage(tmp_path, base, parent, out, verify_git_sha=False)
    base.write_text(base.read_text().replace("end_time = 1e-5", "end_time = 1e-4") + "restart_file_base = 'old'\n")
    with pytest.raises(ChemistryOffContractError, match="fresh solve"):
        stage(tmp_path, base, parent, out, verify_git_sha=False)


def test_include_cycle_and_escape_fail(tmp_path):
    base, parent, out = setup_case(tmp_path)
    (tmp_path / "physics.i").write_text("!include base.i\n")
    with pytest.raises(ChemistryOffContractError, match="cycle"):
        stage(tmp_path, base, parent, out, verify_git_sha=False)
    (tmp_path / "physics.i").write_text("!include ../outside.i\n")
    with pytest.raises((ChemistryOffContractError, FileNotFoundError)):
        stage(tmp_path, base, parent, out, verify_git_sha=False)

def test_exact_surface_chemistry_graph_removed_with_charged_wall_retained(tmp_path):
    base, parent, out = setup_case(tmp_path)
    blocks = {"FunctorMaterials": [], "FVBCs": [], "Postprocessors": []}
    for item in SURFACE_BLOCKS:
        group, name = item.split("/")
        blocks[group].append(f"  [{name}]\n    type = ADGenericFunctorMaterial\n  []\n")
    blocks["FVBCs"] += [
        "  [ion_wall]\n    type = FVFunctorNeumannBC\n  []\n",
        "  [negative_ion_wall]\n    type = FVFunctorNeumannBC\n  []\n",
        "  [atomic_positive_ion_wall]\n    type = FVFunctorNeumannBC\n  []\n",
    ]
    extra = "".join(f"[{group}]\n{''.join(values)}[]\n" for group, values in blocks.items())
    base.write_text(base.read_text() + extra)
    result = stage(tmp_path, base, parent, out, verify_git_sha=False)
    derived = (tmp_path / "base__C0_chemistry_off.i").read_text()
    assert len(result["removed_reactive_wall_objects"]) == len(SURFACE_BLOCKS) == 15
    for path in SURFACE_BLOCKS:
        assert f"[{path.split('/')[-1]}]" not in derived
    for keep in ("ion_wall", "negative_ion_wall", "atomic_positive_ion_wall"):
        assert f"[{keep}]" in derived
    assert base.read_text().endswith(extra)


def test_partial_surface_graph_rejected(tmp_path):
    base, parent, out = setup_case(tmp_path)
    base.write_text(base.read_text() + "[FVBCs]\n  [stageb4_O_surface_loss]\n  []\n[]\n")
    with pytest.raises(ChemistryOffContractError, match="partial surface reaction"):
        stage(tmp_path, base, parent, out, verify_git_sha=False)
    assert not out.exists()
