# New-only FVKernel D5 complete source usage census

Issue [#774](https://github.com/HyungseonSong-plasma/moose-test-repo/issues/774). Stacked source [PR #665](https://github.com/HyungseonSong-plasma/moose-test-repo/pull/665) at `9457191f4c0693ae886586edd961965867ccd5c0` before adding instrumentation.

The earlier [Native P05 #44366325757](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/44366325757) traced **77 FEProblemBase add-object events** per 417/941 case, but only exported the 32 filtered three-ion FVKernel/FVBC/electron-BC registrations. The remaining events were not exported. The 12/15 static source inventory was from `main`, while PR #665 actually contains **13 source .C files / 18 PhysicsApp Factory types** (including the new `FVLogMolarTransport.C`).

This change does not modify the production input, C++, protected rates, P05 Native observer, or original P05 12+12+8 checks. It adds a strict SHA-bound, type-only summary of **all actual addFVKernel registrations** using that same clean trace. Each observed PhysicsApp Factory type is joined to its owner .C and exact Git blob. Names and private rate contents are never exported; unrecognized framework types are counted separately. Both variants retain exact source-head and ELF SHA identities; the original input SHA receipts remain adjacent in the artifact.

Receipt key: `full_fvkernel_source_usage[417|941]` under `p05_negative_receipt.json`. Each of the 13 source rows is `OBSERVED_VIA_FEProblemBase_addFVKernel` or `NOT_OBSERVED_IN_INSTRUMENTED_API` with `safe_to_delete=false`. A missing marker, malformed/truncated trace, wrong SHA, duplicate source Factory owner, or unexpected event fails the P05 clean observation.

**Limitations:** This is the complete observed *interposed registration API*, not full Warehouse traversal, an exhaustive external runtime consumer census, P3 physics parity or deletion approval. Run this instrumented Source-only change before a second build with Thermal source removed. Do not compare unlike input/ELF/source identities or mistake a P2 check for P3 parity.

## Before/after source-deletion A/B contract

1. **Before (A):** Build exact instrumented New-only source, with Thermal `.C/.h` present, capture `full_fvkernel_source_usage` for 417 and 941 with clean P05 success and 11-layer/chemistry JSON/mesh SHA identities.
2. **After (B):** Fork this exact source with **only Thermal `.C/.h` deleted** for the physics difference. Perform a fresh exact-HEAD PhysicsApp build in the same pinned OCI; repeat the identical 417/941 P05 clean Native checks and full trace.
3. Join each run by Case, immutable original 11-layer/JSON/mesh SHA, pinned OCI digest and build provenance. Allow A/B binary SHA to differ because the C++ translation unit was removed; never claim same binary. Require equal full type-count maps, source rows for every **other** implementation file, P05 12+12+8 expected owners and N1–N8 failures.
4. If either run lacks original protected-rate provenance, full trace SHA, one-shot observer marker, or clean success, classify `HOLD`; do not infer absence. Scientific P3 numerical equivalence remains outside the P2 check and demands separate accepted evidence if required.

The Full Native Tracer records *successful FEProblemBase API registrations*, not an exhaustive list of possible statically registered classes. A zero count is only a run-local negative observation.
