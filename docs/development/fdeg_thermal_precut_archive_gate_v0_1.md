# Thermal Diffusion FDEG historical archive gate — pre-cut

This is **artifact integrity validation only**. It never allows FVKernel source deletion.

- Original source and headers remain in the repository. Captured at exact HEAD `331288eb78a09d031588eb43c085374215c7a674` by [Physics Code CI #45148961276](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/45148961276).
- Source blob SHA and all 3 FDEG graph SHA are pinned in `reports/issue774/fdeg_thermal_historical_anchor_v0_1.json`.
- The ZIP artifact is [#14806741858](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/45148961276/artifacts/14806741858), SHA-256 `57e49b50df16dbd690d2899384cf7fa048c01a6f6e6cb4ab59154f1717b414a0`.
- Verify locally with `python3 ci/guards/fdeg_thermal_archive.py --archive-zip path/to/fdeg-retirement-code7-45148961276-1.zip`. The output is always `safe_delete=false`, `global_consumer_closed=false` and `FDEG_RETIREMENT=HOLD`.
- **Storage limitation:** The GitHub Actions ZIP expires; archive metadata by itself cannot restore the three graph JSON documents. Preserve the ZIP in a durable reviewed repository record before attempting source deletion, or recapture from the exact historical HEAD with graph SHA equality. This PR does not assert that durable archival has occurred.
- The existing `physics-code-ci.yml` live `capture` and `verify-archive` calls are **unchanged**, and source-bound FDEG tests remain active. A later deletion PR must review and replace these live-source dependencies, disposition the FDEG active registry profiles, and satisfy `verify-retired` independent receipt gates. Never accept a mere pass of this archive gate as a deletion authorization.
