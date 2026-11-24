# Verification v0.1 — facts before policy

Verification is the third stage after Diagnostics and Analysis. It has no
directory-role policy, package allowlist, or automatic mutation approval.

The implementation has two explicit responsibilities:

- `consistency.py` validates scoped Graph/EvidenceReceipt source-metadata consistency.
- `dependencies.py` derives follow-up verification obligations from GraphDiff
  and provides configurable, source-bound Python dependency verification.
  Repository-specific constraints are supplied from outside Harness Code.

Both functions remain available from `physics_harness.code.verification`.

- Every Diagnostics assembly emits a VerificationReceipt alongside Graph and
  EvidenceReceipt. VERIFIED attests consistency of scoped source provenance:
  SHA/Blob/line references, Scope and file status. The result explicitly
  retains unverified runtime, semantic equivalence and global consumer closure.
- Failed integrity findings are FAILED. Partial scans or unresolved dynamic
  source facts are UNVERIFIED, not green. A source-only VERIFIED result never
  approves removing code or altering production CI.
- plan_change_verification compares two exact-HEAD Graph/Receipt pairs and
  derives checks for removed references, changed interfaces, new dependency
  candidates, Scope gaps and required test replay. It is not a policy migration.
- Explicit runtime/semantic evidence from separately executed verification is
  required to close those obligations in a later version.

Deprecated repository-specific directory-role Guards are retired separately
only after consumers and Workflow registrations are audited. Historical static
adversarial cases remain as risk examples, not hard-coded role rules.

## First retired Guard (issue #743)

The historical static `physics_directory_role_guard.py` and its
`physics_directory_roles_v1.json` role allowlist are retired. The generalized
Verifier works on Graph source Evidence and actual before/after changes.
Its dependency/call candidates produce verification obligations rather than
blocking unfamiliar directories. Other repository checks remain independent
and are not implicitly declared replaced by Verification v0.1.

## Source dependency verification (#743)

`dependencies.py` retains `plan_change_verification` and provides
`verify_dependencies` / `verify_dependency_repository`. The latter uses an
exact-HEAD source provider to verify all tracked Python package files.
Repository-specific package rules are supplied as `DependencyContract`
inputs, not embedded in this module. Findings retain category, file, source
line and Git blob SHA. Missing/invalid source coverage yields UNVERIFIED;
known static violations yield FAIL. A PASS proves only the configured static
absolute-import and source-reference checks, not dynamic resolution, native
runtime evidence, or semantic equivalence. No result approves mutation.

The former `physics_dependency_guard.py` CI gate was replaced only after
legacy/Harness verdict equivalence and an exact-HEAD repository source audit
passed together in the same Repository CI run. The Harness source verifier
retains static absolute-import, repository-tool reference and package cycle
checks; separate Physics/runtime boundary guards remain independent.
