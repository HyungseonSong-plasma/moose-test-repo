"""Optional exact-pin integration, run outside default MOOSE test suite."""
import json
from dataclasses import replace
import pytest
from chatgpt_operation.controller.research import ResearchState
from chatgpt_operation.controller.durable_state import encode_state, decode_state, require_fresh_write
from physics_harness.execution.controller_pr_state import PRBinding, PRStateSnapshot, PRStateHold, plan_pr_state

B = PRBinding('owner/repo', 908, 'issue-888-orchestrator', 'issue:888')

def make(old, proposed):
    return plan_pr_state(binding=B, base=PRStateSnapshot(B, 'a'*40, old.revision,
        encode_state(old), 'b'*64), proposed=proposed, encode_state=encode_state,
        decode_state=decode_state, require_fresh_write=require_fresh_write)

@pytest.mark.parametrize('progress,large', [(False, False), (True, False), (True, True)])
def test_pinned_codec_preserves_state(progress, large):
    old = ResearchState(B.work_id, 'test', revision=3)
    if progress:
        old.progress_checkpoint = dict(schema_version=1, work_id=B.work_id,
            plan_sha256='a'*64, policy_sha256='b'*64,
            units=[dict(id='u',input_sha256='c'*64,requires=[],gates=[])],receipts={})
    if large:
        old.inherited_evidence = [dict(text='x'*60_000)]
    new = replace(old, revision=4, completed_operation_ids=['op-1'])
    p = make(old,new)
    assert decode_state(json.loads(p.record)['state_body']) == new
    assert not p.write_authorized


def test_invalid_checkpoint_rejected():
    old = ResearchState(B.work_id, 'test', revision=3)
    new = replace(old, revision=4, progress_checkpoint={'bad':True})
    with pytest.raises(PRStateHold):
        make(old,new)
