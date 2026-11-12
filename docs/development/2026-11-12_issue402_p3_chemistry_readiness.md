# Issue #402 — S6-417 / S6-941 Chemistry P3 execution-readiness contract

**Status:** STATIC preparation only. **No P3 solve dispatched; no merge.**
The science parity/authorization boundary remains `SCIENCE_HOLD`.

## Required for one Native 400 W / 100 µs Chemistry P3 per case

1. A full, exact-head C++ build of PhysicsApp in the pinned OCI image;
   preserve the source-head and binary SHA-256 in immutable evidence.
2. The pinned historical public 400 W prepared mesh, original ten-layer
   archive from Issue493, and approved **public** Boltzmann rates (19 rate
   table hashes checked), with no private `private_rates` input read.
3. The exact ten-layer disposable C/D scratch copy and canonical FEM
   type/state remap, **followed by** `chemistry/prepare_s6_run_input.py`.
   This removes exactly nine superseded electron particle/energy
   FunctorKernels, preserves the original progress providers, and replaces
   the transport-only sidecar with `s6_<case>_chemistry_run.template.i`.
   Sidecar must name common + one variant JSON, eight independent channels.
   The signed elastic losses are projected inside Chemistry, with no
   auxiliary `[FunctorMaterials]` blocks in the sidecar.
4. Native `--check-input` P2 of that exact staged final deck **using the
   same binary**, for both 417 and 941. Every source owner, signed energy
   coefficient, wall/RF/Poisson and FVM operator must be reconciled.
5. Only then, an explicitly authorized, separately isolated **single**
   461-frame 100-µs Native P3 per case, with canonical Exodus
   `log_e`, `log_e_energy`, `log_O2p`, `log_Om`, `log_Op`.
   Save stdout, input/source hashes, `plasma.e`, `plasma.csv`,
   and a fail-closed `status.json`. P4 reference overlay is
   diagnostic only, not a scientific acceptance.
6. GitHub Actions artifact upload **must have a verified REST artifact ID
   and receipt**. The current main-push P3 workflow uses an unaudited
   single `upload-artifact@v4` and is **not an approved Chemistry workflow**.
   Integrate the separately Draft Issue518 receipt/retry fix or another
   independently verified durable store *before* the costly replay.
7. Independent B-vs-new-D chemistry/transport numerical, source, charge,
   conservation and energy parity review is still **unaccepted**.

## Keep / exclude / retire in the new execution path

| Group | Objects | Decision |
|---|---|---|
| Keep | immutable B/C source archives, hashes, public mesh, rate provenance | required evidence, never modify |
| Keep | original S6 Native Poisson, Maxwell/RF PID, FV ions, BCs, true ion Functors | existing physical owners |
| Keep | existing Native `PlasmaChargeTransportMaterial` for O2p/Om/Op | canonical ion mobility/diffusivity AD Functors, not numerical constants |
| Keep | `oxygen_s6_common.json` plus exactly one 417/941 JSON | eight rate/channel identities |
| Keep | guarded `prepare_s6_run_input.py`, exact-head P1/P2, 461-frame P3, P4 diagnostic | required gates |
| Exclude | P2 synthetic `plasma_auto_*.json`, `plasma_two_channels.json`, constant mock rates | validation fixtures, not physics |
| Exclude | `NVMaterial`/NavierStokes Physics from this S6 electron Chemistry P3 | no approved NavierStokes PDE cutover |
| Exclude | P3 transport-only `plasma_species_only.json` and its old sidecar | wrong scientific scope |
| Retire only in scratch | nine old electron chemistry source Kernels; old `ne_time`/ `ne_transport` | duplicate Physics owners |
| Retire only in scratch | old kinetic rate tokens `R_elastic_O2`, `R_elastic_O`, `R_ion_O2` | direct canonical provider + consumer renames, never rename originals |
| Exclude | Physics-created new energy/potential ICs in archived S6 decks | originals already supply solver states / ICs |
| Exclude | P3 B replay, original archive edits, full science promotion, automatic merge | outside current approval |

**No deletion of source files is justified** by these exclusions. They
are scope reductions inside the new P3 candidate, not claims of
globally unused code.

## Safe preparation command (no Native solve)

```bash
python3 experiments/Issue402_plasma_dsl_g1/p3_chemistry_preflight.py \
  --output /tmp/issue402_chemistry_p3_readiness.json
```

The manifest reports only static readiness and marks P0, P1, P2, P3,
P4, artifact receipts and science acceptance independently. It does not
replace a Native compiled P2 or the expensive scientific replay.

## Future execution interface (not invoked)

`run_chemistry_s6_p3_once.py` invokes the single P3 machinery only with
`--authorize-p3`, an exact source SHA, historical public checkout,
an existing source-bound binary and an unused output path. There is
**no** GitHub Actions trigger wired to this script at present.
The old `issue402-canonical-s6-d-once.yml` runs a transport-only
candidate and must not be used as Chemistry validation.

Readiness must remain blocked until a receipt-safe workflow or
equivalent execution host is approved and the required P1/P2 gates pass.
