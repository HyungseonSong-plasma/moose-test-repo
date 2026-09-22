#!/usr/bin/env python3
"""Issue-215 governed entrypoint.

The acceptance implementation lives in the controlled-wall experiment package.
The former shared PhysicsGroundedElectronSheathFlux helper has been removed;
the legacy compatibility BC now carries its historical algebra locally while
new sheath experiments use standard MOOSE functor materials and Neumann BCs.
"""
from experiments.Issue27_surface_reactions.controlled_wall import issue215_sheath_particle_core as _core


if __name__ == "__main__":
    raise SystemExit(_core.main())
