# FDEG Harness A–D correctness remediation

> **Historical design record (#881).** The standalone subsystem is being retired. Commands and contracts below describe the original implementation at [pre-retirement revision 7a119106](https://github.com/HyungseonSong-plasma/moose-test-repo/tree/7a119106a22f2de2ca5c761a4119f00509e0efdd); they are not current CI instructions. See [historical provenance](archive/issue881_fdeg/README.md) and [Harness Code](../../physics_harness/code/README.md).

**Issue:** #718. **Implementation PR:** #719. **Prior canonical contract:** Structural v0.3, Functional v0.2, Transition v0.1. **Safety:** no Physics C++ changes and `SAFE_DELETE=HOLD`.

## A — Structural consumer accuracy (H01–H05)

- Python AST type keyword filtering is now limited to known MOOSE creation APIs, so `argparse.add_argument(type=Path)` is never treated as dynamic MOOSE Factory use. Dictionary `{"type": make_type()}` still creates an explicit unknown rather than disappearing.
- Source-location `experiments/historical_...` now receives `HISTORICAL_LOCATION_ACTIVITY_UNKNOWN`, not unconditional historical-only disposition. Static Python module imports are incoming graph edges with `NOT_OBSERVED` execution, not caller-zero proof. Exact pinned historical lifecycle requires a separately verified receipt.
- `python_routes` no longer uses file-global `_insert_kernel` text to convert unrelated assertions into generator candidates. Only literal strings under direct AST writer/upsert calls can be declared `STATIC_WRITER_ARGUMENT_CANDIDATE`. AST type maps remain declaration candidates, not generated output.
- Literal MOOSE `[FVKernels]` blocks contained inside multiline Python strings receive **source-attested virtual** `instance_id`, `block_path`, `variable/rho/state_form`, line/blob witness, and `PYTHON_TEMPLATE_INSTANTIATES`. Their activation and generated output remain unknown. This is not permission to edit source or proof of generated/staged `.i`.

## B — Graph completeness and relevance (H06–H08)

- `global_scan_status` and `target_dependency_status` are separate. Target blockers require a source-line witness in the selected target-rooted edges/input bindings; unrelated workflow diagnostics remain in global `unresolved[]`. The legacy `status` remains a conservative global status for compatibility.
- `source_template_census.declared_lines` independently scans literal Python type declaration lines and compares them with source-attested virtual instances. Missing templates are explicit `PYTHON_TEMPLATE_TYPE_DECLARATION_NOT_MAPPED` unresolved and `SOURCE_TEMPLATE_GAP` status, never caller-zero.
- Required code6 evidence test: independent source audit found 10 Python files / 15 declarations; the new scanner must enumerate **at least** 15 source-bound virtual records, including H05/S5D/standard, with no missing literal declaration. This is bounded source coverage, **not** runtime or external consumer coverage.
- Functional's target unresolved contract depends on `target_dependency_status`, not global unresolved count; the full scanner diagnostic count remains available.

## C — Functional/Transition correctness (H09–H12)

- `validParams()` `MooseEnum` allowed values and required locally declared parameters are source-attested. Each consumer now has `declared_input_validation`: `INVALID`, `SUPPORTED_SOURCE_ONLY`, or `UNKNOWN`; generated input remains `NOT_OBSERVED`. A source-declared `state_form=molar_eV` for code2 is invalid against `normalized physical_eV` without silent correction.
- Invalid source input adds a Transition `INVALID_GENERATED_INPUT` blocker. Old code1/4 historical-path generation remains `CURRENT_CONSUMER_MIGRATION_REQUIRED_OR_HOLD`, not frozen-only.
- `change_sites` separately carries protected/lexical/historical **no-edit** paths; REWIRE's affected paths only contain potential editable source-attested sites with a candidate and required gates.
- An owner without approved replacement receives an explicit conditional `RETIRE_UNSUPPORTED_CONSUMER_WITH_EXPLICIT_APPROVAL` **option**, requiring independent supported-scope absence, coverage, historical retention and current-binary compatibility termination. All mandatory approvals are OPEN; `safe_delete=HOLD`.
- Shared C++ translation units expose required independent per-class owner coverage and demand a four-S/F/T exact-HEAD manifest. The independent code5 PR #709 may supply the complete four-owner manifest. A single target's JSON alone never claims 4/4 discharge.

## D — Retirement lifecycle/evidence delivery (H13–H14)

- New `ci/guards/fdeg_retirement_evidence.py` provides `capture`, `verify-archive`, and `verify-retired`. `capture` reconstructs S/F/T at **one clean exact HEAD** and stores canonical JSON reports plus a SHA-256 manifest including graph IDs, baseline source Blob SHA, open blockers, historic receipt and runtime status.
- Post-cut `verify-retired` requires frozen manifest, all registered owner claims, owner/native/coverage/compatibility/historical/rollback receipt references, exact retirement HEAD, source file absence, no in-scope symbol reintroduction, and independent generated/external scope attestation. This is a **static negative guard**, not a verifier of the referenced external Native receipts. Even its positive result cannot say SAFE_DELETE=PASS.
- Canonical Repository CI template and `.github/workflows/ci.yml` run Structural, Functional, Transition, new A–D P0, then code7 exact-HEAD capture and archive verification. The `fdeg-retirement-code7-<run>-<attempt>` artifact includes four JSON files with 14-day retention. Do not conflate a green CI check with independent blind GPT Graph-only acceptance.

### CLI example

```sh
head="$(git rev-parse HEAD)"
python3 ci/guards/fdeg_retirement_evidence.py --mode capture \
  --target PhysicsFVThermalDiffusion --expected-head "$head" \
  --output-dir /tmp/fdeg-retirement-code7
python3 ci/guards/fdeg_retirement_evidence.py --mode verify-archive \
  --expected-head "$head" --output-dir /tmp/fdeg-retirement-code7
python3 -m unittest discover -s tests -p test_fdeg_harness_abcd.py -v
```

The archive must be retained outside the target retirement Git change. `verify-retired` additionally requires a separately reviewed JSON with `schema=fdeg.retired_review.v0.1`, `state=RETIRED` and receipt references. It cannot establish independent experimental acceptance from source strings alone.

**Explicitly not done:** Native residual/AD parity, source or Factory deletion, accepted full external/generated caller census, independent GPT blind Graph-only acceptance, approved tolerances, actual producer activation, automatic code migration or main merge.