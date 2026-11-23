# Issue #774 — D6 official Harness unresolved triage (exact immutable HEAD)

> **Source evidence only / not deletion authorization.** No runtime consumer closure implied.

## Identity

- Official `GitSourceProvider → run_scan()` (not a substitute parser): Draft [#786](https://github.com/HyungseonSong-plasma/moose-test-repo/pull/786) at `a0c325e0fd7f1d871a60f4f179dfea71ddaf1413`.
- [Run #45183621897](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/45183621897), artifact **#14822027558**, ZIP SHA-256 `cec9510f30586fda973a4833da4148ff99b924e6faf87c8d613c293eed2d1d32`.
- Original complete `d6_evidence_receipt.json` is preserved as that immutable GitHub Actions Artifact; this document is a derived audit summary and does not overwrite the receipt.
- Selected **900 files**, `SCANNED=698`, `UNRESOLVED=202`, **1,766 unresolved fact entries**; `PARTIAL/UNVERIFIED`, zero generated-Graph/provenance verification failures. The full scanned source graph is deliberately retained only as the 385 MB artifact entry.

## Unresolved file disposition, not a Thermal consumer count

| Git source family | Unresolved files | Disposition |
|---|---:|---|
| experiments/ | **104** | Generated/input/other experiment sources; **target-specific route not automatically closed** |
| .github/workflows/ | **42** | Dynamic step/job conditions and templated commands; **static parser cannot execute workflow semantics** |
| physics_app/ | **24** | Input/build/script/C++ uncertainties; retain for target-specific follow-up |
| physics_harness/ | **18** | Canonical diagnostics self-source; not direct evidence of active thermal instantiation |
| tests/ | **11** | Test code and dynamically constructed examples |
| Other, including archive/ | **3** | Explicit manual classification needed |
| **TOTAL** | **202** | Relative to selected collectors; never caller-zero |

File extensions: Python **114**, MOOSE `.i` **38**, Workflow `.yml` **42**, C/C++ **8**.

## Unresolved fact types

| Reason | Count |
|---|---:|
| MOOSE_STATEMENT_UNPARSED | 546 |
| MOOSE_DYNAMIC_PARAMETER | 382 |
| PYTHON_GENERATOR_RENDER_UNVERIFIED | 212 |
| UNRESOLVED (file summary) | 202 |
| UNRESOLVED_REFERENCE | 109 |
| DYNAMIC_RUN | 84 |
| STEP_CONDITION_NOT_EVALUATED | 61 |
| DYNAMIC_PYTHON_REFERENCE | 57 |
| PYTHON_MOOSE_TYPE_TEMPLATE_UNRESOLVED | 47 |
| CPP_PARAM_DECLARATION_UNPARSED | 21 |
| JOB_CONDITION_NOT_EVALUATED | 17 |
| MATRIX_EXPANSION_NOT_OBSERVED | 17 |
| DYNAMIC_STEP_CONDITION | 9 |
| CPP_CLASS_UNPARSED | 1 |
| CPP_MOOSE_ENUM_OPTIONS_UNRESOLVED | 1 |
| **TOTAL** | **1,766** |

Only **3** of the 202 unresolved filenames literally contain `thermal`, `fdeg`, or `issue774`: `.github/workflows/issue774-d6-thermal-scope-once.yml`, `tests/test_fdeg_functional.py`, `tests/test_fdeg_structural.py`. These yield **5** corresponding unresolved entries. **This string-filtered shortlist is not proof that all indirectly related generated inputs are absent.** It is only a high-priority starting point.

## Narrow closure strategy

1. **Do not treat 202 as 202 old-Thermal consumers.** Cross-link exact tracked reference census (17 paths / 0 direct tracked PhysicsApp `.i`) and actual D5 P05 417/941 clean registration (Thermal 0) before investigating a candidate dynamic producer.
2. **Target-sensitive dynamic generation:** for a generator capable of constructing MOOSE `type` dynamically, capture the exact **executed rendered `.i`** and Factory registration into a source/binary/run receipt. If not executed, mark `NOT_EVALUATED`.
3. **Historical compatibility:** test the **same synthetic old PhysicsApp Factory input** on immutable pre/post W1 ELF (separate Draft #789), then independently select current-binary support policy. Presence/absence of an API is not AD residual equivalence.
4. **Workflow dynamics:** do not change the canonical diagnostics parser globally just to eliminate unrelated `PARTIAL`. Investigate only workflow paths that can create Thermal consumers; native job execution evidence is separate from YAML static facts.
5. **Independent coverage and owner reviews:** still required for generated/external consumer scope, historical support termination, rollback and scientific parity.

**Gate:** `D6_HARNESS_PARTIAL_UNRESOLVED_REMAINING / LEGACY_BINARY_AB_UNDER_SEPARATE_TEST / SAFE_DELETE=HOLD`.