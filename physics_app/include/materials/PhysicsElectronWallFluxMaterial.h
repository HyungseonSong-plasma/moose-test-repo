#pragma once

#include "FunctorMaterial.h"

/**
 * Verification-stage electron absorbing-wall flux.
 *
 * Assumptions:
 *   - Maxwellian EEDF interpretation of the supplied mean electron energy
 *   - mean electron energy epsilon_bar = (3/2) k_B T_e, expressed in eV
 *   - sticking/absorption probability supplied by the input
 *   - no reflection
 *   - no secondary electron emission
 *   - no sheath suppression factor yet
 *
 * Mean speed:
 *
 *   v_bar = sqrt(16 e epsilon_bar / (3 pi m_e))
 *
 * Outward particle-loss magnitude:
 *
 *   Gamma_e,wall = s_e * (1/4) n_e v_bar
 *
 * The functor returned here is a positive outward-loss magnitude. In the
 * current Physics FV convention it is attached with factor = -1 in
 * FVFunctorNeumannBC.
 */
class PhysicsElectronWallFluxMaterial : public FunctorMaterial
{
public:
  static InputParameters validParams();
  PhysicsElectronWallFluxMaterial(const InputParameters & parameters);

protected:
  const Moose::Functor<ADReal> & _electron_density;
  const Moose::Functor<ADReal> & _mean_energy;
  const Real _sticking;
};
