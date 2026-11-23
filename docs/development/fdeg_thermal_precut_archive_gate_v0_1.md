# Thermal Diffusion FDEG historical archive gate — pre-cut

This is **artifact integrity validation only**. It never allows FVKernel source deletion.

- Original source and headers remain in the repository. Captured at exact HEAD `331288eb78a09d031588eb43c085374215c7a674` by [Physics Code CI #45148961276](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/45148961276).
- Source blob SHA and all 3 FDEG graph SHA are pinned in `reports/issue774/fdeg_thermal_historical_anchor_v0_1.json`.
- The ZIP artifact is [#14806741858](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/45148961276/artifacts/14806741858), SHA-256 `57e49b50df16dbd690d2899384cf7fa048c01a6f6e6cb4ab59154f1717b414a0`.
- Verify the **committed binary archive** with `python3 ci/guards/fdeg_thermal_archive.py --archive-zip reports/issue774/archive/fdeg-retirement-code7-45148961276-1.zip`. The output is always `safe_delete=false`, `global_consumer_closed=false` and `FDEG_RETIREMENT=HOLD`.
- **Durable pre-cut copy:** `reports/issue774/archive/fdeg-retirement-code7-45148961276-1.zip` is a byte-for-byte copy of the exact GitHub Actions artifact (37,949 bytes, Git blob `9bf227311a0683942bb1769dfd174332f803049b`). A regression test verifies this ZIP directly, checking all three original graph hashes and manifest identity. Its durability becomes part of the retained `main` history only **after this PR merges**; until then it is preserved in the PR branch.
- The existing `physics-code-ci.yml` live `capture` and `verify-archive` calls are **unchanged**, and source-bound FDEG tests remain active. A later deletion PR must review and replace these live-source dependencies, disposition the FDEG active registry profiles, and satisfy `verify-retired` independent receipt gates. Never accept a mere pass of this archive gate as a deletion authorization.
