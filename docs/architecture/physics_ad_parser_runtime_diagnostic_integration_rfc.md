# Proposed ADR: PhysicsApp AD FParser runtime diagnosis integration

**Status:** PROPOSED — architectural decision package only; NOT accepted implementation or scientific validation.
**Owner:** Physics/moose-test-repo, linked to runtime #471 and scientific gate #282.
**Decision baseline:** Physics main observed at 6faffd3931e2d8c611e18236ac0bffa8103741d5; pinned MOOSE source 9f388366ccf38b9c34542ec5561198249fde0ac9. Confirm exact head and existing owners before implementation.
**Decision needed:** integrate the existing incidents, probes, build and execution checks without introducing a second runtime/diagnostics authority, weakening scientific gates, or moving local runtime build internals into SOL.

## 1. Architectural problem, not merely a missing script

Physics #471's 5-case original runtime/build-base comparison produced trustworthy discriminating evidence: ADParsed default JIT fails in the scratch image at P2, while the same PhysicsApp executable in the JIT-capable build base passes P2/P3. JIT-disabled ADParsed and nested ADParsed reach P3 SIGSEGV 139 in both environments; ordinary FV and generic functor controls pass. See immutable native run #42263715962 / artifact #13526467231, previous 9-case run #42258104874, and GDB run #42249539811.

The current experiment-specific runner duplicates generic process execution, hashing and evidence storage, and conflates experimental outcome and fix-acceptance in a single verdict. Its existing environment comparison also changes shared libraries, loader environment, compiler headers and executable environment together. Thus a successful JIT-enabled build-base case is *not* proof that a missing compiler alone caused scratch failure.

Treat three distinct questions separately:
1. **Capability contract:** is the selected AD Parsed + JIT mode supported by the *pinned* MOOSE/libMesh build?
2. **Operational compatibility:** can that mode compile, dynamically load and evaluate in the candidate runtime closure?
3. **Physics scientific validity:** does the original 2-D model solve and pass its independent reference and convergence oracle?

CI, successful construction, a zero exit code, and experiment diagnosis are not equivalent answers.

## 2. Critical correction to #471 acceptance: ADParsed with JIT disabled

Exact pinned MOOSE source at idaholab/moose@9f388366ccf38b9c34542ec5561198249fde0ac9:
- framework/src/utils/FunctionParserUtils.C, FunctionParserUtils<true>::functionsOptimize() lines 211-223: if JIT is disabled or JITCompile fails, emits: "AD parsed objects require JIT compilation to be enabled and working."
- The same file, parsedFunctionSetup() lines 228-262: compiles only when enable_jit is true.
- framework/src/functormaterials/ParsedFunctorMaterial.C delegates parser setup via FunctionParserUtils.

These are source facts for the *actual pinned MOOSE commit*, not assumptions based on generic MOOSE documentation. The historical Physics incident INC-ADF-JIT-001 already records the same requirement.

Therefore **requiring full P3 PASS for ADParsedFunctorMaterial with enable_jit=false is not a valid default acceptance condition.** A JIT-OFF ADParsed input is an invalid/unsupported configuration under this source contract unless an independently demonstrated supported non-JIT path exists. Its observed SIGSEGV is still unsafe and merits fail-closed protection and separately scoped upstream defect analysis, but need not be "repaired" into a valid AD numerical solution.

Revised gates:
- Supported JIT ON ADParsed: P0/P1/P2/P3 PASS with correct independently observed integral and no stale cached compilation.
- Explicit unsupported JIT OFF ADParsed: detect at P0/P2 with a stable, explanatory UNSUPPORTED_CONFIGURATION failure; prohibit P3 progression in the canonical harness. A forensic direct-run SIGSEGV remains evidence only.
- If a source-backed supported JIT-OFF implementation is later established, reopen that contract separately; do not infer support from a P2 parser success.
- Non-AD ParsedFunctorMaterial may have different JIT-off behavior; never transfer the AD rule to non-AD cases without evidence.

This supersedes the overly broad original #471 requirement that all five cases have P3 PASS. Do not silently edit/close historical evidence or claim that the original runtime bug is fixed.

## 3. Existing reusable architecture: authoritative owners

| Mechanism or decision | Existing owner | Reuse / boundary |
| --- | --- | --- |
| Hypotheses, input variants, case matrix, execution orchestration | experiments/Issue471_ad_parser_runtime/diagnose_closure.py and Issue282_e2a_rz_bridge/probe_parser_family.py | Keep Issue-specific. Do not promote the case matrix to generic production API. |
| Generic process invocation, timeout, exit and log collection | physics_harness/execution/runtime.py::run_command | Prefer over local capture() duplication; preserve P2/P3 phase identity. |
| Per-run directories and generated-cache purge | physics_harness/execution/cases.py and evidence/identity.py | Reuse fresh-directory and hash functions, isolate cold and warm JIT evidence. |
| Source/executable/input SHA, provenance and artifact reference | physics_harness/evidence/identity.py, evidence/artifacts.py, provenance/ | Return facts only; no model PASS from these helpers. |
| MOOSE P0 parser names/reserved symbols | physics_harness/adapters/moose/preflight.py | Extend only with a source-backed ADParsed/JIT capability precondition when contract agreed; no general-purpose registry. |
| MOOSE P2 failure fact classification | physics_harness/adapters/moose/check_input.py::classify_failure | Reuse JIT_COMPILE_FAIL fact. Do not classify root cause from the error string alone. |
| Backend-specific C++ source inspection | physics_harness/adapters/moose/source_inspection.py | Already source-structure owner; do not misuse it as an ELF process runner. |
| Raw MOOSE/PETSc log grammar | physics_harness/adapters/moose/log.py and check_input.py | Decode backend-specific facts here when reuse is demonstrated. |
| State/hypothesis reasoning | physics_harness/reasoning/diagnosis.py | Consume normalized observations, not Docker or MOOSE syntax. |
| Acceptance/phase/error semantics | physics_harness/validation/ plus docs/protocols/validation.md and ci_scientific_outcome_semantics.md | Evidence validity, runtime compatibility and science acceptance remain independent. |
| Runtime image construction and build provenance | ci/physics-build-base and ci/physics-runtime-image/collect-runtime.sh, Dockerfile | Build toolchain and image dependency closure are PhysicsApp build owners, not SOL semantics. |
| Vertical physics runtime/oracle checkers | physics_app/ci/check_r2_o2_ionization_implementation.py and check_r3_o2s_excitation_implementation.py | Useful additional native positive regression controls, not generic JIT execution owners. |

**Architecture ambiguity (distinguish names precisely):** coding.md explicitly permits a reusable physics_harness/diagnostics/ fact-extraction owner, and physics_architecture_census.py lists diagnostics as an allowed capability directory. However, physics_directory_roles_v1.json and qpx_harness_folder_contracts.md do not assign it an explicit current responsibility, and no actual physics_harness/diagnostics package exists in the reviewed main snapshot. The **older physics_harness/diagnose namespace**, not diagnostics, is explicitly retired. For #471, existing execution/evidence/MOOSE-adapter/reasoning owners are sufficient; a new diagnostics package would require its own demonstrated cross-issue responsibility and a deliberate roles-policy decision rather than being automatically forbidden or automatically justified.

## 4. Dependency graph for this work

~~~text
Issue #471 experimental plan (Physics-owned; diagnostic only)
  |  reusable case staging, executable command, timeout
  +--> physics_harness/execution/runtime + execution/cases
  |  MOOSE-specific input compatibility & decoded error facts
  +--> physics_harness/adapters/moose/preflight + check_input
  |  binary/image/build-specific observations (toolchain witness)
  +--> ci/physics-runtime-image provenance and pinned build-base introspection
  |  source/ELF/log/input identity and artifact references
  +--> physics_harness/evidence + provenance
  |  normalized facts only
  +--> physics_harness/reasoning + validation
  v
Issue-scoped diagnostic decision / minimal proposed repair
  |
  +--> PhysicsApp toolchain/runtime fix only after validated root cause
  +--> Physics #282 2D scientific gate only after compatible native P3
  +--> SOL #172 and Physics #281 / Adapter #29 remain independent
~~~

Forbidden new edges:
- ontology, specification, planning, generic execution, reasoning or evidence must not import Docker/JIT/FParser/MOOSE-specific code.
- Physics runtime build/diagnostic state must not appear as a new SOL public capability, HIT semantic, or Adapter Protocol request field.
- No alternative local SOL session/transport or automatic A2 cutover.
- No new root scripts, second generic runner, issue-specific production "diagnostics" package, or duplicate hash/error/timeout infrastructure.

The on-repo MOOSE-specific diagnostic is transitional PhysicsApp development tooling. Evaluate any later **operational** extraction to sol-adapter-moose only under the existing Adapter #29 / Physics #281 ownership-parity gates, not as a prerequisite to fixing #471.

## 5. Smallest interoperable evidence record (diagnostic, not public DTO)

Persist a version-tagged issue-local JSON summary referring to raw, immutable artifacts. Do not enlarge ontology records or public SOL schemas.

~~~json
{
  "schema": "physics.native-ad-parser-diagnostic.v1",
  "science_acceptance": "NOT_EVALUATED",
  "source": {
    "physics_revision": "<git sha>",
    "moose_revision": "<git sha>",
    "runtime_image_digest": "<immutable image digest>",
    "build_base_image_digest": "<immutable image digest>",
    "physics_opt_sha256": "<file hash>"
  },
  "observations": [
    {
      "case": "mini_ad",
      "environment": "scratch",
      "input_sha256": "<file hash>",
      "jit_mode": "ON",
      "cache_state": "COLD",
      "phases": {
        "P0": "PASS",
        "P2": {"executed": true, "rc": 1, "log": "<artifact relative path>"},
        "P3": {"executed": false, "rc": null, "log": null}
      },
      "compiler_invocation": "NOT_OBSERVED",
      "loaded_library_manifest": "NOT_OBSERVED"
    }
  ],
  "evidence_valid": true,
  "runtime_compatibility": "UNRESOLVED",
  "hypothesis_status": "NOT_DETERMINED",
  "scientific_outcome": "NOT_EVALUATED"
}
~~~

The string fields are **illustrative schema candidates**, not claims about any historical run. Exact shape and allowed values require P0 self-tests before implementation.

Required machine-enforced invariants:
1. Record actual image and binary hashes and specific loaded libraries, not merely image labels or ldd existence.
2. Every P3 claim requires P2 allowed progression and a separately recorded actual P3 invocation.
3. Missing evidence or changed input/image/loader identity makes comparison INCOMPARABLE.
4. Diagnostic experiment outcome is separate from evidence validity and scientific acceptance.
5. Parent Issue #471 CLOSED or CI green never means root cause repaired; compare against explicit runtime gates.
6. Preserve raw command provenance, stdout/stderr, signal/timeout metadata and hash-addressed artifact pointers; normalize before reasoning.
7. Distinguish a known unsupported JIT mode from a failed supported mode.
8. Treat a build-base success with different libmoose/libmesh/ld.so loaded objects as evidence of environment sensitivity, **not an isolated compiler diagnosis**.

## 6. Controlled discriminator matrix and compatibility acceptance

### Supported JIT ON — minimal non-physics controls

- Base FV, ADGenericFunctorMaterial: must independently P2/P3 PASS in each environment.
- Single ADParsedFunctorMaterial and nested ADParsed: run supported JIT ON with identical *source, executable SHA and input*; require expected integral values, not only rc==0.
- Partition cold P2 check, cold independent P3 and optional warm-cache confirmation into distinct work directories; a P2-generated .jitcache must not silently turn "P3 cold" into a warmed reuse path.
- Compare scratch vs build-base both as received; do not overwrite the scratch image or change the source physical model.

### Unsupported JIT OFF — safety controls

- Single/nested ADParsed with enable_jit=false are NEGATIVE acceptance tests, not positive P3 tests under the pinned source contract.
- P0 or P2 emits an explicit UNSUPPORTED_CONFIGURATION and must never enter canonical P3. If a direct forensic run segfaults, retain its signal and stack and consider a separate upstream safety fix; it cannot be counted as missing *supported physics* parity.
- A non-AD ParsedFunctorMaterial JIT-off positive control is independently useful to distinguish broad compiler failures from AD-specific support limitations.

### Exact environment separation

- Compiler: exact FParser-baked invocation or execve trace, wrapper path, flags and headers (including possible ADReal-specific JIT include dependency), effective PATH/CXX/TMPDIR and exit status.
- Dynamic loader: ldd is only an initial preflight. Compare loaded libmoose, libmesh, FParser, compiler runtime and ld.so provenance using ELF build-id/SHA and runtime library maps/loader traces as applicable. Handle dlopen dependencies.
- JIT artifacts: generated source/shared object, cache path and cold/warm identity when safely accessible.
- Source: exact pinned MOOSE API contract. Do not apply current upstream doc behavior to a mismatched pinned binary without verification.
- Any extra debug tracing capability or modified container privileges require an explicit bounded instrumentation decision and unchanged baseline control.

## 7. Minimal staged implementation after architectural review

### Phase A — contract correction and import-boundary tests (no native run)

- Fix the #471 diagnostic acceptance description: ADParsed/JIT-ON supported; ADParsed/JIT-OFF unsupported under pinned source and must fail closed. Leave historical logs intact.
- Add source-backed P0 characterization and expected failure-vs-supported-mode tests in the existing test suite.
- Classify any apparent reverse dependency and existing coding.md/diagnostics ambiguity; use existing architecture guards, not a new implementation hierarchy.
- No change to physics model, image, Adapter protocol or numerical tolerance.

**A completion:** design reviewed, policy and test semantics non-contradictory, source reference pinned, boundary/negative regression specified.

### Phase B — trace-only wiring of existing owners

- In the existing Issue #471 runner, use canonical execution.run_command() and evidence.sha256_file() where behavior-preserving. Introduce no shared module unless a concrete second caller needs the same stable contract.
- Add *read-only* toolchain/loader observations and separate cold P2/P3 directories; record unsupported-config preflight before any P3.
- Reuse existing MOOSE check_input classifier and repository evidence helpers. Keep raw backend probes behind the explicit MOOSE diagnostic/PhysicsApp build boundary.
- P0 self-test incomplete evidence, unavailable strace/loader metadata, mismatched build-libraries, stale cache, wrong phase progression and unsupported JIT OFF.
- Use governed native execution route; no new automatically triggered one-shot workflow merely for orchestration convenience. Follow local workflow guard and Samuel execution policy.

**B completion:** native comparison artifact has trustworthy image/compiler/loader/fparser evidence, independent positive controls, and correctly classified negative controls. Successful diagnostic collection is not release acceptance.

### Phase C — repair, regression and downstream gate (separate approval)

- Select the smallest verified *runtime build/toolchain* defect; preserve prior pinned runtime digest and expose a separately pinned candidate. Do not guess or copy libraries to force green.
- Require supported JIT ON single/nested ADParsed P2 + cold P3 + correct integrals and non-AD controls on candidate, with exact loaded-library and compiler provenance.
- Verify unsupported JIT OFF is rejected deterministically, never as uncontrolled SIGSEGV in the governed path.
- After runtime support and regression are proved, use original-class R4-QF1/E2a D=0/D=100 2D native P3, then separate independent 2D Gaussian/mesh/time/reference V&V. Keep 1e-4 target unchanged.
- Maintain SOL #172 official semantic acceptance and Physics #281/Adapter #29 consumer parity as separate gates. No public plasma advertisement or production cutover.

**C completion:** explicit supported-runtime regression and separate scientific gate evidence. Does not follow merely from merging this ADR.

## 8. Rejected designs and risks

| Choice | Disposition | Rationale |
| --- | --- | --- |
| Copy Issue #8 probes into Issue #471 as a large independent runner | REJECT | Duplicates execution/evidence; creates two sources of phase and error truth. |
| New physics_harness/diagnostics package for this issue | REJECT | Unnecessary extra owner while current primitives suffice; diagnostics is a permitted-but-unimplemented directory name, whereas only the old diagnose namespace is explicitly retired. |
| Promote PhysicsApp JIT test into SOL public contract or advertise plasma via Adapter | REJECT | Runtime build compatibility is not canonical simulation meaning; formal gates pending. |
| Force JIT OFF, replace all ADParsed with ADGeneric, or disable relevant materials to make P3 green | REJECT | Unsupported mode or changes evaluation/physical meaning, invalidates the scientific claim. |
| Assume build-base JIT ON PASS proves "compiler missing" | REJECT | Loader/libmesh/header/wrapper variables co-vary. |
| Ship compiler/development tree in scratch image immediately | DEFER | Might be appropriate after exact compiler+header closure is known; changes runtime footprint and security surface. |
| Extract stable source-backed ADParsed/JIT compatibility preflight in adapters/moose | CONDITIONAL | Only if independent test demonstrates it belongs in backend compatibility and not an issue-local assumption; preserve future adapter migration. |
| Reuse existing execution/evidence and issue-local MOOSE probes | PREFERRED | Minimal ownership growth, testable phase separation and clear rollback. |

## 9. Review questions and explicit non-goals

Architecture reviewer must confirm:
1. Exact source-backed JIT ON/OFF contract; unsupported-mode P0/P2 prevention and retained forensic P3 evidence.
2. Generic execution and evidence helpers suffice without new abstractions; source inspection and binary introspection remain distinct.
3. The scope of reusable MOOSE compatibility preflight, if any, versus PhysicsApp image build diagnostics.
4. The issue-local diagnostic evidence shape meets phase/identity/interpretability requirements without becoming a SOL schema.
5. Whether generic CI should validate only P0/source contract or preserve any reproducible bounded native JIT fixture, and how evidence validity maps to workflow success.
6. Whether a separate upstream MOOSE safety report is warranted for unsupported JIT-OFF SIGSEGV, without treating the unsupported path as scientific acceptance.

Non-goals: new JIT interpreter, MOOSE source patch before diagnosis, new Physics equation, SOL API extension, adapter capability advertisement, runtime image publish, integration merge, new 2D numeric claim or automatic approval.

## 10. Sources reviewed

- docs/architecture/qpx_harness_folder_contracts.md; physics_directory_roles_v1.json; physics_sol_adapter_boundary_refactor.md; adapter_extraction_evaluation.md.
- docs/protocols/coding.md CODE-01/03/05/06/08/10/11; validation.md VAL-01/04/18/19; problem_solving.md PS-03/04/05/11/12/20; ci_scientific_outcome_semantics.md.
- docs/incidents/adfparser_jitcompile_failure.md and adfparser_jit_environment_evidence.md: Issue #8 historical compiler/JIT/cache investigation, which specifically does **not** prove conda activation caused its later recovery.
- experiments/Issue282_e2a_rz_bridge/probe_parser_family.py and diagnose_gdb_stack.py.
- experiments/Issue471_ad_parser_runtime/diagnose_closure.py; tests/characterization/test_issue471_runtime_closure.py.
- physics_harness/execution/runtime.py and cases.py; evidence/identity.py and artifacts.py; adapters/moose/preflight.py and check_input.py; reasoning/diagnosis.py; physics_app/ci R2 and R3 local runtime checkers.
- ci/physics-runtime-image/collect-runtime.sh; pinned Physics runtime/base images as in #471 and PR #474.
- Exact upstream MOOSE 9f388366 FunctionParserUtils.C and ParsedFunctorMaterial.C.

**Review status:** source and ownership inventory performed; this proposal has not received independent approval. Do not interpret a draft PR or its green CI as approval of the acceptance contract or its implementation.

## 11. Exact-source codeQA pilot (2026-11-09)

Evidence: Physics [Draft PR #486](https://github.com/HyungseonSong-plasma/moose-test-repo/pull/486), [Actions #42591065322](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/42591065322), artifact #13660149954. Analyzer codeQA@1b6110631883f1299127e134b4134d3686765d2c; Physics subject@625702fa325a0a62243786b5a752c548ba54100f. Artifact JSON SHA-256 internally verified. This is source-bounded static evidence, not architecture/science acceptance.

Reused unchanged codeQA B1 inventory, B2 metrics, B3 opportunity discovery, and selected Python Mechanical pipeline: 175 analyzed Python files, 182 resolved static pairs, 10 B3 signals (3 cross-role concentrations, 4 role boundary candidates, 3 static SCCs), and 28 Mechanical review findings in 13 focal files. Analysis status LIMITED. B2 noted 760 outside-snapshot and 4 dynamic-import unresolved observations; these are unknowns, not proven defects. No C++/MOOSE/ELF/ABI or scientific result was analyzed. B4/B5/B7 layout/migration assessment was not executed against Physics.

### Interpretation and design decisions

1. The application role has 22/24 cross-role outgoing import pairs. Composition is its documented responsibility; KEEP, no automatic move. A high ratio raises a question, not a code-quality verdict.
2. All four projected role violations originate in application/performance.py. Physics source policy explicitly approves the moose.performance operational boundary. The pilot dropped that exception and broadened moose-only prohibition to all adapters, also catching an unconstrained PETSc performance import. These are policy projection artifacts, **not proven repository violations**. codeQA follow-up [#294](https://github.com/HyungseonSong-plasma/codeQA/issues/294).
3. Static SCC input_contract.py:443 -> target.py:13 includes a deferred self_test import. Static SCC default_plot.py:305 -> species_plot.py:16 includes a branch-local dispatch import. Both need real initialization/use-case evidence before refactoring.
4. Ontology __init__.py:12 -> service.py:11 candidate cycle includes the ambiguous Python form 'from . import records as semantic_model' and an existing sibling records.py. CodeQA's current package-candidate edge is not proven semantic/member binding, so classifying the cycle as harmful would overstate evidence. codeQA follow-up [#293](https://github.com/HyungseonSong-plasma/codeQA/issues/293).
5. Issue471 diagnose_closure.py main, prepare, run_modes and verdict were flagged for syntactic outgoing call-site counts above 12. This supports a targeted responsibility review of the runner and acceptance logic, not a new diagnostics package or blind function splitting.
6. The source-backed MOOSE requirement that ADParsed/JIT-OFF is unsupported comes from pinned MOOSE code, **not codeQA**. Keep unsupported-mode negative safety check separate from supported JIT ON P2/P3 scientific/runtime regression.
7. No source-grounded codeQA signal justifies a new generic diagnostics module, SOL schema, or adapter capability. Prefer existing execution, evidence, MOOSE preflight, reasoning and validation owners.

### Reusable codeQA improvements

- The external consumer needs a stable read-only pinned Git snapshot entrypoint and explicit policy-compatibility status. The Pilot temporarily supplied this integration outside codeQA production; do not vendor a parallel codeQA engine.
- Relative package-import resolution should expose candidate targets and uncertainty rather than a high-confidence actionable runtime cycle (#293).
- Nested role/module-prefix prohibitions, approved operational exceptions and transitional exceptions must not be flattened into a false violation (#294).
- Review hints should distinguish syntax call-site count from API coupling or semantic ownership, and categorize unknown imports by excluded internal vs stdlib/external where provable.
- Follow the same exact-source/denominator methodology after each separately approved change. Do not interpret fewer counts as an improvement without independent behavior tests.

### Pilot execution history

First run #42590892365 completed B1/B2/B3 but failed in the **Pilot adapter** reading output key 'signals' instead of the codeQA contract key 'architecture_signals'. The adapter was corrected; verified follow-up #42591065322 completed successfully. This is not a codeQA B3 defect. The Draft Pilot workflow remains unmerged and read-only; no Runtime image, SOL/Adapter contract, Physics model or 2D acceptance gate was changed.
