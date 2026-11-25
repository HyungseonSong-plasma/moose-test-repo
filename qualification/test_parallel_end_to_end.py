"""Local bare Git + separate clones + pinned Samuel portions; never GitHub writes."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
import json
import subprocess
from threading import Barrier

import pytest
from chatgpt_operation.controller.research import ResearchState
from chatgpt_operation.controller.durable_state import encode_state, decode_state, require_fresh_write
from chatgpt_operation.controller.progress_resume import detail_digest, validate_checkpoint
from physics_harness.execution.controller_pr_state import PRBinding, PRStateSnapshot, plan_pr_state, classify_publication
from physics_harness.execution.controller_merge_reconciliation import PRMergeSource, UnitRequirement, GateEvidence, reconcile_merge
from physics_harness.execution.controller_git_evidence import GitEvidence

PLAN, POLICY, INPUT, ANCHOR = ('a'*64,'b'*64,'c'*64,'d'*64)
A=PRBinding('owner/repo',1,'issue-a','work-a')
B=PRBinding('owner/repo',2,'issue-b','work-b')


def git(repo,*args,check=True):
    result=subprocess.run(['git','-C',str(repo),*args],capture_output=True,check=check,timeout=20)
    return result.stdout if check else result


def configure(repo):
    git(repo,'config','user.name','local-test'); git(repo,'config','user.email','local@example.invalid')


def commit(repo,message):
    git(repo,'add','.'); git(repo,'commit','-m',message)
    return git(repo,'rev-parse','HEAD').decode().strip()


def run_check(repo,head):
    # Exercise actual candidate content, not a constant success callback.
    a=git(repo,'show',head+':a.txt').strip(); b=git(repo,'show',head+':b.txt').strip()
    return a==b'2' and b==b'3' and int(a)+int(b)==5


@pytest.fixture
def scenario(tmp_path, request):
    remote=tmp_path/'remote'; remote.mkdir(); git(remote,'init','--bare','--initial-branch=main')
    seed=tmp_path/'seed'; seed.mkdir(); git(seed,'init','--initial-branch=main'); configure(seed)
    (seed/'a.txt').write_text('1\n'); (seed/'b.txt').write_text('1\n')
    basehead=commit(seed,'base'); git(seed,'remote','add','origin',str(remote))
    for branch in ('main',A.branch,B.branch): git(seed,'push','origin','HEAD:refs/heads/'+branch)
    barrier=Barrier(2)
    def worker(binding,filename,value):
        root=tmp_path/binding.branch; git(tmp_path,'clone','-b',binding.branch,str(remote),str(root)); configure(root)
        (root/filename).write_text(value+'\n'); code_head=commit(root,'code')
        before=ResearchState(binding.work_id,'local qualification',revision=0)
        evidence={'code_head':code_head,'path':filename,'sha256':sha256((value+'\n').encode()).hexdigest()}
        cp=dict(schema_version=1,work_id=binding.work_id,plan_sha256=PLAN,policy_sha256=POLICY,
                units=[dict(id='unit',input_sha256=INPUT,requires=[],gates=[])],
                receipts={'0':dict(outcome='PASS',input_sha256=INPUT,detail=evidence,detail_sha256=detail_digest(evidence))})
        after=replace(before,revision=1,progress_checkpoint=cp)
        p=plan_pr_state(binding=binding,base=PRStateSnapshot(binding,code_head,0,encode_state(before),ANCHOR),proposed=after,
            encode_state=encode_state,decode_state=decode_state,require_fresh_write=require_fresh_write)
        path=root/p.path; path.parent.mkdir(parents=True); path.write_bytes(p.record)
        head=commit(root,'state'); barrier.wait(timeout=10)
        git(root,'push','origin','HEAD:refs/heads/'+binding.branch)
        return binding,p,head
    with ThreadPoolExecutor(max_workers=2) as pool:
        fa=pool.submit(worker,A,'a.txt','2'); fb=pool.submit(worker,B,'b.txt',getattr(request,'param','3')); plans=(fa.result(),fb.result())
    # New clone: no state/lock files shared with either writer.
    fresh=tmp_path/'fresh'; git(tmp_path,'clone',str(remote),str(fresh)); configure(fresh)
    reader=GitEvidence(fresh); base=reader.tree(basehead); sources=[]
    for binding,p,head in plans:
        assert git(fresh,'rev-parse','origin/'+binding.branch).decode().strip()==head
        source=PRMergeSource(binding,basehead,reader.tree(head),0,ANCHOR,PLAN,POLICY,(UnitRequirement('unit',INPUT),),{p.path:p.record})
        assert reader.verify_source_history(base,source)
        assert classify_publication(p,binding=binding,current_head=head,record_at_path=git(fresh,'show',head+':'+p.path),verified_record_commit=True)=='RECORD_OBSERVED'
        sources.append(source)
        git(fresh,'merge','--no-ff','--no-edit','origin/'+binding.branch)
    head=git(fresh,'rev-parse','HEAD').decode().strip()
    return fresh,reader,base,tuple(sources),head,plans


def assess(scenario,head=None,gates_head=None,**overrides):
    root,reader,base,sources,original,plans=scenario; head=head or original
    candidate=reader.tree(head)
    enrolled=tuple((s.binding,s.tree.head) for s in sources)
    def verify_inventory(base,inventory): return inventory==enrolled
    def verify_source(base,s):
        return reader.verify_source_history(base,s) and git(root,'rev-parse','origin/'+s.binding.branch).decode().strip()==s.tree.head
    def verify_receipt(s,unit,r):
        d=r['detail']; code=d['code_head']; content=git(root,'show',code+':'+d['path'])
        return unit=='unit' and sha256(content).hexdigest()==d['sha256'] and git(root,'merge-base','--is-ancestor',code,s.tree.head,check=False).returncode==0 and git(root,'show',s.tree.head+':'+d['path'])==content
    def verify_gate(base,sources,candidate,g):
        return g.evidence_ref=='local-test:'+candidate.head and run_check(root,candidate.head)
    return reconcile_merge(**(dict(base=base,sources=sources,candidate=candidate,expected_sources=enrolled,
        gate_evidence=tuple(GateEvidence(g,gates_head or head,'PASS','local-test:'+(gates_head or head)) for g in ('semantic_compatibility','integrated_validation')),
        decode_state=decode_state,validate_checkpoint=validate_checkpoint,verify_tree=reader.verify_tree,
        verify_inventory=verify_inventory,verify_source=verify_source,verify_receipt=verify_receipt,verify_gate=verify_gate)|overrides))


def test_parallel_writers_fresh_runner_merge(scenario):
    r=assess(scenario); assert r.status=='READY_FOR_REVIEW',r.reasons
    assert r.preserved_records==2 and r.covered_units==2 and not r.merge_authorized


def test_missing_record_after_merge(scenario):
    root,_,_,sources,_,_=scenario; git(root,'rm',next(iter(sources[0].records))); head=commit(root,'lost state')
    assert assess(scenario,head).reasons[0].startswith('CANDIDATE_TREE_MISMATCH:')


def test_stale_gate_after_head_change(scenario):
    root,_,_,_,original,_=scenario; git(root,'commit','--allow-empty','-m','changed head'); head=git(root,'rev-parse','HEAD').decode().strip()
    assert assess(scenario,head,gates_head=original).reasons[0].startswith('INTEGRATION_GATE_UNVERIFIED:')


def test_source_history_record_edit_reverted(scenario):
    root,reader,base,sources,_,_=scenario; s=sources[0]; git(root,'checkout','-b','tamper',s.tree.head)
    path,raw=next(iter(s.records.items())); (root/path).write_bytes(b'tampered'); commit(root,'tamper')
    (root/path).write_bytes(raw); head=commit(root,'restore')
    assert not reader.verify_source_history(base,replace(s,tree=reader.tree(head)))


@pytest.mark.parametrize('scenario',['4'],indirect=True)
def test_actual_semantic_mismatch_with_preserved_changes(scenario):
    r=assess(scenario)
    assert r.preserved_records==2 and r.covered_units==2
    assert r.reasons[0].startswith('INTEGRATION_GATE_UNVERIFIED:')


def test_unverified_semantics_holds_even_with_exact_tree(scenario):
    assert assess(scenario,verify_gate=lambda *a:False).reasons[0].startswith('INTEGRATION_GATE_UNVERIFIED:')


def test_forged_parent_in_record(scenario):
    root,reader,base,sources,_,_=scenario; s=sources[0]; path,raw=next(iter(s.records.items()))
    git(root,'checkout','-b','forged',s.tree.head+'^')
    doc=json.loads(raw); doc['expected_parent']='f'*40; data=(json.dumps(doc,sort_keys=True,separators=(',',':'))+'\n').encode()
    p=root/path; p.parent.mkdir(parents=True,exist_ok=True); p.write_bytes(data); head=commit(root,'forged parent')
    assert not reader.verify_source_history(base,replace(s,tree=reader.tree(head),records={path:data}))


def test_symlink_gitlink_and_exec_mode(tmp_path):
    git(tmp_path,'init','--initial-branch=main'); configure(tmp_path); (tmp_path/'file').write_text('a'); base=commit(tmp_path,'base')
    (tmp_path/'file').chmod(0o755); (tmp_path/'link').symlink_to('file'); git(tmp_path,'add','.'); git(tmp_path,'update-index','--add','--cacheinfo','160000,'+base+',submodule'); git(tmp_path,'commit','-m','modes')
    head=git(tmp_path,'rev-parse','HEAD').decode().strip(); t=GitEvidence(tmp_path).tree(head)
    assert t.entries['link'].mode=='120000' and t.entries['link'].sha256==sha256(b'file').hexdigest()
    assert t.entries['file'].mode=='100755'; assert t.entries['submodule'].sha256==sha256(base.encode()).hexdigest()
