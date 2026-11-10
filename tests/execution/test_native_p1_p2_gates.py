"""P1->P2 non-bypassable sequence, build identity and failure classification."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from physics_harness.execution.native_gates import (
    P1GateError, record_p1_success, require_p1_success, run_p2_checked,
)

OCI = "ghcr.io/example/build-base@sha256:" + "a" * 64


@pytest.fixture
def built(tmp_path: Path):
    source = tmp_path / "src"
    source.mkdir()
    subprocess.run(["git", "init", "-q", str(source)], check=True)
    (source / "README").write_text("test\n")
    subprocess.run(["git", "-C", str(source), "add", "README"], check=True)
    subprocess.run(["git", "-C", str(source), "-c", "user.name=test", "-c", "user.email=test@example.com", "commit", "-qm", "setup"], check=True)
    sha = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip()
    exe = source / "physics-opt"
    exe.write_text("#!/usr/bin/env python3\nprint('Syntax OK')\n")
    exe.chmod(0o755)
    evidence = tmp_path / "evidence" / "P1.json"
    return source, sha, exe, evidence


def kw(built):
    src, sha, exe, _ = built
    return {"source_root": src, "source_sha": sha, "binary": exe, "image_ref": OCI}


def run(built, tmp_path, command=None, logfile="P2.log"):
    src, sha, exe, evidence = built
    return run_p2_checked(command or [sys.executable, "-c", "print('Syntax OK')", "--check-input"],
                          evidence=evidence, cwd=tmp_path, log_path=tmp_path / logfile, success_marker="Syntax OK", **kw(built))


def test_gate_requires_successful_p1_first(built, tmp_path):
    with pytest.raises(P1GateError, match="P1_EVIDENCE_MISSING"):
        run(built, tmp_path)
    assert not (tmp_path / "P2.log").exists()
    record_p1_success(built[3], **kw(built))
    report = run(built, tmp_path)
    assert report["P2"] == "PASS"
    assert report["classification"]["status"] == "PASS"
    assert report["p1_binary_sha256"] == require_p1_success(built[3], **kw(built))["binary_sha256"]


def test_identity_rejection_before_command_launch(built, tmp_path):
    record_p1_success(built[3], **kw(built))
    with pytest.raises(P1GateError, match="P1_EVIDENCE_OCI_IMAGE_MISMATCH"):
        run_p2_checked(["would-not-execute", "--check-input"], evidence=built[3], cwd=tmp_path,
                       log_path=tmp_path / "bad.log", **{**kw(built), "image_ref": OCI.replace("a" * 64, "b" * 64)})
    built[2].write_text("#!/usr/bin/env python3\nprint('changed')\n")
    with pytest.raises(P1GateError, match="P1_BINARY_SHA_MISMATCH"):
        run(built, tmp_path)
    assert not (tmp_path / "P2.log").exists()


def test_wrong_source_and_missing_binary_block(built, tmp_path):
    record_p1_success(built[3], **kw(built))
    with pytest.raises(P1GateError, match="P1_SOURCE_HEAD_MISMATCH"):
        run_p2_checked(["not-executed", "--check-input"], evidence=built[3], cwd=tmp_path,
                       log_path=tmp_path / "wrong.log", **{**kw(built), "source_sha": "0" * 40})
    built[2].unlink()
    with pytest.raises(P1GateError, match="P1_BINARY_MISSING_OR_NOT_EXECUTABLE"):
        run(built, tmp_path)


def test_evidence_is_exclusive_and_cannot_be_redispatched(built, tmp_path):
    record_p1_success(built[3], **kw(built))
    with pytest.raises(P1GateError, match="P1_EVIDENCE_ALREADY_EXISTS"):
        record_p1_success(built[3], **kw(built))
    with pytest.raises(P1GateError, match="P2_CHECK_INPUT_COMMAND_REQUIRED"):
        run(built, tmp_path, [sys.executable, "-c", "print('Syntax OK')"])


def test_docker_start_error_is_environment_hold_not_science_failure(built, tmp_path):
    record_p1_success(built[3], **kw(built))
    r = run(built, tmp_path, [sys.executable, "-c", "import sys; sys.exit(125)", "--check-input"])
    assert r["P2"] == "HOLD"
    assert r["classification"]["reason"] == "P2_LAUNCHER_FAIL"
    assert r["classification"]["class"] == "ENVIRONMENT_OR_BUILD_FAIL"


def test_check_input_error_and_missing_success_marker(built, tmp_path):
    record_p1_success(built[3], **kw(built))
    r = run(built, tmp_path, [sys.executable, "-c", "import sys; print('*** ERROR ***\\nmissing input'); sys.exit(2)", "--check-input"])
    assert r["P2"] == "HOLD" and r["classification"]["reason"] == "NATIVE_CHECK_INPUT_FAIL"
    r2 = run(built, tmp_path, [sys.executable, "-c", "print('no evidence of syntax success')", "--check-input"], logfile="P2b.log")
    assert r2["P2"] == "HOLD" and r2["classification"]["reason"] == "P2_SUCCESS_MARKER_MISSING"


def test_timeout_and_bad_evidence_fail_closed(built, tmp_path):
    record_p1_success(built[3], **kw(built))
    r = run_p2_checked([sys.executable, "-c", "import time; time.sleep(3)", "--check-input"],
                       evidence=built[3], cwd=tmp_path, log_path=tmp_path / "timeout.log", timeout_seconds=0.2,
                       **kw(built))
    assert r["P2"] == "HOLD" and r["classification"]["reason"] == "P2_TIMEOUT"
    payload = json.loads(built[3].read_text())
    payload["status"] = "NOT_RUN"
    built[3].write_text(json.dumps(payload))
    with pytest.raises(P1GateError, match="P1_EVIDENCE_NOT_PASS"):
        run(built, tmp_path)


def test_unpinned_oci_and_invalid_source_rejected(built, tmp_path):
    with pytest.raises(P1GateError, match="P1_OCI_NOT_DIGEST_PINNED"):
        record_p1_success(built[3], **{**kw(built), "image_ref": "ghcr.io/example/build-base:latest"})
    with pytest.raises(P1GateError, match="P1_SOURCE_HEAD_MISMATCH"):
        record_p1_success(built[3], **{**kw(built), "source_sha": "f" * 40})
