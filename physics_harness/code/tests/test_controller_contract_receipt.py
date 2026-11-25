from copy import deepcopy
from hashlib import sha256
from io import BytesIO
import json
from zipfile import ZipFile

import pytest
from physics_harness.execution.controller_contract_receipt import (
    REPO, WORKFLOW, SOURCE_PATHS, TESTS, ContractRequest, verify_receipt, dispatch_contract, observe_contract)


@pytest.fixture
def evidence():
    request = ContractRequest("a"*40, "b"*40, {p: "c"*64 for p in SOURCE_PATHS}, "cycle-1")
    run = dict(id=12, run_attempt=2, repository={"full_name": REPO}, head_repository={"full_name": REPO},
               path=WORKFLOW, event="workflow_dispatch", head_branch="main", head_sha=request.source_sha,
               display_title="checkpoint-contract:cycle-1", status="completed", conclusion="success")
    job = dict(id=13, run_id=12, run_attempt=2, head_sha=request.source_sha, name="qualify", status="completed", conclusion="success")
    junit = ('<testsuite>'+''.join(f'<testcase name="{n}"/>' for n in sorted(TESTS))+'</testsuite>').encode()
    receipt = dict(schema_version=1, repository=REPO, source_sha=request.source_sha,
                   samuel_pin=request.samuel_pin, source_sha256=dict(request.source_hashes), run_id="12", run_attempt="2",
                   correlation_id=request.correlation_id, tests_passed=sorted(TESTS), junit_sha256=sha256(junit).hexdigest(),
                   status="LOCAL_GIT_CONTRACT_QUALIFIED", live_connector_qualified=False, write_authorized=False)
    def pack(receipt=receipt, junit=junit, extra=False):
        buf = BytesIO()
        with ZipFile(buf, 'w') as z:
            z.writestr('checkpoint-contract-receipt.json', json.dumps(receipt))
            z.writestr('checkpoint-cas.xml', junit)
            if extra:
                z.writestr('unexpected', 'x')
        raw = buf.getvalue()
        artifact = dict(id=14, name='checkpoint-contract-12-2', expired=False,
                        workflow_run=dict(id=12, head_sha=request.source_sha), size_in_bytes=len(raw), digest='sha256:'+sha256(raw).hexdigest())
        return artifact, raw
    artifact, raw = pack()
    return request, dict(correlation_status='MATCHED_TERMINAL', matched_run_id=12, run=run, job=job, artifact=artifact, archive=raw), receipt, junit, pack


def test_valid_receipt_and_samuel_dispatch_args(evidence):
    request, kwargs, *_ = evidence
    result = verify_receipt(request, **kwargs)
    assert not result.write_authorized and not result.live_connector_qualified
    assert result.run_id == 12 and result.run_attempt == 2
    dispatch = request.dispatch_kwargs()
    assert dispatch['correlation_input'] == 'correlation_id' and dispatch['correlation_run_name_prefix'] == 'checkpoint-contract:'


@pytest.mark.parametrize('field,value', [('correlation_status','AMBIGUOUS_MATCH'),('matched_run_id',99)])
def test_bad_correlation(evidence, field, value):
    request, kwargs, *_ = evidence
    kwargs[field] = value
    with pytest.raises(ValueError): verify_receipt(request, **kwargs)


@pytest.mark.parametrize('section,field,value', [
    ('run','head_sha','d'*40), ('run','event','push'), ('run','display_title','checkpoint-contract:other'),
    ('run','conclusion','failure'), ('run','run_attempt',3), ('job','conclusion','skipped'),
    ('job','run_id',99), ('artifact','expired',True), ('artifact','digest','sha256:'+'d'*64),
    ('artifact','name','checkpoint-contract-12-1'), ('artifact','workflow_run',{'id':99})])
def test_wrong_metadata(evidence, section, field, value):
    request, kwargs, *_ = evidence
    kwargs[section][field] = value
    with pytest.raises(ValueError): verify_receipt(request, **kwargs)


@pytest.mark.parametrize('field,value', [('samuel_pin','d'*40), ('source_sha256',{}), ('run_attempt','1'),
                                        ('correlation_id','other'), ('write_authorized',True), ('live_connector_qualified',True), ('tests_passed',[])])
def test_bad_receipt(evidence, field, value):
    request, kwargs, receipt, junit, pack = evidence
    receipt[field] = value
    kwargs['artifact'], kwargs['archive'] = pack(receipt, junit)
    with pytest.raises(ValueError): verify_receipt(request, **kwargs)


def test_extra_archive_member(evidence):
    request, kwargs, receipt, junit, pack = evidence
    kwargs['artifact'], kwargs['archive'] = pack(receipt,junit,True)
    with pytest.raises(ValueError): verify_receipt(request, **kwargs)


def test_failed_junit_even_with_matching_hash(evidence):
    request, kwargs, receipt, junit, pack = evidence
    junit = junit.replace(b'/>',b'><failure/></testcase>',1)
    receipt['junit_sha256'] = sha256(junit).hexdigest()
    kwargs['artifact'], kwargs['archive'] = pack(receipt,junit)
    with pytest.raises(ValueError, match='JUNIT_NOT_QUALIFIED'): verify_receipt(request, **kwargs)


def test_existing_samuel_ports(evidence):
    request, *_ = evidence
    class Samuel:
        def dispatch_workflow(self, transport, **kwargs):
            assert transport == "trusted-port"
            assert kwargs == request.dispatch_kwargs()
            return dict(workflow_path=WORKFLOW, ref="main", correlation_id=request.correlation_id,
                        correlation_input="correlation_id", correlation_run_name_prefix="checkpoint-contract:")
        def observe_dispatch_once(self, transport, receipt, **kwargs):
            assert transport == "trusted-port"
            assert kwargs == {"expected_head_sha": request.source_sha}
            return {"status": "MATCHED_ACTIVE", "matched_run_ids": [12]}
    runtime = Samuel()
    receipt = dispatch_contract(request, "trusted-port", samuel_runtime=runtime)
    assert observe_contract(request, "trusted-port", receipt, samuel_runtime=runtime)["status"] == "MATCHED_ACTIVE"
    receipt["correlation_id"] = "other"
    with pytest.raises(ValueError, match="DISPATCH_RECEIPT_MISMATCH"):
        observe_contract(request, "trusted-port", receipt, samuel_runtime=runtime)


def test_request_hash_inventory_is_immutable(evidence):
    request, *_ = evidence
    with pytest.raises(TypeError):
        request.source_hashes[WORKFLOW] = "d"*64
