"""Receipt qualification is not production authority."""
import importlib.util
import json
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET

import pytest

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location("qualification", ROOT / "automation/controller/qualify_checkpoint_contract.py")
q = importlib.util.module_from_spec(spec)
spec.loader.exec_module(q)


@pytest.fixture
def evidence(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    for name in (q.CONTRACT, q.TEST, q.WORKFLOW, q.SCRIPT, q.PIN, q.RECEIPT_TEST, q.VERIFIER, q.VERIFIER_TEST):
        p = root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes((ROOT / name).read_bytes() if name != q.PIN else json.dumps({"operating_system": {"revision": "a"*40}}).encode())
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(["git", "-C", str(root), "add", "."], check=True)
    subprocess.run(["git", "-C", str(root), "-c", "user.name=test", "-c", "user.email=test@example.invalid", "commit", "-qm", "fixture"], check=True)
    head = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
    env = dict(GITHUB_ACTIONS="true", GITHUB_REF="refs/heads/main", GITHUB_REPOSITORY="HyungseonSong-plasma/moose-test-repo", GITHUB_SHA=head, EXPECTED_MAIN_SHA=head, EXPECTED_CONTRACT_SHA256=q.digest(root / q.CONTRACT), EXPECTED_SAMUEL_PIN="a"*40, CORRELATION_ID="test-1", GITHUB_RUN_ID="1", GITHUB_RUN_ATTEMPT="1")
    xml = tmp_path / "result.xml"
    names = [line.split("(")[0][4:] for line in (root / q.TEST).read_text().splitlines() if line.startswith("def test_")]
    suite = ET.Element("testsuite")
    for name in names:
        ET.SubElement(suite, "testcase", name=name)
    ET.ElementTree(suite).write(xml)
    return root, env, xml


def test_receipt_is_non_authorizing(evidence):
    receipt = q.qualify(*evidence)
    assert len(receipt["tests_passed"]) == 7
    assert receipt["write_authorized"] is False
    assert receipt["live_connector_qualified"] is False


@pytest.mark.parametrize("key,value,reason", [
    ("GITHUB_REF", "refs/heads/issue-1", "TRUSTED_MAIN_REQUIRED"),
    ("GITHUB_REPOSITORY", "other/repo", "REPOSITORY_MISMATCH"),
    ("EXPECTED_MAIN_SHA", "b"*40, "SOURCE_SHA_MISMATCH"),
    ("EXPECTED_CONTRACT_SHA256", "b"*64, "CONTRACT_HASH_MISMATCH"),
    ("EXPECTED_SAMUEL_PIN", "b"*40, "SAMUEL_PIN_MISMATCH"),
    ("GITHUB_RUN_ID", "", "RUN_IDENTITY_MISSING"),
])
def test_mismatch_stops(evidence, key, value, reason):
    root, env, xml = evidence
    env[key] = value
    with pytest.raises(ValueError, match=reason):
        q.qualify(root, env, xml)


@pytest.mark.parametrize("kind", ["failure", "error", "skipped", "missing", "duplicate"])
def test_incomplete_result_stops(evidence, kind):
    root, env, xml = evidence
    suite = ET.parse(xml).getroot()
    case = list(suite)[0]
    if kind == "missing":
        suite.remove(case)
    elif kind == "duplicate":
        suite.append(case)
    else:
        ET.SubElement(case, kind)
    ET.ElementTree(suite).write(xml)
    with pytest.raises(ValueError, match="QUALIFICATION_TESTS_INCOMPLETE"):
        q.qualify(root, env, xml)
