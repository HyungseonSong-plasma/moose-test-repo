# Issue #402 — DDMaterial absorbs species transport alias forwarding

All new drift-diffusion species coefficient providers use DDMaterial.

`DDMaterial model=functor` accepts `mobility_source` [m²/(V s)]
and `diffusivity_source` [m²/s] as existing AD Functors and publishes
`<species>_mobility` and `<species>_diffusivity` without conversion,
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
  "O2p":{"model":"functor",
         "mobility_source":"ion_mobility",
         "diffusivity_source":"ion_diffusion"}
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
