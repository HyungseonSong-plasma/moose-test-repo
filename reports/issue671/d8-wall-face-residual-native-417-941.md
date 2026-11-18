# D8 actual Wall FaceArg / Lower-D Surface Current residual — both S6 cases

Verdict: **PASS_BOTH_CASES_BOUNDED_NUMERICAL_FACE_AND_RESIDUAL**, final integrated PR #665 Native P2 **HOLD**, science **SCIENCE_HOLD**.

Run: https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/44303391987; Artifact #14427412814 ZIP SHA256 7b74bc979d2b3b48fc1083f1d360bf2c0f839e55f67a2a2d1c84dfe4de78946e; independently downloaded, ZIP CRC and all log digests verified. Artifact link: https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/44303391987/artifacts/14427412814

Diagnostic source HEAD c78b824e8e94db3c6879b5eb4e0c74f33313a146; ELF SHA256 98c3c2d1667b1902882cbc9feae8da44f83f76b44212660150769e7bb98d50aa (original extracted ELF directly rehashed). Fixed OCI sha256:2c3352da4f5c1b2ae98475fc01463ad0cdbc6ce7d221ce55055ddea152182008. Original PR #665 production fork 05d7ce4eceb81769cb2f0146c51535fc35e74ac1, latest #665 74a2b0fbeaf411d9c76cb82a69de1629fa55fa7f; this source is an isolated instrumented branch, not merged.

Both cases actual source 11-layer hashes unchanged, P4-X final C0 SHA 2c3bab8a8e28b360dcd54775d91ba13c97401364c709944bc21d6bf0b6d79490, original parent mesh SHA ac70642df75bf7b4bc4ec0d92511e545f0942f9e07a1361618fb9eb5696b83fc. Actual --check-input exit 0 / Syntax OK, 12 ion FVKernel + 12 ion FVBC each. 5 protected EI rate source files per case, temporary private /dev/shm removed after native execution; no private bytes in public Artifact.

| Observed first actual Moose::FaceArg | S6-417 | S6-941 | Units |
|---|---:|---:|---|
| O2p number wall flux (face 104) | 1.11381e17 | 1.11381e17 | particles/m2/s |
| Om number wall flux (face 104) | 1.57517e14 | 1.57517e14 | particles/m2/s |
| Op number wall flux (face 104) | 1.57517e14 | 1.57517e14 | particles/m2/s |
| O2p mass wall flux (face 89) | 5.9185e-9 | 5.9185e-9 | kg/m2/s |
| Om mass wall flux (face 89) | 4.18501e-12 | 4.18501e-12 | kg/m2/s |
| Op mass wall flux (face 89) | 4.18501e-12 | 4.18501e-12 | kg/m2/s |
| Electron wall flux (face 104) | 2.73215e20 | 2.73215e20 | particles/m2/s |

| Actual PhysicsLowerDSurfaceCurrent::computeQpResidual caller | face | element | j_to_surface A/m2 | observed first residual (both cases) |
|---|---:|---:|---:|---:|
| sigma_surface_current | 350 | 3155 | -43.7561 | +43.7561 |
| sigma_wafer_surface_current | 104 | 3208 | -43.7561 | +43.7561 |
| sigma_focus_ring_surface_current | 2153 | 3235 | -43.7561 | +43.7561 |

Actual compiled residual = -test[i][qp] * j_to_surface, with sided FaceArg resolved from higher-dimensional FV plasma side. All three kernels called and returned finite values independently for BOTH cases. Bounded numerical exits both 0 and Finished Executing; last accepted step 1.5625e-11 s. The numeric diagnostic adds a private 12th overlay with RF child, seven Transfers and RF Control disabled; it does not prove RF-coupled/full-science parity.

Log SHA: 417 check_input 899f1ade8bf89b52080ac94f6dbe7ad89d5d8e3f52a036cd8012b87b662bbd8b; 941 check_input 91baa5105d47347826efc24419af632f454309da6fcfda0eb0664434bf317ee8.
Log SHA: 417 numeric 1bb70bb69485a05c471b5915f1d609ca1028d4c0826a32977b0617ea9c02f0c3; 941 numeric 92ab977cb6070a87677592f6d53ff24fcf45267485f682407c91116ad0db7090.
Actual 417 P05 duplicate negative exit 1, expected error, log 284ee48966cc84185d5466af30a314491d963a159a338faeb84bac1f7ab60611.

Correction: earlier Run 44301891393 accidentally executed numerical block outside per-case loop (941 only). Corrected Run 44303391987 has independent numeric evidence and fail-closed requirement for 417 and 941. Final latest-HEAD PR665, full D8 RF/Poisson coupled numerical evaluation, complete N1-N8 and science P3/P4 remain HOLD/NOT_RUN.
