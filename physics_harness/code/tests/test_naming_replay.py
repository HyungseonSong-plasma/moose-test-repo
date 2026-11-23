from hashlib import sha256
import pytest
from physics_harness.code.verification.junit_compare import ReplayArtifact, compare_replay_artifacts

A = 'a'*40
B = 'b'*40

def artifact(sha, cases, *, digest=None, run='ci-run'):
    xml = ('<testsuite>' + cases + '</testsuite>').encode()
    return ReplayArtifact(sha, xml, digest or sha256(xml).hexdigest(), run)

def test_equal_green_still_hold():
    x = '<testcase classname="a" name="one"/>'
    result = compare_replay_artifacts(artifact(A,x),artifact(B,x))
    assert result.status == 'HOLD' and not result.mutation_approved
    assert 'AUTHENTICATE_CI_PRODUCER_AND_ARTIFACT_ORIGIN' in result.unresolved

def test_removed_test_blocks():
    x = '<testcase classname="a" name="one"/>'
    assert 'BASELINE_TEST_MISSING:a::one' in compare_replay_artifacts(artifact(A,x),artifact(B,'<testcase name="two"/>')).blockers

def test_changed_body_failure_blocks():
    x = '<testcase classname="a" name="one"/>'
    y = '<testcase classname="a" name="one"><failure/></testcase>'
    assert 'CANDIDATE_TEST_FAILED:a::one' in compare_replay_artifacts(artifact(A,x),artifact(B,y)).blockers

def test_skipped_holds():
    x = '<testcase name="one"/>'
    y = '<testcase name="one"><skipped/></testcase>'
    result=compare_replay_artifacts(artifact(A,x),artifact(B,y))
    assert result.status == 'HOLD' and 'CANDIDATE_TEST_SKIPPED:::one' in result.unresolved

def test_digest_mismatch_blocks():
    x = '<testcase name="one"/>'
    assert 'JUNIT_DIGEST_MISMATCH' in compare_replay_artifacts(artifact(A,x),artifact(B,x,digest='0'*64)).blockers

def test_duplicate_test_ids_block():
    x = '<testcase name="one"/><testcase name="one"/>'
    assert 'MISSING_OR_DUPLICATE_TEST_ID' in compare_replay_artifacts(artifact(A,x),artifact(B,x)).blockers

def test_dtd_blocks():
    x = '<!DOCTYPE testsuite [<!ENTITY x "evil">]><testsuite><testcase name="one"/></testsuite>'
    raw=x.encode()
    y=ReplayArtifact(A,raw,sha256(raw).hexdigest(),'run')
    assert 'UNTRUSTED_XML_DECLARATION' in compare_replay_artifacts(y,artifact(B,'<testcase name="one"/>')).blockers

def test_same_commit_blocks():
    x = '<testcase name="one"/>'
    assert 'CANDIDATE_REVISION_NOT_DISTINCT' in compare_replay_artifacts(artifact(A,x),artifact(A,x)).blockers

def test_new_test_is_uncertainty():
    x='<testcase name="one"/>'
    y=x+'<testcase name="two"/>'
    assert 'NEW_CANDIDATE_TEST:::two' in compare_replay_artifacts(artifact(A,x),artifact(B,y)).unresolved

def test_size_limit_holds():
    x='<testcase name="one"/>'
    assert 'JUNIT_SIZE_LIMIT' in compare_replay_artifacts(artifact(A,x),artifact(B,x),max_xml_bytes=4).unresolved

def test_invalid_input_raises():
    with pytest.raises(TypeError): compare_replay_artifacts(None,None)
    with pytest.raises(ValueError): compare_replay_artifacts(artifact(A,''),artifact(B,''),max_xml_bytes=0)


def test_replay_must_bind_candidate_revision():
    from physics_harness.code.verification.junit_compare import compare_candidate_replay
    x = '<testcase name="one"/>'
    result = compare_candidate_replay(A, 'c'*40, artifact(A,x), artifact(B,x))
    assert result.status == 'BLOCKED'
    assert 'REPLAY_REVISION_DOES_NOT_MATCH_NAMING_CANDIDATE' in result.blockers
