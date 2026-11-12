"""Chemistry S6 P3 preparation: static-only guard, not numerical evidence."""
from pathlib import Path
import ast
import importlib.util
import json
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
PILOT = ROOT / "experiments/Issue402_plasma_dsl_g1"
PREFLIGHT = PILOT / "p3_chemistry_preflight.py"

spec = importlib.util.spec_from_file_location("issue402_p3_static_gate", PREFLIGHT)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_chemistry_p3_only_static_ready_and_no_dispatch():
    report = module.audit(ROOT)
    assert report["status"] == "STATIC_INPUTS_READY_P3_NOT_AUTHORIZED"
    assert report["checks"]["P3"] == "NOT_RUN"
    assert report["checks"]["real_s6_417_941_scratch_chemistry"] == "P2_REQUIRED"
    assert report["science"] == "SCIENCE_HOLD"
    assert set(report["cases"]) == {"417", "941"}
    for case in ("417", "941"):
        assert report["cases"][case]["reaction_count"] == 8
        assert report["cases"][case]["superseded_electron_source_kernels"] == 9


def test_preflight_cli_writes_readonly_manifest(tmp_path):
    target = tmp_path / "readiness.json"
    subprocess.run([sys.executable, str(PREFLIGHT), "--output", str(target)],
                   cwd=ROOT, check=True, stdout=subprocess.DEVNULL)
    saved = json.loads(target.read_text())
    assert saved["checks"]["P3"] == "NOT_RUN"
    assert saved["sha256"]["chemistry/oxygen_s6_common.json"]
    again = subprocess.run([sys.executable, str(PREFLIGHT), "--output", str(target)],
                           cwd=ROOT, capture_output=True, text=True)
    assert again.returncode != 0


def test_new_runner_is_explicitly_authorized_and_not_in_workflow():
    wrapper = (PILOT / "run_chemistry_s6_p3_once.py").read_text()
    core = (PILOT / "run_canonical_s6_p3_once.py").read_text()
    ast.parse(wrapper)
    ast.parse(core)
    assert "--authorize-p3" in wrapper
    assert "readiness = audit()" in wrapper
    assert "chemistry_mode=True" in wrapper
    assert "        import shutil" not in core
    assert "require_energy=True" in core
    assert 'prepare(staged / option.p2.CHEM, ordered, case)' in core
    workflow = (ROOT / ".github/workflows/issue402-canonical-s6-d-once.yml").read_text()
    assert "run_chemistry_s6_p3_once.py" not in workflow
    assert "workflow_dispatch" not in workflow
