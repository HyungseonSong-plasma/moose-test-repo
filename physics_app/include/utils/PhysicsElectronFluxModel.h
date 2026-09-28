#pragma once

#include "MooseTypes.h"

#include <cmath>

namespace PhysicsElectronFluxModel
{
/**
 * Reconstruct a transported physical state from the solved scalar state.
 *
 * identity:    u_phys = u
 * exponential: u_phys = exp(u)
 */
inline ADReal
transportedState(const ADReal & solved_state, const bool exponential)
{
  if (!exponential)
    return solved_state;

  using std::exp;
  return exp(solved_state);
}

/**
 * Signed electrostatic drift velocity projected on a face normal:
 *
 *   u_d . n = z * mu * E . n
 */
template <typename NormalType>
inline ADReal
driftNormal(const Real charge_number,
            const ADReal & mobility,
            const ADRealVectorValue & electric_field,
            const NormalType & normal)
{
  return charge_number * mobility * (electric_field * normal);
}

/**
 * Orthogonal finite-volume diffusive flux for a reconstructed scalar.
 */
inline ADReal
orthogonalDiffusiveFlux(const ADReal & diffusion,
                        const ADReal & value_elem,
                        const ADReal & value_neighbor,
                        const Real distance)
{
  return -diffusion * (value_neighbor - value_elem) / distance;
}

/**
 * Local electron particle flux used by electron-energy work terms:
 *
 *   Gamma_e = -mu_e*n_e*E - D_e*grad(n_e)
 *
 * This is the same constitutive drift-diffusion model used by the particle
 * equation; the FV face reconstruction itself remains owned by the flux
 * kernels.
 */
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

/**
 * Positive electric work deposited into the electron population:
 *
 *   -E . Gamma_e
 */
inline ADReal
electronElectricWork(const ADReal & electron_density,
                               const ADRealVectorValue & grad_electron_density,
                               const ADRealVectorValue & electric_field,
                               const ADReal & mobility,
                               const ADReal & diffusion)
{
  const auto particle_flux =
      electronParticleFlux(electron_density,
                                     grad_electron_density,
                                     electric_field,
                                     mobility,
                                     diffusion);
  return -(electric_field * particle_flux);
}
} // namespace PhysicsElectronFluxModel
