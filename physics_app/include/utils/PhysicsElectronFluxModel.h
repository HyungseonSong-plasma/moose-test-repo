#pragma once

#include "MooseTypes.h"

/**
 * Shared constitutive helpers for electron drift-diffusion particle flux.
 *
 * With positive mobility and diffusion magnitudes,
 *
 *   Gamma_e = -mu_e n_e E - D_e grad(n_e)
 *
 * for electron charge number -1.  Electron-energy electric work expressed in
 * eV/(m^3 s) is -E.Gamma_e; callers that assemble a residual may apply the
 * residual sign separately.
 */
namespace PhysicsElectronFluxModel
{
inline ADRealVectorValue
electronParticleFlux(const ADReal & electron_density,
                     const ADRealVectorValue & grad_electron_density,
                     const ADRealVectorValue & electric_field,
                     const ADReal & mobility,
                     const ADReal & diffusion)
{
  return -mobility * electron_density * electric_field -
         diffusion * grad_electron_density;
}

inline ADReal
electronElectricWork(const ADReal & electron_density,
                     const ADRealVectorValue & grad_electron_density,
                     const ADRealVectorValue & electric_field,
                     const ADReal & mobility,
                     const ADReal & diffusion)
{
  const auto electron_flux = electronParticleFlux(
      electron_density, grad_electron_density, electric_field, mobility, diffusion);
  return electric_field * electron_flux;
}
} // namespace PhysicsElectronFluxModel
