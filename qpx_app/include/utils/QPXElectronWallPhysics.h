#pragma once

#include "QPX.h"

#include <cmath>

namespace QPXElectronWallPhysics
{
template <typename T>
inline auto
meanSpeed(const T & mean_energy_eV)
{
  using std::sqrt;

  return sqrt(16.0 * QPX_CONSTANTS::e * mean_energy_eV /
              (3.0 * QPX_CONSTANTS::pi * QPX_CONSTANTS::m));
}

template <typename DensityType, typename EnergyType>
inline auto
absorbingNumberFlux(const DensityType & electron_density,
                    const EnergyType & mean_energy_eV,
                    const Real sticking)
{
  return sticking * 0.25 * electron_density * meanSpeed(mean_energy_eV);
}
}
