# Oxygen24 corrected-neutral 2 ns reference candidate — 2026-10-31

**Status:** `BOUNDED_2NS_REFERENCE_CANDIDATE` (not the canonical physics baseline; not merged to `main`).

This branch preserves the input-generation code and the **exact executed-source revision** for the successful **400 W and 1000 W** real-`physics-opt` two-step initialization smoke. It serves as a branch-local **quasi-baseline** for future controlled comparisons, not a 100 µs chemistry acceptance.

## Immutable evidence and generated inputs

- Executed repository commit: [`0fe03c1e5f6bf14385f51130a43dc4732f2608dc`](https://github.com/HyungseonSong-plasma/moose-test-repo/commit/0fe03c1e5f6bf14385f51130a43dc4732f2608dc).
- Executed GitHub Actions [run #41188685410](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/41188685410): 400 W and 1000 W jobs `success`, including P0–P4.
- Archived run artifacts (retention 14 days): `oxygen24-2ns-neutral-400W` (artifact `13037947569`), `oxygen24-2ns-neutral-1000W` (artifact `13037727736`). They contain the full generated main `.i` input, checks, runtime log and 3-row output CSV. Do not assume these temporary artifact ZIPs are permanent.
- Exact SHA-256 of **both generated main `.i` files**: `07056e7d61089f85cc6fdf340a6fdeef462bf989843b254d59982b03759aa531`. **They are byte-identical**, even though the RF target differs, because the **power-specific MultiApp/Maxwell parent/child overlay** controls power. The main input alone is not a standalone runnable 400 W or 1000 W case.
- The complete traceable contract, source/overlay paths, numerical settings, run artifact IDs, file hashes, outputs and acceptance limits are frozen in [`manifest.json`](manifest.json).

## Frozen physical input contract

| Inlet / initial state | Number fraction | Neutral mass fraction |
| --- | ---: | ---: |
| O₂(X) (residual) | 0.99997 | 0.9999799997999981 |
| O₂(a¹Δ), `w_O2s` | 1e-5 | 1.000010000100001e-5 |
| O(³P), `w_O` | 1e-5 | 5.000050000500005e-6 |
| O(¹D), `w_Os` | 1e-5 | 5.000050000500005e-6 |

- Inlet: **200 sccm**, total neutral mass flow **4.758967769568476e-6 kg/s**.
- Charged seeds: `n_e=n_O2+=1e15 m^-3`, `n_O+=n_O-=1e12 m^-3`.
- Initial measured `n_O(3P)=n_O(1D)=n_O2(a)=3.2188342917495e15 m^-3` on both jobs.
- Full24 research chemistry: 24 active reactions, 19 private lookup tables; EI-936 excluded.
- Time sequence `0, 1e-9, 2e-9 s`, two 1 ns steps. P3 wall clock **152 s (400 W)** and **156 s (1000 W)**; this **does not** include Python setup, native compilation, or P2 time.

## Reproducing the bounded reference

Check out **the exact executed source SHA**, not a floating branch head. With the approved private rate tables mounted externally, a compatible environment and the required native `physics-opt` build image:

```bash
git checkout 0fe03c1e5f6bf14385f51130a43dc4732f2608dc
export OXYGEN_RESEARCH_400=1
export OXYGEN_RESEARCH_FULL24=1
export OXYGEN_RESEARCH_QUICK_5MIN=1
export OXYGEN_RESEARCH_RATE_DIR=/path/to/private/19-tables
export CHATGPT_WORK_BASE_SHA=0fe03c1e5f6bf14385f51130a43dc4732f2608dc

bash experiments/Issue395_powered_chemistry_ladder/issue397_l1_power_scan_replay.sh prepare 400
bash experiments/Issue395_powered_chemistry_ladder/issue397_l1_power_scan_replay.sh build 400
bash experiments/Issue395_powered_chemistry_ladder/issue397_l1_power_scan_replay.sh check 400
timeout -s TERM -k 10s 285s bash experiments/Issue395_powered_chemistry_ladder/issue397_l1_power_scan_replay.sh solve 400
```

Use `1000` in the same commands for the independent 1000 W case. The source script runs only from its checkout root, generates meshes and overlays, and expects Docker/build dependencies. Never commit the private numeric collision/rate tables. Before treating a regenerated case as matching this reference, compare its main-input SHA-256 and source/overlay identity with the manifest, and re-run P0–P4.

For convenient retrieval of the original full generated inputs, use the two archived GitHub Actions ZIPs while available; they are **evidence artifacts**, not files copied into this Git branch. The **branch-persistent** baseline consists of exact source generators, this frozen contract, and provenance, with reconstruction requiring external private rates.

## Claim boundary / next promotion gate

Accepted: same inlet and neutral seeds for 400/1000 W, full real Physics construction and input check, two solved 1 ns steps, successful CSV endpoint and bounded P3 wall time.

**Not accepted:** validated 100 µs evolution, stationary O density, scientific agreement of all 24 channels/cross sections, mesh/step convergence, RF-power calibration over longer times, or a complete build-and-run in five minutes. Do not merge this experimental candidate to `main` or label it a production physics baseline without separate acceptance.
