# Issue 256 — T1/T2 canonical promotion provenance

Date: 2026-09-18

Purpose: clean-mode canonicalization of already accepted T1/T2 electron representation code. This promotion introduces no new plasma or numerical claim.

## Source provenance

Retained provenance ref:

`issue-234-m1-1d-electron-drift-surface`

Accepted production blobs promoted unchanged:

| Path | Source blob SHA |
|---|---|
| `physics_app/include/fvkernels/PhysicsFVLogMolarElectronTransport.h` | `1d6fc31c82208bfcfde8076a3ee28ba26348f1c9` |
| `physics_app/src/fvkernels/PhysicsFVLogMolarElectronTransport.C` | `4846888eeb2d00800c60353ed8ad0985698a0799` |
| `physics_app/include/fvbcs/PhysicsFVElectronGroundedSheathCollectionBC.h` | `ff4fc270cdfa2b15b3762b6176da6994d5da812d` |
| `physics_app/src/fvbcs/PhysicsFVElectronGroundedSheathCollectionBC.C` | `5982e19834b956498f52d81eb6a81620e7440b20` |
| `physics_app/include/fvbcs/PhysicsFVElectronGroundedSheathEnergyBC.h` | `6acbd8ba94eafe6dfdd022fdb95c65cbf58e3a33` |
| `physics_app/src/fvbcs/PhysicsFVElectronGroundedSheathEnergyBC.C` | `7ae8ac05f6a13d6c615b60c0252a975748253ec4` |

Historical acceptance anchors recorded by Issue #234:
- T1 lineage: Issue #243
- T2 implementation base: `97e39479c818f1027235d11f7a0bc546858e0c99`
- qualified T2 control: `a15ebd262735689a2aa17a2343ccf276f0e44947`
- governed T2 run: `35209765495`

## Canonicalization rule

Only reusable production owners are promoted.

Explicitly excluded:
- Issue234/243/245 one-off experiment runners;
- issue-specific GitHub Actions workflows;
- fixed-chi validator code;
- Poisson/Gauss/Gummel work;
- any new science threshold or acceptance claim.

A generic structural regression lives at:

`physics_app/ci/check_electron_molar_representation_contract.py`

It guards simultaneous availability of:
- T1 log-molar particle transport;
- T1 log-molar grounded-wall collection;
- T2 molar-energy grounded-wall mode;
- the legacy normalized compatibility paths.
