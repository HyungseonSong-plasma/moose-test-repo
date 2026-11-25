"""Emit a non-authorizing local Git qualification receipt after exact-source tests."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = "automation/controller/checkpoint-write-contract.json"
TEST = "physics_harness/code/tests/test_checkpoint_cas_contract.py"
WORKFLOW = ".github/workflows/controller-checkpoint-contract.yml"
SCRIPT = "automation/controller/qualify_checkpoint_contract.py"
PIN = "docs/operating_system/central_skills.json"
VERIFIER = "physics_harness/execution/controller_contract_receipt.py"
VERIFIER_TEST = "physics_harness/code/tests/test_controller_contract_receipt.py"
RECEIPT_TEST = "physics_harness/code/tests/test_checkpoint_contract_receipt.py"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def qualify(root, env, junit):
    def require(condition, reason):
        if not condition:
            raise ValueError(reason)
    require(env.get("GITHUB_ACTIONS") == "true" and env.get("GITHUB_REF") == "refs/heads/main", "TRUSTED_MAIN_REQUIRED")
    require(env.get("GITHUB_REPOSITORY") == "HyungseonSong-plasma/moose-test-repo", "REPOSITORY_MISMATCH")
    head = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
    require(re.fullmatch(r"[a-f0-9]{40}", head) and head == env.get("EXPECTED_MAIN_SHA") == env.get("GITHUB_SHA"), "SOURCE_SHA_MISMATCH")
    sources = {p: digest(root / p) for p in (CONTRACT, TEST, WORKFLOW, SCRIPT, PIN, RECEIPT_TEST, VERIFIER, VERIFIER_TEST)}
    require(sources[CONTRACT] == env.get("EXPECTED_CONTRACT_SHA256"), "CONTRACT_HASH_MISMATCH")
    pin = json.loads((root / PIN).read_text())["operating_system"]["revision"]
    require(re.fullmatch(r"[a-f0-9]{40}", pin) and pin == env.get("EXPECTED_SAMUEL_PIN"), "SAMUEL_PIN_MISMATCH")
    suites = ET.parse(junit).getroot()
    cases = list(suites.iter("testcase"))
    required = {"test_exact_parent_single_path", "test_independent_pr_parallel", "test_same_pr_race_exactly_one_wins", "test_intervening_code_commit_is_preserved", "test_lost_response_requires_readback_not_replay", "test_record_cannot_be_overwritten", "test_unexpected_parent_rejected"}
    require(len(cases) == len(required) and {c.get("name") for c in cases} == required and all(not any(c.find(t) is not None for t in ("failure", "error", "skipped")) for c in cases), "QUALIFICATION_TESTS_INCOMPLETE")
    require(all(re.fullmatch(r"[1-9][0-9]*", env.get(k, "")) for k in ("GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT")), "RUN_IDENTITY_MISSING")
    require(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}", env.get("CORRELATION_ID", "")), "CORRELATION_ID_MISSING")
    return {"correlation_id": env["CORRELATION_ID"], "schema_version": 1, "repository": env["GITHUB_REPOSITORY"], "source_sha": head, "samuel_pin": pin, "source_sha256": sources, "run_id": env["GITHUB_RUN_ID"], "run_attempt": env["GITHUB_RUN_ATTEMPT"], "tests_passed": sorted(required), "junit_sha256": digest(junit), "status": "LOCAL_GIT_CONTRACT_QUALIFIED", "live_connector_qualified": False, "write_authorized": False}


if __name__ == "__main__":
    receipt = qualify(ROOT, os.environ, Path(sys.argv[1]))
    with Path(sys.argv[2]).open("x", encoding="utf-8") as f:
        json.dump(receipt, f, sort_keys=True, indent=2)
        f.write("\n")
