# #774 — clean New-only Thermal source/CI integration, final exact test verdict

> **Production candidate Ready for independent review, not merged.** The user's old typed `PhysicsFVThermalDiffusion` input support waiver remains in force. Actual Native source/Factory/CI and S6-417/941 Public D construction checks are green on an isolated validation child. This does **not** grant automatic permission to merge with unrelated Poisson or claim long-time P3/P4 scientific equivalence.

## Code isolation and exact source ownership

- **Production candidate [Draft #807](https://github.com/HyungseonSong-plasma/moose-test-repo/pull/807)** head `51475b5eeb2e40c9f71bac30012daa7954e3b3b7`, stacked on validated D9 and B post-cut ancestry. Compared against original post-cut B `c77d2f773eee96c30eeca49d7486fea22ea8e557`: **zero Physics C++/Header or Poisson changes**; only canonical CI/template + permanent D9 Guard/test and removal of the D5 temporary source-census Workflow.
- Canonical `.github/workflows/ci.yml` equals `ci/workflow_templates/general-ci.yml` byte-for-byte. Existing P6 retirement tests remain in the existing validation step; **no new production CI Job**. Adds Public D in-place full-stage source invariant: 22 original public support files, 2 authorized edits (100-row electron table and migrated continuity overlay), exactly 1 new mechanism JSON, all other file SHA unchanged. Prevents D12/D13 minimal-output-directory bug.
- **Test-only [Draft #808](https://github.com/HyungseonSong-plasma/moose-test-repo/pull/808)** head `edbdcf2ea4867e7fcbee4a0e40b6780f1acf2a06`: exact Git compare against #807 shows **only five added temporary verification files** (1 Workflow, 2 guards, 2 tests). *No differences* to Physics source, generated-input implementation, canonical CI, template, or Poisson. Do not merge these five files into production.

## Actual sequential test at one source HEAD

[GitHub Actions run #45219450397](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/45219450397) **three jobs SUCCESS**, in order: (1) D5/D9 P0 and single actual W1 build; (2) protected 417/941 Native P05 and N1–N8 negatives; (3) full Public D 100-row 417/941 Native `--check-input` using **the same W1 build artifact from this run**. There was **no duplicated PhysicsApp build**.

| Artifact or result | Verified |
|---|---|
| W1 actual ELF and 2 app libraries | Artifact **#14841390062**, ZIP SHA256 `84afb3e5f15ac57eeb041766771376ef1d0f53d00c43d35665ac5b10ee1f487d` |
| Built PhysicsApp ELF SHA256 | `a8c6b7ad7ace8bd5430421129ca414b8b3f2030540d4f0e67d80dc8ae6f82d00` |
| Protected Native P05 | Artifact **#14840526856**, ZIP SHA256 `2eb13a54556c2812081a323e77dc8a2556a9a81f15033b8478423817304c8448` |
| P05 negatives | **16/16 PASS**, correct expected native rejection family |
| 417 / 941 actual registrations per case | **40 FVKernel + 21 FVBC + 16 FE BoundaryCondition = 77** |
| Reference D10 native parity | **44/44 checks PASS**, input/chemistry/mesh SHA and Factory/source usage |
| Public D actual 100-row Native P2 | Artifact **#14841083348**, ZIP SHA256 `7b244dcba7c48fec201201596d92b1c40f3efd3fa3ba8cc942d9556e3e15f1d7` |
| Public D eight variants (417 + 941) | **8/8 actual rc0 / Syntax OK**, including both full 100-row inputs |
| Public staging source invariants | **22 originals preserved; 2 changed + 1 new JSON; all other SHA unchanged** |
| Private-rate handling in both Native jobs | No private artifacts; verified protected scratch cleanup |

The W1 ELF SHA appearing in **both** Native P05 and Public D P2 receipts is the identical source-bound digest `a8c6b7ad...`. W1 is from run #45219450397, not an older D10/D14 binary. The independent 44-check comparison JSON digest is `d28b03f9beb2fe3b1482f91e00b736f4ec409aa2e8ebb9df982275761d6787d6`; consolidated local receipt digest `5ecce9c00889a9ae5efaee23e3b1106d50393101af7f893e2be2905becd3bb4c`.

## Release boundary

**Closed for these routes:** Legacy Factory C++ removal source-scope evidence, authoritative New-only CI + Workflow generation parity, 417/941 42-row protected native P05, 16 negative controls, real generated Public D 100-row Native P2, and original B rollback-source/ELF custody. External consumers are **NONE REPORTED (not proven universally absent)** and the requester waived historical typed-input support; they are not speculative release blockers. Distinct `QPXFVThermalDiffusion` remains unchanged.

**Open:** independent code-owner review and release rollback authorization, exact *future* Poisson/main merged SHA and branch consistency, and applicable full 100-µs P3/P4 physical/science gates. Branch #807 is Draft and not merged. The complete canonical `ci.yml` on a final **main-targeting** merge SHA was not executed here; this branch-limited validation is bound to the #808 exact source commit with the same production content and five extra test-only files. Never confuse one-off validation green with an already-approved full main release.

**Verdict: `PRODUCTION_CODE_CLEAN / W1_PASS / 417_941_P05_PASS / 16_16_NEGATIVES_PASS / 44_44_PARITY_PASS / PUBLIC_D_100ROW_NATIVE_P2_PASS / EXTERNAL_SCOPE_NONE_REPORTED_NOT_GATE / MAIN_MERGE_DEFERRED`.**

[Machine JSON receipt](newonly_clean_integration_final_verified_v0_1.json).