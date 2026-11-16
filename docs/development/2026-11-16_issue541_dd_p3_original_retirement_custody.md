# DD P3 original retirement — Wave1 scope and archive custody (2026-11-16)

Status: `STAGED_DELETE_KEEP_HOLD_INTEGRATION`; `SCIENCE_HOLD`. The full original source is preserved byte-for-byte as `docs/development/archive/issue402-dd-json-p3-smoke-once.yml.txt`, Git blob `068ef7f78b84b45dbf8c678522ada049d4a42b7a`. Original path: `.github/workflows/issue402-dd-json-p3-smoke-once.yml`.

The historical branch `issue-402-dd-plasma-boundary-action@632aa2376cad03faa271bad2986c664086842225` still contains its self-path push workflow at staging. It is **not** caller-zero-proven. No historical branch delete, default-branch registration or live P3 rerun is authorized here. The maintained candidate `.github/workflows/issue541-arch-dd-p3-replay.yml` is **manual-only**, SHA-bound and typed approval gated; it is not registered on the current default branch.

## Independently saved P3 outputs

Private Drive archive: https://drive.google.com/drive/folders/1b-Y-vdwrFZjFn0S-XMTyU-TbYoNUdobA

- DD 2-step P3: https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/43911477519, source `e0a1a9f7ec92d555f4da50af1ae2b87d046746a5`. Artifact `14247572989`, 16167 bytes, SHA256 `1e2c52623a0ba1936a8c44ae69a1f2c273526a5b96048325288f6854de1d47da`, Drive `1REOmp30hqVl069EqShs_5mR58yOa0L7S`. Continuity and energy each evolved, two steps converged.
- S6-417 3-step P3: https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/43902067509, Artifact `14243685279`, SHA256 `5ed26e8cd52e1a8b64164c733cd7452850b542f5c3e4e2cab18b6f3e4f8a8bf8`, Drive `1X_L6I88FY0oyfj73rmt-8aSlM0vRiSQw`.
- S6-941 3-step P3: same S6 run, Artifact `14243116086`, SHA256 `6f20edfa50d64921af495f21aa9e533d910fe98a5696224f7888c5d1da654098`, Drive `1cKDwUi_tF5W1JlccdF9fCiuZetFexT-v`.
- Historical original DD failed Native artifact ZIP `14090046268` is separately preserved in the prior archive, Drive `1kcw5K_gvmyeydTDuddIHs3VHZCMhQCaL`; failure is NOT used as P3 PASS.

All three **new** Drive ZIPs were independently downloaded from Drive, ZIP CRC checked and SHA256 matched against their corresponding GitHub Actions artifact digest. WORM/Object Lock is **not proven**. The owner can still modify or delete Drive files. Drive copies are independent of GitHub Actions automatic expiration; do not imply regulatory immutable retention.

## Rollback and boundaries

Before restoring the original YAML, verify archived bytes Git-blob `068ef7f78b84b45dbf8c678522ada049d4a42b7a`, inspect any self-path push trigger on the target branch, obtain separate operator authorization if reactivation can run costly P3, then restore in a bounded reviewed commit and rerun P0/CI. Never blindly retarget the original push to `main`.

Global acceptance requires exact-head CI success, branch cutover and provenance readback; neither the bounded DD 2-step nor S6 3-step smoke implies science parity. `SCIENCE_HOLD`.
