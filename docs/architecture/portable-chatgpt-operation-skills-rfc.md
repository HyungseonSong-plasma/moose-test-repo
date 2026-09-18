# Issue #264 Review Copy

This RFC is reviewed and proven in `moose-test-repo` because CodeRabbit is enabled here. The intended production home for the generic package/workflows is `HyungseonSong-plasma/chatgpt-operation`.

The review copy must remain architecture-only until reviewer findings are dispositioned. Implementation migration begins only after this review surface is accepted.

---

# RFC-0001 — Portable ChatGPT Operation Skills

**Status:** REVIEW  
**Scope:** central reusable skill architecture  
**Initial consumer:** `HyungseonSong-plasma/moose-test-repo`

## 1. Motivation

Operational rules currently live partly in natural-language instructions and partly in repository-local automation.

The working hypothesis is:

> LLMs should own semantic intent and judgment. Repetitive, deterministic, machine-verifiable operating procedures should be implemented as reusable skills.

The first validated example is the repository-mutation capability in `moose-test-repo`, which mechanizes fresh-read, exact identity, no-op, CI-lock, mutation, and read-back checks.

The next step is to make that capability portable across repositories without copying code or duplicating rules.

## 2. Proposed ownership model

`chatgpt-operation` becomes the central source for reusable operating capabilities.

```text
chatgpt-operation
├── Python package / CLI
├── private composite GitHub Actions
├── schemas
├── shared tests
└── skill documentation
             │
             ├──────── exact-SHA consumer pin ────────┐
             ▼                                        ▼
       moose-test-repo                           other repos
       local policy                              local policy
       local manifests                           local manifests
```

The central repository owns **how a generic operation is safely executed**.

Each consumer repository owns **what that repository permits**.

## 3. Proposed package layout

```text
chatgpt-operation/
├── pyproject.toml
├── src/
│   └── chatgpt_operation/
│       ├── cli.py
│       ├── repository/
│       │   └── mutation.py
│       ├── git/
│       └── validation/
├── schemas/
│   ├── repository-mutation.schema.json
│   └── repository-policy.schema.json
├── skills/
│   └── repository-mutation/
│       └── README.md
├── .github/
│   └── actions/
│       └── repository-mutation/
│           └── action.yml
└── tests/
```

The Python package is the deterministic engine.

The private composite action is the GitHub-hosted execution surface. The action invokes package code from its own immutable action revision through `GITHUB_ACTION_PATH`; it does not clone or install the central private repository with the consumer repository's `GITHUB_TOKEN`.

A consumer-local workflow owns token permissions, triggers, concurrency, and repository-specific gating.

The Markdown skill documentation describes intent, boundaries, and review guidance; it is not the enforcement mechanism.

## 4. Consumer layout

A consumer should remain thin.

```text
consumer-repo/
├── .chatgpt-operation.yml
├── automation/
│   └── mutations/
│       └── *.json
└── .github/
    └── workflows/
        └── repository-mutation.yml
```

The **consumer-local workflow** should reference the central private action by an **exact commit SHA**, not by a moving branch or tag.

Example concept:

```yaml
permissions:
  contents: write
  actions: read

concurrency:
  group: repository-mutation-${{ github.repository }}
  cancel-in-progress: false

jobs:
  mutate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@<reviewed-full-sha>
      - uses: HyungseonSong-plasma/chatgpt-operation/.github/actions/repository-mutation@<exact-central-sha>
        with:
          manifest: automation/mutations/update.json
          policy: .chatgpt-operation.yml
```

For private-to-private reuse, the central repository's GitHub Actions **Access** setting must explicitly allow consumer repositories owned by the same user/organization. GitHub then supplies the runner a short-lived scoped installation token to download the private action. The design does not rely on the consumer `GITHUB_TOKEN` cloning `chatgpt-operation`.

## 5. Package distribution

The core should also be usable outside GitHub Actions.

Proposed CLI:

```bash
chatgpt-op repository mutate --manifest mutation.json
```

Proposed Python API:

```python
from chatgpt_operation.repository.mutation import MutationEngine
```

Initial v1 distribution is deliberately narrow:

1. **GitHub Actions:** use the private composite action at an exact commit SHA through GitHub's private-action sharing mechanism;
2. **developer/local Python:** install only from the canonical private repository `HyungseonSong-plasma/chatgpt-operation` using authenticated Git access and an exact 40-hex commit SHA.

Portable v1 publishes **no wheel/package artifact** and has **no third-party Python runtime dependencies**. This removes an unnecessary artifact-provenance surface from the first release.

A local installer or bootstrap check must verify both:
- the canonical repository identity/remote URL; and
- the resolved commit equals the requested exact SHA.

If wheel or registry distribution is introduced later, it requires a separate reviewed design for immutable digest verification plus signed/attested provenance and dependency integrity.

The privileged GitHub workflow must **not** perform `pip install git+...` or `actions/checkout` against the private central repository using the consumer repository's write token.

Copying `mutation.py` independently into every consumer repository is explicitly rejected because it creates skill drift.

## 6. Repository policy boundary

The generic engine must not embed `moose-test-repo` assumptions.

Consumer policy should be declarative, for example:

```yaml
schema_version: 1

repository:
  protected_branches:
    - main

mutation:
  allow:
    file: [create, update, delete]
    branch: [create]

  file_paths:
    allow:
      - "docs/**"
      - "automation/mutations/**"
    deny:
      - ".github/workflows/**"
      - ".github/actions/**"

validation_gate:
  workflows:
    - Repository CI
    - Governed refactor entrypoint
```

The central engine validates the policy schema and fails closed for unsupported fields or actions.

File mutation authorization is path-sensitive:
- `deny` rules take precedence over `allow`;
- a file path that matches no `allow` rule is denied;
- patterns are repository-relative POSIX-style globs;
- path normalization occurs before authorization and `..\`, absolute paths, and ambiguous normalized forms are rejected;
- protected paths must be routed through a separately reviewed higher-trust workflow/policy rather than bypassing the generic action.

Policy should be treated as authorization constraints, not suggestions.

## 7. Repository-mutation generic contract

The portable engine should preserve the validated mechanical sequence:

```text
declared semantic intent
    ↓
repository / resource / action binding
    ↓
consumer policy authorization
    ↓
mutation-lock evaluation
    ↓
fresh canonical read
    ↓
exact expected identity gate
    ↓
semantic no-op gate
    ↓
mutation
    ↓
read-back verification
    ↓
PASS | NO_MUTATION_NEEDED | HARD_STOP
```

Portable v1 distinguishes operations with a server-enforced compare-and-swap identity from operations that only support a read-then-write check.

| Resource | v1 default | Concurrency property |
|---|---|---|
| file | create/update/delete | GitHub Contents update/delete uses the expected blob SHA |
| branch create | supported | expected absence |
| branch move | disabled by default | no server-side expected-old-SHA precondition; may be enabled only under consumer-enforced exclusive-writer serialization |
| branch delete | unsupported in v1 | no server-side expected-SHA delete precondition; read-then-delete is TOCTOU-vulnerable |
| issue update/close/reopen | unsupported in v1 | REST issue PATCH is not conditional on the prior `updated_at`; read-then-PATCH can overwrite a concurrent edit |

The portable engine must not claim exact-identity safety for an API that does not provide a server-side conditional mutation primitive.

If a future consumer enables a non-CAS mutation through an external serialization mechanism, that serialization becomes part of the explicit consumer safety contract and must be validated independently.

Any issue-like response containing GitHub's `pull_request` marker must be rejected by an `issue` resource handler. Pull requests are a distinct resource class and are not implicitly authorized by issue permissions.

History rewrite is not part of v1.

## 7A. Review-derived hard requirements from the existing prototype

Greptile's review of the current `moose-test-repo` mutation prototype identified several portability/security issues that become hard requirements for the central design:

1. **Trusted control plane and mutation target must be separate identities.**  
   The code that receives a write-scoped token must come from the consumer's immutable central-skill pin. A mutation manifest, target commit, or caller-supplied source SHA must never select executable control-plane code.

2. **No read-then-write operation may be advertised as exact-identity safe without server-side CAS or exclusive serialization.**  
   This applies directly to branch deletion and issue PATCH operations in the current prototype.

3. **Issue handlers must reject pull requests.**  
   GitHub exposes PRs through the Issues API; the closed-world resource schema must preserve the distinction.

4. **All privileged third-party actions must be pinned to reviewed full commit SHAs.**  
   Mutable action tags such as `@v4` are not acceptable in a write-scoped mutation job.

5. **Boundary failures must remain inside the structured result contract.**  
   Malformed manifests, encoding/decoding errors, network timeouts, non-JSON responses, and result-write failures must produce a deterministic `HARD_STOP`-class result rather than an unclassified traceback.

6. **Mutation retry must be idempotent after ambiguous local result persistence.**  
   A remote mutation may succeed even if local artifact writing fails. The operation contract therefore needs a deterministic operation identity plus post-state/no-op recognition so retry does not create a second semantic mutation.

7. **File mutation authorization is path-sensitive and fail-closed.**  
   Resource/action authorization alone is insufficient. Consumer policy must explicitly authorize target paths; deny rules win; unmatched paths are rejected.

8. **Validation-gate enumeration must be complete.**  
   GitHub Actions run enumeration must paginate until exhaustion. Any pagination/API failure before completeness is proven yields `HARD_STOP`.

9. **Local package provenance is intentionally minimized in v1.**  
   v1 supports exact-SHA installation only from the canonical private repository and has no external Python runtime dependencies or wheel distribution.

These requirements are inherited from review evidence on the local prototype and must be resolved before that prototype is generalized.

## 7B. Deterministic operation identity and retry semantics

Every mutation computes:

```text
operation_id = SHA-256(canonical JSON of:
  schema_version,
  repository,
  resource,
  action,
  normalized target,
  normalized desired state)
```

`expected` concurrency identity is deliberately excluded from the semantic operation identity; it proves whether a first write may proceed, but it does not change the desired end state.

For file operations, **post-state recognition occurs before stale-identity rejection**:

```text
create:
  target exists with desired content -> NO_MUTATION_NEEDED
  target exists with different content -> HARD_STOP
  target absent -> create

update:
  target content already equals desired -> NO_MUTATION_NEEDED
  target differs and current blob SHA != expected -> HARD_STOP
  target differs and SHA matches -> update

delete:
  target absent -> NO_MUTATION_NEEDED
  target exists and current blob SHA != expected -> HARD_STOP
  target exists and SHA matches -> delete
```

This ordering makes a retry safe when GitHub accepted the mutation but local result persistence failed afterward.

The structured result includes `operation_id`, status, and resulting identity when available. A retry of the same semantic operation must converge to the same post-state without creating a second semantic mutation.

## 8. Validation gate versus mutation serialization

The current prototype checks queued/in-progress Actions runs before mutation. That check is a **validation gate snapshot**, not a repository reservation and not a concurrency primitive.

Portable v1 therefore separates two concepts:

```text
validation gate
  -> consumer policy may refuse to begin while named/all Actions validations are active

workflow serialization
  -> consumer-local GitHub Actions `concurrency` serializes mutation workflow instances

mutation conflict safety
  -> supported v1 mutations must remain safe even if a non-Actions writer races them
  -> server-side CAS/uniqueness is the authority
```

Candidate validation-gate semantics:

```text
validation_gate.mode = named_workflows | all_actions
validation_gate.workflows = [...]
validation_gate.ignore_current_run = true
```

Enumeration is complete-or-fail-closed: the implementation requests all pages of queued and in-progress workflow runs until GitHub returns no further page. If any page cannot be retrieved or decoded, the gate returns `HARD_STOP`; it must never interpret an incomplete first page as proof that no gated validation is active.

GitHub Actions `concurrency` is useful for serializing this skill's own workflow runs, but it does not cover humans or external API writers and therefore cannot make a non-CAS mutation safe.

Any future branch-move/delete or issue-PATCH support must provide a separately reviewed lease/serialization mechanism whose scope covers **all** relevant writers, or remain unsupported.

## 9. GitHub authentication and permissions

The consumer-local workflow should run using the **consumer repository's workflow token**, not a long-lived token stored in `chatgpt-operation`.

The central composite action implementation must come only from the immutable revision selected in the consumer's `uses: ...@<exact-sha>` reference. GitHub's private-action sharing mechanism provides a short-lived scoped installation token for downloading the central action when repository Access is configured. A consumer-supplied target SHA may identify data or mutation target state, but must never select executable control-plane code.

Principles:

- least privilege;
- no token in manifests;
- no token in artifacts/logs;
- explicit permissions are owned by the consumer-local workflow;
- composite actions cannot silently elevate those permissions;
- read-only review workflows must not acquire mutation permission;
- mutation execution exposes only closed-world resource/action paths;
- every third-party action executed in a write-scoped job is pinned to a reviewed full commit SHA;
- v1 excludes issue mutation, so the default mutation workflow does not need `issues: write`.

Portable v1 target permissions:

```text
contents: write
actions: read
```

If future resource classes require additional scopes, they should prefer separate consumer workflows/actions when that materially reduces privilege.

## 10. Supply-chain and versioning model

Consumer repositories should pin reusable workflows and Python package sources to immutable revisions.

Proposed lifecycle:

```text
central change
→ central tests/review
→ tagged release / immutable commit
→ consumer pin-update PR
→ consumer CI
→ adoption
```

Candidate semantic versioning:

- PATCH: implementation fix with unchanged manifest/policy contract;
- MINOR: backward-compatible resource/action/schema extension;
- MAJOR: schema or authorization semantics change.

Open question: should exact commit SHA remain canonical even when release tags are published?

Proposed answer: yes. Tags are human-readable discovery aliases; consumer execution pins exact SHA.

## 11. GitHub Actions execution boundary

Portable v1 does **not** require a central reusable workflow.

The consumer-local workflow should:

1. own triggers, permissions, validation gating, and GitHub Actions concurrency;
2. check out the consumer repository using a third-party action pinned to a reviewed full SHA;
3. invoke the private central composite action using an exact central commit SHA;
4. pass only the consumer-local manifest/policy paths and execution identity;
5. upload or expose the structured result through consumer-controlled steps.

The central composite action should:

1. execute package code bundled in the same immutable central revision;
2. validate the consumer manifest and policy;
3. perform only the closed-world mutation operations allowed by portable v1;
4. emit structured outputs.

It must not dynamically check out or execute arbitrary control-plane code selected by manifest input.

A reusable workflow may be added later as a convenience layer, but it is not part of the trusted v1 core.

## 12. Review and test strategy

Central tests should include:

- manifest schema negative controls;
- policy schema negative controls;
- stale file identity;
- stale branch identity;
- stale issue identity and explicit proof that issue mutation remains disabled without serialization;
- PR-as-issue rejection;
- no-op suppression;
- non-fast-forward rejection;
- lock-policy enforcement;
- wrong repository binding;
- post-write verification mismatch;
- token/secret redaction;
- consumer-policy denial;
- package/CLI equivalence;
- control-plane SHA cannot be influenced by the mutation target/manifest;
- privileged action references are immutable full SHAs;
- malformed JSON/UTF-8/base64, timeout, and non-JSON response failures remain structured;
- successful remote mutation followed by local result-write failure is retry-safe;
- file create/update/delete recognize already-achieved post-state before stale-identity rejection;
- operation IDs are deterministic across retry;
- file-path deny precedence, unmatched-path rejection, normalization, and protected-path routing;
- validation-gate pagination with more than 100 runs and fail-closed page-fetch failure;
- local exact-SHA install rejects a non-canonical repository source or mismatched resolved commit;
- v1 package imports and CLI run with no third-party Python runtime dependency.

A local fake/in-memory transport remains mandatory for mutation self-tests.

No test may create live GitHub resources merely to prove connectivity.

Integration testing against GitHub should use explicitly provisioned test fixtures or ephemeral repositories, never production repositories.

## 13. Migration plan for moose-test-repo

```text
Phase 1
  bootstrap central package + schemas + tests

Phase 2
  port current repository-mutation implementation
  preserve behavior

Phase 3
  add private composite action
  add repository-policy adapter
  configure chatgpt-operation Actions access for private consumers

Phase 4
  add consumer-local mutation workflow in moose-test-repo
  consume central private action at exact SHA
  run full consumer CI

Phase 5
  remove vendored skills/repository/mutation.py
  retain only local policy + manifests + thin caller
```

Portability is not considered proven until Phase 4 passes in a real consumer repository.

## 14. Deliberate non-goals for v1

- scientific reasoning;
- deciding whether a requested semantic change is desirable;
- force push/history rewriting;
- release/package/project mutations;
- arbitrary GitHub API passthrough;
- executing commands supplied by a mutation manifest;
- automatically expanding authorization beyond consumer policy.

## 15. Architecture principles to preserve

1. **LLM intent, deterministic execution.**
2. **Fail closed on unknown schema/action.**
3. **Exact identity before destructive mutation.**
4. **No semantic no-op history.**
5. **Read-back after mutation.**
6. **Consumer repository owns authorization policy.**
7. **Central package owns generic mechanics.**
8. **Consumers pin immutable central revisions.**
9. **No duplicated skill implementation across repositories.**
10. **Reviewability before automation convenience.**

## 16. Reviewer questions

Reviewers should explicitly challenge:

1. Is the package + private-composite-action split appropriate for v1, with consumer-local workflows owning permissions and concurrency?
2. Is private-action sharing through the central repository's Actions Access setting sufficient, or is an immutable package artifact preferable?
3. Does exact-SHA pinning sufficiently address central supply-chain risk?
4. Is the proposed consumer policy expressive enough without becoming another large rule language?
5. Is the validation-gate/concurrency/CAS separation explicit enough to avoid treating a point-in-time Actions check as a lease?
6. Does v1's reduced `contents: write` + `actions: read` scope sufficiently minimize privilege?
7. Should future resource classes use separate composite actions/workflows for permission isolation?
8. Since `updated_at` is not a PATCH precondition, should issue mutation remain entirely outside v1 unless an exclusive-writer lease is proven?
9. Should branch move/delete remain disabled unless a server-side CAS or repository-wide exclusive-writer mechanism exists?
10. Is the v1 decision to avoid wheel/registry distribution sufficient to defer artifact-signing requirements without weakening GitHub Actions consumption?
11. Are path-level allow/deny rules sufficient, or should protected paths always require a distinct action/workflow identity?
12. Which parts of the current repository-mutation prototype should **not** be generalized?

## 17. Acceptance for this RFC

This RFC should not be accepted until:

- at least two independent automated reviewers have examined it where available;
- security/permission objections are dispositioned;
- the package/private-action/consumer-workflow boundary is explicit;
- consumer policy ownership is explicit;
- migration can be performed without weakening the current `moose-test-repo` mutation safety contract;
- CodeRabbit findings on package provenance, path authorization, retry idempotency, and complete validation-gate enumeration are represented as executable acceptance tests before consumer migration.
