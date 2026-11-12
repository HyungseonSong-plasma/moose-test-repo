"""Validate exact-head, no-solve Chemistry S6 P2 run preparation."""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "experiments/Issue402_plasma_dsl_g1"


def test_s6_full_p2_cli_is_explicit_and_never_calls_p3():
    script = (BASE / "run_chemistry_s6_p2_only.py").read_text()
    ast.parse(script)
    assert 'option.p2.preflight(ROOT)' in script
    assert 'option.check_source(expected_head, historical, binary)' in script
    assert 'option.p2.stage(ROOT, historical, case, "C", staged, manifest)' in script
    assert 'option.canonicalize_staged_D_inputs(chemistry, ordered)' in script
    assert 'option.remap_staged_fem_types(chemistry, ordered)' in script
    assert 'cutover = prepare(chemistry, ordered, case)' in script
    assert 'checked = option.run_one(' in script
    assert '"P3": "NOT_RUN"' in script
    assert 'run_canonical_s6_p3_once' not in script.replace(
        'never calls run_canonical_s6_p3_once.run', '')
    assert '"both", "417", "941"' in script
    assert '"readiness.json"' in script
    assert 'P2_REPORT_DIRECTORY_ALREADY_EXISTS' in script


def test_review_chemistry_input_is_not_silently_activated_with_synthetic_mu_d():
    script = (BASE / "run_chemistry_s6_p2_only.py").read_text()
    prepare = (BASE / "chemistry/prepare_s6_run_input.py").read_text()
    assert 'The original S6 Native ion' in script or (
        'original S6 Native ion' in script)
    assert 'files = \'chemistry/oxygen_s6_common.json chemistry/oxygen_s6_' in prepare
    assert '"e_transport.txt"' not in script
    assert '"P3": "NOT_RUN"' in script
