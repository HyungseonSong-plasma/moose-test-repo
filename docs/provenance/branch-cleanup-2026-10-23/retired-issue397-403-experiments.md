# Issue #397 / #403 research-branch retirement — 2026-10-23

## Decision and boundaries

The operator authorized cleanup of the five completed Issue #397 / #403 experimental research refs. All were freshly inspected at exact SHA, were unprotected, and did not own any open pull request. This cleanup **removes only branch pointers** through Samuel's exact-SHA deletion contract. It does **not** fast-forward, merge, or restore the branch trees into `main`: doing so would reactivate retired Bohm/negative-ion-wall experiments and unauthorized historical workflow files. Mainline implementation entered through the separately reviewed and merged [#398](https://github.com/HyungseonSong-plasma/moose-test-repo/pull/398), [#399](https://github.com/HyungseonSong-plasma/moose-test-repo/pull/399), and [#400](https://github.com/HyungseonSong-plasma/moose-test-repo/pull/400).

## Exact retiring refs and source preservation

| Ref to retire | Exact head SHA before deletion | Preserved executable-workflow source (inert text only) |
| --- | --- | --- |
| `issue-397-l1-graded-coarse-baseline` | `048f8d6f39990a546257b1beee1112b7e0da5b23` | [original L1/L2/L3 workflow](experiment-workflows/issue397-pre2x-graded-coarse-3levels-100us.yml.txt), Git blob `1d3b0d09e3f7169ee2cef154d2270f626b4236d3` |
| `issue-397-l1-graded-power-scan-200-250-300w` | `60d4069756b315b9bd68cf56ae43f7bf5a2faea6` | [original 200/250/300 W workflow](experiment-workflows/issue397-graded-l1-power-scan-200-250-300w-100us.yml.txt), Git blob `e94c3b2c2d9a568e6b5d33ae12fa6b0ce52e4a08` |
| `issue-397-maxwell-tolerance-300-400w-diagnostics` | `93aec9dfa6d107f61425ad442562577f68c9ff3a` | [original 300/400 W validation workflow](experiment-workflows/issue397-maxwell-tolerance-300-400w-validation.yml.txt), Git blob `965a473ea0449ef887783b9e9646ed7c407e39ab` |
| `issue-403-graded-l1-500-600-700w-power-up` | `3d78a7227757cae4307d89a64c5c59c62d8e4453` | [original 500/600/700 W workflow](experiment-workflows/issue403-500-600-700w-graded-l1-power-up.yml.txt), Git blob `e9bc98a8e75220be02f30fcf620216691d0bf149` |
| `issue-403-graded-l1-800-900-1000w-final-scan` | `b49c44183257941279a806783a1d1f4dea04e5ea` | [original 800/900/1000 W workflow](experiment-workflows/issue403-800-900-1000w-final-power-up.yml.txt), Git blob `d372351bcf8e8448cef916540d27523d12fdcfe8` |

The five source files above are **byte-identical Git blobs**, copied from their respective branch heads under `docs/provenance/` with `.yml.txt` extensions so they cannot become GitHub Actions entrypoints. These are provenance snapshots, not newly validated runnable workflows.

## Scientific evidence, no reinterpretation

| Case | Evidence | Assessment at branch cleanup |
| --- | --- | --- |
| Canonical Graded Coarse L1 | [#397](https://github.com/HyungseonSong-plasma/moose-test-repo/issues/397), [merged #399](https://github.com/HyungseonSong-plasma/moose-test-repo/pull/399) | Selected mesh: 1,739 nodes, 3,155 triangles, **27 wafer faces**, mesh SHA256 `ac70642df75bf7b4bc4ec0d92511e545f0942f9e07a1361618fb9eb5696b83fc` |
| 200 W / 250 W / original 300 W | [run 39617859962](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/39617859962) | 200 and 250 W completed P3/P4; original 300 W run cancelled during P3 under `nl_abs_tol=1e-12`. Workflow aggregate **cancelled**, not full PASS |
| 300 W / 400 W | [run 39740088502](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/39740088502) | P3/P4/P5 PASS through 100 µs after exact Maxwell `nl_abs_tol=1e-11` change |
| 500 W / 600 W / 700 W | [run 39772139957](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/39772139957) | P3/P4/P5 PASS through 100 µs |
| 800 W / 900 W / 1000 W | [run 39815484444](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/39815484444) | 800 and 900 W P3/P4/P5 PASS; 1000 W P3/P4 PASS, **P5 FAIL** due original 3.0 PID drive saturation (final controlled RF power 984.812 W vs 1000 W target). Aggregate **failure**, not full PASS |

See [completed #403](https://github.com/HyungseonSong-plasma/moose-test-repo/issues/403) for the bounded numerical-convergence resolution. Maxwell `nl_abs_tol=1e-11` is empirically sufficient for the tested mesh, chemistry, duration and power range. This is not a proof of physically equivalent solutions at different nonlinear tolerances.

### Important expiration of binary scientific evidence

The existing ZIP artifacts were checked **present and unexpired** on 2026-10-23. GitHub currently reports the original 200/250 W artifacts expiring **2026-11-20** and the 300–1000 W follow-up artifacts expiring **2026-11-21**. This Git documentation does **not** retain raw `plasma.e`/`plasma.csv` or override Actions artifact retention. For long-term scientific reproducibility, independently export and checksum those binaries before expiry. A deleted branch ref is not itself an Actions artifact deletion, but cannot extend an artifact's lifetime.

## Selected historically unmerged files carried forward

- [Issue #403 read-only four-gate diagnostic](../../../experiments/Issue395_powered_chemistry_ladder/issue397_four_checks.py) preserved **verbatim** from historical Git blob `2666f9dcbc8fe73ef433ffd7254c1b2ce43f6bf9`. [Synthetic regression tests](../../../tests/characterization/test_issue403_four_checks.py) verify that 1000 W PID-cap failure does not become a false Maxwell numerical failure/pass. Tests do not repeat an actual physics calculation.
- [Historical oxygen reaction activation ladder](legacy-chemistry/chemistry_sets.json.txt), Git blob `8c05a476c201d13878c048280d56de35c4e6184c`; [static ladder checker](legacy-chemistry/check_chemistry_sets.py.txt), Git blob `442079c0e20dc64c7a6bdac214d13b175ffa71d1`; [original EI17 scan contract](legacy-chemistry/ei17_power_scan_execution_contract.json.txt), Git blob `9cf3faa7d65f4896d5010761815466113b0517de`. These are **archival only**. Their existence does not activate, validate or authorize the remaining oxygen chemistry channels.
- Current accepted mainline [L1 mesh declaration](../../../experiments/Issue395_powered_chemistry_ladder/issue397_baseline_mesh.json) and [Samuel governed scan replay](../../../experiments/Issue395_powered_chemistry_ladder/issue397_l1_power_scan_replay.sh) remain the operational starting points.

## Explicit exclusions

- **Retain** `main` and `issue-280-sol-gateway-cutover` (open [PR #303](https://github.com/HyungseonSong-plasma/moose-test-repo/pull/303)).
- **Retain** `feat/semantic-directory-role-guard` (separate unmerged development work).
- **Retain** `experiment-full-fem-contour-mesh` (separate legacy FEM study and unique unmerged C++ changes).
- This is selective evidence/code preservation, **not a claim that every unique intermediate commit or rejected experimental source file was integrated**. Without a permanent ref, orphaned historical Git objects may later be pruned. Inert archived workflow files preserve their exact original source text, but may rely on former branch-specific helpers that were intentionally not promoted.
- No new production GitHub Actions workflow, wall BC, solver setting, PID bounds, branch merge, or physics run is authorized by this cleanup.

## Verification contract

The branch removal is to be performed by writing these five exact `branch` and `expected_sha` pairs to `automation/mutations/branch-delete-request.json`, triggering the existing `samuel-branch-delete.yml` on `main`. Verify that all matrix jobs are successful and all five branch refs return `404 / Branch not found` on fresh readback. Any stale SHA must fail closed.

Deletion status: **Pending Samuel exact-SHA execution and readback** (the text of this document will be updated only after observed terminal results).
