# R5a — retire physical-eV grounded sheath energy mode

Scope approved in #713; normalized dependency chain deferred to #864. Exact pre-cut Native A/B [45438713911](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/45438713911), artifact 14941118834, passed both representations and independent inventory/ledger at 0 V and 10 V. The live smoke is the exact qualified molar input (SHA256 1e2d47dce00829d3233459b884d68d5f7198ed42eebea44471769450a061a99a). Existing normalized and molar formula branches, shared helper, cell-side selection, validity guards, and protected discriminator are preserved. Only the obsolete physical_eV_state branch/parameter/member is removed. No new permanent workflow. Post-cut native positive and retired parameter negative checks still required.

Original source identity (base b342e9e8861736a7af59b02b90f1d7bed01c7dc6):

| Path | Git blob |
|---|---|
| `physics_app/src/fvbcs/PhysicsFVElectronGroundedSheathEnergyBC.C` | `0ec3766b00e16cdd24a5e29f355689920bb3178a` |
| `physics_app/include/fvbcs/PhysicsFVElectronGroundedSheathEnergyBC.h` | `ceccdb4e6dcb9f34af90a84b0c655d00d7865b31` |
| `physics_app/ci/electron_grounded_sheath_energy_smoke.i` | `ac94ef49820f016c94327f61726680da5de859c5` |
| `physics_app/ci/check_electron_molar_representation_contract.py` | `715f9c064863716e260f25c55029da1645f61a57` |
