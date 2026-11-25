"""Optional integration with pinned Samuel source; synthetic evidence providers."""
from dataclasses import replace
from hashlib import sha256

import pytest

from chatgpt_operation.controller.research import ResearchState
from chatgpt_operation.controller.durable_state import encode_state, decode_state, require_fresh_write
from chatgpt_operation.controller.progress_resume import validate_checkpoint, detail_digest
from physics_harness.execution.controller_pr_state import PRBinding, PRStateSnapshot, plan_pr_state
from physics_harness.execution.controller_merge_reconciliation import (
    TreeEntry, TreeSnapshot, UnitRequirement, PRMergeSource, GateEvidence, reconcile_merge,
)


def build(binding, head, base, complete=True, large=False):
    old=ResearchState(binding.work_id,'verify',revision=0)
    detail={'evidence':'x'*60_000 if large else 'receipt'}
    checkpoint=dict(schema_version=1,work_id=binding.work_id,plan_sha256='a'*64,
        policy_sha256='b'*64,units=[dict(id='unit',input_sha256='c'*64,requires=[],gates=[])],
        receipts={'0':dict(input_sha256='c'*64,outcome='PASS',detail=detail,
                          detail_sha256=detail_digest(detail))} if complete else {})
    new=replace(old,revision=1,progress_checkpoint=checkpoint)
    plan=plan_pr_state(binding=binding,base=PRStateSnapshot(binding,base.head,0,encode_state(old),'d'*64),
        proposed=new,encode_state=encode_state,decode_state=decode_state,require_fresh_write=require_fresh_write)
    tree=TreeSnapshot(head,dict(base.entries)|{plan.path:TreeEntry('100644',sha256(plan.record).hexdigest())})
    return PRMergeSource(binding,base.head,tree,0,'d'*64,'a'*64,'b'*64,
                         (UnitRequirement('unit','c'*64),),{plan.path:plan.record})


@pytest.mark.parametrize('complete,large,expected', [(True,False,'READY_FOR_REVIEW'),
    (True,True,'READY_FOR_REVIEW'),(False,False,'HOLD')])
def test_pinned_samuel_checkpoint_reconciliation(complete,large,expected):
    base=TreeSnapshot('a'*40,{})
    sources=(build(PRBinding('owner/repo',1,'issue-a','work-a'),'b'*40,base,complete,large),
             build(PRBinding('owner/repo',2,'issue-b','work-b'),'c'*40,base))
    candidate=TreeSnapshot('d'*40,dict(sources[0].tree.entries)|dict(sources[1].tree.entries))
    r=reconcile_merge(base=base,sources=sources,candidate=candidate,
        expected_sources=tuple((s.binding,s.tree.head) for s in sources),
        gate_evidence=tuple(GateEvidence(g,candidate.head,'PASS','synthetic') for g in
            ('semantic_compatibility','integrated_validation')),
        decode_state=decode_state,validate_checkpoint=validate_checkpoint,
        verify_tree=lambda *a:True,verify_inventory=lambda *a:True,verify_source=lambda *a:True,
        verify_receipt=lambda *a:True,verify_gate=lambda *a:True)
    assert r.status==expected
    if not complete: assert r.reasons==('WORK_UNIT_INCOMPLETE',)
