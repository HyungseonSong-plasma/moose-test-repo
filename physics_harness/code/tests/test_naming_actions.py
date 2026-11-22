"""P0: GitHub run/job/artifact metadata is not self-declared naming safety."""
from __future__ import annotations
from dataclasses import replace
from hashlib import sha256
from io import BytesIO
from zipfile import ZipFile, ZipInfo
import pytest

from physics_harness.code.verification.naming_actions import (
    GitHubActionsRestReader, ActionsArtifactReceipt,
    verify_actions_junit_artifact, compare_actions_junit_replays,
)

REPO = "example/repo"
BEFORE, AFTER = "a" * 40, "b" * 40
JOB = "Harness Code pytest"
WORKFLOW = ".github/workflows/harness-code.yml"
STEP = "Verify exact source revision"
ARTIFACT = "harness-junit"
JUNIT = b'<testsuite><testcase classname="t" name="c"/></testsuite>'


def zip_bytes(xml=JUNIT, filename="junit.xml"):
    stream = BytesIO()
    with ZipFile(stream, "w") as z:
        z.writestr(filename, xml)
    return stream.getvalue()


class Fake:
    def __init__(self, revision=BEFORE, run_id=10):
        self.revision, self.run_id = revision, run_id
        self.run_obj = dict(id=run_id, repository=dict(full_name=REPO, id=7),
                            head_sha=revision, path=WORKFLOW,
                            run_attempt=1, status="completed", conclusion="success")
        self.job_items = [dict(id=21, name=JOB, status="completed", conclusion="success",
                               steps=[dict(name=STEP, conclusion="success")])]
        self.artifact_items = [dict(id=32, name=ARTIFACT, expired=False,
                                    workflow_run=dict(id=run_id, head_sha=revision, repository_id=7))]
        self.zip = zip_bytes()
        self.downloads = 0

    def run(self, repo, id):
        assert repo == REPO and id == self.run_id
        return self.run_obj

    def jobs(self, repo, id):
        assert repo == REPO and id == self.run_id
        return self.job_items

    def artifacts(self, repo, id):
        assert repo == REPO and id == self.run_id
        return self.artifact_items

    def archive(self, repo, id):
        assert repo == REPO and id == 32
        self.downloads += 1
        return self.zip


def inspect(f=None, *, revision=BEFORE, run_id=10, entry=None):
    f = f or Fake(revision, run_id)
    return verify_actions_junit_artifact(
        REPO, revision, run_id, job_name=JOB, artifact_name=ARTIFACT,
        workflow_path=WORKFLOW, source=f, junit_entry=entry,
        required_step_names=(STEP,))


def test_valid_source_association_is_metadata_only_and_not_authentication():
    r=inspect()
    assert r.status == "GITHUB_METADATA_WITNESSED"
    assert r.artifact_id == 32 and r.junit_xml == JUNIT
    assert r.junit_sha256 == sha256(JUNIT).hexdigest()
    assert r.archive_sha256 == sha256(zip_bytes()).hexdigest()
    assert r.source == "INJECTED_READER" and not r.producer_authenticated
    assert not r.mutation_approved
    assert "RUNNER_IDENTITY_AND_TOOLCHAIN_NOT_ATTESTED" in r.unresolved


def test_missing_real_junit_artifact_holds_without_download():
    f=Fake()
    f.artifact_items=[]
    r=inspect(f)
    assert r.status == "HOLD" and "JUNIT_ARTIFACT_NOT_UPLOADED" in r.unresolved
    assert f.downloads == 0


def test_other_non_junit_artifact_is_not_misclassified():
    f=Fake()
    f.artifact_items[0]["name"]="physics-architecture-census"
    assert inspect(f).status == "HOLD"
    assert f.downloads == 0


def test_wrong_run_sha_blocks_before_downloading():
    f=Fake()
    f.run_obj["head_sha"] = AFTER
    r=inspect(f)
    assert r.status == "BLOCKED" and "ACTIONS_RUN_NOT_EXACT_REVISION" in r.blockers
    assert f.downloads == 0


def test_wrong_run_id_repo_and_workflow_block():
    f=Fake()
    f.run_obj.update(id=12,path=".github/workflows/other.yml")
    f.run_obj["repository"]["full_name"]="other/repo"
    r=inspect(f)
    assert set(r.blockers) >= {"RUN_REPOSITORY_OR_ID_MISMATCH","WORKFLOW_PATH_MISMATCH"}


def test_failed_workflow_and_failed_job_block():
    f=Fake()
    f.run_obj["conclusion"]="failure"
    f.job_items[0]["conclusion"]="failure"
    r=inspect(f)
    assert "ACTIONS_RUN_NOT_SUCCESSFUL" in r.blockers
    assert "REQUIRED_JOB_DID_NOT_PASS" in r.blockers


def test_missing_required_exact_sha_step_blocks():
    f=Fake()
    f.job_items[0]["steps"][0]["conclusion"]="skipped"
    r=inspect(f)
    assert "REQUIRED_JOB_STEP_NOT_PASSED:"+STEP in r.blockers


def test_wrong_artifact_run_or_commit_association_blocks():
    f=Fake()
    f.artifact_items[0]["workflow_run"]["head_sha"] = AFTER
    f.artifact_items[0]["workflow_run"]["id"] = 9
    r=inspect(f)
    assert "ARTIFACT_RUN_SHA_ASSOCIATION_MISMATCH" in r.blockers
    assert f.downloads==0


def test_wrong_artifact_repo_blocks():
    f=Fake()
    f.artifact_items[0]["workflow_run"]["repository_id"] = 9
    assert "ARTIFACT_REPOSITORY_ASSOCIATION_MISMATCH" in inspect(f).blockers


def test_expired_artifact_holds():
    f=Fake()
    f.artifact_items[0]["expired"] = True
    r=inspect(f)
    assert "ACTIONS_ARTIFACT_EXPIRED_OR_UNKNOWN" in r.unresolved
    assert f.downloads == 0


def test_rerun_artifact_attempt_is_not_claimed():
    f=Fake()
    f.run_obj["run_attempt"] = 2
    r=inspect(f)
    assert r.status == "GITHUB_METADATA_WITNESSED"
    assert "ARTIFACT_RUN_ATTEMPT_NOT_PROVEN" in r.unresolved


def test_ambiguous_artifact_name_blocks():
    f=Fake()
    f.artifact_items.append(dict(f.artifact_items[0], id=33))
    r=inspect(f)
    assert "AMBIGUOUS_JUNIT_ARTIFACT_NAME" in r.blockers


def test_ambiguous_junit_xml_requires_selection():
    f=Fake()
    stream=BytesIO()
    with ZipFile(stream, "w") as z:
        z.writestr("one.xml",JUNIT)
        z.writestr("two.xml",JUNIT)
    f.zip=stream.getvalue()
    r=inspect(f)
    assert r.status == "BLOCKED"
    assert any("JUNIT_XML_AMBIGUOUS_OR_MISSING" in b for b in r.blockers)
    assert inspect(f,entry="one.xml").status == "GITHUB_METADATA_WITNESSED"


def test_zip_traversal_rejected():
    f=Fake()
    f.zip=zip_bytes(filename="../junit.xml")
    r=inspect(f)
    assert any("UNSAFE_ARCHIVE_ENTRY_PATH" in b for b in r.blockers)


def test_invalid_zip_rejected_without_source_pass():
    f=Fake()
    f.zip=b"not-a-zip"
    assert inspect(f).status == "BLOCKED"


def test_zip_symlink_rejected():
    stream=BytesIO()
    with ZipFile(stream,"w") as z:
        info=ZipInfo("junit.xml")
        info.create_system=3
        info.external_attr=(0o120777 << 16)
        z.writestr(info,JUNIT)
    f=Fake()
    f.zip=stream.getvalue()
    assert any("ARCHIVE_SYMLINK_UNSUPPORTED" in b for b in inspect(f).blockers)


def test_complete_two_revision_replay_never_approves_mutation():
    a=inspect(Fake(BEFORE,10),revision=BEFORE,run_id=10)
    b=inspect(Fake(AFTER,11),revision=AFTER,run_id=11)
    r=compare_actions_junit_replays(a,b)
    assert r.replay is not None and r.replay.status == "HOLD"
    assert r.status == "HOLD" and not r.mutation_approved
    assert "INJECTED_SOURCE_NOT_GITHUB_AUTHENTICATION" in r.unresolved


def test_candidate_test_failure_blocks_even_with_success_run():
    f=Fake(AFTER,11)
    f.zip=zip_bytes(b'<testsuite><testcase classname="t" name="c"><failure/></testcase></testsuite>')
    a=inspect(Fake(BEFORE,10),revision=BEFORE,run_id=10)
    b=inspect(f,revision=AFTER,run_id=11)
    r=compare_actions_junit_replays(a,b)
    assert r.status == "BLOCKED"
    assert "CANDIDATE_TEST_FAILED:t::c" in r.blockers


def test_baseline_test_missing_in_candidate_blocks():
    a=inspect(Fake(BEFORE,10),revision=BEFORE,run_id=10)
    f=Fake(AFTER,11)
    f.zip=zip_bytes(b'<testsuite><testcase classname="t" name="different"/></testsuite>')
    b=inspect(f,revision=AFTER,run_id=11)
    r=compare_actions_junit_replays(a,b)
    assert "BASELINE_TEST_MISSING:t::c" in r.blockers


def test_missing_artifact_pair_holds_without_fake_replay():
    f=Fake(AFTER,11)
    f.artifact_items=[]
    a=inspect(Fake(BEFORE,10),revision=BEFORE,run_id=10)
    b=inspect(f,revision=AFTER,run_id=11)
    r=compare_actions_junit_replays(a,b)
    assert r.replay is None
    assert "JUNIT_SOURCE_REPLAY_NOT_AVAILABLE" in r.unresolved


def test_cross_repository_pair_and_identical_revisions_block():
    a=inspect()
    b=replace(a,repository="other/repo")
    assert "CROSS_REPOSITORY_ACTIONS_REPLAY" in compare_actions_junit_replays(a,b).blockers
    assert "ACTIONS_REPLAY_REVISIONS_NOT_DISTINCT" in compare_actions_junit_replays(a,a).blockers


@pytest.mark.parametrize("repo,revision,run",[("bad",BEFORE,1),(REPO,"bad",1),(REPO,BEFORE,0)])
def test_invalid_identifiers_fail_fast(repo,revision,run):
    with pytest.raises(ValueError):
        verify_actions_junit_artifact(repo,revision,run,job_name=JOB,artifact_name=ARTIFACT,
                                      workflow_path=WORKFLOW,source=Fake())


def test_rest_source_has_no_mutating_endpoint_methods():
    reader=GitHubActionsRestReader()
    assert not hasattr(reader,"dispatch") and not hasattr(reader,"merge")
    assert not hasattr(reader,"upload")


def test_pagination_fails_closed_on_truncated_data_without_network(monkeypatch):
    reader=GitHubActionsRestReader()
    monkeypatch.setattr(reader,"_json",lambda endpoint:{"total_count":101,"artifacts":[{"id":1}]})
    with pytest.raises(ValueError,match="INCOMPLETE_GITHUB_PAGINATION"):
        reader.artifacts(REPO,1)


def test_junit_dtd_entity_rejected_before_replay():
    f=Fake()
    f.zip=zip_bytes(b'<!DOCTYPE testsuite [<!ENTITY x "unsafe">]><testsuite/>')
    r=inspect(f)
    assert r.status == "BLOCKED"
    assert any("JUNIT_XML_DTD_OR_ENTITY" in b for b in r.blockers)


def test_invalid_junit_root_rejected():
    f=Fake()
    f.zip=zip_bytes(b'<not-junit><testcase name="x"/></not-junit>')
    r=inspect(f)
    assert "GITHUB_SOURCE_OR_ARCHIVE_INVALID:INVALID_JUNIT_ROOT" in r.blockers


def test_partial_or_unavailable_source_remains_hold():
    f=Fake()
    def unavailable(repo,id):
        raise OSError("temporary error")
    f.run=unavailable
    r=inspect(f)
    assert r.status == "HOLD" and "GITHUB_SOURCE_OR_ARCHIVE_UNAVAILABLE:OSError" in r.unresolved


def test_live_entrypoint_fetches_both_exact_sha_runs_not_user_supplied_receipts():
    from physics_harness.code.verification.naming_actions import audit_actions_replay
    class Duplex:
        def __init__(self):
            self.by_id = {10: Fake(BEFORE, 10), 11: Fake(AFTER, 11)}
        def run(self, repo, run_id): return self.by_id[run_id].run(repo, run_id)
        def jobs(self, repo, run_id): return self.by_id[run_id].jobs(repo, run_id)
        def artifacts(self, repo, run_id): return self.by_id[run_id].artifacts(repo, run_id)
        def archive(self, repo, artifact_id):
            assert artifact_id == 32
            return self.by_id[10].zip
    result = audit_actions_replay(REPO, BEFORE, AFTER, 10, 11,
                                  job_name=JOB, artifact_name=ARTIFACT,
                                  workflow_path=WORKFLOW, source=Duplex(),
                                  required_step_names=(STEP,))
    assert result.replay is not None and result.status == "HOLD"
    assert not result.mutation_approved


def test_run_attempt_change_during_archive_download_blocks():
    f=Fake()
    original=f.run
    count=0
    def shifting_run(repo,id):
        nonlocal count
        count+=1
        if count>1:
            return dict(original(repo,id),run_attempt=2)
        return original(repo,id)
    f.run=shifting_run
    r=inspect(f)
    assert "ACTIONS_RUN_CHANGED_DURING_READ" in r.blockers
