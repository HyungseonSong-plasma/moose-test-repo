# Issue #402 — DDMaterial absorbs species transport alias forwarding

All new drift-diffusion species coefficient providers use DDMaterial.

`DDMaterial model=functor` (the internal MOOSE transport mode) uses the existing
`<species>_mobility` [m²/(V s)] and
`<species>_diffusivity` [m²/s] AD Functors by naming convention.
If those Functors are already published, DDMaterial never publishes
duplicate aliases; any values are forwarded without conversion,
smoothing, clamping or a new coefficient formula. It rejects mixed input
modes and directly self-referential source names. The entire
`SpeciesTransportAliasMaterial.h/.C` implementation is retired.

For the S6 417 and 941 **review JSON**, three ion entries use
`{"model":"constants"}` and are automatically mapped to the internal
`DDMaterial model=functor` implementation. This means **existing
species-named AD Functors** from Native providers; it does not imply
spatially constant numerical values. The old manual DDMaterial blocks
are absent from the new review and run-input overlays.

The same mode is usable directly from ordered JSON:
```json
{"transport_coefficients":{"drift_diffusion":{
  "O2p":{"model":"constants"}
}}}
```
Do not define an explicit DDMaterial block for the same species at the
same time as a JSON owner. The frozen B/C archive remains immutable.
The old template's original legacy tokens are not retained as aliases:
new D scratch is rewritten instead; other old inputs require migration
before use.

**Verification:** Native P1 and P2 on exact source head, synthetic JSON
auto-binding input, full S6 417 and 941 input construction, and future
numerical/AD parity are independent gates. No P3 or science acceptance.

**Current JSON contract:** A `model=constants` entry is exactly
`{"model":"constants"}`. The keys `mobility_source` and
`diffusivity_source` are rejected by the JSON parser. The upstream
producer (e.g. `PlasmaChargeTransportMaterial`) must publish the
canonical species names first. Legacy direct `.i` Material blocks
may still use explicit source parameters, outside the JSON contract.
