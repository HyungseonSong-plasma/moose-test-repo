import base64
from copy import deepcopy
from hashlib import sha1, sha256
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from physics_harness.execution import controller_contract_ingress as m

BASE = "a" * 40
HEAD = "b" * 40
PIN = "c" * 40
BRANCH = "issue-888-checkpoint-qualification-123456abcdef"
REPO = {"id": m.REPO_ID, "full_name": m.REPO}
OWNER = {"id": m.OWNER_ID}


class Fake:
    def __init__(self, root):
        self.root = root
        for p in m.SOURCE_PATHS:
            f = root / p
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(json.dumps({"operating_system": {"revision": PIN}}) if p.endswith('central_skills.json') else 'fixture')
        self.request = {"schema_version": 1, "expected_main_sha": BASE,
                        "expected_contract_sha256": sha256((root / m.CONTRACT).read_bytes()).hexdigest(),
                        "expected_samuel_pin": PIN}
        self.upstream = dict(id=1, workflow_id=11, path=m.CI_PATH, event="pull_request", status="completed",
                             conclusion="success", run_attempt=1, repository=REPO, head_repository=REPO,
                             actor=OWNER, triggering_actor=OWNER, head_branch=BRANCH, head_sha=HEAD)
        self.ingress = dict(id=2, workflow_id=12, path=m.WORKFLOW, event="workflow_run", run_attempt=1,
                            head_sha=BASE, head_branch="main", display_title="checkpoint-ingress:"+HEAD,
                            repository=REPO, head_repository=REPO)
        self.pr = dict(number=900, state="open", draft=True, merged=False, user=OWNER,
                       head={"repo":REPO,"ref":BRANCH,"sha":HEAD}, base={"repo":REPO,"ref":"main","sha":BASE})
        self.commit = {"sha":HEAD,"parents":[{"sha":BASE}],"files":[{"filename":m.REQUEST_PATH,"status":"added"}]}
        self.prs = [self.pr]
        self.runs = {"pull_request":[self.upstream],"workflow_run":[self.ingress],"workflow_dispatch":[]}
        self.refs = {"main": BASE, BRANCH: HEAD}
        self.raw_override = None
        self.truncated = False
        self.calls = []
    def get(self, path, *, query=None):
        self.calls.append((path,query))
        if path == "/actions/runs/1": return deepcopy(self.upstream)
        if path == "/actions/runs/2": return deepcopy(self.ingress)
        if path == "/pulls": return deepcopy(self.prs)
        if path == "/pulls/900": return deepcopy(self.pr)
        raw = self.raw_override if self.raw_override is not None else json.dumps(self.request).encode()
        blob = sha1(f"blob {len(raw)}\0".encode()+raw).hexdigest()
        if path == "/commits/"+HEAD:
            result = deepcopy(self.commit)
            for file in result["files"]: file["sha"] = blob
            return result
        if path == "/contents/"+m.REQUEST_PATH:
            return dict(type="file",path=m.REQUEST_PATH,encoding="base64",sha=blob,size=len(raw),content=base64.b64encode(raw).decode())
        if path.startswith("/git/ref/heads/"): return {"object":{"sha":self.refs[path.split('/')[-1]]}}
        if path.startswith("/actions/workflows/"):
            runs = deepcopy(self.runs[query["event"]])
            return {"total_count":len(runs)+(1 if self.truncated else 0),"workflow_runs":runs}
        raise AssertionError(path)
    def bind(self, **kw):
        args = dict(root=self.root, main_sha=BASE, upstream_id=1, ingress_id=2, ingress_attempt=1)
        return m.bind_request(self, **(args|kw))


@pytest.fixture
def fake(tmp_path): return Fake(tmp_path)


def test_exact_request_only_pr(fake):
    r,b = fake.bind()
    assert r.source_sha == BASE and r.samuel_pin == PIN
    assert r.correlation_id == "checkpoint-request-" + HEAD
    assert r.dispatch_kwargs()["workflow"] == "controller-checkpoint-contract.yml"
    assert b["pr_number"] == 900


@pytest.mark.parametrize('field,value', [('event','push'),('conclusion','failure'),('run_attempt',2),('actor',{'id':1}),('triggering_actor',{'id':1}),('head_repository',{'id':1}),('head_branch','issue-888-checkpoint-qualification-other'),('path','.github/workflows/other.yml')])
def test_upstream_identity(fake, field, value):
    fake.upstream[field]=value
    with pytest.raises(ValueError,match='UPSTREAM_NOT_AUTHORIZED'): fake.bind()


@pytest.mark.parametrize('field,value', [('event','workflow_dispatch'),('head_sha','d'*40),('display_title','wrong'),('run_attempt',2)])
def test_ingress_identity(fake, field, value):
    fake.ingress[field]=value
    with pytest.raises(ValueError,match='INGRESS_RUN_MISMATCH'): fake.bind()


@pytest.mark.parametrize('key,value', [('expected_main_sha','d'*40),('expected_contract_sha256','d'*64),('expected_samuel_pin','d'*40)])
def test_stale_request(fake,key,value):
    fake.request[key]=value
    with pytest.raises(ValueError,match='REQUEST_STALE_CONTRACT'): fake.bind()


def test_arbitrary_dispatch_rejected(fake):
    fake.request['workflow']='other.yml'
    with pytest.raises(ValueError,match='REQUEST_SCHEMA'): fake.bind()


def test_duplicate_request_key(fake):
    fake.raw_override=b'{"schema_version":1,"schema_version":1}'
    with pytest.raises(ValueError,match='DUPLICATE_REQUEST_FIELD'): fake.bind()


def test_no_pr(fake):
    fake.prs=[]
    with pytest.raises(ValueError,match='INDEPENDENT_PR_REQUIRED'): fake.bind()


def test_non_draft_pr(fake):
    fake.pr['draft']=False
    with pytest.raises(ValueError,match='PR_IDENTITY_MISMATCH'): fake.bind()


def test_source_change_rejected(fake):
    fake.commit['files'].append({'filename':'some.py','status':'modified'})
    with pytest.raises(ValueError,match='REQUEST_ONLY_COMMIT_REQUIRED'): fake.bind()


def test_wrong_parent(fake):
    fake.commit['parents']=[{'sha':'d'*40}]
    with pytest.raises(ValueError,match='REQUEST_ONLY_COMMIT_REQUIRED'): fake.bind()


def test_upstream_duplicate(fake):
    fake.runs['pull_request'].append({'id':3})
    with pytest.raises(ValueError,match='UPSTREAM_AMBIGUOUS'): fake.bind()


def test_ingress_duplicate(fake):
    fake.runs['workflow_run'].append(fake.ingress|{'id':3})
    with pytest.raises(ValueError,match='INGRESS_AMBIGUOUS'): fake.bind()


def test_already_dispatched(fake):
    fake.runs['workflow_dispatch']=[{'id':3,'display_title':'checkpoint-contract:checkpoint-request-'+HEAD}]
    with pytest.raises(ValueError,match='CHILD_ALREADY_EXISTS'): fake.bind()


def test_partial_inventory(fake):
    fake.truncated=True
    with pytest.raises(ValueError,match='INCOMPLETE_RUN_ENUMERATION'): fake.bind()


def test_main_drift(fake):
    fake.refs['main']='d'*40
    with pytest.raises(ValueError,match='LIVE_HEAD_CHANGED'): fake.bind()


def test_branch_drift(fake):
    fake.refs[BRANCH]='d'*40
    with pytest.raises(ValueError,match='LIVE_HEAD_CHANGED'): fake.bind()


def test_rerun(fake):
    with pytest.raises(ValueError,match='INGRESS_IDENTITY_OR_REPLAY'): fake.bind(ingress_attempt=2)


def test_dispatch_reuses_samuel_and_preserves_receipt(fake):
    output=fake.root/'receipt.json'
    calls=[]
    def dispatch(transport, **kw):
        assert json.loads(output.read_text())['status']=='DISPATCH_OUTCOME_UNKNOWN'
        calls.append(kw)
        return {'workflow_run_id':123,'correlation_id':kw['correlation_id']}
    runtime=SimpleNamespace(dispatch_workflow=dispatch)
    kw=dict(root=fake.root,main_sha=BASE,upstream_id=1,ingress_id=2,ingress_attempt=1,output=output,samuel_runtime=runtime)
    assert m.execute(fake, **kw)['workflow_run_id']==123
    assert json.loads(output.read_text())['dispatch']['workflow_run_id']==123
    with pytest.raises(FileExistsError): m.execute(fake, **kw)
    assert len(calls)==1


def test_unknown_dispatch_not_replayed(fake):
    output=fake.root/'receipt.json'
    def fail(*args,**kw): raise TimeoutError('unknown outcome')
    kw=dict(root=fake.root,main_sha=BASE,upstream_id=1,ingress_id=2,ingress_attempt=1,output=output,
            samuel_runtime=SimpleNamespace(dispatch_workflow=fail))
    with pytest.raises(TimeoutError): m.execute(fake, **kw)
    assert json.loads(output.read_text())['status']=='DISPATCH_OUTCOME_UNKNOWN'
    with pytest.raises(FileExistsError): m.execute(fake, **kw)


@pytest.mark.parametrize("event,reason", [("workflow_run", "INGRESS_TITLE_MISSING"), ("workflow_dispatch", "CHILD_TITLE_MISSING")])
def test_missing_title_is_not_proof_of_absence(fake, event, reason):
    fake.runs[event].append({"id":99})
    with pytest.raises(ValueError, match=reason): fake.bind()
