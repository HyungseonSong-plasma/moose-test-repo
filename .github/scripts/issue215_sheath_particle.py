#!/usr/bin/env python3
"""Issue-215 governed entrypoint.

The accepted particle-current experiment now builds its sheath law with
ADParsedFunctorMaterial and applies it through PhysicsFVCellFunctorNeumannBC.
The full construction/runtime/scientific gates remain owned by the controlled
wall experiment implementation.
"""
from experiments.Issue27_surface_reactions.controlled_wall import issue215_sheath_particle_core as _core


if __name__ == "__main__":
    raise SystemExit(_core.main())
