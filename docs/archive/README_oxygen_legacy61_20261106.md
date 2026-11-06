# Archived Oxygen / Legacy experimental branches — 2026-11-06

This index records the **exact Git commit identity** for 61 retired branches (40 Oxygen/Legacy, 21 Oxygen24/Oxygen25). The active Oxygen14 BASE, Boltzmann, Physics and main branches are **outside this deletion list**.

- [Exact branch→SHA→immutable tag mapping](oxygen_legacy61_20261106.json).
- Tags use `archive/oxygen-cleanup-20261106/<branch-slug>-<sha12>`, and are created and independently verified **before** Samuel's pinned exact-SHA branch-deletion action.
- A missing tag, a mismatched branch HEAD, or a tag collision blocks deletion. All tags are lightweight commit refs, not a claim of branch merge.
- To restore: `git fetch --tags origin`, then `git switch -c recovered-branch '<archive-tag>'`.
- The archived commit preserves version-controlled scripts, inputs, documentation and their Git ancestry.

## Experimental data and provenance limits

**Git tags do not contain generated MOOSE Exodus, CSV or checkpoint files unless those data were committed to Git.** GitHub Actions runs and their artifact links are not deleted with branches, but artifacts may expire according to their retention periods. Every manifest entry includes its original Actions branch query URL for finding run histories, even after the branch is removed. The manifest is a *provenance index*, not a permanent raw-field-data backup.

For the surviving active **Oxygen14 BASE 100→300 µs** experiment, the 400 W and 1000 W validated native+Exodus+CSV archives come from [Actions Run #42187714174](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/42187714174). The upstream 100 µs BASE is [Run #42049066748](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/42049066748). Download raw result archives to durable external storage before Actions retention expiry; do not publish private rate or cross-section data without separate authorization.

Historical failed/HOLD results remain failed/HOLD. Archiving and branch deletion are administrative, not scientific validation or permission to reuse old chemistry. `SCIENCE_HOLD` remains.
