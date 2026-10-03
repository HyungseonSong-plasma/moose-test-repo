#!/usr/bin/env bash
set -euo pipefail

# The MOOSE developer image exposes the compiler/MPI toolchain through this
# activation script. AD FParser JIT invokes the OpenMPI compiler wrapper at
# runtime, so the same environment used to build Physics must be restored.
source /environment

export MOOSE_DIR=/opt/physics_vendor/moose
export CRANE_DIR=/opt/physics_vendor/crane
export SQUIRREL_DIR=/opt/physics_vendor/squirrel
export ZAPDOS_DIR=/opt/physics_vendor/zapdos
export METHOD=opt
export LD_LIBRARY_PATH="/opt/physics/test/lib:/opt/physics/lib:${LD_LIBRARY_PATH:-}"

exec /opt/physics/physics-opt "$@"
