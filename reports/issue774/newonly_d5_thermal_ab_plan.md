# D5 exact New-only A/B post-cut Native rehearsal

**Draft-only** — do not merge into any production branch.

- A = full-coverage census branch `issue-774-d5-newonly-native-source-census`, derived from PR #665 plus strictly read-only P05 instrumentation. Actual A run must be successful with a preserved `full_fvkernel_source_usage` receipt for both 417 and 941.
- B = this branch, derived directly from A with **only** `physics_app/src/fvkernels/PhysicsFVThermalDiffusion.C` and its paired `.h` removed as a physical code difference. Test fixture expectations adjust from 13/18 source/factory inventory to 12/17; the other Factory registrations and input source are unchanged.
- Native job is the exact existing P6 W1/P05 two-job path, with source head and binary SHA re-proven and the same protected rate loader, original eleven public source layers, OCI, 12+12+8 positive owner checks, and N1-N8 x2 negatives.
- Compare **full type counts and per-source counts** across all other 12 .C units, 11-layer SHA, JSON SHA, mesh SHA, 77 post-original registration events and 417/941 clean P2. If any differ unexpectedly, set HOLD, do not claim a safe deletion.
- Raw trace names and protected reaction-rate data are not archived; both sanitized receipts only. Separate Source/CI compatibility and history tests remain in Draft #777. No full P3 scientific parity claim is made by this P2 experiment.

**Important:** Creating this branch is preparation only; until both clean exact-run A and B receipts exist, `safe_delete=false`. No active `main` code is modified by this branch.
