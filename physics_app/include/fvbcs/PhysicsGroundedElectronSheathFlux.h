#pragma once

#include "FVQpFluxBC.h"

#include <cmath>

namespace PhysicsGroundedElectronSheath
{
constexpr Real negative_drop_tolerance_V = 1.0e-10;
constexpr Real elementary_charge_C = 1.602176634e-19;
constexpr Real electron_mass_kg = 9.1093837139e-31;
constexpr Real pi = 3.141592653589793238462643383279502884;

inline ADReal
electronTemperatureEV(const ADReal & mean_energy_eV)
{
  return (2.0 / 3.0) * mean_energy_eV;
}

inline ADReal
meanSpeedMPerS(const ADReal & electron_temperature_eV)
{
  using std::sqrt;
  return sqrt(8.0 * elementary_charge_C * electron_temperature_eV / (pi * electron_mass_kg));
}

inline ADReal
suppression(const ADReal & effective_drop_V, const ADReal & electron_temperature_eV)
{
  using std::exp;
  return exp(-effective_drop_V / electron_temperature_eV);
}

inline ADReal
primaryParticleFluxHat(const ADReal & n_e_hat,
                       const ADReal & mean_energy_eV,
                       const ADReal & effective_drop_V)
{
  const ADReal electron_temperature_eV = electronTemperatureEV(mean_energy_eV);
  return 0.25 * n_e_hat * meanSpeedMPerS(electron_temperature_eV) *
         suppression(effective_drop_V, electron_temperature_eV);
}

inline ADReal
primaryEnergyFluxHat(const ADReal & n_e_hat,
                     const ADReal & mean_energy_eV,
                     const ADReal & effective_drop_V,
                     const ADReal & energy_per_particle_te_factor,
                     const Real energy_reference_eV)
{
  const ADReal electron_temperature_eV = electronTemperatureEV(mean_energy_eV);
  const ADReal primary_particle_flux_hat =
      primaryParticleFluxHat(n_e_hat, mean_energy_eV, effective_drop_V);

  // The default BC functor value alpha=2 reproduces the accepted kinetic
  // half-Maxwellian sheath-edge relation Gamma_p * (2 T_e + e Delta phi).
  // A caller may explicitly supply another closure factor (for example 5/2
  // in a diffusion-only transport-matched diagnostic). In eV per electron,
  // e*Delta phi numerically equals Delta phi[V].
  return primary_particle_flux_hat *
         (energy_per_particle_te_factor * electron_temperature_eV + effective_drop_V) /
         energy_reference_eV;
}
} // namespace PhysicsGroundedElectronSheath
