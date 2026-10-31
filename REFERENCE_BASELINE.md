# Branch-local reference baseline (candidate)

This branch intentionally keeps the corrected Oxygen24 400/1000 W inputs and the exact 2026-10-31 **2 ns, two-time-step** native smoke evidence as a reusable reference **without merging to main**.

**Reference ID:** `oxygen24-neutral-x1e-5-400-1000W-2ns-20261031`

**Status:** `BOUNDED_2NS_REFERENCE_CANDIDATE`; *not* a scientifically validated 100 µs ICP baseline.

Canonical branch-local record:

- [Baseline details](experiments/Issue395_powered_chemistry_ladder/reference_baselines/oxygen24_2ns_neutral_x1e5_20261031/README.md)
- [Machine-readable source/run/input manifests and SHA-256](experiments/Issue395_powered_chemistry_ladder/reference_baselines/oxygen24_2ns_neutral_x1e5_20261031/manifest.json)
- [Reference verifier](experiments/Issue395_powered_chemistry_ladder/reference_baselines/oxygen24_2ns_neutral_x1e5_20261031/verify_reference.py)
- [Exact successful native execution](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/41188685410), run head `0fe03c1e5f6bf14385f51130a43dc4732f2608dc`

**Invariants:** inlet = 200 sccm; neutral minority species O₂(a), O(³P), O(¹D) each number fraction 1e-5; residual O₂(X) 0.99997; charged seeds unchanged; 400 and 1000 W overlays distinct; 2 ns / 2 steps completed in real `physics-opt`.

**Important:** The full generated `.i` inputs are preserved in the successful run artifacts (14-day retention), referenced by exact SHA-256 in the manifest. They are **not directly checked in** as full snapshots; regeneration is pinned to source SHA and requires the private lookup tables and exact pipeline. The identical generated main `.i` files alone do not encode the distinct RF power. Do not infer 100 µs scientific validity or 5-minute whole-pipeline completion from the 2 ns smoke PASS.
