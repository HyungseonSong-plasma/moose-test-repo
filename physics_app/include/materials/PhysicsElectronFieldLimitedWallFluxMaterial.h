#pragma once

#include "FunctorMaterial.h"

/**
 * Electron absorbing-wall flux with signed normal electric drift.
 *
 * On a wall face, positive flux means electrons leave the plasma:
 *
 *   Gamma_e = n_e max(s * vbar_e / 4 - mu_e E_n, 0)
 *
 * where E_n = E . n_out and electron drift velocity is -mu_e E.
 * A positive outward electric field therefore drives electrons inward and
 * reduces the thermal wall loss. A negative outward electric field increases
 * electron wall loss. The zero floor prevents an absorbing wall from becoming
 * an electron source.
 */
class PhysicsElectronFieldLimitedWallFluxMaterial : public FunctorMaterial
{
public:
  static InputParameters validParams();
  PhysicsElectronFieldLimitedWallFluxMaterial(const InputParameters & parameters);

protected:
  const Moose::Functor<ADReal> & _electron_density;
  const Moose::Functor<ADReal> & _mean_energy;
  const Moose::Functor<ADReal> & _potential;
  const Moose::Functor<ADReal> & _mobility;
  const Real _sticking;
  const Real _wall_velocity_gate_smoothing_width;
  const bool _use_element_gradient_for_potential;
};
