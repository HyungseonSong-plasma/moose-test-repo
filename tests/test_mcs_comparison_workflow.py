"""Issue #432 security controls, using synthetic inputs and mocked GitHub only."""
from __future__ import annotations

import base64
import importlib.util
import io
import json
from pathlib import Path
import stat
import tarfile
from urllib.error import HTTPError

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "mcs_security", ROOT / ".github/scripts/mcs_lookup_archive_ci.py"
)
SECURITY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SECURITY)
TEST_SHA = "a" * 40
CODE_RECORD = f"https://github.com/{SECURITY.REPOSITORY}/issues/432#issuecomment-7000000001"
DISCLOSURE_RECORD = f"https://github.com/{SECURITY.REPOSITORY}/issues/432#issuecomment-7000000002"


@pytest.fixture
def approved_env():
    return {
        "GITHUB_SHA": TEST_SHA,
        "GITHUB_REPOSITORY": SECURITY.REPOSITORY,
        "GITHUB_EVENT_NAME": "workflow_dispatch",
        "EXPECTED_SHA": TEST_SHA,
        "MCS_CODE_REVIEWED_SHA": TEST_SHA,
        "MCS_CODE_REVIEW_RECORD_URL": CODE_RECORD,
        "MCS_PNG_PUBLIC_DISCLOSURE_SHA": TEST_SHA,
        "MCS_PNG_PUBLIC_DISCLOSURE_RECORD_URL": DISCLOSURE_RECORD,
    }


@pytest.fixture
def protected_environment():
    return {
        "name": SECURITY.ENVIRONMENT,
        "protection_rules": [
            {
                "type": "required_reviewers",
                "prevent_self_review": True,
                "reviewers": [{"type": "User", "reviewer": {"id": 123}}],
            }
        ],
    }


def test_approvals_bind_current_workflow_commit_and_protected_environment(approved_env, protected_environment):
    assert SECURITY.verify_approvals(approved_env, protected_environment) == TEST_SHA


def test_code_review_record_can_be_actual_pr_review(approved_env, protected_environment):
    approved_env["MCS_CODE_REVIEW_RECORD_URL"] = (
        f"https://github.com/{SECURITY.REPOSITORY}/pull/433#pullrequestreview-7000000003"
    )
    assert SECURITY.verify_approvals(approved_env, protected_environment) == TEST_SHA


@pytest.mark.parametrize(
    "field,bad",
    [
        ("GITHUB_SHA", "latest"),
        ("GITHUB_REPOSITORY", "other/project"),
        ("GITHUB_EVENT_NAME", "push"),
        ("EXPECTED_SHA", "b" * 40),
        ("MCS_CODE_REVIEWED_SHA", ""),
        ("MCS_CODE_REVIEWED_SHA", "b" * 40),
        ("MCS_PNG_PUBLIC_DISCLOSURE_SHA", ""),
        ("MCS_PNG_PUBLIC_DISCLOSURE_SHA", "b" * 40),
        ("MCS_CODE_REVIEW_RECORD_URL", ""),
        ("MCS_CODE_REVIEW_RECORD_URL", "https://example.org/approve"),
        (
            "MCS_CODE_REVIEW_RECORD_URL",
            f"https://github.com/{SECURITY.REPOSITORY}/issues/432#issuecomment-6631358844",
        ),
        ("MCS_PNG_PUBLIC_DISCLOSURE_RECORD_URL", ""),
        ("MCS_PNG_PUBLIC_DISCLOSURE_RECORD_URL", CODE_RECORD.replace("432", "431")),
        (
            "MCS_PNG_PUBLIC_DISCLOSURE_RECORD_URL",
            f"https://github.com/{SECURITY.REPOSITORY}/issues/432#issuecomment-6631358844",
        ),
    ],
)
def test_missing_stale_or_wrong_scope_approval_rejects_before_private_job(
    approved_env, protected_environment, field, bad
):
    approved_env[field] = bad
    with pytest.raises(SECURITY.BoundaryError):
        SECURITY.verify_approvals(approved_env, protected_environment)


@pytest.mark.parametrize(
    "environment",
    [None, {}, {"name": "other"}, {"name": SECURITY.ENVIRONMENT},
     {"name": SECURITY.ENVIRONMENT, "protection_rules": []},
     {"name": SECURITY.ENVIRONMENT, "protection_rules": [{"type": "wait_timer"}]}],
)
def test_absent_or_unprotected_environment_cannot_implicitly_authorize(approved_env, environment):
    with pytest.raises(SECURITY.BoundaryError):
        SECURITY.verify_approvals(approved_env, environment)


@pytest.mark.parametrize(
    "reviewers,prevent_self_review",
    [([], True), ([{"type": "User", "reviewer": {"id": 1}}], False),
     ([{"type": "User", "reviewer": {"id": True}}], True),
     ([{"type": "User", "reviewer": {"id": 0}}], True),
     ([{"type": "Unknown", "reviewer": {"id": 1}}], True),
     ([{}], True), (None, True)],
)
def test_environment_requires_independent_valid_reviewer(
    approved_env, protected_environment, reviewers, prevent_self_review
):
    protected_environment["protection_rules"][0].update(
        reviewers=reviewers, prevent_self_review=prevent_self_review
    )
    with pytest.raises(SECURITY.BoundaryError):
        SECURITY.verify_approvals(approved_env, protected_environment)


@pytest.mark.parametrize("status", [403, 404, 500])
def test_github_environment_api_errors_fail_closed_without_response_or_token(monkeypatch, status):
    def fail(request, **kwargs):
        raise HTTPError(request.full_url, status, "SYNTHETIC_SENSITIVE_RESPONSE", None, None)

    monkeypatch.setattr(SECURITY, "urlopen", fail)
    with pytest.raises(SECURITY.BoundaryError) as result:
        SECURITY.github_environment("SYNTHETIC_TOKEN")
    assert str(result.value) == "Protected Environment could not be verified"


def test_environment_api_uses_only_fixed_repository_and_environment(monkeypatch, protected_environment):
    class Response(io.BytesIO):
        pass

    def response(request, **kwargs):
        assert request.full_url == (
            f"https://api.github.com/repos/{SECURITY.REPOSITORY}/environments/{SECURITY.ENVIRONMENT}"
        )
        assert kwargs["timeout"] == 20
        return Response(json.dumps(protected_environment).encode())

    monkeypatch.setattr(SECURITY, "urlopen", response)
    assert SECURITY.github_environment("SYNTHETIC_TOKEN") == protected_environment


def archive_blob(entries):
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:xz") as archive:
        for name, kind, body in entries:
            member = tarfile.TarInfo(name)
            member.type = kind
            if kind == tarfile.REGTYPE:
                member.size = len(body)
                archive.addfile(member, io.BytesIO(body))
            else:
                member.linkname = "SYNTHETIC_TARGET"
                archive.addfile(member)
    return base64.b64encode(buffer.getvalue()).decode()


def test_safe_restore_reuses_base64_tar_xz_without_private_fixture(tmp_path):
    blob = archive_blob([
        ("./", tarfile.DIRTYPE, b""),
        ("./EI-407_O2_X.txt", tarfile.REGTYPE, b"1 2\n3 4\n"),
    ])
    destination = tmp_path / "rates"
    SECURITY.restore_archive(blob, destination)
    table = destination / "EI-407_O2_X.txt"
    assert table.read_bytes() == b"1 2\n3 4\n"
    assert stat.S_IMODE(destination.stat().st_mode) == 0o700
    assert stat.S_IMODE(table.stat().st_mode) == 0o600


def test_restore_accepts_wrapped_base64_used_by_existing_secret_mechanism(tmp_path):
    blob = archive_blob([("EI-407_O2_X.txt", tarfile.REGTYPE, b"1 2\n")])
    wrapped = "\r\n ".join(blob[n:n + 40] for n in range(0, len(blob), 40)) + "\r\n"
    SECURITY.restore_archive(wrapped, tmp_path / "rates")
    assert (tmp_path / "rates/EI-407_O2_X.txt").read_bytes() == b"1 2\n"


@pytest.mark.parametrize(
    "name,kind",
    [("../EI-407_O2_X.txt", tarfile.REGTYPE),
     ("/EI-407_O2_X.txt", tarfile.REGTYPE),
     ("nested/EI-407_O2_X.txt", tarfile.REGTYPE),
     ("EI-407_O2_X.txt", tarfile.SYMTYPE),
     ("EI-407_O2_X.txt", tarfile.LNKTYPE),
     ("EI-407_O2_X.txt", tarfile.CHRTYPE),
     ("EI-407_O2_X.txt", tarfile.FIFOTYPE),
     ("EI-407_O2_X.txt", tarfile.DIRTYPE),
     ("script.py", tarfile.REGTYPE),
     ("C:\\EI-407_O2_X.txt", tarfile.REGTYPE)],
)
def test_archive_rejects_traversal_links_devices_and_non_rate_files(tmp_path, name, kind):
    blob = archive_blob([(name, kind, b"SYNTHETIC_COEFFICIENT")])
    destination = tmp_path / "rates"
    with pytest.raises(SECURITY.BoundaryError) as result:
        SECURITY.restore_archive(blob, destination)
    assert str(result.value) == "Private Lookup package unavailable or invalid"
    assert not destination.exists()


def test_archive_duplicate_normalized_names_rejected_before_write(tmp_path):
    blob = archive_blob([
        ("EI-407_O2_X.txt", tarfile.REGTYPE, b"1 2\n"),
        ("./EI-407_O2_X.txt", tarfile.REGTYPE, b"3 4\n"),
    ])
    with pytest.raises(SECURITY.BoundaryError):
        SECURITY.restore_archive(blob, tmp_path / "rates")
    assert not (tmp_path / "rates").exists()


@pytest.mark.parametrize("blob", ["", "SYNTHETIC_NOT_BASE64", base64.b64encode(b"not tar").decode()])
def test_invalid_archive_has_only_generic_public_error(tmp_path, blob):
    with pytest.raises(SECURITY.BoundaryError) as result:
        SECURITY.restore_archive(blob, tmp_path / "rates")
    assert str(result.value) == "Private Lookup package unavailable or invalid"


def test_restore_never_overwrites_preexisting_directory(tmp_path):
    target = tmp_path / "rates"
    target.mkdir()
    (target / "user-file").write_text("keep")
    blob = archive_blob([("EI-407_O2_X.txt", tarfile.REGTYPE, b"1 2\n")])
    with pytest.raises(SECURITY.BoundaryError):
        SECURITY.restore_archive(blob, target)
    assert (target / "user-file").read_text() == "keep"
    assert len(list(target.iterdir())) == 1


def test_restore_rejects_expansion_and_member_limits(tmp_path, monkeypatch):
    blob = archive_blob([("EI-407_O2_X.txt", tarfile.REGTYPE, b"1 2\n")])
    monkeypatch.setattr(SECURITY, "MAX_UNPACKED_BYTES", 1)
    with pytest.raises(SECURITY.BoundaryError):
        SECURITY.restore_archive(blob, tmp_path / "rates")
    monkeypatch.setattr(SECURITY, "MAX_UNPACKED_BYTES", 100)
    monkeypatch.setattr(SECURITY, "MAX_MEMBERS", 0)
    with pytest.raises(SECURITY.BoundaryError):
        SECURITY.restore_archive(blob, tmp_path / "rates")


def test_png_output_allowlist_rejects_raw_file_and_symlink(tmp_path):
    png = tmp_path / "MCS_MOOSE_3x3_LINEAR.png"
    png.write_bytes(SECURITY.PNG_SIGNATURE + b"SYNTHETIC")
    SECURITY.check_png(png)
    raw = tmp_path / "raw.txt"
    raw.write_bytes(png.read_bytes())
    with pytest.raises(SECURITY.BoundaryError):
        SECURITY.check_png(raw)
    png.unlink()
    png.symlink_to(raw)
    with pytest.raises(SECURITY.BoundaryError):
        SECURITY.check_png(png)


def test_approval_cli_uses_mocked_environment_and_outputs_only_sha(
    monkeypatch, tmp_path, capsys, approved_env, protected_environment
):
    for name, value in approved_env.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("GH_TOKEN", "SYNTHETIC_TOKEN")
    output = tmp_path / "github-output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    monkeypatch.setattr(SECURITY, "github_environment", lambda token: protected_environment)
    assert SECURITY.main(["--check-approvals"]) == 0
    assert output.read_text() == f"approved_sha={TEST_SHA}\n"
    assert capsys.readouterr().out == "MCS_COMPARISON_APPROVAL_GATE=PASS\n"


def test_restore_cli_does_not_print_archive_input(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("PRIVATE_RATES_B64", "SYNTHETIC_NOT_BASE64")
    assert SECURITY.main(["--restore", str(tmp_path / "rates")]) == 1
    assert capsys.readouterr().out == "::error::Private Lookup package unavailable or invalid\n"


@pytest.fixture
def workflow():
    return yaml.safe_load((ROOT / ".github/workflows/mcs-oxygen-private-lookup-compare.yml").read_text())


def test_workflow_keeps_tests_and_approval_gate_secret_free(workflow):
    jobs = workflow["jobs"]
    for name in ("synthetic-tests", "approval-gate"):
        text = json.dumps(jobs[name])
        assert "secrets." not in text
        assert "PRIVATE_RATES" not in text
        assert "environment" not in jobs[name]
        assert "upload-artifact" not in text
    assert workflow["permissions"] == {"contents": "read"}
    assert "--check-approvals" in json.dumps(jobs["approval-gate"])


def test_private_workflow_is_exact_head_dispatch_only_with_independent_review(workflow):
    triggers = workflow.get("on", workflow.get(True))  # PyYAML 1.1 treats 'on' as boolean.
    assert set(triggers) == {"push", "pull_request", "workflow_dispatch"}
    assert "pull_request_target" not in triggers
    private = workflow["jobs"]["compare-oxygen-rate-coefficients"]
    assert private["needs"] == ["synthetic-tests", "approval-gate"]
    assert private["environment"] == SECURITY.ENVIRONMENT
    for condition in (
        "github.event_name == 'workflow_dispatch'",
        "needs.approval-gate.outputs.approved_sha == github.sha",
        "inputs.expected_sha == github.sha",
        "vars.MCS_CODE_REVIEWED_SHA == github.sha",
        "vars.MCS_PNG_PUBLIC_DISCLOSURE_SHA == github.sha",
    ):
        assert condition in private["if"]
    for job in workflow["jobs"].values():
        for step in job["steps"]:
            if str(step.get("uses", "")).startswith("actions/checkout@"):
                assert step["with"]["ref"] == "${{ github.sha }}"
                assert step["with"]["persist-credentials"] is False


def test_only_exact_png_is_uploaded_with_one_day_retention(workflow):
    uploads = [
        step for job in workflow["jobs"].values() for step in job["steps"]
        if str(step.get("uses", "")).startswith("actions/upload-artifact@")
    ]
    assert len(uploads) == 1
    upload = uploads[0]["with"]
    assert upload["path"] == (
        "${{ runner.temp }}/mcs-lookup-comparison-${{ github.run_id }}-${{ github.run_attempt }}"
        "/output/MCS_MOOSE_3x3_LINEAR.png"
    )
    assert "*" not in upload["path"]
    assert upload["retention-days"] == 1
    assert upload["if-no-files-found"] == "error"
    assert upload["include-hidden-files"] is False


def test_private_restoration_diagnostics_and_cleanup_stay_outside_checkout(workflow):
    private = workflow["jobs"]["compare-oxygen-rate-coefficients"]
    assert private["env"]["PRIVATE_ROOT"].startswith("${{ runner.temp }}/")
    restore = next(step for step in private["steps"] if "PRIVATE_RATES_B64" in step.get("env", {}))
    assert restore["env"] == {"PRIVATE_RATES_B64": "${{ secrets.OXYGEN24_RATES_TAR_XZ_B64 }}"}
    assert "--restore" in restore["run"] and "umask 077" in restore["run"]
    render = next(step for step in private["steps"] if "--mode linear-3x3" in step.get("run", ""))
    assert '> "$PRIVATE_ROOT/comparison.log" 2>&1' in render["run"]
    assert "--require-complete-mcs" in render["run"]
    assert "mcs_oxygen_supplemental_reactions_20261104.csv" in render["run"]
    cleanup = private["steps"][-1]
    assert cleanup["if"] == "always()"
    assert '.owned-by-comparison-job' in cleanup["run"]
    assert 'rm -rf -- "$PRIVATE_ROOT"' in cleanup["run"]
