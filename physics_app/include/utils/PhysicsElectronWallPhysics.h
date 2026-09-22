#pragma once

#include "Physics.h"

#include <cmath>

namespace PhysicsElectronWallPhysics
{
template <typename T>
inline auto
meanSpeed(const T & mean_energy_eV)
{
  using std::sqrt;

  return sqrt(16.0 * PHYSICS_CONSTANTS::e * mean_energy_eV /
              (3.0 * PHYSICS_CONSTANTS::pi * PHYSICS_CONSTANTS::m));
}

template <typename DensityType, typename EnergyType>
inline auto
absorbingNumberFlux(const DensityType & electron_density,
                    const EnergyType & mean_energy_eV,
                    const Real sticking)
{
  // COMSOL Drift-Diffusion wall convention for zero reflection:\n  //   Gamma_e,thermal = (1/2) * n_e * v_e,th.\n  return sticking * 0.5 * electron_density * meanSpeed(mean_energy_eV);
}
}
