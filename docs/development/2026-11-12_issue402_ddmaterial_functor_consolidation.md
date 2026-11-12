# Issue #402 — DDMaterial absorbs species transport alias forwarding

All new drift-diffusion species coefficient providers use DDMaterial.

`DDMaterial model=functor` uses the existing
`<species>_mobility` [m²/(V s)] and
`<species>_diffusivity` [m²/s] AD Functors by naming convention.
If those Functors are already published, DDMaterial never publishes
duplicate aliases; any values are forwarded without conversion,
smoothing, clamping or a new coefficient formula. It rejects mixed input
modes and directly self-referential source names. The entire
`SpeciesTransportAliasMaterial.h/.C` implementation is retired.

For the scratch S6 417 and 941 Chemistry overlays, each of three ion
providers uses `type = DDMaterial`, `model = functor`, preserving
the original ion, negative-ion and atomic-ion source Functors and
AD derivatives. The explicit old block *instance names* remain for
audit diff stability but their C++ Material type is DDMaterial.

The same mode is usable directly from ordered JSON:
```json
{"transport_coefficients":{"drift_diffusion":{
  "O2p":{"model":"functor"}
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

**Current JSON contract:** A `model=functor` entry is exactly
`{"model":"functor"}`. The keys `mobility_source` and
`diffusivity_source` are rejected by the JSON parser. The upstream
producer (e.g. `PlasmaChargeTransportMaterial`) must publish the
canonical species names first. Legacy direct `.i` Material blocks
may still use explicit source parameters, outside the JSON contract.
