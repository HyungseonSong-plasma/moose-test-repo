#pragma once

#include "FunctorMaterial.h"

/**
 * Electron absorbing-wall flux with signed normal drift and diffusion correction.
 *
 * On a wall face, positive flux means electrons leave the plasma:
 *
 *   Gamma_e = n_e max(s * vbar_e / 4
 *                     - mu_e E_n
 *                     - D_e grad(log n_e).n_out, 0)
 *
 * where E_n = E.n_out and E=-grad(phi).  Because grad(log n_e) is unchanged
 * by the constant Avogadro conversion between molar and physical density, this
 * is exactly the normal drift-diffusion particle flux written as an effective
 * velocity and added to the thermal absorbing-wall collection term.
 *
 * The zero floor prevents an absorbing wall from becoming an electron source.
 */
class PhysicsElectronDriftDiffusionLimitedWallFluxMaterial : public FunctorMaterial
{
public:
  static InputParameters validParams();
  PhysicsElectronDriftDiffusionLimitedWallFluxMaterial(const InputParameters & parameters);

protected:
  const Moose::Functor<ADReal> & _electron_density;
  const Moose::Functor<ADReal> & _mean_energy;
  const Moose::Functor<ADReal> & _log_density;
  const Moose::Functor<ADReal> & _potential;
  const Moose::Functor<ADReal> & _mobility;
  const Moose::Functor<ADReal> & _diffusion;
  const Real _sticking;
  const Real _wall_velocity_gate_smoothing_width;
  const bool _use_element_gradient_for_potential;
  const bool _use_element_gradient_for_log_density;
};
