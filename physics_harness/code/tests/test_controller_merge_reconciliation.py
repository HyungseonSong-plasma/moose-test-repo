"""Synthetic trusted ports and actual local Git tree observations."""
from dataclasses import asdict, dataclass, replace
from hashlib import sha256
import json
import subprocess

import pytest

from physics_harness.execution.controller_pr_state import PRBinding, PRStateSnapshot, plan_pr_state
from physics_harness.execution.controller_merge_reconciliation import (
    TreeEntry, TreeSnapshot, UnitRequirement, PRMergeSource, GateEvidence, reconcile_merge,
)

BASE = 'a'*40
A = PRBinding('owner/repo', 1, 'issue-a', 'work-a')
B = PRBinding('owner/repo', 2, 'issue-b', 'work-b')
PLAN, POLICY, INPUT, ANCHOR = ('a'*64, 'b'*64, 'c'*64, 'd'*64)

@dataclass
class State:
    research_id: str
    revision: int
    progress_checkpoint: dict | None = None


def encode(s):
    return '<!-- samuel-controller-state -->\n' + json.dumps(asdict(s), sort_keys=True)


def decode(body):
    return State(**json.loads(body.split('\n', 1)[1]))


def fresh(old, new):
    assert old.research_id == new.research_id and old.revision + 1 == new.revision


def checkpoint(binding, complete=True):
    return dict(schema_version=1, work_id=binding.work_id, plan_sha256=PLAN, policy_sha256=POLICY,
                units=[dict(id='u',input_sha256=INPUT,requires=[],gates=[])],
                receipts={'0': {'outcome':'PASS','detail':'proof'}} if complete else {})


def entry(data, mode='100644'):
    return TreeEntry(mode, sha256(data).hexdigest())


def source(binding=A, head='b'*40, base=None, changes=None, cp=None, records_count=1):
    base = base or TreeSnapshot(BASE, {'keep.py':entry(b'keep'), 'remove.py':entry(b'old')})
    tree = dict(base.entries)
    for p, e in (changes or {binding.branch+'.py':entry(b'new')}).items():
        if e is None:
            tree.pop(p,None)
        else:
            tree[p] = e
    records = {}
    old = State(binding.work_id,0)
    snapshot = PRStateSnapshot(binding,base.head,0,encode(old),ANCHOR)
    for i in range(1,records_count+1):
        proposed = State(binding.work_id,i,cp if cp is not None else checkpoint(binding))
        p = plan_pr_state(binding=binding,base=snapshot,proposed=proposed,encode_state=encode,
                          decode_state=decode,require_fresh_write=fresh)
        records[p.path] = p.record
        tree[p.path] = entry(p.record)
        snapshot = PRStateSnapshot(binding,head,i,encode(proposed),p.record_sha256)
    return PRMergeSource(binding,base.head,TreeSnapshot(head,tree),0,ANCHOR,PLAN,POLICY,
                         (UnitRequirement('u',INPUT),),records)


def setup():
    base = TreeSnapshot(BASE, {'keep.py':entry(b'keep'), 'remove.py':entry(b'old')})
    a = source(base=base,changes={'a.py':entry(b'a'),'remove.py':None})
    b = source(B,'c'*40,base,{'b.py':entry(b'b','100755')})
    tree = dict(a.tree.entries)
    tree.update({p:e for p,e in b.tree.entries.items() if base.entries.get(p)!=e})
    return base,a,b,TreeSnapshot('e'*40,tree)


def evaluate(base,a,b,candidate,**kwargs):
    sources=(a,b)
    gates=tuple(GateEvidence(g,candidate.head,'PASS','test-proof') for g in
                ('semantic_compatibility','integrated_validation'))
    return reconcile_merge(**(dict(base=base,sources=sources,candidate=candidate,
        expected_sources=tuple((s.binding,s.tree.head) for s in sources),gate_evidence=gates,
        decode_state=decode,validate_checkpoint=lambda cp:cp,verify_tree=lambda t:True,
        verify_inventory=lambda *a:True,verify_source=lambda *a:True,
        verify_receipt=lambda *a:True,verify_gate=lambda *a:True) | kwargs))


def test_disjoint_merge_preserves_deletion_mode_records_and_units():
    r=evaluate(*setup())
    assert r.status=='READY_FOR_REVIEW' and r.preserved_records==2 and r.covered_units==2
    assert not r.merge_authorized and not r.execution_authorized


@pytest.mark.parametrize('path,value', [('a.py',None),('b.py',entry(b'b')),
    ('remove.py',entry(b'old')),('keep.py',entry(b'altered')),('unexpected',entry(b'new'))])
def test_missing_or_extra_candidate_change(path,value):
    base,a,b,c=setup(); tree=dict(c.entries)
    if value is None: tree.pop(path)
    else: tree[path]=value
    r=evaluate(base,a,b,TreeSnapshot(c.head,tree))
    assert r.status=='HOLD' and 'CANDIDATE_TREE_MISMATCH:'+path in r.reasons


@pytest.mark.parametrize('mutate', ['missing','altered'])
def test_record_loss(mutate):
    base,a,b,c=setup(); tree=dict(c.entries); p=next(iter(a.records))
    if mutate=='missing': tree.pop(p)
    else: tree[p]=entry(b'changed')
    assert evaluate(base,a,b,TreeSnapshot(c.head,tree)).status=='HOLD'


def test_whole_pr_omitted():
    base,a,b,c=setup()
    r=evaluate(base,a,b,c,sources=(a,))
    assert r.reasons==('SOURCE_INVENTORY_MISMATCH',)


def test_same_work_competing_prs():
    base,a,b,c=setup(); b=source(replace(B,work_id=A.work_id),'c'*40,base)
    assert evaluate(base,a,b,c).reasons==('SAME_WORK_RECONCILIATION_REQUIRED',)


def test_divergent_file_change():
    base,a,b,c=setup(); b=source(B,'c'*40,base,{'a.py':entry(b'other')})
    assert evaluate(base,a,b,c).reasons==('DIVERGENT_PATH_CHANGE:a.py',)


def test_identical_file_change_allowed_with_gates():
    base,a,b,c=setup(); b=source(B,'c'*40,base,{'a.py':entry(b'a')})
    tree=dict(a.tree.entries); tree.update({p:b.tree.entries[p] for p in b.records})
    assert evaluate(base,a,b,TreeSnapshot(c.head,tree)).status=='READY_FOR_REVIEW'


@pytest.mark.parametrize('change,reason', [({'base_head':'f'*40},'COMMON_BASE_REQUIRED'),
    ({'initial_record_sha256':'f'*64},'RECORD_CHAIN_OR_IDENTITY_MISMATCH'),
    ({'initial_revision':1},'RECORD_REVISION_GAP'),
    ({'plan_sha256':'f'*64},'CHECKPOINT_SCOPE_MISMATCH'),
    ({'required_units':(UnitRequirement('missing',INPUT),)},'WORK_COVERAGE_MISMATCH')])
def test_stale_or_wrong_source(change,reason):
    base,a,b,c=setup(); assert evaluate(base,replace(a,**change),b,c).reasons==(reason,)


def test_incomplete_work():
    base,a,b,c=setup(); a=source(base=base,cp=checkpoint(A,False))
    assert evaluate(base,a,b,c).reasons==('WORK_UNIT_INCOMPLETE',)


@pytest.mark.parametrize('port,reason', [('verify_tree','TREE_EVIDENCE_UNVERIFIED'),
    ('verify_inventory','SOURCE_INVENTORY_MISMATCH'),('verify_source','SOURCE_EVIDENCE_UNVERIFIED'),
    ('verify_receipt','SOURCE_RECEIPT_UNVERIFIED')])
def test_untrusted_ports(port,reason):
    assert evaluate(*setup(),**{port:lambda *a:False}).reasons==(reason,)


@pytest.mark.parametrize('gates', [(),(GateEvidence('semantic_compatibility','e'*40,'PASS','proof'),),
    (GateEvidence('semantic_compatibility','f'*40,'PASS','proof'),GateEvidence('integrated_validation','e'*40,'PASS','proof')),
    (GateEvidence('semantic_compatibility','e'*40,'FAIL','proof'),GateEvidence('integrated_validation','e'*40,'PASS','proof'))])
def test_integration_gates_required_and_exact_head(gates):
    assert evaluate(*setup(),gate_evidence=gates).status=='HOLD'


def test_forged_gate_rejected():
    assert evaluate(*setup(),verify_gate=lambda *a:False).status=='HOLD'


def test_foreign_state_path():
    base,a,b,c=setup(); tree=dict(a.tree.entries); tree[B.prefix+'r0000000000000001.json']=entry(b'foreign')
    assert evaluate(base,replace(a,tree=TreeSnapshot(a.tree.head,tree)),b,c).reasons[0].startswith('FOREIGN_OR_HISTORICAL_STATE_MUTATION:')


def test_missing_record_inventory():
    base,a,b,c=setup(); tree=dict(a.tree.entries); tree[A.prefix+'r0000000000000002.json']=entry(b'extra')
    assert evaluate(base,replace(a,tree=TreeSnapshot(a.tree.head,tree)),b,c).reasons==('INCOMPLETE_RECORD_INVENTORY',)


def test_two_revision_chain_preserved():
    base,a,b,c=setup(); a=source(base=base,records_count=2)
    tree=dict(a.tree.entries); tree.update({p:e for p,e in b.tree.entries.items() if base.entries.get(p)!=e})
    r=evaluate(base,a,b,TreeSnapshot(c.head,tree)); assert r.status=='READY_FOR_REVIEW' and r.preserved_records==3


def test_port_exception_fail_closed():
    def fail(*args): raise OSError('offline')
    assert evaluate(*setup(),verify_tree=fail).reasons==('RECONCILIATION_EVIDENCE_UNAVAILABLE',)


def git(root,*args):
    return subprocess.check_output(['git','-C',str(root),*args])


def read_tree(root,ref):
    head=git(root,'rev-parse',ref).decode().strip(); entries={}
    for row in git(root,'ls-tree','-rz',head).split(b'\0'):
        if not row: continue
        meta,p=row.split(b'\t',1); mode,kind,oid=meta.decode().split()
        entries[p.decode()]=entry(git(root,'cat-file','blob',oid),mode)
    return TreeSnapshot(head,entries)


def test_actual_git_merge_and_silent_record_removal(tmp_path):
    git(tmp_path,'init','--initial-branch=main'); git(tmp_path,'config','user.name','test'); git(tmp_path,'config','user.email','test@example.invalid')
    (tmp_path/'keep.py').write_bytes(b'keep'); (tmp_path/'remove.py').write_bytes(b'old')
    git(tmp_path,'add','.'); git(tmp_path,'commit','-m','base'); base=read_tree(tmp_path,'main')
    sources=[]
    for binding in (A,B):
        git(tmp_path,'checkout','-b',binding.branch,base.head)
        s=source(binding,base=base,changes={binding.branch+'.py':entry(b'work')})
        (tmp_path/(binding.branch+'.py')).write_bytes(b'work')
        for p,raw in s.records.items():
            path=tmp_path/p; path.parent.mkdir(parents=True,exist_ok=True); path.write_bytes(raw)
        git(tmp_path,'add','.'); git(tmp_path,'commit','-m','work')
        sources.append(replace(s,tree=read_tree(tmp_path,'HEAD')))
    git(tmp_path,'checkout','main')
    for s in sources: git(tmp_path,'merge','--no-ff','--no-edit',s.binding.branch)
    c=read_tree(tmp_path,'HEAD'); assert evaluate(base,*sources,c).status=='READY_FOR_REVIEW'
    git(tmp_path,'rm',next(iter(sources[0].records))); git(tmp_path,'commit','-m','silent record removal')
    assert evaluate(base,*sources,read_tree(tmp_path,'HEAD')).status=='HOLD'
