"""Fresh local clones with pinned Samuel codec; no real GitHub writes."""
from dataclasses import replace
import subprocess
import pytest
from chatgpt_operation.controller.research import ResearchState
from chatgpt_operation.controller.durable_state import encode_state, decode_state, require_fresh_write
from physics_harness.execution.controller_pr_state import PRBinding, PRStateSnapshot, PRStateHold, plan_pr_state
from physics_harness.execution.controller_git_evidence import GitEvidence
from physics_harness.execution.controller_pr_restore import RestoreAnchor, PRHeadObservation, restore_pr_state

A=PRBinding('owner/repo', 8, 'issue-8', 'work-8')
B=PRBinding('owner/repo', 9, 'issue-9', 'work-9')


def git(repo,*args):
    return subprocess.run(['git','-C',str(repo),*args],check=True,capture_output=True,timeout=20).stdout.decode().strip()


def commit(repo,msg):
    git(repo,'add','.'); git(repo,'commit','-m',msg); return git(repo,'rev-parse','HEAD')


@pytest.fixture
def scenario(tmp_path):
    seed=tmp_path/'seed'; seed.mkdir(); git(seed,'init','--initial-branch=main')
    git(seed,'config','user.name','test'); git(seed,'config','user.email','test@example.invalid')
    (seed/'seed.txt').write_text('base'); base=commit(seed,'base')
    state=ResearchState(A.work_id,'restore test',revision=0)
    initial=PRStateSnapshot(A,base,0,encode_state(state),'a'*64)
    current=initial; plans=[]
    for i in (1,2):
        (seed/'seed.txt').write_text(str(i)); code=commit(seed,'code')
        plan=plan_pr_state(binding=A,base=replace(current,head=code),proposed=replace(state,revision=i),
             encode_state=encode_state,decode_state=decode_state,require_fresh_write=require_fresh_write)
        f=seed/plan.path; f.parent.mkdir(parents=True,exist_ok=True); f.write_bytes(plan.record)
        head=commit(seed,'state'); current=PRStateSnapshot(A,head,i,encode_state(replace(state,revision=i)),plan.record_sha256)
        plans.append(plan)
    (seed/'seed.txt').write_text('latest code'); head=commit(seed,'latest code')
    fresh=tmp_path/'fresh'; git(tmp_path,'clone',str(seed),str(fresh))
    git(fresh,'config','user.name','test'); git(fresh,'config','user.email','test@example.invalid')
    return fresh,initial,plans,head


def run(scenario,**kw):
    repo,initial,plans,head=scenario
    args=dict(reader=GitEvidence(repo),binding=A,anchor=RestoreAnchor(initial,2,plans[-1].record_sha256),
              observe_head=lambda b:PRHeadObservation(b,head),verify_anchor=lambda b,a:True,
              encode_state=encode_state,decode_state=decode_state,require_fresh_write=require_fresh_write)
    return restore_pr_state(**(args|kw))


def test_fresh_clone_restores_latest_incomplete_checkpoint(scenario):
    result=run(scenario)
    assert result.records_checked==2 and result.snapshot.revision==2 and result.snapshot.head==scenario[-1]
    assert decode_state(result.snapshot.body).progress_checkpoint is None
    assert not result.execution_authorized


def test_untrusted_anchor_rejected(scenario):
    with pytest.raises(PRStateHold,match='ANCHOR_UNVERIFIED'): run(scenario,verify_anchor=lambda b,a:False)


def test_wrong_minimum_digest(scenario):
    with pytest.raises(PRStateHold,match='TIP_MISMATCH'): run(scenario,anchor=RestoreAnchor(scenario[1],2,'b'*64))


def test_rollback_to_initial_head(scenario):
    with pytest.raises(PRStateHold,match='ROLLBACK'): run(scenario,observe_head=lambda b:PRHeadObservation(b,scenario[1].head))


def test_head_changes_during_restore(scenario):
    observations=iter([PRHeadObservation(A,scenario[-1]),PRHeadObservation(A,scenario[1].head)])
    with pytest.raises(PRStateHold,match='HEAD_CHANGED'): run(scenario,observe_head=lambda b:next(observations))


def test_wrong_pr_binding(scenario):
    with pytest.raises(PRStateHold,match='HEAD_UNVERIFIED'): run(scenario,observe_head=lambda b:PRHeadObservation(B,scenario[-1]))


def test_edit_then_revert_rejected(scenario):
    repo,initial,plans,_=scenario; path=repo/plans[0].path
    path.write_bytes(b'tampered'); commit(repo,'edit'); path.write_bytes(plans[0].record); head=commit(repo,'restore')
    with pytest.raises(PRStateHold,match='STATE_EDIT_OR_FOREIGN_WRITE'): run((repo,initial,plans,head))


def test_foreign_state_write_rejected(scenario):
    repo,initial,plans,_=scenario; path=repo/B.prefix/'r0000000000000001.json'; path.parent.mkdir(parents=True); path.write_bytes(b'foreign')
    head=commit(repo,'foreign')
    with pytest.raises(PRStateHold,match='STATE_EDIT_OR_FOREIGN_WRITE'): run((repo,initial,plans,head))


def test_missing_history_not_enrollment(scenario):
    with pytest.raises(PRStateHold,match='ANCHOR_UNVERIFIED'): run(scenario,anchor=None)


def test_no_records_valid_only_at_verified_initial_anchor(scenario):
    initial=scenario[1]; result=run(scenario,anchor=RestoreAnchor(initial,0,initial.record_sha256),observe_head=lambda b:PRHeadObservation(b,initial.head))
    assert result.records_checked==0 and result.snapshot==initial and not result.execution_authorized
