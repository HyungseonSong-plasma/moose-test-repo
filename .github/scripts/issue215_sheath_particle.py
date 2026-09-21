#!/usr/bin/env python3
"""Issue-215 governed entrypoint compatible with the shared W4/W4.5 sheath relation.

The full Issue-215 acceptance implementation is retained unchanged in the
controlled-wall experiment package.  This adapter only updates the static C++
contract audit after #217 moved the particle-flux algebra into the shared
PhysicsGroundedElectronSheath helper; runtime construction and scientific gates
remain owned by the original Issue-215 implementation.
"""
from experiments.Issue27_surface_reactions.controlled_wall import issue215_sheath_particle_core as _core


def _shared_helper_cpp_contract_audit() -> dict:
    source = _core.CPP_SOURCE.read_text()
    helper_path = _core.ROOT / "physics_app/include/fvbcs/PhysicsGroundedElectronSheathFlux.h"
    helper_exists = helper_path.is_file()
    helper = helper_path.read_text() if helper_exists else ""
    checks = {
        "registered_object": "registerMooseObject(\"PhysicsApp\", PhysicsFVElectronGroundedSheathCollectionBC)"
        in source,
        "plasma_cell_state": "elemArg()" in source and "neighborArg()" in source,
        "face_arg_not_used_for_sheath_state": "singleSidedFaceArg" not in source,
        "shared_helper_exists": helper_exists,
        "uses_shared_particle_relation":
        "PhysicsGroundedElectronSheath::primaryParticleFluxHat" in source,
        "grounded_repelling_branch_guard":
        "raw_phi_s_V < -PhysicsGroundedElectronSheath::negative_drop_tolerance_V" in source,
        "temperature_from_mean_energy": "(2.0 / 3.0) * mean_energy_eV" in helper,
        "boltzmann_suppression":
        "exp(-effective_drop_V / electron_temperature_eV)" in helper,
        "quarter_maxwellian_flux": (
            "0.25 * n_e_hat * meanSpeedMPerS(electron_temperature_eV)" in helper
            and "suppression(effective_drop_V, electron_temperature_eV)" in helper
        ),
        "no_see_owner": "see_number_flux" not in source,
    }
    return {
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
    }


_core.cpp_contract_audit = _shared_helper_cpp_contract_audit


if __name__ == "__main__":
    raise SystemExit(_core.main())
