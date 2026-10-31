"""Static and mutation-gate tests for five genuinely independent native CI runs."""
import importlib.util
import json
from pathlib import Path
import sys

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / ".github/scripts/oxygen25_five_stage_plan.py"
spec = importlib.util.spec_from_file_location("oxygen25_five_stage_test", SCRIPT)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)

STAGE_NAMES = [
    "Oxygen25 500us stage1 initial native checkpoint",
    *[f"Oxygen25 500us stage{i} genuine advanced restart" for i in range(2,6)],
]


def test_five_segments_total_500_steps_500us():
    assert [s.end_ns for s in m.STAGES] == [100,2000,10000,100000,500000]
    assert [s.requested_spacing_ns for s in m.STAGES] == [1,10,100,1000,10000]
    assert [s.requested_steps for s in m.STAGES] == [100,190,80,90,40]
    assert len(m.grid_ns()) == 501
    assert len(set(m.grid_ns())) == 501
    assert m.grid_ns()[-1] == 500000
    assert sum(s.requested_steps for s in m.STAGES) == 500


@pytest.mark.parametrize("stage", [1,2,3,4,5])
def test_each_stage_has_distinct_independent_native_workflow(stage):
    suffix = "-initial" if stage == 1 else "-restart"
    path = ROOT / f".github/workflows/oxygen25-500us-stage{stage}{suffix}.yml"
    raw = path.read_text()
    workflow = yaml.safe_load(raw)
    assert workflow["name"] == STAGE_NAMES[stage-1]
    on = workflow.get("on",workflow.get(True))
    assert "workflow_dispatch" in on
    if stage == 1:
        assert "workflow_run" not in on
        assert "checkpoint" in workflow["jobs"]
        assert "initial_checkpoint.py" in raw
        assert "--attest" in raw
    else:
        assert on["workflow_run"]["workflows"] == [STAGE_NAMES[stage-2]]
        assert on["workflow_run"]["types"] == ["completed"]
        assert "recover" in workflow["jobs"]
        assert "workflow_run.conclusion == 'success'" in workflow["jobs"]["recover"]["if"]
        assert "download-artifact@v4" in raw
        assert "--check-upstream" in raw and "--verify-recovery" in raw
        assert "--attest" in raw
        assert "OXYGEN25_FIVE_STAGE_INPUT_IDENTITY_PASS" in raw
        assert "upstream_run_id" in on["workflow_dispatch"]["inputs"]
        assert f"START_NS: '{m.stage(stage).start_ns}'" in raw
        assert f"END_NS: '{m.stage(stage).end_ns}'" in raw
        assert f"INTERVAL_NS: '{m.stage(stage).requested_spacing_ns}'" in raw
    assert "fail-fast: false" in raw
    assert "[400, 1000]" in raw
    assert "8e2fe042dbc204b5fda22d346f1ad8d2e32db3ab" in raw


def _native_before(number, power=400):
    previous = m.stage(number-1)
    manifest = {
        "source_sha": m.SCIENCE_SOURCE_SHA, "power_w": power,
        "chemistry": m.CHEMISTRY, "scientific_acceptance":"HOLD",
        "actual_moose_step": 143, "final_time_s":str(previous.end_ns*1e-9),
        "recovery_requirements":{"native_recover_prefix":"x/0143"},
        "archives":{
            "restart_run.tar.gz":{"sha256":"a"*64,"bytes":12},
            "restart_inputs.tar.gz":{"sha256":"b"*64,"bytes":34},
        },
    }
    return m.add_attestation(manifest,number-1,power,None if number==2 else 1001)


@pytest.mark.parametrize("number", [2,3,4,5])
def test_inherit_only_exact_prior_stage_and_power(number):
    previous = _native_before(number)
    identity = m.verify_previous_manifest(previous,number,400,789)
    assert identity["from_stage"] == number-1
    assert identity["to_stage"] == number
    assert identity["checkpoint_prefix"] == "x/0143"
    for malformed in (
        dict(previous,power_w=1000),
        dict(previous,source_sha="0"*40),
        dict(previous,actual_moose_step=42),
        dict(previous,five_stage_chain=dict(previous["five_stage_chain"],stage=5)),
        dict(previous,archives={}),
        dict(previous,final_time_s=5e-9),
        dict(previous,scientific_acceptance="PASS"),
    ):
        with pytest.raises(ValueError):
            m.verify_previous_manifest(malformed,number,400,789)
    with pytest.raises(ValueError):
        m.verify_previous_manifest(previous,number,1000,789)
    with pytest.raises(ValueError):
        m.verify_previous_manifest(previous,number,400,0)


def test_first_stage_must_be_true_initialization_and_preserve_native_checkpoint():
    native = {
        "source_sha":m.SCIENCE_SOURCE_SHA,"power_w":400,
        "chemistry":m.CHEMISTRY,"scientific_acceptance":"HOLD",
        "actual_moose_step":104,"final_time_s":1e-7,
    }
    first = m.add_attestation(native,1,400)
    assert first["five_stage_chain"]["initialization"] is True
    assert first["five_stage_chain"]["upstream_run_id"] is None
    with pytest.raises(ValueError):
        m.add_attestation(native,1,400,777)
    with pytest.raises(ValueError):
        m.add_attestation(native,2,400,777)
    with pytest.raises(ValueError):
        m.add_attestation(dict(native,actual_moose_step=0),1,400)


def test_numerical_solver_state_not_fabricated_from_requested_grid():
    helper=(ROOT / ".github/scripts/oxygen25_restart_chain.py").read_text()
    assert "MAX_TIME_NS = 500000" in helper
    assert "actual_step < 1" in helper
    assert "not (start == 100 and manifest.get" in helper
    assert "schema" in helper
    assert "verify_boundary_monitors" in helper
    assert "RF_REINITIALIZED_MONITORS" in helper
    assert "IterationAdaptiveDT" in helper
    assert "checkpoint_prefix" in helper
    assert "OXYGEN25_GENUINE_CROSS_RUN_ADVANCED_RESTART_PASS" in helper


def test_all_yaml_workflows_have_valid_job_ids():
    folder=ROOT / ".github/workflows"
    for n in range(1,6):
        suffix="initial" if n==1 else "restart"
        loaded=yaml.safe_load((folder/f"oxygen25-500us-stage{n}-{suffix}.yml").read_text())
        assert isinstance(loaded.get("jobs"),dict)
        assert not any("private_rates" in str(v).lower() and "artifact" in k.lower()
                       for k,v in loaded["jobs"].items())
