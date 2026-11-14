"""Exact-main, D-only public S6 P3 gate and canonical Exodus schema tests.

These tests never launch Docker, access private rates, or solve a plasma state.
"""
from __future__ import annotations

import ast
from pathlib import Path

import numpy as np
import pytest
from scipy.io import netcdf_file


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_NAME = "issue402-canonical-s6-d-once.yml"
WORKFLOW = ROOT / ".github" / "workflows" / WORKFLOW_NAME
PILOT = ROOT / "experiments" / "Issue402_plasma_dsl_g1"
RUNNER = PILOT / "run_canonical_s6_p3_once.py"


def test_exact_main_trigger_and_isolated_d_run_contract():
    text = WORKFLOW.read_text()
    script = RUNNER.read_text()
    ast.parse(script)
    assert "  push:\n    branches: [main]\n" in text
    assert f"paths: [.github/workflows/{WORKFLOW_NAME}]" in text
    assert "workflow_dispatch" not in text
    assert "ref: ${{ github.sha }}" in text
    assert 'matrix:' in text
    assert "case: ['417', '941']" in text
    assert "--timeout-seconds 19800" in text
    # The pinned historical mesh builder rejects 400 W without this opt-in.
    assert "OXYGEN_RESEARCH_400: '1'" in text
    for research_off in ("OXYGEN_RESEARCH_FULL24", "OXYGEN_RESEARCH_EI2738_FORMULA",
                         "OXYGEN_RESEARCH_QUICK_5MIN"):
        assert f"{research_off}: '0'" in text
    assert "run_canonical_s6_p3_once.py" in text
    assert "run_native_binding_smoke.sh" in text
    assert "run_public_option_s6_p2.sh" not in text
    assert 'option.p2.stage(ROOT, historical, case, "C", staged, manifest)' in script
    assert "canonicalize_staged_D_inputs" in script
    assert "option.remap_staged_fem_types" in script
    assert "option.run_one(" in script  # same binary must pass P2 before P3
    assert "verify_native_csv(csv_file)" in script
    assert "verify_canonical_exodus(exodus)" in script
    assert '"SCIENCE_HOLD"' in script
    assert 'label=f"S6-{case}-D"' in script
    assert "source_sha" in script and "native_exodus_sha256" in script
    assert "19800" in script


def _names(variable, names):
    rows = np.zeros((len(names), 32), dtype="S1")
    for i, name in enumerate(names):
        encoded = np.frombuffer(name.encode("ascii"), dtype="S1")
        rows[i, :len(encoded)] = encoded
    variable[:] = rows


def _fake_exodus(root: Path, *, canonical=True, ambiguous=False):
    path = root / "P3.e"
    electron = ("log_e", "log_ne") if ambiguous else (
        ("log_e",) if canonical else ("log_ne",)
    )
    ions = ("log_O2p", "log_Om", "log_Op") if canonical else (
        "log_ni", "log_nm", "log_nop"
    )
    with netcdf_file(str(path), "w") as f:
        f.createDimension("time_step", 461)
        f.createDimension("num_nod_var", len(electron))
        f.createDimension("num_elem_var", 3)
        f.createDimension("len_string", 32)
        f.createVariable("time_whole", "d", ("time_step",))[:] = np.linspace(0, 1e-4, 461)
        _names(f.createVariable("name_nod_var", "c", ("num_nod_var", "len_string")), electron)
        _names(f.createVariable("name_elem_var", "c", ("num_elem_var", "len_string")), ions)
    return path


def test_p3_accepts_only_canonical_output_names(tmp_path):
    tree = ast.parse(RUNNER.read_text())
    function = next(node for node in tree.body
                    if isinstance(node, ast.FunctionDef)
                    and node.name == "verify_canonical_exodus")
    scope = {"Path": Path}
    exec(compile(ast.Module(body=[function], type_ignores=[]),
                 str(RUNNER), "exec"), scope)
    verify = scope["verify_canonical_exodus"]

    canonical = tmp_path / "canonical"
    canonical.mkdir()
    info = verify(_fake_exodus(canonical))
    assert info == {"nodal_electron": "log_e",
                    "elemental_ions": ["log_O2p", "log_Om", "log_Op"],
                    "frames": 461}

    archive = tmp_path / "archive"
    archive.mkdir()
    with pytest.raises(ValueError, match="P3_NONCANONICAL_ELECTRON_STATE"):
        verify(_fake_exodus(archive, canonical=False))

    mixed = tmp_path / "mixed"
    mixed.mkdir()
    with pytest.raises(ValueError, match="P3_NONCANONICAL_ELECTRON_STATE"):
        verify(_fake_exodus(mixed, ambiguous=True))
