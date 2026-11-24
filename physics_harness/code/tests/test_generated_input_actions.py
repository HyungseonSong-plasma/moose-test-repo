"""P1b acquisition: archive custody and invocation assertions are distinct."""
from dataclasses import asdict, replace
from hashlib import sha256
from io import BytesIO
import json
from zipfile import ZipFile, ZipInfo

import pytest

from physics_harness.code.diagnostics import GitSourceProvider, ScanRequest
from physics_harness.code.diagnostics.providers.generated_input import GeneratedInputIdentity
from physics_harness.code.verification.generated_input_actions import acquire_generated_input
from physics_harness.code.verification.naming_actions import read_actions_archive_members


HIT = b"[Kernels]\n  [./example]\n    type = MyKernel\n  [../]\n[]\n"
WORKFLOW = ".github/workflows/generate.yml"
MANIFEST = "manifest.json"
ARTIFACT = "generated-input"
STEP = "Generate input"
JOB_ID = 21


def zip_members(items):
    stream = BytesIO()
    with ZipFile(stream, "w") as archive:
        for name, data in items:
            archive.writestr(name, data)
    return stream.getvalue()


class FakeReader:
    def __init__(self, identity):
        self.identity = identity
        self.run_record = dict(
            id=identity.run_id, repository=dict(full_name=identity.repository, id=7),
            head_sha=identity.source_sha, run_attempt=identity.attempt,
            path=WORKFLOW, status="completed", conclusion="success",
            updated_at="2026-11-24T21:00:00Z")
        self.job_records = [dict(
            id=JOB_ID, run_id=identity.run_id, head_sha=identity.source_sha,
            run_attempt=identity.attempt, status="completed", conclusion="success",
            steps=[dict(name=STEP, status="completed", conclusion="success")])]
        self.artifact_records = [dict(
            id=identity.artifact_id, name=ARTIFACT, expired=False,
            workflow_run=dict(id=identity.run_id, head_sha=identity.source_sha,
                              repository_id=7))]
        claim = asdict(identity)
        claim.pop("artifact_id")
        self.manifest = dict(schema_version=1, identity=claim,
                             job_id=JOB_ID, workflow_path=WORKFLOW)
        self.downloads = 0
        self.refresh_archive()

    def refresh_archive(self, hit=HIT, extra=(), manifest_bytes=None):
        manifest_bytes = (json.dumps(self.manifest).encode()
                          if manifest_bytes is None else manifest_bytes)
        self.data = zip_members([
            (self.identity.artifact_path, hit), (MANIFEST, manifest_bytes), *extra])
        self.digest = sha256(self.data).hexdigest()
        self.artifact_records[0]["digest"] = "sha256:" + self.digest

    def run(self, repository, run_id):
        assert (repository, run_id) == (self.identity.repository, self.identity.run_id)
        return self.run_record

    def jobs(self, repository, run_id):
        return self.job_records

    def artifacts(self, repository, run_id):
        return self.artifact_records

    def archive(self, repository, artifact_id):
        assert artifact_id == self.identity.artifact_id
        self.downloads += 1
        return self.data


@pytest.fixture
def scenario(git_factory):
    root, revision = git_factory({"src/generator.py": "def generate(): pass\n"})
    request = ScanRequest("example/repo", revision, ("src/*",),
                          collectors=("python_ast",))
    provider = GitSourceProvider(root)
    producer = provider.read_at_revision(revision, "src/generator.py")
    identity = GeneratedInputIdentity(
        request.repository, revision, producer.record.path, producer.record.blob_sha,
        10, 1, 20, "inputs/generated.i", sha256(HIT).hexdigest(),
        sha256(b"configuration").hexdigest())
    return request, provider, identity, FakeReader(identity)


def acquire(scenario, **changes):
    request, provider, identity, reader = scenario
    options = dict(expected=identity, workflow_path=WORKFLOW, job_id=JOB_ID,
                   artifact_name=ARTIFACT, manifest_path=MANIFEST,
                   expected_archive_sha256=reader.digest,
                   required_step_names=(STEP,), source=reader)
    options.update(changes)
    return acquire_generated_input(request, provider, **options)


def test_archive_identity_and_generated_graph_join_remain_partial(scenario):
    _, _, identity, reader = scenario
    result = acquire(scenario)
    assert result.identity == identity
    assert result.archive_sha256 == reader.digest
    assert result.manifest_sha256 == sha256(json.dumps(reader.manifest).encode()).hexdigest()
    assert result.source == "INJECTED_READER"
    assert not result.producer_authenticated
    assert result.result.status == "PARTIAL"
    assert "GENERATOR_INVOCATION_CAUSAL_BINDING_UNVERIFIED" in result.unresolved
    assert "INJECTED_SOURCE_NOT_GITHUB_AUTHENTICATION" in result.unresolved
    assert any(e.relation == "GENERATED_DECLARES_TYPE_USE"
               for e in result.result.batch.edges)
    assert not any(e.observation_status == "RUNTIME_OBSERVED"
                   for e in result.result.batch.evidence)
    assert reader.downloads == 1


@pytest.mark.parametrize("key,value", [
    ("head_sha", "b" * 40), ("run_attempt", 2), ("id", 11),
    ("path", ".github/workflows/other.yml"), ("conclusion", "failure"),
    ("updated_at", None),
])
def test_run_identity_mismatch_before_download(scenario, key, value):
    reader = scenario[-1]
    reader.run_record[key] = value
    with pytest.raises(ValueError, match="GENERATED_ACTIONS_RUN_MISMATCH"):
        acquire(scenario)
    assert reader.downloads == 0


@pytest.mark.parametrize("key,value", [
    ("run_id", 11), ("head_sha", "c" * 40), ("run_attempt", 2),
    ("conclusion", "failure"),
])
def test_job_identity_mismatch(scenario, key, value):
    scenario[-1].job_records[0][key] = value
    with pytest.raises(ValueError, match="GENERATED_JOB_ASSOCIATION_MISMATCH"):
        acquire(scenario)


def test_required_step_must_pass(scenario):
    scenario[-1].job_records[0]["steps"][0]["conclusion"] = "skipped"
    with pytest.raises(ValueError, match="GENERATED_REQUIRED_STEP_NOT_PASSED"):
        acquire(scenario)


def test_later_attempt_cannot_be_inferred(scenario):
    with pytest.raises(ValueError, match="ARTIFACT_ATTEMPT_BINDING_UNPROVEN"):
        acquire(scenario, expected=replace(scenario[2], attempt=2))
    assert scenario[-1].downloads == 0


@pytest.mark.parametrize("key,value", [
    ("id", 99), ("name", "wrong"), ("expired", True),
    ("digest", "sha256:" + "a" * 64),
])
def test_artifact_identity_mismatch(scenario, key, value):
    scenario[-1].artifact_records[0][key] = value
    with pytest.raises(ValueError, match="GENERATED_ARTIFACT_ASSOCIATION_MISMATCH"):
        acquire(scenario)


def test_artifact_wrong_owner(scenario):
    scenario[-1].artifact_records[0]["workflow_run"]["repository_id"] = 8
    with pytest.raises(ValueError, match="GENERATED_ARTIFACT_ASSOCIATION_MISMATCH"):
        acquire(scenario)


def test_archive_bytes_mismatch(scenario):
    scenario[-1].data += b"tampered"
    with pytest.raises(ValueError, match="GENERATED_ARCHIVE_DIGEST_MISMATCH"):
        acquire(scenario)


def test_manifest_invocation_mismatch(scenario):
    reader = scenario[-1]
    reader.manifest["identity"]["invocation_sha256"] = "f" * 64
    reader.refresh_archive()
    with pytest.raises(ValueError, match="GENERATED_RECEIPT_IDENTITY_MISMATCH"):
        acquire(scenario)


def test_manifest_cannot_claim_post_upload_id(scenario):
    reader = scenario[-1]
    reader.manifest["identity"]["artifact_id"] = 20
    reader.refresh_archive()
    with pytest.raises(ValueError, match="GENERATED_RECEIPT_IDENTITY_MISMATCH"):
        acquire(scenario)


def test_hit_bytes_mismatch_despite_matching_archive(scenario):
    scenario[-1].refresh_archive(hit=HIT + b"# changed")
    with pytest.raises(ValueError, match="GENERATED_CONTENT_DIGEST_MISMATCH"):
        acquire(scenario)


def test_duplicate_manifest_key_rejected(scenario):
    scenario[-1].refresh_archive(manifest_bytes=b'{"schema_version":1,"schema_version":1}')
    with pytest.raises(ValueError, match="GENERATED_MANIFEST_DUPLICATE_KEY"):
        acquire(scenario)


def test_run_changes_during_acquisition(scenario):
    reader = scenario[-1]
    original = reader.archive

    def shifting(repo, artifact_id):
        data = original(repo, artifact_id)
        reader.run_record["updated_at"] = "2026-11-24T21:01:00Z"
        return data
    reader.archive = shifting
    with pytest.raises(ValueError, match="GENERATED_ACTIONS_CHANGED_DURING_READ"):
        acquire(scenario)


@pytest.mark.parametrize("name", ["../escape", "/absolute", "C:/escape", "a/../escape", "a//b"])
def test_unsafe_zip_member_rejected(name):
    data = zip_members([("valid.i", HIT), (name, b"x")])
    with pytest.raises(ValueError, match="UNSAFE_ARCHIVE_ENTRY_PATH"):
        read_actions_archive_members(data, entries=("valid.i",))


def test_archive_total_budget():
    data = zip_members([("one.i", b"1234"), ("two.i", b"5678")])
    with pytest.raises(ValueError, match="ARCHIVE_TOTAL_SIZE_LIMIT"):
        read_actions_archive_members(data, entries=("one.i",), max_total_bytes=7)


def test_archive_symlink_rejected():
    link = ZipInfo("link")
    link.create_system = 3
    link.external_attr = 0o120777 << 16
    data = zip_members([("valid.i", HIT), (link, b"target")])
    with pytest.raises(ValueError, match="ARCHIVE_SYMLINK_UNSUPPORTED"):
        read_actions_archive_members(data, entries=("valid.i",))


# P1c: execute only an explicitly selected, vetted text-returning generator.
def load_fixture_module(root, relative):
    import importlib.util
    spec = importlib.util.spec_from_file_location("capture_test_module", root / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def capture_fixture(git_factory, source="def render(kind='MyKernel'):\n    return '[Kernels]\\n [./k]\\n type = ' + kind + '\\n [../]\\n[]\\n'\n"):
    from physics_harness.code.verification.generated_input_actions import capture_generated_return
    path = "src/generator.py"
    root, revision = git_factory({path: source})
    provider = GitSourceProvider(root)
    request = ScanRequest("example/repo", revision, (path,), collectors=("python_ast",))
    blob = provider.read_at_revision(revision, path).record.blob_sha
    module = load_fixture_module(root, path)
    options = dict(producer_path=path, producer_blob_sha=blob, function=module.render,
                   arguments={}, artifact_path="inputs/generated.i", run_id=10,
                   attempt=1, job_id=JOB_ID, workflow_path=WORKFLOW)
    return request, provider, options, capture_generated_return


def test_capture_real_callable_and_exact_invocation_hash(git_factory):
    request, provider, options, capture = capture_fixture(git_factory)
    a = capture(request, provider, **options)
    b = capture(request, provider, **dict(options, arguments={"kind": "MyKernel"}))
    c = capture(request, provider, **dict(options, arguments={"kind": "OtherKernel"}))
    assert a == b and a != c
    assert b"MyKernel" in a.hit and b"OtherKernel" in c.hit
    manifest = json.loads(a.manifest)
    assert manifest["identity"]["artifact_sha256"] == sha256(a.hit).hexdigest()
    assert "artifact_id" not in manifest["identity"]
    assert b"MyKernel" not in a.manifest
    assert not a.producer_authenticated


def test_capture_rejects_changed_worktree(git_factory):
    request, provider, options, capture = capture_fixture(git_factory)
    (provider.root / options["producer_path"]).write_text("def render(): return 'changed'\n")
    with pytest.raises(ValueError, match="GENERATED_CAPTURE_WORKTREE_SOURCE_MISMATCH"):
        capture(request, provider, **options)


def test_capture_rejects_changed_loaded_code(git_factory):
    request, provider, options, capture = capture_fixture(git_factory)
    function = options["function"]
    function.__code__ = function.__code__.replace(co_consts=("changed",))
    with pytest.raises(ValueError, match="GENERATED_CAPTURE_CODE_MISMATCH"):
        capture(request, provider, **options)


def test_capture_rejects_wrong_blob_before_call(git_factory):
    request, provider, options, capture = capture_fixture(git_factory)
    with pytest.raises(ValueError, match="GENERATED_PRODUCER_BLOB_MISMATCH"):
        capture(request, provider, **dict(options, producer_blob_sha="a" * 40))


@pytest.mark.parametrize("value", [{"unsafe": 1}, float("nan"), "x" * 4097])
def test_capture_rejects_unbounded_or_nonfinite_arguments(git_factory, value):
    request, provider, options, capture = capture_fixture(git_factory)
    with pytest.raises(ValueError):
        capture(request, provider, **dict(options, arguments={"kind": value}))


def test_capture_rejects_nontext_result(git_factory):
    request, provider, options, capture = capture_fixture(
        git_factory, "def render(): return 42\n")
    with pytest.raises(TypeError, match="GENERATED_CAPTURE_TEXT_RETURN_REQUIRED"):
        capture(request, provider, **options)


def test_code6_existing_generator_through_capture_and_acquisition():
    """Real repository generator, actual returned HIT, simulated Actions API.

    Do not run its solver or main() and do not treat fake metadata as an
    authenticated GitHub upload. This is a Code-only P0 regression.
    """
    from pathlib import Path
    from physics_harness.code.verification.generated_input_actions import capture_generated_return

    root = Path(__file__).resolve().parents[3]
    path = "physics_app/ci/check_stage5_ei20_runtime.py"
    provider = GitSourceProvider(root)
    revision = provider._git("rev-parse", "HEAD").decode("ascii").strip()
    request = ScanRequest("HyungseonSong-plasma/moose-test-repo", revision,
                          (path,), collectors=("python_ast",))
    blob = provider.read_at_revision(revision, path).record.blob_sha
    module = load_fixture_module(root, path)
    options = dict(producer_path=path, producer_blob_sha=blob,
                   function=module.runtime_input, arguments={"mean": 5.73276},
                   artifact_path="inputs/generated.i", run_id=10, attempt=1,
                   job_id=JOB_ID, workflow_path=WORKFLOW)
    captured = capture_generated_return(request, provider, **options)
    assert b"PhysicsFVMassFractionTimeDerivative" in captured.hit
    identity = GeneratedInputIdentity(
        **json.loads(captured.manifest)["identity"], artifact_id=20)
    reader = FakeReader(identity)
    reader.refresh_archive(hit=captured.hit, manifest_bytes=captured.manifest)
    acquired = acquire((request, provider, identity, reader))
    assert acquired.identity == identity
    assert acquired.result.status == "PARTIAL"
    assert not acquired.producer_authenticated
    assert any(n.kind == "moose_type" and n.name == "PhysicsFVMassFractionTimeDerivative"
               for n in acquired.result.batch.nodes)
    assert not any(e.observation_status == "RUNTIME_OBSERVED"
                   for e in acquired.result.batch.evidence)
